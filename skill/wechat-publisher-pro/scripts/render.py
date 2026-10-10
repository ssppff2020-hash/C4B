"""
The WeChat rendering pipeline: raw Markdown/Word/HTML -> publishable HTML.

The order of the stages below is load-bearing -- each depends on the previous
one having already happened::

    read -> tokenise -> markdown -> drop forbidden -> normalise headings
         -> restore code/formulas -> code blocks -> callouts -> quotes
         -> inline markup -> dividers -> images -> tables -> links
         -> typography -> header/TOC/footer -> inline styles -> clean

Three invariants hold throughout:

* **Nothing is emitted as a ``class``.**  WeChat strips class attributes and has
  no stylesheet, so every visual property must be inlined on the element that
  needs it.  ``wechat_validate.py`` enforces this afterwards.
* **Boxes are single-cell tables.**  WeChat keeps borders, padding and radius on
  a table cell but drops them from an empty styled ``<p>``, so every framed
  element -- callout, TOC, code block, divider -- is a one-cell table tagged
  ``data-wp-box`` so later stages can recognise their own output.
* **Generated furniture is tagged ``data-wp-skip``.**  The typography pass must
  not re-space a code line or a byline, and these markers are stripped in the
  final clean-up, so they never reach WeChat.
"""

from __future__ import annotations

import base64
import html as html_mod
import re
import struct
from dataclasses import dataclass, field
from pathlib import Path

from bs4 import BeautifulSoup, Comment, NavigableString, Tag

import typography as typo
from converters import read_docx, read_text, split_front_matter
from mathpng import MathRenderer
from themes import (CALLOUT_COLORS, CALLOUT_TYPES, build_styles, derive_palette,
                    palette_from_file)

# --------------------------------------------------------------------------
# WeChat's rulebook, as code
# --------------------------------------------------------------------------
ALLOWED_TAGS = {
    "p", "h2", "h3", "ul", "ol", "li", "span", "img", "a",
    "table", "tr", "th", "td", "br",
}

# Removed outright -- they either do nothing after the paste or are a liability.
DROP_TAGS = {
    "script", "style", "iframe", "video", "audio", "svg", "object", "embed",
    "form", "input", "button", "select", "textarea", "canvas", "noscript",
    "link", "meta", "base", "map", "area", "frame", "frameset", "applet",
}

ALLOWED_CSS_PROPS = {
    "color", "background-color", "font-size", "font-weight", "font-style",
    "font-family", "line-height", "text-align", "text-indent", "text-decoration",
    "letter-spacing", "word-break", "word-spacing", "white-space", "overflow-wrap",
    "margin", "margin-top", "margin-right", "margin-bottom", "margin-left",
    "padding", "padding-top", "padding-right", "padding-bottom", "padding-left",
    "border", "border-top", "border-right", "border-bottom", "border-left",
    "border-width", "border-style", "border-color", "border-radius",
    "border-collapse", "border-spacing", "list-style-type",
    "display", "vertical-align", "width", "height", "max-width", "min-width",
    "max-height", "min-height", "box-sizing", "opacity", "text-transform",
}

# Layout, motion and effect properties WeChat reliably strips.  Dropping them
# ourselves keeps the output honest: what you preview is what gets published.
FORBIDDEN_CSS_PROPS = {
    "position", "top", "left", "right", "bottom", "float", "clear", "z-index",
    "flex", "flex-direction", "flex-wrap", "justify-content", "align-items",
    "align-content", "grid", "grid-template-columns", "gap", "order",
    "animation", "transition", "transform", "filter", "backdrop-filter",
    "box-shadow", "text-shadow", "cursor", "visibility", "content", "resize",
    "clip-path", "mask", "perspective", "will-change",
}

IMAGE_EXT_MIME = {
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".gif": "image/gif", ".webp": "image/webp", ".bmp": "image/bmp",
}

MAX_ARTICLE_CHARS = 20000
WIDE_TABLE_COLUMNS = 5
BOX_ATTR = "data-wp-box"
SKIP_ATTR = "data-wp-skip"

# Block-level elements that must never end up inside a <p>.
BLOCK_LEVEL = ("p", "table", "ul", "ol", "h2", "h3")


# --------------------------------------------------------------------------
# Options / report
# --------------------------------------------------------------------------
@dataclass
class Options:
    theme: str = "default"
    theme_file: str | None = None
    accent: str | None = None
    font_size: int | None = None
    heading_style: str | None = None
    indent: str = "none"
    letter_spacing: float | None = None
    cjk_spacing: bool = True
    punct: str = "safe"                 # safe | aggressive | off
    toc: str = "auto"                   # auto | always | never
    toc_min_headings: int = 4
    heading_numbers: bool = True
    header: str = "auto"                # auto | full | off
    footer: str | None = None
    footer_off: bool = False
    callout_style: str = "table"        # table | plain
    syntax_highlight: bool = True
    math: str = "png"                   # png | unicode | off
    math_font_size: int = 18
    math_dpi: int = 200
    image_mode: str = "embed"           # embed | keep
    image_caption: bool = True
    divider: str = "dots"               # dots | rule | none
    links: str = "keep"                 # keep | plain | footnote | strip
    nl2br: bool = True
    base_dir: Path = field(default_factory=Path.cwd)

    @classmethod
    def from_dict(cls, data: dict) -> "Options":
        """Build from CLI args or front matter, ignoring unknown keys."""
        known = set(cls.__dataclass_fields__)
        return cls(**{k: v for k, v in data.items() if k in known and v is not None})


