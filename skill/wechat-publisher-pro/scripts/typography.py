"""
Chinese typography + pre-markdown tokenisation.

Two responsibilities:

1. **Tokenising** (``protect_source``) -- before Markdown is parsed we replace
   inline code and LaTeX formulas with opaque placeholders.  Without this,
   ``$a_1$`` loses its underscore to Markdown emphasis and a code span like
   ``a*b*c`` turns into italics.  The placeholders use Private Use Area
   characters, which no Markdown syntax can consume.

2. **Chinese typography** -- inserting a hair of space between CJK and Latin
   glyphs, normalising Chinese punctuation, and collapsing the double blank
   lines that Word exports are notorious for.
"""

from __future__ import annotations

import re

# Private Use Area sentinels.  Chosen because they survive Markdown parsing,
# URL-encoding, and BeautifulSoup unchanged, yet never occur in real prose.
_OPEN = ""
_CLOSE = ""

# --------------------------------------------------------------------------
# Character classes
# --------------------------------------------------------------------------
# Built from explicit escapes rather than literal glyphs: literal CJK ranges
# are invisible in diffs and silently corrupt if the file is ever re-saved in a
# non-UTF-8 encoding.
CJK = (
    "⺀-⿿"   # CJK radicals supplement
    "　-〿"   # CJK symbols and punctuation (incl. ideographic space)
    "぀-ヿ"   # hiragana + katakana
    "㄰-㆏"   # hangul compatibility jamo
    "㇀-㇯"   # CJK strokes
    "㐀-䶿"   # CJK unified ideographs extension A
    "一-鿿"   # CJK unified ideographs
    "豈-﫿"   # CJK compatibility ideographs
    "︰-﹏"   # CJK compatibility forms
    "＀-￯"   # half/full-width forms
)

# Ideographs, kana and hangul -- CJK *word* characters, as opposed to CJK
# punctuation and full-width forms.  The distinction matters for spacing: a
# full-width comma or colon already carries its own trailing space, so inserting
# another one produced "地址： https://…".  Only word characters take a space.
HAN = (
    "぀-ヿ"   # hiragana + katakana
    "㄰-㆏"   # hangul compatibility jamo
    "㐀-䶿"   # CJK unified ideographs extension A
    "一-鿿"   # CJK unified ideographs
    "豈-﫿"   # CJK compatibility ideographs
)

_CJK_RE = re.compile("[" + CJK + "]")

# Latin/digit adjacent to a CJK word character, in either order.  We never touch
# a boundary that already has whitespace on it, because the substitutes below
# require the two characters to be directly adjacent.
_CJK_LATIN_BOUNDARY = re.compile("([" + HAN + "])([A-Za-z0-9@#$%&+=<>~|^\\\\])")
_LATIN_CJK_BOUNDARY = re.compile("([A-Za-z0-9%)\\]}>])([" + HAN + "])")

# Sentence punctuation in half-width form, only converted when it sits *between*
# CJK characters (never inside `1,000` or `foo::bar`).
_HALF_TO_FULL = {",": "，", ";": "；", ":": "：",
                 "!": "！", "?": "？"}


def _is_cjk(ch: str) -> bool:
    return bool(ch) and bool(_CJK_RE.match(ch))


# --------------------------------------------------------------------------
# Tokenisation
# --------------------------------------------------------------------------
def protect_source(text: str):
    """Mask inline code and math so Markdown cannot mangle them.

    Returns ``(masked_text, math_spans, inline_code_spans)``.

    Fenced code blocks are passed through verbatim: ``fenced_code`` already
    handles them correctly, and skipping them here keeps formulas inside a code
    sample from being rendered as pictures.

    Block math (``$$...$$``) may span blank lines, so it is scanned to the
    matching ``$$`` regardless of what lies in between.
    """
    math_spans: list[str] = []
    code_spans: list[str] = []

    out: list[str] = []
    i = 0
    n = len(text)
    in_fence = False
    fence_marker = ""
    fence_ticks = 3

    _inline_math = re.compile(r"\$(?!\s)([^$\n]{1,400}?)\$")

    while i < n:
        # --- fenced code: pass through verbatim --------------------------
        if not in_fence and text.startswith(("```", "~~~"), i):
            marker = text[i:i + 3]
            fence_marker = marker
            fence_ticks = len(re.match(re.escape(marker[0]) + r"{3,}", text[i:]).group(0))
            in_fence = True
            out.append(text[i:i + fence_ticks])
            i += fence_ticks
            continue
        if in_fence:
            if text.startswith(fence_marker, i):
                out.append(text[i:i + fence_ticks])
                i += fence_ticks
                in_fence = False
                continue
            out.append(text[i])
            i += 1
            continue

        # --- block math ---------------------------------------------------
        if text.startswith("$$", i):
            end = text.find("$$", i + 2)
            if end != -1:
                math_spans.append(text[i + 2:end].strip())
                out.append("%sMATH%d%s" % (_OPEN, len(math_spans) - 1, _CLOSE))
                i = end + 2
                continue

        # --- inline math --------------------------------------------------
        if text[i] == "$":
            m = _inline_math.match(text, i)
            if m and not m.group(1)[:1].isdigit():
                math_spans.append(m.group(1).strip())
                out.append("%sMATH%d%s" % (_OPEN, len(math_spans) - 1, _CLOSE))
                i = m.end()
                continue

        # --- inline code ---------------------------------------------------
        if text[i] == "`":
            ticks = len(re.match(r"`+", text[i:]).group(0))
            close = text.find("`" * ticks, i + ticks)
            if close != -1:
                code_spans.append(text[i + ticks:close])
                out.append("%sCODE%d%s" % (_OPEN, len(code_spans) - 1, _CLOSE))
                i = close + ticks
                continue

        out.append(text[i])
        i += 1

    return "".join(out), math_spans, code_spans


