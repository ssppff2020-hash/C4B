"""
Input readers (Markdown / Word / HTML) and output exporters (Zhihu / plain text).

The starter kit's ``read_docx`` walked ``doc.paragraphs`` and stopped there,
which silently drops every table and every embedded picture in a Word document
-- a serious loss for the report-style documents people actually paste into
WeChat.  This version walks the document body in order, so tables and images
land in the right place.
"""

from __future__ import annotations

import base64
import io
import re
from pathlib import Path

from bs4 import BeautifulSoup, NavigableString, Tag

# --------------------------------------------------------------------------
# Front matter
# --------------------------------------------------------------------------
_FM_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.S)
_LIST_RE = re.compile(r"^\[(.*)\]$")


def split_front_matter(text: str):
    """Return ``(metadata_dict, body)``.

    A deliberately small YAML subset: flat scalars, inline ``[a, b]`` lists, and
    ``|`` literal blocks.  Pulling in PyYAML for this would add a dependency
    that many users cannot install, for no expressive gain -- article metadata
    is flat by nature.
    """
    m = _FM_RE.match(text)
    if not m:
        return {}, text

    meta: dict = {}
    lines = m.group(1).split("\n")
    i = 0
    while i < len(lines):
        line = lines[i]
        i += 1
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key, value = key.strip().lower(), value.strip()

        if value in ("|", ">"):  # literal / folded block
            block: list[str] = []
            while i < len(lines) and (lines[i].startswith((" ", "\t")) or not lines[i].strip()):
                block.append(lines[i].strip())
                i += 1
            meta[key] = "\n".join(block).strip() if value == "|" else " ".join(
                b for b in block if b
            ).strip()
            continue

        if value.startswith('"') and value.endswith('"') and len(value) > 1:
            value = value[1:-1]
        elif value.startswith("'") and value.endswith("'") and len(value) > 1:
            value = value[1:-1]

        lm = _LIST_RE.match(value)
        if lm:
            meta[key] = [p.strip().strip("'\"") for p in lm.group(1).split(",") if p.strip()]
        else:
            meta[key] = value

    return meta, text[m.end():]


def truthy(value, default: bool = True) -> bool:
    """Interpret the many spellings of yes/no an author might type."""
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() not in ("false", "no", "off", "0", "none", "")


