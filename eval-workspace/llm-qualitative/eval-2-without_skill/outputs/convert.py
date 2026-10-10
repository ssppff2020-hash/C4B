#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
convert.py -- turn a messy Word / WeChat-editor HTML export into HTML that can be
copy-pasted straight into the WeChat Official Account editor (mp.weixin.qq.com).

Why the output looks the way it does
------------------------------------
The WeChat editor is not a browser. When you paste HTML into it, its sanitiser:
  * throws away <style> blocks, <script>, <link>, <meta>, <iframe> and friends
  * throws away class= / id= attributes
  * keeps inline style="" attributes (mostly as-is)
  * keeps a limited tag set (section, p, span, h1-h6, img, a, strong, em, ul, ol,
    li, blockquote, table, br, hr ...)
So the only reliable way to control appearance is *inline styles on every element*
and a small, conservative tag vocabulary. That is exactly what this script emits.

Usage:
    python -I convert.py <input.html|md> <output.wechat.html> [preview.html]
"""

import html as html_mod
import re
import sys
from html.parser import HTMLParser

# --------------------------------------------------------------------------
# 1. Tag policy
# --------------------------------------------------------------------------

# Dropped entirely, children included. Nothing here has a place in a WeChat body.
DROP_TAGS = {
    "script", "style", "link", "meta", "base", "head", "title", "noscript",
    "iframe", "object", "embed", "applet", "form", "input", "textarea",
    "select", "option", "button", "svg", "canvas", "video", "audio", "source",
    "track", "map", "area", "template", "slot", "dialog", "menu", "menuitem",
    "col", "colgroup", "param", "frame", "frameset", "xml",
}

# Transparent containers: tag is replaced by its children. Word wraps everything
# in divs; WeChat does not need them and they only add inline-style noise.
UNWRAP_TAGS = {
    "html", "body", "div", "section", "article", "main", "header", "footer",
    "nav", "aside", "font", "center", "span", "tt", "wbr", "ruby", "rt", "rp",
    "bdi", "bdo", "label", "fieldset", "legend", "address", "dir", "hgroup",
    "picture",
}

# Tags we keep as real block elements.
BLOCK_TAGS = {"p", "h1", "h2", "h3", "h4", "h5", "h6", "img", "ul", "ol",
              "blockquote", "pre", "table", "hr", "figure", "figcaption"}

INLINE_TAGS = {"strong", "b", "em", "i", "a", "code", "sub", "sup", "br",
               "mark", "abbr", "cite", "q", "time", "kbd", "samp", "var",
               "u", "s", "strike", "del", "ins", "small", "big"}

VOID_TAGS = {"img", "br", "hr", "input", "meta", "link", "source", "track", "area", "base", "col", "param", "embed", "wbr"}

# Word exports routinely forget to close inline tags. A single missing </b> would
# otherwise turn every following paragraph bold, so a block-level start tag is
# treated as implying the end of any still-open paragraph / inline formatting.
# <img> and <br> are deliberately excluded: they are legal inside a paragraph.
BLOCK_STARTERS = (BLOCK_TAGS - {"img"}) | {
    "li", "dl", "dt", "dd", "thead", "tbody", "tfoot", "tr", "td", "th", "caption",
}

# Everything that must not stay open across a block boundary.
POP_ON_BLOCK = (INLINE_TAGS - {"br"}) | {
    "span", "font", "p", "center", "nobr", "label", "picture", "tt", "small",
    "big", "u", "s", "strike", "del", "ins", "ruby", "rt", "rp",
}

# Attributes carried over. Everything else (class/id/data-*/on*/style) is dropped;
# style is dropped because we re-derive it ourselves.
KEEP_ATTRS = {"img": {"src", "alt"}, "a": {"href", "title"}, "td": {"colspan", "rowspan"},
              "th": {"colspan", "rowspan"}}

# --------------------------------------------------------------------------
# 2. Visual design (WeChat-safe, phone-first)
# --------------------------------------------------------------------------

# NOTE: single quotes only. These land inside a double-quoted style="..." attribute,
# so a double quote in a font name would terminate the attribute and produce garbage.
FONT = ("-apple-system,BlinkMacSystemFont,'Helvetica Neue','PingFang SC',"
        "'Hiragino Sans GB','Microsoft YaHei',sans-serif")
MONO = "Menlo,Consolas,'Courier New',monospace"

INK = "#1a1a1a"       # headings
BODY = "#3f3f3f"      # body copy  (a hair darker than the usual #666 for phones)
MUTED = "#888888"
ACCENT = "#07C160"    # WeChat green
RULE = "#ececec"
CODEBG = "#f6f7f9"

S = {
    "container": (
        f"font-family:{FONT};font-size:15px;line-height:1.8;color:{BODY};"
        "letter-spacing:.5px;word-break:break-word;text-align:justify;"
        "background:#ffffff;"
    ),
    # The document's <h1>. In WeChat the real article title lives in a separate
    # field, so this is styled as an in-body lead heading, not a page banner.
    "title": (f"font-family:{FONT};font-size:21px;font-weight:bold;color:{INK};"
              "line-height:1.45;letter-spacing:.5px;margin:4px 0 22px;text-align:center;"),
    "h2": (f"font-family:{FONT};font-size:18px;font-weight:bold;color:{INK};"
           "line-height:1.5;letter-spacing:.5px;margin:28px 0 14px;padding-left:10px;"
           f"border-left:4px solid {ACCENT};"),
    "h3": (f"font-family:{FONT};font-size:16px;font-weight:bold;color:{INK};"
           "line-height:1.5;letter-spacing:.5px;margin:22px 0 10px;padding-left:2px;"),
    "h3dot": (f"display:inline-block;width:6px;height:6px;background:{ACCENT};"
              "border-radius:50%;margin-right:7px;vertical-align:middle;"),
    "p": (f"font-family:{FONT};font-size:15px;line-height:1.8;color:{BODY};"
          "letter-spacing:.5px;margin:0 0 17px;text-align:justify;"),
    # Same, but with the trailing gap removed -- used for the last block in a box.
    "p_tight": (f"font-family:{FONT};font-size:15px;line-height:1.8;color:{BODY};"
                "letter-spacing:.5px;margin:0;text-align:justify;"),
    "imgwrap": "margin:22px 0;text-align:center;line-height:0;",
    "img": ("max-width:100%;height:auto;display:block;margin:0 auto;"
            "border-radius:6px;"),
    "caption": (f"font-family:{FONT};font-size:12px;color:{MUTED};line-height:1.6;"
                "margin:8px 0 0;text-align:center;letter-spacing:.5px;"),
    "quote": (f"font-family:{FONT};font-size:14px;line-height:1.75;color:#555555;"
              f"margin:18px 0;padding:12px 14px;border-left:3px solid {ACCENT};"
              "background:#f7f8f8;border-radius:4px;letter-spacing:.5px;"),
    "ul": "margin:0 0 17px;padding-left:22px;",
    "li": (f"font-family:{FONT};font-size:15px;line-height:1.8;color:{BODY};"
           "letter-spacing:.5px;margin:0 0 9px;"),
    "pre": (f"font-family:{MONO};font-size:12.5px;line-height:1.65;color:#2f363d;"
            f"background:{CODEBG};border-radius:6px;padding:14px 14px;margin:0 0 17px;"
            "white-space:pre-wrap;word-break:break-word;text-align:left;letter-spacing:0;"),
    "code": (f"font-family:{MONO};font-size:13px;color:#c7254e;background:#f5f5f5;"
             "padding:1px 5px;border-radius:3px;letter-spacing:0;"),
    "strong": f"font-weight:bold;color:{INK};",
    "em": "font-style:italic;",
    "a": f"color:{ACCENT};text-decoration:none;word-break:break-all;",
    "hr": f"border:none;border-top:1px solid {RULE};margin:26px 0;height:0;",
    "table": ("width:100%;border-collapse:collapse;margin:0 0 17px;"
              "font-size:14px;line-height:1.6;"),
    "th": (f"font-family:{FONT};border:1px solid {RULE};padding:8px 10px;"
           f"background:#f7f8f8;color:{INK};font-weight:bold;text-align:left;"),
    "td": (f"font-family:{FONT};border:1px solid {RULE};padding:8px 10px;"
           "text-align:left;"),
}

# --------------------------------------------------------------------------
# 3. Tiny DOM
# --------------------------------------------------------------------------


class El:
    __slots__ = ("tag", "attrs", "children")

    def __init__(self, tag, attrs=None):
        self.tag = tag
        self.attrs = attrs or {}
        self.children = []


class Txt:
    __slots__ = ("data",)

    def __init__(self, data):
        self.data = data


class Builder(HTMLParser):
    """Forgiving HTML -> tree. Unclosed tags are closed at EOF."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = El("root")
        self.stack = [self.root]

    def handle_starttag(self, tag, attrs):
        if tag in BLOCK_STARTERS:
            while len(self.stack) > 1 and self.stack[-1].tag in POP_ON_BLOCK:
                self.stack.pop()
        el = El(tag, {k.lower(): (v or "") for k, v in attrs})
        self.stack[-1].children.append(el)
        if tag not in VOID_TAGS:
            self.stack.append(el)

    def handle_startendtag(self, tag, attrs):
        self.stack[-1].children.append(El(tag, {k.lower(): (v or "") for k, v in attrs}))

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                return
        # stray close tag -> ignore

    def handle_data(self, data):
        self.stack[-1].children.append(Txt(data))