# Keys an article may set in its front matter.  Kept here rather than in the CLI
# so the command line and the eval harness resolve settings identically -- when
# they drifted, the eval was silently testing different options than users get.
FM_KEYS = (
    "theme", "theme_file", "accent", "font_size", "heading_style", "indent",
    "letter_spacing", "cjk_spacing", "punct", "toc", "toc_min_headings",
    "heading_numbers", "header", "footer", "footer_off", "callout_style",
    "syntax_highlight", "math", "math_font_size", "math_dpi", "image_mode",
    "image_caption", "divider", "links", "nl2br",
)
_FM_INT_KEYS = ("font_size", "toc_min_headings", "math_font_size", "math_dpi")
_FM_FLOAT_KEYS = ("letter_spacing",)
_FM_BOOL_KEYS = ("cjk_spacing", "heading_numbers", "footer_off",
                 "syntax_highlight", "image_caption", "nl2br")
_FM_ENUM_KEYS = ("toc", "header", "math", "image_mode", "divider", "links",
                 "callout_style", "punct", "theme", "heading_style", "indent")


def front_matter_options(meta: dict, base_dir: Path) -> dict:
    """Coerce an article's front matter into ``Options`` keyword arguments.

    Values arrive as strings, so each key needs the type its field expects.  A
    value that cannot be coerced is skipped rather than raising: a typo in a
    draft should cost the author one option, not the whole conversion.
    """
    from converters import truthy

    out: dict = {}
    for key in FM_KEYS:
        value = meta.get(key)
        if value in (None, ""):
            continue
        try:
            if key in _FM_BOOL_KEYS:
                coerced = truthy(value)
            elif key in _FM_INT_KEYS:
                coerced = int(float(value))
            elif key in _FM_FLOAT_KEYS:
                coerced = float(value)
            elif key in _FM_ENUM_KEYS:
                coerced = str(value).strip().lower()
            else:
                coerced = value
        except (TypeError, ValueError):
            continue
        out[key] = coerced

    # A theme file named in front matter is relative to the article, not to
    # whatever directory the command happened to run from.
    if out.get("theme_file"):
        candidate = Path(str(out["theme_file"]))
        if not candidate.is_absolute():
            candidate = (base_dir / candidate).resolve()
        out["theme_file"] = str(candidate)
    out["base_dir"] = base_dir
    return out


@dataclass
class Report:
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    stats: dict = field(default_factory=dict)
    theme: str = ""
    dropped_css: int = 0
    # What the content actually was -- not what the extension claimed.  A file
    # named .md whose body is HTML is common (people paste HTML out of Word and
    # save it with a .md extension), and downstream exporters must not assume the
    # extension tells the truth.
    source_kind: str = ""

    def warn(self, message: str):
        if message not in self.warnings:
            self.warnings.append(message)

    def error(self, message: str):
        if message not in self.errors:
            self.errors.append(message)


# --------------------------------------------------------------------------
# Node helpers
# --------------------------------------------------------------------------
_BR_SPLIT_RE = re.compile(r"(?i)<br\s*/?>")


def _frag(html: str) -> list:
    """Parse an HTML fragment into a list of nodes for ``replace_with``."""
    return list(BeautifulSoup(html, "html.parser").children)


def _tag(soup: BeautifulSoup, name: str, style: str | None = None,
         skip: bool = False) -> Tag:
    el = soup.new_tag(name)
    if style:
        el["style"] = style
    if skip:
        el[SKIP_ATTR] = "1"
    return el


def _box_table(soup: BeautifulSoup, wrap_style: str, cell_style: str,
               inner_html: str) -> Tag:
    """Build a framed single-cell table -- the shape every box in the doc uses."""
    table = _tag(soup, "table", wrap_style)
    table[BOX_ATTR] = "1"
    row = soup.new_tag("tr")
    cell = _tag(soup, "td", cell_style)
    for node in _frag(inner_html):
        cell.append(node)
    row.append(cell)
    table.append(row)
    return table


def _is_box(tag: Tag) -> bool:
    return bool(tag.get(BOX_ATTR))


def _is_generated(tag: Tag) -> bool:
    node: Tag | None = tag
    for _ in range(8):
        if node is None:
            return False
        if getattr(node, "attrs", None) and node.get(SKIP_ATTR):
            return True
        node = node.parent
    return False


def _png_dimensions(data_uri: str):
    """Read width/height from a PNG's IHDR chunk so formulas can be sized."""
    try:
        raw = base64.b64decode(data_uri.split(",", 1)[1])
        if raw[:8] != b"\x89PNG\r\n\x1a\n":
            return None
        return struct.unpack(">II", raw[16:24])
    except Exception:
        return None


def _esc(text: str) -> str:
    return html_mod.escape(text, quote=False)


# A file saved as .md whose body is really HTML is a common authoring accident
# (paste out of Word, save as Markdown). Treating it as Markdown happens to work
# -- python-markdown passes block-level HTML through -- but downstream exporters
# need to know, or they will copy the raw HTML into a Markdown variant.
_HTML_SNIFF_RE = re.compile(
    r"^\s*<(?:!doctype|html|body|div|p|h[1-6]|table|section|article|span|ul|ol)\b",
    re.I)


def looks_like_html(text: str) -> bool:
    return bool(_HTML_SNIFF_RE.match(text or ""))


# --------------------------------------------------------------------------
# Stage 1 -- forbidden tags and comments
# --------------------------------------------------------------------------
def drop_forbidden(soup: BeautifulSoup):
    for name in DROP_TAGS:
        for el in soup.find_all(name):
            el.decompose()
    for node in soup.find_all(string=lambda s: isinstance(s, Comment)):
        node.extract()