# --------------------------------------------------------------------------
# Markdown / HTML readers
# --------------------------------------------------------------------------
def read_text(path: str | Path) -> str:
    """Read a text file, tolerating the encodings Chinese users actually have.

    GB18030 is tried second because it is a strict superset of GBK/GB2312, so
    one fallback covers every legacy Windows-exported document.
    """
    raw = Path(path).read_bytes()
    for encoding in ("utf-8-sig", "utf-8", "gb18030", "big5"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def markdown_to_html(text: str) -> str:
    """Convert Markdown to HTML with the extensions this pipeline relies on."""
    import markdown

    return markdown.markdown(
        text,
        extensions=[
            "extra",         # tables, footnotes, abbreviations, attribute lists
            "fenced_code",   # ```lang blocks
            "sane_lists",    # predictable nesting
            "nl2br",         # one-line-per-paragraph, the Chinese authoring norm
        ],
        output_format="html",
    )


# --------------------------------------------------------------------------
# Word reader
# --------------------------------------------------------------------------
_W_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_A_NS = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
_R_NS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"

_MIME_BY_EXT = {
    "png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
    "gif": "image/gif", "bmp": "image/bmp", "webp": "image/webp",
    "emf": "image/emf", "wmf": "image/wmf", "tiff": "image/tiff",
}


def _inline_html(para) -> str:
    """Render a Word paragraph's runs, preserving bold/italic/strike."""
    out: list[str] = []
    for run in para.runs:
        t = run.text
        if not t:
            continue
        t = (t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
        if run.bold and run.italic:
            out.append("<strong><em>%s</em></strong>" % t)
        elif run.bold:
            out.append("<strong>%s</strong>" % t)
        elif run.italic:
            out.append("<em>%s</em>" % t)
        elif run.font is not None and run.font.strike:
            out.append("<del>%s</del>" % t)
        else:
            out.append(t)
    return "".join(out)


def _para_images(para, document) -> list[str]:
    """Extract images embedded in a paragraph as base64 HTML ``<img>`` tags."""
    tags: list[str] = []
    for blip in para._element.iter(_A_NS + "blip"):
        rid = blip.get(_R_NS + "embed")
        if not rid:
            continue
        try:
            part = document.part.related_parts[rid]
            blob = part.blob
        except Exception:
            continue
        ext = str(part.partname).rsplit(".", 1)[-1].lower()
        mime = _MIME_BY_EXT.get(ext, "image/png")
        tags.append(
            '<img src="data:%s;base64,%s" alt="%s">'
            % (mime, base64.b64encode(blob).decode("ascii"),
               Path(str(part.partname)).name)
        )
    return tags


_HEADING_MAP = {"1": "h2", "2": "h2", "3": "h3", "4": "h3",
                "5": "h3", "6": "h3", "7": "h3", "8": "h3", "9": "h3"}
_LIST_STYLES = {
    "List Bullet": "ul", "List Paragraph": "ul", "List Number": "ol",
    "List Number 2": "ol", "List Bullet 2": "ul",
}


def read_docx(path: str | Path) -> str:
    """Convert a .docx to HTML, walking the body in document order.

    Iterating ``document.element.body`` (rather than ``document.paragraphs``)
    is what lets tables and images keep their position relative to the prose.
    """
    from docx import Document
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    document = Document(str(path))
    parts: list[str] = []
    open_list: str | None = None

    def close_list():
        nonlocal open_list
        if open_list:
            parts.append("</%s>" % open_list)
            open_list = None

    def emit_paragraph(para):
        nonlocal open_list
        text = para.text.strip()
        images = _para_images(para, document)
        style = (para.style.name or "") if para.style else ""

        if not text and not images:
            close_list()
            return

        if style.startswith("Heading"):
            close_list()
            level = style.split()[-1]
            tag = _HEADING_MAP.get(level, "h3")
            parts.append("<%s>%s</%s>" % (tag, _inline_html(para), tag))
            return

        if style in _LIST_STYLES:
            want = _LIST_STYLES[style]
            if open_list != want:
                close_list()
                parts.append("<%s>" % want)
                open_list = want
            parts.append("<li>%s</li>" % _inline_html(para))
            return

        close_list()
        for img in images:
            parts.append(img)
        if text:
            parts.append("<p>%s</p>" % _inline_html(para))

    for child in document.element.body.iterchildren():
        if child.tag == _W_NS + "p":
            emit_paragraph(Paragraph(child, document))
        elif child.tag == _W_NS + "tbl":
            close_list()
            table = Table(child, document)
            rows: list[str] = []
            for r_index, row in enumerate(table.rows):
                cells = []
                for cell in row.cells:
                    body = "<br>".join(
                        _inline_html(p) if _inline_html(p) else p.text
                        for p in cell.paragraphs if p.text.strip()
                    ) or cell.text.strip()
                    tag = "th" if r_index == 0 else "td"
                    cells.append("<%s>%s</%s>" % (tag, body, tag))
                rows.append("<tr>%s</tr>" % "".join(cells))
            parts.append("<table>%s</table>" % "".join(rows))
    close_list()

    return "\n".join(parts)


def read_source(path: str | Path):
    """Dispatch on extension.  Returns ``(html, raw_text_or_None)``."""
    path = Path(path)
    ext = path.suffix.lower()
    if ext in (".md", ".markdown", ".txt"):
        return "markdown", read_text(path)
    if ext == ".docx":
        return "docx", read_docx(path)
    if ext in (".html", ".htm"):
        return "html", read_text(path)
    raise ValueError("Unsupported input format '%s'. Supported: .md .markdown .txt .docx .html .htm" % ext)


# --------------------------------------------------------------------------
# Exporters -- Level 4 "one source, many destinations"
# --------------------------------------------------------------------------
_CALLOUT_LABEL_RE = re.compile(r"^\[!(\w+)\]\s*", re.I)
_HTML_STRIP_RE = re.compile(r"<[^>]+>")


def to_zhihu_markdown(body_text: str, meta: dict | None = None) -> str:
    """Produce a Zhihu-friendly Markdown variant of the same article.

    Zhihu renders Markdown natively and keeps images as remote URLs, so the two
    changes that matter are dropping the WeChat front matter and turning the
    alert syntax into a plain blockquote with a bold label -- Zhihu has no notion
    of alert boxes.

    Pass the article *body* (front matter already split off), not the raw file;
    otherwise the YAML block reappears verbatim in the middle of the post.
    """
    meta = meta or {}
    out: list[str] = []
    has_title = bool(meta.get("title"))
    if has_title:
        out.append("# %s" % meta["title"])
        out.append("")

    for line in body_text.split("\n"):
        # With a title heading prepended, any `#` still in the body is a section
        # heading; leaving it at level 1 would give the post two top-level
        # headings. This mirrors the WeChat pipeline, which also demotes h1.
        if has_title and line.startswith("# "):
            line = "#" + line
        stripped = line.lstrip("> ").strip() if line.lstrip().startswith(">") else None
        match = _CALLOUT_LABEL_RE.match(stripped) if stripped else None
        if match:
            # Reuse the pipeline's own kind table so a new callout type gets the
            # same label on Zhihu as in the WeChat article.
            from themes import CALLOUT_TYPES
            spec = CALLOUT_TYPES.get(match.group(1).lower())
            label = ("%s %s" % (spec["emoji"], spec["label"])) if spec \
                else match.group(1).capitalize()
            title = _CALLOUT_LABEL_RE.sub("", stripped).strip()
            # The remainder of the marker line is the box's title, so it belongs
            # on the label line -- the WeChat box renders "🔑 重点 · 判断顺序",
            # and splitting them here would make the two versions of the same
            # article read differently.  A title identical to the type's own
            # label is dropped, or the box reads "结论 · 结论".
            if title and not (spec and title == spec["label"]):
                label = "%s · %s" % (label, title)
            out.append("> **%s**" % label)
            continue
        out.append(line)

    text = "\n".join(out)
    return re.sub(r"\n{3,}", "\n\n", text).strip() + "\n"


def to_plain_text(html: str) -> str:
    """Flatten rendered HTML to readable plain text (plain-text newsletter use).

    Spacer cells are dropped first: the divider and TOC boxes are single-cell
    tables whose only content is ``&nbsp;``, and left in they render as a stray
    `` | `` line in the middle of the output.
    """
    import html as html_mod

    text = re.sub(r"(?is)<(script|style).*?</\1>", "", html)
    # Cells holding nothing but a space carry no text; they only produce pipes.
    text = re.sub(r"(?is)<t[dh][^>]*>(?:\s|&nbsp;| )*</t[dh]>", "", text)
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</(p|h2|h3|h4|li|tr|div|table)>", "\n", text)
    text = re.sub(r"(?i)<li[^>]*>", "  - ", text)
    text = re.sub(r"(?i)</t[dh]>", " | ", text)
    text = _HTML_STRIP_RE.sub("", text)
    text = html_mod.unescape(text).replace(" ", " ")
    text = re.sub(r"(?m)^\s*\|\s*$", "", text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip() + "\n"


# --------------------------------------------------------------------------
# Fragment -> Markdown (for HTML and Word sources)
# --------------------------------------------------------------------------
_MONO_RE = re.compile(r"monospace")
_BOLD_RE = re.compile(r"font-weight:\s*(?:bold|[6-9]00)")
_ITALIC_RE = re.compile(r"font-style:\s*italic")
_STRIKE_RE = re.compile(r"line-through")
_CALL_OUT_LABEL_RE = re.compile(r"^(?:📘|💡|🔑|⚠️|🚨|✅|🧪|🤔|💬|🖼)\s")


def _style_of(node) -> str:
    return str(node.get("style", "")) if hasattr(node, "get") else ""


_LATEX_HINT_RE = re.compile(r"\\[A-Za-z]+|[\^_]\{|[\^_][A-Za-z0-9](?![A-Za-z0-9])")


def _looks_like_latex(text: str) -> bool:
    """Distinguish a formula's TeX alt text from ordinary image alt text.

    Prose captions essentially never contain a backslash command or a braced
    superscript, so this is a safe discriminator -- and it matters because the
    two want opposite treatment: prose becomes a caption, TeX must be
    re-escaped as maths.
    """
    return bool(text) and bool(_LATEX_HINT_RE.search(text))


def _is_single_cell(table) -> bool:
    rows = table.find_all("tr")
    if len(rows) != 1:
        return False
    return len(rows[0].find_all(["td", "th"])) == 1


def _inline_md(node) -> str:
    """Serialise an inline fragment to Markdown."""
    from bs4 import NavigableString, Tag

    if isinstance(node, NavigableString):
        return re.sub(r"\s+", " ", str(node))
    if not isinstance(node, Tag):
        return ""
    if node.name == "br":
        return "\n"
    style = _style_of(node)
    if node.name == "img":
        alt = node.get("alt") or "图片"
        src = (node.get("data-md-src") or "").strip()
        if not src:
            # No resolvable file to point at. A rendered formula carries its TeX
            # in `alt`, and Zhihu renders LaTeX natively -- so round-trip it as
            # maths. Anything else degrades to its alt text, because
            # `![caption]()` is a broken image, not a caption.
            if _looks_like_latex(alt):
                return "$%s$" % alt
            return alt
        return "![%s](%s)" % (alt, src)
    if node.name == "a":
        return "[%s](%s)" % (_inline_children(node), node.get("href", ""))
    if node.name == "span":
        inner = _inline_children(node)
        if not inner.strip():
            return inner
        if _MONO_RE.search(style):
            return "`%s`" % inner
        if _BOLD_RE.search(style):
            return "**%s**" % inner
        if _ITALIC_RE.search(style):
            return "*%s*" % inner
        if _STRIKE_RE.search(style):
            return "~~%s~~" % inner
        return inner
    return _inline_children(node)


def _inline_children(node) -> str:
    return "".join(_inline_md(child) for child in node.children)


def _table_to_markdown(table) -> str:
    rows = []
    for tr in table.find_all("tr"):
        cells = [_inline_children(td).strip().replace("|", "\\|")
                 for td in tr.find_all(["td", "th"])]
        rows.append(cells)
    if not rows:
        return ""
    width = max(len(r) for r in rows)
    rows = [r + [""] * (width - len(r)) for r in rows]
    lines = ["| " + " | ".join(rows[0]) + " |",
             "|" + "---|" * width]
    lines += ["| " + " | ".join(r) + " |" for r in rows[1:]]
    return "\n".join(lines)


def _box_to_markdown(table) -> str | None:
    """Serialise one of the generated single-cell boxes, or return None.

    The rendered fragment has already had its ``data-wp-*`` bookkeeping
    attributes stripped, so each box kind is recognised by its shape: a code
    block is a cell of monospace paragraphs, a callout opens with an emoji label,
    a divider is an empty cell with a top border, and the TOC opens with 目录.
    """
    cell = table.find(["td", "th"])
    if cell is None:
        return None

    first = cell.find("p")
    first_text = first.get_text().strip() if first is not None else ""
    cell_style = _style_of(cell)

    if first_text.startswith("目 录") or first_text.startswith("目录"):
        items = [p.get_text().strip() for p in cell.find_all("p")[1:]]
        return "\n".join("- " + i for i in items if i)

    if "border-top" in cell_style and not cell.get_text().strip():
        return "---"

    paragraphs = cell.find_all("p")
    if paragraphs and any(_MONO_RE.search(_style_of(p)) for p in paragraphs):
        # A leading non-monospace paragraph is the language label, which the
        # renderer writes in uppercase and which becomes the fence info string.
        body = paragraphs
        lang = ""
        head = paragraphs[0].get_text().strip()
        if not _MONO_RE.search(_style_of(paragraphs[0])) and head.isascii():
            lang = head.lower()
            body = paragraphs[1:]
        code = "\n".join(p.get_text() for p in body)
        return "```%s\n%s\n```" % (lang, code)

    if _CALL_OUT_LABEL_RE.match(first_text):
        parts = ["> **%s**" % first_text]
        for node in list(cell.children):
            if node is first:
                continue
            text = _inline_children(node).strip() if hasattr(node, "children") \
                else str(node).strip()
            if text:
                parts.append(">")
                parts.append("> " + text.replace("\n", " "))
        return "\n".join(parts)

    return None


def fragment_to_markdown(fragment: str, meta: dict | None = None,
                         image_dir=None, image_prefix: str = "") -> str:
    """Turn a rendered WeChat fragment back into portable Markdown.

    Needed because ``--also zhihu`` cannot reuse the Markdown source when the
    input was HTML or Word: there is no Markdown to reuse.  Deriving it from the
    rendered structure also means the Zhihu version reflects the *cleaned* text
    (scripts removed, h1 demoted, punctuation normalised) instead of shipping the
    original mess to a second platform.

    Embedded images are written to ``image_dir`` and referenced relatively --
    Zhihu re-uploads from real files, so a base64 data URI would be useless there.
    """
    from bs4 import NavigableString, Tag

    soup = BeautifulSoup(fragment, "html.parser")
    meta = meta or {}

    # Materialise embedded images so the Markdown can point at real files.
    counter = 0
    if image_dir is not None:
        image_dir = Path(image_dir)
        for img in soup.find_all("img"):
            src = str(img.get("src", ""))
            if not src.startswith("data:"):
                img["data-md-src"] = src
                continue
            try:
                header, payload = src.split(",", 1)
                ext = "png" if "png" in header else (
                    "jpg" if "jpeg" in header or "jpg" in header else "png")
                counter += 1
                image_dir.mkdir(parents=True, exist_ok=True)
                name = "fig-%02d.%s" % (counter, ext)
                (image_dir / name).write_bytes(base64.b64decode(payload))
                img["data-md-src"] = "%s/%s" % (image_prefix, name) \
                    if image_prefix else name
            except Exception:
                img["data-md-src"] = ""
    else:
        for img in soup.find_all("img"):
            img["data-md-src"] = ""

    out: list[str] = []
    if meta.get("title"):
        out.append("# %s\n" % meta["title"])

    last_image_alt: str | None = None

    for node in soup.children:
        if isinstance(node, NavigableString):
            continue
        if not isinstance(node, Tag):
            continue
        name = node.name

        if name == "h2":
            out.append("## %s" % _inline_children(node).strip())
        elif name == "h3":
            out.append("### %s" % _inline_children(node).strip())
        elif name == "p":
            text = _inline_children(node).strip()
            # Skip the caption the renderer generated for the preceding image:
            # Markdown's alt text already carries it, and repeating it reads as a
            # stray line under every picture.
            if text and text == last_image_alt:
                last_image_alt = None
                continue
            last_image_alt = None
            if text and text != "· · ·":
                out.append(text)
        elif name in ("ul", "ol"):
            for i, li in enumerate(node.find_all("li"), 1):
                marker = "-" if name == "ul" else "%d." % i
                out.append("%s %s" % (marker, _inline_children(li).strip()))
        elif name == "table":
            if _is_single_cell(node):
                boxed = _box_to_markdown(node)
                if boxed is not None:
                    out.append(boxed)
                    continue
            out.append(_table_to_markdown(node))
        elif name == "img":
            last_image_alt = (node.get("alt") or "").strip() or None
            out.append(_inline_md(node))

    text = "\n\n".join(out)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip() + "\n"


def strip_data_uris(html: str) -> str:
    """Replace base64 image payloads with a short placeholder.

    Used for the ``--report`` view and for diffs: a single embedded formula is
    thousands of characters and makes any human-readable output useless.
    """
    return re.sub(
        r'src="data:([^;"]+);base64,[A-Za-z0-9+/=]+"',
        lambda m: 'src="data:%s;base64,<omitted>"' % m.group(1),
        html,
    )