def sanitize(node):
    """Drop unwanted subtrees, unwrap transparent containers, strip attributes."""
    out = []
    for ch in node.children:
        if isinstance(ch, Txt):
            out.append(ch)
            continue
        tag = ch.tag
        if tag in DROP_TAGS:
            continue
        if tag in UNWRAP_TAGS:
            out.extend(sanitize(ch))
            continue
        keep = {k: v for k, v in ch.attrs.items() if k in KEEP_ATTRS.get(tag, set())}
        if keep.get("src", "").strip().lower().startswith("javascript:"):
            keep.pop("src", None)
        if keep.get("href", "").strip().lower().startswith("javascript:"):
            keep.pop("href", None)
        clean = El(tag, keep)
        clean.children = sanitize(ch)
        out.append(clean)
    return out


# --------------------------------------------------------------------------
# 4. Chinese typography repair
# --------------------------------------------------------------------------

CJK_RE = re.compile(r"[㐀-䶿一-鿿豈-﫿]")
URL_RE = re.compile(r"https?://[^\s<>　]+|[\w.+\-]+@[\w\-]+(?:\.[\w\-]+)+")

# Half-width -> full-width, applied only when a CJK character is adjacent.
PUNCT = {",": "，", "?": "？", "!": "！", ";": "；",
         ":": "：", "(": "（", ")": "）",
         "[": "【", "]": "】"}