# --------------------------------------------------------------------------
# Stage 2 -- headings
# --------------------------------------------------------------------------
def normalize_headings(soup: BeautifulSoup, report: Report):
    """``h1`` -> ``h2`` (WeChat owns h1); ``h4`` and deeper -> ``h3``."""
    for h1 in soup.find_all("h1"):
        h1.name = "h2"
    demoted = soup.find_all(["h4", "h5", "h6"])
    for tag in demoted:
        tag.name = "h3"
    if demoted:
        report.warn("%d 个 h4/h5/h6 标题已统一为 h3 —— 公众号正文只稳定支持两级小标题"
                    % len(demoted))
    if soup.find("h2") is None and soup.find("h3") is not None:
        report.warn("文章只有三级标题，没有二级标题：目录会退化为一层")


# --------------------------------------------------------------------------
# Stage 3 -- code and formula placeholders
# --------------------------------------------------------------------------
def restore_tokens(soup: BeautifulSoup, math_spans, code_spans, renderer,
                   styles: dict, opts: Options, report: Report):
    """Expand the MATH/CODE placeholders left by ``typography.protect_source``.

    The placeholder trick is what keeps ``$a_1$`` from losing its underscore to
    Markdown emphasis and ``a*b*c`` from turning into italics.
    """
    for node in list(soup.find_all(string=typo.TOKEN_RE.search)):
        parent = node.parent
        if parent is None or parent.name in ("code", "pre"):
            continue
        original = str(node)
        chunks: list = []
        cursor = 0
        for kind, index, start, end in typo.iter_tokens(original):
            if start > cursor:
                chunks.append(NavigableString(original[cursor:start]))
            if kind == "CODE" and index < len(code_spans):
                span = _tag(soup, "span", styles["code_inline"], skip=True)
                span.string = code_spans[index]
                chunks.append(span)
            elif kind == "MATH" and index < len(math_spans):
                chunks.append(_math_node(soup, math_spans[index], parent,
                                         styles, renderer, opts, report))
            cursor = end
        if cursor < len(original):
            chunks.append(NavigableString(original[cursor:]))
        if chunks:
            node.replace_with(*chunks)


def _math_node(soup: BeautifulSoup, latex: str, parent: Tag, styles: dict,
               renderer, opts: Options, report: Report):
    """Render one formula as an ``<img>``, or fall back to text."""
    parent_text = parent.get_text() if parent is not None else ""
    solo = (
        parent is not None
        and parent.name == "p"
        and len(typo.TOKEN_RE.findall(parent_text)) == 1
        and typo.TOKEN_RE.sub("", parent_text).strip() == ""
    )

    if renderer is None or opts.math == "off":
        span = _tag(soup, "span", styles["code_inline"], skip=True)
        span.string = "$%s$" % latex
        return span

    result = renderer.render(latex, display=solo)
    if result.get("mode") != "png":
        report.warn("公式无法渲染为图片，已降级为文本：%s" % latex[:60])
        span = _tag(soup, "span", styles["code_inline"], skip=True)
        span.string = result.get("text", latex)
        return span

    img = soup.new_tag("img")
    img["src"] = result["uri"]
    img["alt"] = latex
    # Marked so the image stage does not overwrite the sizing computed here.
    img["data-wp-math"] = "1"

    # Scaling must be a *constant*, not derived from each formula's own bounding
    # box.  matplotlib bakes the glyph size into the PNG at a fixed rate
    # (points x dpi), so an image's pixel height tells you how tall the formula
    # is -- not how big its letters are.  Dividing by height would make a tall
    # formula and a short one render at different glyph sizes.
    em_px = float(opts.font_size or 16)
    png_em_px = (opts.math_font_size / 72.0) * opts.math_dpi
    scale = em_px / png_em_px
    dims = _png_dimensions(result["uri"])

    if dims is None:
        img["style"] = (
            "display: %s; max-width: 100%%; height: %.1fem; "
            "margin: %s;" % ("block" if solo else "inline-block",
                             em_px / 16.0 * (2.2 if solo else 1.35),
                             "16px auto 18px auto" if solo else "0 2px")
        )
        return img

    width, height = dims
    if solo:
        # Display equations are set 25% larger than body text, the usual
        # typographic relationship for a centred formula.
        img["style"] = (
            "display: block; max-width: 100%%; width: %.0fpx; height: auto; "
            "margin: 16px auto 18px auto;" % (width * scale * 1.25)
        )
    else:
        # Inline: clamp to the line box so a fraction does not tear the leading
        # apart mid-sentence.
        css_w, css_h = width * scale, height * scale
        if css_h > em_px * 1.6:
            css_w *= (em_px * 1.6) / css_h
            css_h = em_px * 1.6
        img["style"] = (
            "display: inline-block; vertical-align: middle; max-width: 100%%; "
            "width: %.0fpx; height: %.0fpx; margin: 0 2px;" % (css_w, css_h)
        )
    return img


# --------------------------------------------------------------------------
# Stage 4 -- code blocks
# --------------------------------------------------------------------------
_LANG_CLASS_RE = re.compile(r"^language-(\w+)")


def convert_code_blocks(soup: BeautifulSoup, styles: dict, opts: Options,
                        report: Report):
    """``<pre><code>`` -> a single-cell table with one paragraph per line.

    The starter kit placed the whole block in one ``<p>``; WeChat collapses the
    newlines, turning every sample into a single unreadable line.  One element
    per line is the only representation that survives the round trip.
    """
    for pre in soup.find_all("pre"):
        code = pre.find("code")
        source = code if code is not None else pre
        text = source.get_text().rstrip("\n")

        lang = ""
        if code is not None:
            for cls in (code.get("class") or []):
                m = _LANG_CLASS_RE.match(cls)
                if m:
                    lang = m.group(1)
                    break

        highlighted = None
        if opts.syntax_highlight and lang and lang not in ("text", "plain", "none"):
            highlighted = _highlight(text, lang)

        parts: list[str] = []
        if lang:
            parts.append('<p style="%s" %s="1">%s</p>'
                         % (styles["code_lang"], SKIP_ATTR, _esc(lang)))
        lines = highlighted if highlighted is not None else [
            _esc(line) for line in text.split("\n")
        ]
        for line in lines:
            body = line if line.strip() else "&nbsp;"
            parts.append('<p style="%s" %s="1">%s</p>'
                         % (styles["code_line"], SKIP_ATTR, body))

        table = _box_table(soup, styles["code_wrap"], styles["code_cell"],
                           "".join(parts))
        pre.replace_with(table)