_TOKEN_RE = re.compile(_OPEN + r"(MATH|CODE)(\d+)" + _CLOSE)

# Public alias: the render pipeline needs to test for placeholders too.
TOKEN_RE = _TOKEN_RE


def iter_tokens(text: str):
    """Yield ``(kind, index, start, end)`` for every placeholder in *text*."""
    for m in _TOKEN_RE.finditer(text):
        yield m.group(1), int(m.group(2)), m.start(), m.end()


# --------------------------------------------------------------------------
# Chinese typography
# --------------------------------------------------------------------------
def add_cjk_spacing(text: str) -> str:
    """Insert a space between CJK and Latin/digit runs.

    ``用Python写代码`` becomes ``用 Python 写代码``.  This is the single
    highest-leverage Chinese typography fix: without it, mixed-script text
    reads as one solid block on a phone screen.
    """
    if not text:
        return text
    text = _CJK_LATIN_BOUNDARY.sub(r"\1 \2", text)
    text = _LATIN_CJK_BOUNDARY.sub(r"\1 \2", text)
    return text


def normalize_punctuation(text: str, level: str = "safe") -> str:
    """Normalise punctuation.  ``level`` is ``safe``, ``aggressive`` or ``off``.

    The split between the two levels is about *how the rule can fail*, not about
    how common the pattern is:

    * ``safe`` (the default) handles everything where a half-width mark sitting
      next to Chinese characters is unambiguous.  A comma between two Chinese
      characters is never correct in Chinese prose, and ``1,000`` or ``a,b,c``
      are protected because their neighbours are Latin or digits, not CJK.
      Skipping these rules by default was a real defect: an article pasted out of
      Word kept its half-width commas and question marks, and the user reasonably
      concluded the converter had not done its job.
    * ``aggressive`` adds the rules that can be wrong in specialised text --
      half-width parentheses around Chinese content, which may be a deliberate
      citation of code or a formula rather than sloppy typing.
    """
    if level == "off":
        return text

    text = text.replace("...", "……").replace("。。。", "……")
    text = text.replace("?!", "？！").replace("!?", "！？")
    # An ideographic space at the start of a line is a Word-export artifact.
    text = re.sub("(?m)^[　]+", "", text)
    text = re.sub("[ \t]{2,}", " ", text)

    # Half-width sentence punctuation directly between two Chinese characters.
    text = re.sub(
        "([%s])([,;:!?])([%s])" % (HAN, HAN),
        lambda m: m.group(1) + _HALF_TO_FULL[m.group(2)] + m.group(3),
        text,
    )
    # ...or right after a Chinese character, ending a clause.
    text = re.sub(
        "([%s])([,;:!?])(\\s|$)" % HAN,
        lambda m: m.group(1) + _HALF_TO_FULL[m.group(2)] + m.group(3),
        text,
    )
    # A space after a full-width mark is a leftover from mixed typing; the mark
    # already occupies a full em, so the extra gap reads as a typo.
    text = re.sub("([，。、；：！？）】》」』])\\s+", r"\1", text)

    if level == "aggressive":
        text = re.sub(
            "([%s])\\(([^()]*[%s][^()]*)\\)" % (HAN, HAN),
            lambda m: m.group(1) + "（" + m.group(2) + "）",
            text,
        )
    return text


def collapse_blank_lines(text: str) -> str:
    """Collapse 3+ newlines to 2 -- keeps the author's paragraph breaks only."""
    return re.sub(r"\n{3,}", "\n\n", text)


def tidy(text: str, cjk_spacing: bool = True, punct: str = "safe") -> str:
    """Apply the typography pass to a block of *prose*.

    Callers must not pass code, formulas, or raw HTML through this.
    """
    text = collapse_blank_lines(text)
    text = normalize_punctuation(text, level=punct)
    if cjk_spacing:
        text = add_cjk_spacing(text)
    return text


# --------------------------------------------------------------------------
# Alt-text heuristics
# --------------------------------------------------------------------------
_URL_RE = re.compile(r"^(https?://|mailto:|/|\./|\.\./|#)")


def looks_like_filename(text: str) -> bool:
    """Is this alt text a filename rather than a caption?

    Authors write ``![cover.png](cover.png)`` far more often than they write
    real captions, so rendering every alt as a caption would litter the article
    with filenames.
    """
    if not text:
        return True
    if _URL_RE.match(text):
        return True
    if len(text) > 60:
        return True
    if re.search(r"\.(png|jpe?g|gif|webp|svg|bmp|tiff?)$", text, re.I):
        return True
    if re.search(r"[/\\]", text):
        return True
    # Pure ASCII with no spaces reads like a slug, not a sentence.
    if not _CJK_RE.search(text) and " " not in text:
        return True
    return False