def _is_cjk(ch):
    return bool(ch) and bool(CJK_RE.match(ch))


def fix_punctuation(s):
    out = []
    n = len(s)
    for i, ch in enumerate(s):
        prev = s[i - 1] if i else ""
        nxt = s[i + 1] if i + 1 < n else ""
        near_cjk = _is_cjk(prev) or _is_cjk(nxt)
        if ch == "." and (near_cjk and not (prev.isdigit() and nxt.isdigit())):
            out.append("。")
        elif ch in PUNCT and near_cjk:
            out.append(PUNCT[ch])
        else:
            out.append(ch)
    return "".join(out)


CJK_TO_LATIN = re.compile(r"([㐀-䶿一-鿿豈-﫿])([A-Za-z0-9])")
LATIN_TO_CJK = re.compile(r"([A-Za-z0-9])([㐀-䶿一-鿿豈-﫿])")


def pad_cjk_latin(s):
    """Insert the conventional thin gap between Chinese and Latin/digits.

    Only ideographs count as 'CJK' here -- full-width punctuation already carries
    its own side bearing, so padding next to it would look wrong.
    """
    s = CJK_TO_LATIN.sub(r"\1 \2", s)
    s = LATIN_TO_CJK.sub(r"\1 \2", s)
    return s


SMART_QUOTES = True