def _highlight(code: str, lang: str):
    """Return one HTML string per line with inline-styled token spans.

    ``noclasses=True`` makes Pygments emit ``style="color:#..."`` directly, which
    is exactly what WeChat needs -- the usual class-based theme would be stripped
    and the code would come out monochrome.
    """
    try:
        from pygments import highlight
        from pygments.formatters import HtmlFormatter
        from pygments.lexers import get_lexer_by_name
        from pygments.util import ClassNotFound

        try:
            lexer = get_lexer_by_name(lang, stripall=False)
        except ClassNotFound:
            return None
        rendered = highlight(code, lexer,
                             HtmlFormatter(noclasses=True, nowrap=True))
        # Pygments styles runs of whitespace as a token ("#bbbbbb"). Inline, that
        # is pure bloat -- thousands of invisible spans that WeChat keeps and the
        # reader never sees. Unwrap them back to plain text.
        rendered = re.sub(r"<span[^>]*>(\s+)</span>", r"\1", rendered)
        rendered = re.sub(r"<span[^>]*>\s*</span>", "", rendered)
        return rendered.rstrip("\n").split("\n")
    except Exception:
        return None


# --------------------------------------------------------------------------
# Stage 5 -- callouts and quotes
# --------------------------------------------------------------------------
CALL_RE = re.compile(r"\s*\[!(\w+)\]\s*([^\n<]*)")
# Markdown merges *consecutive* `> [!TYPE]` blocks into a single <blockquote>
# holding one <p> per alert -- nine alerts in a row arrive as one element with
# nine paragraphs.  Handling only the first paragraph silently leaves the rest as
# raw `[!WARNING]` text in the published article, so every top-level paragraph is
# examined as a potential alert start.
_TRAILING_BR_RE = re.compile(r"^\s*(?:<br\s*/?>\s*)+")


def _alert_header(node: Tag):
    """Return ``(kind, title, rest_html)`` if *node* opens an alert box."""
    if getattr(node, "name", None) != "p":
        return None
    inner = "".join(str(c) for c in node.children)
    m = CALL_RE.match(inner)
    if not m:
        return None
    return m.group(1).lower(), m.group(2).strip(), \
        _TRAILING_BR_RE.sub("", inner[m.end():])


def convert_callouts(soup: BeautifulSoup, styles: dict, opts: Options,
                     report: Report) -> int:
    """Turn GitHub-style alert blockquotes into framed boxes.

    Syntax::

        > [!NOTE] 可选标题
        > 正文，可以有多段。

    Recognised kinds live in ``themes.CALLOUT_TYPES``; the label emoji and the
    box colour are data, so adding a new kind is a one-line change.
    """
    count = 0
    for bq in soup.find_all("blockquote"):
        top = [c for c in bq.children if isinstance(c, Tag)]
        headers = [_alert_header(c) for c in top]
        if not any(h for h in headers):
            continue  # an ordinary quote; convert_blockquotes owns it

        # Group the children into runs, each starting at an alert paragraph.
        runs: list[tuple[tuple | None, list[Tag]]] = []
        for child, head in zip(top, headers):
            if head is not None:
                runs.append((head, [child.extract()]))
            elif runs and runs[-1][0] is not None:
                runs[-1][1].append(child.extract())
            else:
                runs.append((None, [child.extract()]))

        produced: list[Tag] = []
        for head, nodes in runs:
            if head is None:
                for node in nodes:
                    produced.extend(_as_quote(soup, styles, node))
                continue
            kind, title, rest = head
            if kind not in CALLOUT_TYPES:
                report.warn("未知的 callout 类型 [!%s]，已按普通引用处理" % kind)
                for node in nodes:
                    produced.extend(_as_quote(soup, styles, node))
                continue

            token = CALLOUT_TYPES[kind]["token"]
            body: list[Tag] = []
            if rest:
                for chunk in _BR_SPLIT_RE.split(rest):
                    if chunk.strip():
                        body.append(_frag("<p>%s</p>" % chunk)[0])
            body.extend(nodes[1:])

            produced.append(_callout_box(soup, styles, token, kind, title, body,
                                         opts))
            count += 1

        for node in produced:
            bq.insert_before(node)
        bq.decompose()

    return count


def _callout_box(soup: BeautifulSoup, styles: dict, token: str, kind: str,
                 title: str, body: list[Tag], opts: Options) -> Tag:
    spec = CALLOUT_TYPES[kind]
    # A title identical to the kind's own label would render "✅ 结论 · 结论".
    suffix = (" · " + _esc(title)) if title and title != spec["label"] else ""
    parts = ['<p style="%s" %s="1">%s %s%s</p>'
             % (styles["callout_label_%s" % token], SKIP_ATTR, spec["emoji"],
                spec["label"], suffix)]
    last = len(body) - 1
    for i, node in enumerate(body):
        style_key = "callout_body_last_%s" % token if i == last \
            else "callout_body_%s" % token
        if node.name in ("ul", "ol"):
            for li in node.find_all("li"):
                li["style"] = styles[style_key]
        else:
            node["style"] = styles[style_key]
        parts.append(str(node))

    if opts.callout_style == "plain":
        # Degrade to a paragraph run for editors that mangle tables. The label
        # colour and the left rule still carry the meaning, so nothing is lost.
        _, border, _ = CALLOUT_COLORS[token]
        return _box_table(
            soup,
            "border-collapse: collapse; width: 100%; margin: 18px 0 20px 0;",
            "border-left: 4px solid %s; padding: 6px 0 6px 14px;" % border,
            "".join(parts),
        )
    return _box_table(soup, styles["callout_wrap_%s" % token],
                      styles["callout_cell_%s" % token], "".join(parts))


def _as_quote(soup: BeautifulSoup, styles: dict, node: Tag) -> list[Tag]:
    """Render a non-alert child of an alert blockquote as a plain quote."""
    if node.name == "p":
        node["style"] = styles["blockquote"]
        return [node]
    return [node]


def convert_blockquotes(soup: BeautifulSoup, styles: dict):
    """Flatten the blockquotes that were not callouts.

    Lists and tables inside a quote are lifted out as siblings: nesting a
    ``<ul>`` inside a ``<p>`` produces markup WeChat renders inconsistently.
    """
    for bq in soup.find_all("blockquote"):
        if bq.find(["ul", "ol", "table"], recursive=False) is None:
            merged = soup.new_tag("p")
            merged["style"] = styles["blockquote"]
            children = list(bq.children)
            for i, child in enumerate(children):
                name = getattr(child, "name", None)
                if name == "br":
                    continue
                if name == "p":
                    merged.extend(list(child.children))
                    if i != len(children) - 1:
                        merged.append(soup.new_tag("br"))
                else:
                    merged.append(child.extract())
            bq.replace_with(merged)
            continue

        anchor: Tag = bq
        for child in list(bq.children):
            name = getattr(child, "name", None)
            if name == "p":
                child["style"] = styles["blockquote"]
                anchor.insert_before(child.extract())
            elif name in ("ul", "ol", "table"):
                anchor.insert_before(child.extract())
        bq.decompose()


# --------------------------------------------------------------------------
# Stage 6 -- inline markup and dividers
# --------------------------------------------------------------------------
def convert_inline(soup: BeautifulSoup, styles: dict):
    for names, key in ((("strong", "b"), "strong"),
                       (("em", "i"), "em"),
                       (("del", "s", "strike"), "del")):
        for tag in soup.find_all(list(names)):
            span = _tag(soup, "span", styles[key])
            for child in list(tag.children):
                span.append(child.extract())
            tag.replace_with(span)
    # Superscripts are kept as spans rather than unwrapped: `x²` loses its
    # meaning once the vertical offset is gone.
    for tag in soup.find_all("sup"):
        span = _tag(soup, "span", "font-size: 0.75em; vertical-align: super;")
        for child in list(tag.children):
            span.append(child.extract())
        tag.replace_with(span)
    for tag in soup.find_all("sub"):
        span = _tag(soup, "span", "font-size: 0.75em; vertical-align: sub;")
        for child in list(tag.children):
            span.append(child.extract())
        tag.replace_with(span)
    for tag in soup.find_all(["u", "mark", "small", "font", "ins", "abbr", "cite"]):
        tag.unwrap()


def convert_dividers(soup: BeautifulSoup, styles: dict, opts: Options):
    """``---`` becomes a section break that survives WeChat's cleanup."""
    for hr in soup.find_all("hr"):
        if opts.divider == "none":
            hr.decompose()
        elif opts.divider == "rule":
            table = _box_table(soup, styles["divider_table"],
                               styles["divider_cell"], "&nbsp;")
            hr.replace_with(table)
        else:
            p = _tag(soup, "p", styles["divider_dots"], skip=True)
            p.string = "· · ·"
            hr.replace_with(p)


# --------------------------------------------------------------------------
# Stage 7 -- images
# --------------------------------------------------------------------------
def process_images(soup: BeautifulSoup, styles: dict, opts: Options,
                   report: Report) -> int:
    count = 0
    for img in soup.find_all("img"):
        if img.get("data-wp-math"):
            continue  # formula images carry their own sizing
        count += 1
        src = (img.get("src") or "").strip()
        alt = (img.get("alt") or "").strip()

        if not src:
            img.replace_with(_notice_box(soup, styles, "🖼 空图片地址"))
            report.warn("有一张图片没有 src 地址，已替换为占位提示")
            continue

        if src.startswith("data:image/svg") or src.lower().endswith(".svg"):
            report.warn("检测到 SVG：公众号保存时会丢弃 SVG，请改用 PNG/JPG")
        elif src.startswith("data:"):
            pass
        elif src.startswith(("http://", "https://", "//")):
            report.warn(
                "存在外部图片链接：粘贴后需在公众号编辑器里手动点一次「上传图片」，"
                "否则发布时图片会丢失；或改用本地图片配合 --image-mode embed"
            )
        else:
            resolved = (opts.base_dir / src).resolve()
            if not resolved.exists():
                report.warn("图片缺失：%s" % src)
                img.replace_with(_notice_box(soup, styles, "🖼 图片缺失：%s" % src))
                continue
            if opts.image_mode == "embed":
                mime = IMAGE_EXT_MIME.get(resolved.suffix.lower())
                if mime is None:
                    report.warn("不支持的图片格式：%s（支持 PNG/JPG/GIF/WebP/BMP）" % src)
                    continue
                payload = base64.b64encode(resolved.read_bytes()).decode("ascii")
                img["src"] = "data:%s;base64,%s" % (mime, payload)
            else:
                report.warn("图片仍为相对路径：%s（公众号无法访问本地路径）" % src)

        img["style"] = styles["img"]
        for attr in ("width", "height", "class", "id", "loading", "srcset"):
            if attr in img.attrs:
                del img.attrs[attr]

        if opts.image_caption and alt and not typo.looks_like_filename(alt):
            caption = _tag(soup, "p", styles["caption"], skip=True)
            caption.string = alt
            parent = img.parent
            if parent is not None and parent.name == "p" \
                    and len([c for c in parent.children if str(c).strip()]) == 1:
                parent.insert_after(caption)
                parent.unwrap()
            else:
                img.insert_after(caption)
    return count