def smart_quotes(s, state):
    """Turn "..." into “...” inside CJK text. `state` is a 1-item list holding the
    open/close toggle, so a pair split across inline runs still pairs up."""
    if not SMART_QUOTES or '"' not in s:
        return s
    out = []
    for ch in s:
        if ch == '"':
            out.append("”" if state[0] else "“")
            state[0] = not state[0]
        else:
            out.append(ch)
    return "".join(out)


WS_MAP = {0x3000: " ", 0x00A0: " ", 0x2002: " ", 0x2003: " ", 0x2004: " ",
          0x2005: " ", 0x2006: " ", 0x2007: " ", 0x2008: " ", 0x2009: " ",
          0x200A: " ", 0x202F: " ", 0x205F: " ", 0x200B: "", 0xFEFF: ""}


def normalize_text(s, strip_leading=False, strip_trailing=False, quote_state=None):
    s = s.translate(WS_MAP)
    s = re.sub(r"[ \t\r\n]+", " ", s)
    if strip_leading:
        s = s.lstrip(" ")
    if strip_trailing:
        s = s.rstrip(" ")

    # Never mangle URLs / e-mail addresses that happen to sit inside prose.
    parts = URL_RE.split(s)
    urls = URL_RE.findall(s)
    fixed = []
    for idx, part in enumerate(parts):
        p = fix_punctuation(part)
        p = pad_cjk_latin(p)
        if quote_state is not None and CJK_RE.search(s):
            p = smart_quotes(p, quote_state)
        fixed.append(p)
        if idx < len(urls):
            fixed.append(urls[idx])
    return "".join(fixed)


# --------------------------------------------------------------------------
# 5. Rendering
# --------------------------------------------------------------------------


def esc(s):
    return html_mod.escape(s, quote=True)


def render_inline(children, quote_state=None):
    """Render phrasing content -> HTML string with inline styles."""
    if quote_state is None:
        quote_state = [False]
    out = []
    for i, ch in enumerate(children):
        if isinstance(ch, Txt):
            first = i == 0
            last = i == len(children) - 1
            out.append(esc(normalize_text(ch.data, first, last, quote_state)))
            continue
        t = ch.tag
        if t == "img":
            out.append(render_img(ch))
            continue
        if t == "br":
            out.append("<br>")
            continue
        if t not in INLINE_TAGS:
            # A stray block inside a phrasing context: render its contents flat.
            out.append(render_inline(ch.children, quote_state))
            continue
        if t in ("strong", "b"):
            out.append(f'<strong style="{S["strong"]}">'
                       + render_inline(ch.children, quote_state) + "</strong>")
        elif t in ("em", "i", "cite", "q", "var"):
            out.append(f'<em style="{S["em"]}">'
                       + render_inline(ch.children, quote_state) + "</em>")
        elif t == "u":
            out.append('<span style="text-decoration:underline;">'
                       + render_inline(ch.children, quote_state) + "</span>")
        elif t in ("s", "strike", "del"):
            out.append(f'<span style="text-decoration:line-through;color:{MUTED};">'
                       + render_inline(ch.children, quote_state) + "</span>")
        elif t == "ins":
            out.append('<span style="text-decoration:underline;">'
                       + render_inline(ch.children, quote_state) + "</span>")
        elif t == "small":
            out.append('<span style="font-size:13px;color:#666666;">'
                       + render_inline(ch.children, quote_state) + "</span>")
        elif t == "big":
            out.append('<span style="font-size:17px;">'
                       + render_inline(ch.children, quote_state) + "</span>")
        elif t == "code":
            out.append(f'<code style="{S["code"]}">'
                       + esc(raw_text(ch)) + "</code>")
        elif t == "a":
            href = (ch.attrs.get("href") or "").strip()
            body = render_inline(ch.children, quote_state) or esc(href)
            if href:
                out.append(f'<a href="{esc(href)}" style="{S["a"]}">{body}</a>')
            else:
                out.append(body)
        elif t in ("sub", "sup"):
            out.append(f'<{t} style="font-size:12px;line-height:0;">'
                       + render_inline(ch.children, quote_state) + f"</{t}>")
        elif t == "mark":
            out.append('<span style="background:#fff3a3;padding:0 2px;">'
                       + render_inline(ch.children, quote_state) + "</span>")
        else:
            out.append(render_inline(ch.children, quote_state))
    return "".join(out)