def _notice_box(soup: BeautifulSoup, styles: dict, message: str) -> Tag:
    """A visible amber box where an image should have been.

    Silently dropping a broken image is worse than showing the author exactly
    which file is missing while they still have the source open.
    """
    token = "amber"
    return _box_table(
        soup, styles["callout_wrap_%s" % token],
        styles["callout_cell_%s" % token],
        '<p style="%s" %s="1">%s</p>'
        % (styles["callout_label_%s" % token], SKIP_ATTR, _esc(message)),
    )


# --------------------------------------------------------------------------
# Stage 8 -- tables and links
# --------------------------------------------------------------------------
def process_tables(soup: BeautifulSoup, styles: dict, report: Report) -> int:
    count = 0
    for table in soup.find_all("table"):
        if _is_box(table):
            continue
        count += 1
        rows = table.find_all("tr")
        if rows:
            columns = max(len(r.find_all(["td", "th"])) for r in rows)
            if columns > WIDE_TABLE_COLUMNS:
                report.warn("表格有 %d 列，手机上会挤成一团：建议拆表或改成列表" % columns)
        if not str(table.get("style", "")).strip():
            table["style"] = styles["table"]
        for th in table.find_all("th"):
            th["style"] = styles["th"]
        for td in table.find_all("td"):
            td["style"] = styles["td"]
    return count


def process_links(soup: BeautifulSoup, styles: dict, opts: Options,
                  report: Report) -> list[str]:
    """Handle the fact that WeChat silently de-links non-WeChat URLs.

    Only links back to ``mp.weixin.qq.com`` stay clickable after publishing, so
    an author who wants their sources reachable has to spell them out.  That is
    what ``--links plain`` and ``--links footnote`` are for.
    """
    anchors = soup.find_all("a")
    if not anchors:
        return []
    external = [a for a in anchors if (a.get("href") or "").startswith(("http", "//"))]
    if external and opts.links == "keep":
        report.warn(
            "文章含 %d 个外部链接：公众号保存后普通链接会退化为纯文本（只有公众号"
            "文章链接可点）。可用 --links footnote 改为文末脚注" % len(external)
        )

    if opts.links == "keep":
        for a in anchors:
            if not str(a.get("style", "")).strip():
                a["style"] = styles["a"]
        return []

    urls: list[str] = []
    for index, a in enumerate(anchors, 1):
        href = (a.get("href") or "").strip()
        text = a.get_text()
        if opts.links == "strip" or not href:
            a.replace_with(NavigableString(text))
        elif opts.links == "footnote":
            urls.append(href)
            a.replace_with(NavigableString("%s[%d]" % (text, index)))
        else:  # plain
            a.replace_with(NavigableString("%s（%s）" % (text, href)))
    return urls


def append_footnotes(soup: BeautifulSoup, styles: dict, urls: list[str]):
    if not urls:
        return
    head = _tag(soup, "p", styles["byline"], skip=True)
    head.string = "参考链接"
    soup.append(head)
    for i, url in enumerate(urls, 1):
        item = _tag(soup, "p", styles["footer"] + " text-align: left;", skip=True)
        item.string = "[%d] %s" % (i, url)
        soup.append(item)


# --------------------------------------------------------------------------
# Stage 9 -- Chinese typography on prose text nodes
# --------------------------------------------------------------------------
def typography_pass(soup: BeautifulSoup, opts: Options):
    if not opts.cjk_spacing and opts.punct == "off":
        return
    for node in list(soup.find_all(string=True)):
        parent = node.parent
        if parent is None or parent.name in ("code", "pre", "script", "style"):
            continue
        if _is_generated(parent):
            continue
        text = str(node)
        if not text.strip():
            continue
        new = typo.normalize_punctuation(text, level=opts.punct)
        if opts.cjk_spacing:
            new = typo.add_cjk_spacing(new)
        if new != text:
            node.replace_with(NavigableString(new))


# --------------------------------------------------------------------------
# Stage 10 -- article furniture
# --------------------------------------------------------------------------
def build_header(soup: BeautifulSoup, styles: dict, meta: dict, opts: Options):
    if opts.header == "off":
        return
    nodes: list[Tag] = []
    if opts.header == "full" and meta.get("title"):
        title = _tag(soup, "p", styles["h2"] + " text-align: center; margin-top: 0;",
                     skip=True)
        title.string = str(meta["title"])
        nodes.append(title)

    bits = [str(b) for b in (meta.get("author"), meta.get("date")) if b]
    if bits:
        byline = _tag(soup, "p", styles["byline"], skip=True)
        byline.string = " · ".join(bits)
        nodes.append(byline)

    if meta.get("digest"):
        digest = _tag(soup, "p", styles["digest"], skip=True)
        digest.string = str(meta["digest"])
        nodes.append(digest)

    for node in reversed(nodes):
        soup.insert(0, node)


def build_toc(soup: BeautifulSoup, styles: dict, opts: Options) -> int:
    """Build a readable index of the article's headings.

    Deliberately *not* a set of anchor links: WeChat strips ``id`` attributes, so
    the jump targets cannot exist after publishing.  A dead link is worse than a
    plain index, so the entries are text.
    """
    headings = soup.find_all(["h2", "h3"])
    if opts.toc == "never" or not headings:
        return 0
    if opts.toc == "auto" and len(headings) < opts.toc_min_headings:
        return 0

    entries: list[tuple[str, str, str]] = []
    h2_index = h3_index = 0
    for h in headings:
        text = h.get_text().strip()
        if not text:
            continue
        if h.name == "h2":
            h2_index += 1
            h3_index = 0
            entries.append(("h2", text, "%d." % h2_index))
        else:
            h3_index += 1
            prefix = ("%d.%d" % (h2_index or 1, h3_index)) if opts.heading_numbers \
                else "·"
            entries.append(("h3", text, prefix))
    if len(entries) < 2:
        return 0

    parts = ['<p style="%s" %s="1">目 录</p>'
             % (styles["toc_title"], SKIP_ATTR)]
    for level, text, prefix in entries:
        key = "toc_item_sub" if level == "h3" else "toc_item"
        parts.append('<p style="%s" %s="1">%s %s</p>'
                     % (styles[key], SKIP_ATTR, prefix, _esc(text)))
    table = _box_table(soup, styles["toc_table"], styles["toc_wrap"],
                       "".join(parts))

    # Insert after the header block, before the first piece of body content.
    anchor = None
    for node in soup.children:
        if isinstance(node, NavigableString) and not str(node).strip():
            continue
        if isinstance(node, Tag) and node.get(SKIP_ATTR) and not _is_box(node):
            anchor = node
            continue
        break
    if anchor is not None:
        anchor.insert_after(table)
    else:
        soup.insert(0, table)
    return len(entries)


def build_footer(soup: BeautifulSoup, styles: dict, meta: dict, opts: Options):
    if opts.footer_off:
        return
    text = opts.footer or meta.get("footer") or meta.get("copyright")
    if not text:
        author = meta.get("author") or "本文"
        text = "%s · 转载请保留作者与出处" % author

    soup.append(_box_table(soup, styles["divider_table"],
                           styles["divider_cell"], "&nbsp;"))
    for line in str(text).split("\n"):
        if not line.strip():
            continue
        p = _tag(soup, "p", styles["footer"], skip=True)
        p.string = line.strip()
        soup.append(p)


# --------------------------------------------------------------------------
# Stage 11 -- inline styles and final cleanup
# --------------------------------------------------------------------------
def apply_styles(soup: BeautifulSoup, styles: dict):
    """Style any element that does not already carry a style.

    Existing styles win: the code-block, callout, formula and image stages each
    set accurate values that a blanket rule would otherwise overwrite.
    """
    for tag_name in ("h2", "h3", "p", "li", "ul", "ol", "table", "th", "td", "a"):
        style = styles.get(tag_name)
        if not style:
            continue
        for el in soup.find_all(tag_name):
            if not str(el.get("style", "")).strip():
                el["style"] = style


def filter_css(style: str, report: Report) -> str:
    kept: list[str] = []
    for part in style.split(";"):
        if ":" not in part:
            continue
        prop, _, value = part.partition(":")
        prop, value = prop.strip().lower(), value.strip()
        if not prop or not value:
            continue
        if prop in FORBIDDEN_CSS_PROPS or prop not in ALLOWED_CSS_PROPS:
            report.dropped_css += 1
            continue
        kept.append("%s: %s" % (prop, value))
    return "; ".join(kept) + (";" if kept else "")


def split_nested_blocks(soup: BeautifulSoup):
    """Lift block-level elements out of any ``<p>`` that contains them.

    Word exports and hand-written HTML both produce ``<p><table>...</table></p>``,
    which WeChat renders unpredictably -- the paragraph's inline styles bleed
    into the table, or the table vanishes.
    """
    for p in soup.find_all("p"):
        if p.find(BLOCK_LEVEL, recursive=False) is None:
            continue
        style = p.get("style")
        new_nodes: list[Tag] = []
        current: Tag | None = None
        for child in list(p.children):
            if isinstance(child, Tag) and child.name in BLOCK_LEVEL:
                current = None
                new_nodes.append(child.extract())
            else:
                if current is None:
                    current = _tag(soup, "p", style)
                    new_nodes.append(current)
                current.append(child.extract())
        for node in new_nodes:
            if node.name == "p" and not str(node).strip():
                node.decompose()
                continue
            p.insert_before(node)
        p.decompose()


def clean_attributes(soup: BeautifulSoup, report: Report):
    """Strip class/id/data/event attributes and non-portable CSS."""
    for tag in soup.find_all(True):
        for attr in list(tag.attrs):
            if attr in ("class", "id") or attr.startswith(("data-", "on", "aria-")):
                del tag.attrs[attr]
        style = tag.get("style")
        if style:
            filtered = filter_css(style, report)
            if filtered:
                tag["style"] = filtered
            else:
                del tag.attrs["style"]

    for tag in soup.find_all(True):
        if tag.name not in ALLOWED_TAGS:
            tag.unwrap()

    # Drop the empty husks left behind by unwrapping.
    for p in soup.find_all("p"):
        if not p.get_text().strip() and p.find("img") is None \
                and not str(p.get("style", "")).strip():
            p.decompose()
    split_nested_blocks(soup)


# --------------------------------------------------------------------------
# Assembly
# --------------------------------------------------------------------------
PREVIEW_SHELL = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
</head>
<!--
  公众号预览页。整页正文就是可粘贴片段：浏览器里 Ctrl+A / Cmd+A 全选，
  Ctrl+C / Cmd+C，然后粘贴进 mp.weixin.qq.com 的编辑器即可。
  正文宽度限制在 640px 以内，接近手机阅读宽度，便于做视觉校对。
  本注释与 <head> 都不会被复制进编辑器。