def raw_text(node):
    buf = []
    for ch in node.children:
        buf.append(ch.data if isinstance(ch, Txt) else raw_text(ch))
    return "".join(buf)


def render_img(el):
    src = (el.attrs.get("src") or "").strip()
    alt = (el.attrs.get("alt") or "").strip()
    if not src:
        return esc(alt)
    return (f'<img src="{esc(src)}" alt="{esc(alt)}" style="{S["img"]}">')


def is_image_only(el):
    """A <p> whose only real content is an image should behave like a figure."""
    kids = [c for c in el.children
            if not (isinstance(c, Txt) and not c.data.strip())]
    return len(kids) == 1 and isinstance(kids[0], El) and kids[0].tag == "img"


def blockify(node):
    """Flatten the tree into an ordered list of block-level nodes.

    Anything phrasing that sits loose at block level is grouped into a synthetic
    <p>, which is what happens to naked text and bare <strong>/<a> runs.
    """
    blocks = []
    pending = []

    def flush():
        if pending:
            p = El("p")
            p.children = list(pending)
            blocks.append(p)
            del pending[:]

    for ch in node.children:
        if isinstance(ch, Txt):
            if ch.data.strip():
                pending.append(ch)
            continue
        if ch.tag in BLOCK_TAGS or ch.tag == "li":
            flush()
            blocks.append(ch)
        else:
            pending.append(ch)
    flush()
    return blocks


def heading_tag(level):
    """WeChat renders headings but the editor's UI only surfaces two levels.
    h1 is reserved for the document title, so h2 -> level 1 and h3-h6 -> level 2."""
    if level <= 1:
        return "title"
    if level == 2:
        return "h2"
    return "h3"


def render_block(el, quote_state):
    t = el.tag

    if t in ("h1", "h2", "h3", "h4", "h5", "h6"):
        kind = heading_tag(int(t[1]))
        body = render_inline(el.children, quote_state)
        if not body.strip():
            return ""
        if kind == "title":
            return f'<h1 style="{S["title"]}">{body}</h1>'
        if kind == "h2":
            return f'<h2 style="{S["h2"]}">{body}</h2>'
        return (f'<h3 style="{S["h3"]}"><span style="{S["h3dot"]}"></span>{body}</h3>')

    if t == "p":
        if is_image_only(el):
            return render_block(el.children[0], quote_state)
        body = render_inline(el.children, quote_state)
        if not body.strip():
            return ""
        return f'<p style="{S["p"]}">{body}</p>'

    if t == "img":
        # A dead <img> must not leave an invisible line-height:0 box behind --
        # fall back to a plain paragraph so the reader still sees something.
        if not (el.attrs.get("src") or "").strip():
            alt = (el.attrs.get("alt") or "").strip()
            if not alt:
                return ""
            return f'<p style="{S["p"]}">{esc(alt)}</p>'
        return f'<p style="{S["imgwrap"]}">{render_img(el)}</p>'

    if t == "hr":
        return f'<hr style="{S["hr"]}">'

    if t in ("ul", "ol"):
        items = []
        for li in collect_items(el):
            body = render_inline(li.children, quote_state)
            if body.strip():
                items.append(f'<li style="{S["li"]}">{body}</li>')
        if not items:
            return ""
        return f'<{t} style="{S["ul"]}">' + "".join(items) + f"</{t}>"

    if t == "blockquote":
        parts = [x for x in (render_block(b, quote_state) for b in blockify(el)) if x]
        if not parts:
            return ""
        # Drop the trailing gap on the last block so the box padding is even.
        parts[-1] = parts[-1].replace(f'style="{S["p"]}"', f'style="{S["p_tight"]}"')
        return f'<blockquote style="{S["quote"]}">' + "".join(parts) + "</blockquote>"

    if t == "pre":
        return f'<pre style="{S["pre"]}">{esc(raw_text(el))}</pre>'

    if t == "table":
        return render_table(el, quote_state)

    if t in ("figure", "figcaption"):
        inner = "".join(x for x in (render_block(b, quote_state) for b in blockify(el)) if x)
        return inner

    # Fallback: treat as a paragraph.
    body = render_inline(el.children, quote_state)
    if not body.strip():
        return ""
    return f'<p style="{S["p"]}">{body}</p>'