-->
<body style="margin: 0; padding: 0; background-color: #eceff3;">
<article style="max-width: 640px; margin: 0 auto; padding: 28px 22px 48px 22px;
                background-color: #ffffff;
                font-family: -apple-system, BlinkMacSystemFont, 'PingFang SC',
                             'Hiragino Sans GB', 'Microsoft YaHei', sans-serif;">
{content}
</article>
</body>
</html>
"""


def render_document(source_path: Path, opts: Options, kind: str | None = None,
                    raw_text: str | None = None):
    """Run the full pipeline.  Returns ``(preview_html, fragment_html, report, meta)``."""
    report = Report()
    palette = palette_from_file(opts.theme_file) if opts.theme_file \
        else derive_palette(opts.theme)
    if opts.accent:
        palette = dict(palette, accent=opts.accent)
    report.theme = palette.get("label", palette.get("name", ""))

    styles = build_styles(palette, {
        "heading_style": opts.heading_style,
        "indent": opts.indent,
        "letter_spacing": opts.letter_spacing if opts.letter_spacing is not None else 0.4,
        "font_size": opts.font_size,
    })

    if kind is None:
        kind = source_path.suffix.lower()
    if raw_text is None:
        raw_text = read_text(source_path)

    meta: dict = {}
    math_spans: list[str] = []
    code_spans: list[str] = []

    if kind in ("markdown", ".md", ".markdown", ".txt"):
        meta, body = split_front_matter(raw_text)
        if looks_like_html(body):
            report.source_kind = "html"
            html = body
        else:
            report.source_kind = "markdown"
            body = typo.collapse_blank_lines(body)
            masked, math_spans, code_spans = typo.protect_source(body)
            import markdown
            extensions = ["extra", "fenced_code", "sane_lists"]
            if opts.nl2br:
                extensions.append("nl2br")
            html = markdown.markdown(masked, extensions=extensions)
    elif kind in ("docx", ".docx"):
        report.source_kind = "docx"
        html = read_docx(source_path)
    else:
        report.source_kind = "html"
        html = raw_text

    if not html.strip():
        report.error("源文件没有可转换的内容")
        return "", "", report, meta

    # Parse once with lxml for its error recovery on messy real-world HTML, then
    # re-parse the extracted body as a flat BeautifulSoup document.  The second
    # parse matters: every stage below needs to *create* tags, and `new_tag` only
    # exists on BeautifulSoup, not on a body Tag.  Working on one flat object
    # also means `soup.children` is the article rather than <html>/<head>.
    parsed = BeautifulSoup(html, "lxml")
    body = parsed.body if parsed.body is not None else parsed
    soup = BeautifulSoup("".join(str(c) for c in body.children), "html.parser")
    container = soup

    # --- transforms, in dependency order ---------------------------------
    drop_forbidden(container)
    normalize_headings(container, report)

    renderer = None
    if opts.math != "off":
        renderer = MathRenderer(fontsize=opts.math_font_size, dpi=opts.math_dpi)
        if not renderer.available and opts.math == "png":
            report.warn("matplotlib 不可用，公式将降级为 Unicode 文本"
                        "（安装：pip install matplotlib）")

    restore_tokens(container, math_spans, code_spans, renderer, styles, opts, report)
    convert_code_blocks(container, styles, opts, report)
    n_callouts = convert_callouts(container, styles, opts, report)
    convert_blockquotes(container, styles)
    convert_inline(container, styles)
    convert_dividers(container, styles, opts)
    n_images = process_images(container, styles, opts, report)
    n_tables = process_tables(container, styles, report)
    footnote_urls = process_links(container, styles, opts, report)

    split_nested_blocks(container)
    typography_pass(container, opts)

    build_header(container, styles, meta, opts)
    n_toc = build_toc(container, styles, opts)
    build_footer(container, styles, meta, opts)
    append_footnotes(container, styles, footnote_urls)

    apply_styles(container, styles)
    # Count the generated boxes before cleanup strips their bookkeeping
    # attribute, otherwise the report claims zero framed elements.
    box_count = sum(1 for t in container.find_all("table") if _is_box(t))
    clean_attributes(container, report)

    # --- report -----------------------------------------------------------
    fragment = "\n".join(str(c) for c in container.children if str(c).strip())
    plain_len = len(re.sub(r"<[^>]+>", "", fragment))
    imgs = container.find_all("img")
    report.stats = {
        "headings": len(container.find_all(["h2", "h3"])),
        "paragraphs": len(container.find_all("p")),
        "images": n_images,
        "formulas": len(math_spans),
        "formulas_as_png": sum(1 for i in imgs
                               if str(i.get("src", "")).startswith("data:image/png")),
        "embedded_images": sum(1 for i in imgs
                               if str(i.get("src", "")).startswith("data:")),
        "callouts": n_callouts,
        "user_tables": n_tables,
        "toc_entries": n_toc,
        "characters": plain_len,
        "boxes": box_count,
    }
    if report.dropped_css:
        report.warn("已移除 %d 条公众号不支持的 CSS 声明（定位/动画/阴影等）"
                    % report.dropped_css)
    if math_spans and renderer is not None and renderer.failures:
        report.warn("%d 个公式渲染失败：%s"
                    % (len(renderer.failures), "；".join(renderer.failures[:3])))
    if plain_len > MAX_ARTICLE_CHARS:
        report.warn("正文约 %d 字，超过公众号单篇 %d 字的建议上限"
                    % (plain_len, MAX_ARTICLE_CHARS))

    title = meta.get("title") or source_path.stem
    preview = PREVIEW_SHELL.format(title=_esc(str(title)), content=fragment)
    return preview, fragment, report, meta