def render_table(el, quote_state):
    rows = []

    def walk(node):
        for ch in node.children:
            if isinstance(ch, El) and ch.tag in ("tr",):
                cells = []
                for cell in ch.children:
                    if isinstance(cell, El) and cell.tag in ("td", "th"):
                        cells.append(cell)
                if cells:
                    rows.append(cells)
            elif isinstance(ch, El):
                walk(ch)

    walk(el)
    if not rows:
        return ""
    html = [f'<table style="{S["table"]}">']
    for r in rows:
        html.append("<tr>")
        for cell in r:
            style = S["th"] if cell.tag == "th" else S["td"]
            span = ""
            if cell.attrs.get("colspan", "1") not in ("", "1"):
                span += f' colspan="{esc(cell.attrs["colspan"])}"'
            if cell.attrs.get("rowspan", "1") not in ("", "1"):
                span += f' rowspan="{esc(cell.attrs["rowspan"])}"'
            body = render_inline(cell.children, quote_state)
            html.append(f'<{cell.tag} style="{style}"{span}>{body}</{cell.tag}>')
        html.append("</tr>")
    html.append("</table>")
    return "".join(html)


def collect_items(lst):
    items = []
    for ch in lst.children:
        if isinstance(ch, El):
            if ch.tag == "li":
                items.append(ch)
            else:
                items.extend(collect_items(ch))
    return items


# --------------------------------------------------------------------------
# 6. Document assembly
# --------------------------------------------------------------------------


def extract_body_html(source):
    """A .md/.html file that is really an HTML fragment: find the body content.

    If the file is a full document, the parser's unwrap pass has already dealt
    with <html>/<body>, so we just walk the root in document order.
    """
    parser = Builder()
    parser.feed(source)
    parser.close()
    return sanitize(parser.root)


def convert(source, title_hint=None):
    nodes = extract_body_html(source)
    root = El("root")
    root.children = nodes
    blocks = blockify(root)
    parts = []
    for b in blocks:
        html = render_block(b, [False])
        if html:
            parts.append(html)
    body = "\n".join(parts)
    return f'<section style="{S["container"]}">\n{body}\n</section>\n'


def preview_document(fragment, title):
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)}</title>
<style>
  html,body{{margin:0;padding:0;background:#e9ebee;}}
  .phone{{max-width:677px;margin:0 auto;background:#fff;padding:28px 18px 60px;
          box-shadow:0 0 0 1px rgba(0,0,0,.05);}}
  @media (max-width:700px){{.phone{{padding:20px 14px 40px;}}}}
</style>
</head>
<body>
<!--
  Preview page. The block below is the whole article.
  Select from here --><div class="phone">
{fragment}</div><!--
  <- to here, copy, and paste into the mp.weixin.qq.com editor.
  Only the inline styles travel with the paste; this page's own CSS does not.
-->
</body>
</html>
"""


def guess_title(source):
    m = re.search(r"<h1[^>]*>(.*?)</h1>", source, re.I | re.S)
    if m:
        t = re.sub(r"<[^>]+>", "", m.group(1))
        t = re.sub(r"\s+", " ", t).strip()
        if t:
            return t
    return "未命名文章"


def main(argv):
    if len(argv) < 3:
        sys.stderr.write(__doc__)
        return 2
    in_path, out_path = argv[1], argv[2]
    preview_path = argv[3] if len(argv) > 3 else None

    with open(in_path, "r", encoding="utf-8") as f:
        source = f.read()

    fragment = convert(source)
    with open(out_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(fragment)

    if preview_path:
        with open(preview_path, "w", encoding="utf-8", newline="\n") as f:
            f.write(preview_document(fragment, guess_title(source)))

    sys.stderr.write(f"wrote {out_path}"
                     + (f" and {preview_path}" if preview_path else "") + "\n")
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass
    sys.exit(main(sys.argv))
