"""
Deterministic conformance checks for WeChat-ready HTML.

This module exists because "it looked fine in the browser" is not evidence.  A
page can render perfectly and still be destroyed by WeChat's editor on paste --
the failures are silent (a script tag vanishes, a class-based style never
applies, an SVG image disappears at save time).  Every rule below corresponds to
a documented behaviour of the WeChat editor, and each check returns the actual
offending element so the author can fix it rather than guess.

Usage::

    python wechat_validate.py output.html
    python wechat_validate.py output.html --json
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

from bs4 import BeautifulSoup, Comment

from render import (ALLOWED_CSS_PROPS, ALLOWED_TAGS, DROP_TAGS,
                    FORBIDDEN_CSS_PROPS, MAX_ARTICLE_CHARS)

# Tags that must never reach the editor, even though a "div" is only converted
# rather than removed upstream -- if one survives, a transform silently failed.
HARD_FORBIDDEN = {
    "script", "style", "iframe", "h1", "div", "svg", "video", "audio",
    "pre", "code", "blockquote", "form", "input", "button", "object", "embed",
}

# Elements that must carry their own style: WeChat has no stylesheet, so an
# unstyled block falls back to the editor's defaults and breaks the visual
# rhythm the theme set up.
MUST_HAVE_STYLE = ("p", "h2", "h3", "ul", "ol", "li", "table", "th", "td")
INLINE_MARKUP = ("strong", "em", "i", "b", "u", "del", "s", "small", "mark")


@dataclass
class Check:
    id: str
    description: str
    passed: bool
    evidence: str = ""
    severity: str = "error"          # error | warning

    def to_dict(self) -> dict:
        return asdict(self)


def _sample(items, limit: int = 3) -> str:
    """Render up to *limit* offending elements so a report stays readable."""
    out = []
    for item in items[:limit]:
        text = re.sub(r"\s+", " ", str(item))[:110]
        out.append(text)
    if len(items) > limit:
        out.append("… 共 %d 处" % len(items))
    return " | ".join(out)


def validate_fragment(html: str) -> list[Check]:
    """Run every conformance check against a paste-ready HTML fragment."""
def _to_article_body(html: str) -> BeautifulSoup:
    """Return just the article body, whether given a fragment or a preview page.

    Three independent testers each ran the documented command
    ``wechat_validate.py out.html`` against the preview file the converter had
    just produced, and got a non-zero exit -- because the preview page carries a
    ``<head>``, two ``<meta>`` tags, a ``<title>`` and an ``<article>`` wrapper.
    Those are scaffolding, not article content, and reporting them as violations
    makes a correct conversion look broken.

    So the validator accepts either input form. ``article`` is unwrapped because
    the renderer never emits one -- a stray ``<article>`` in the pasted content
    would itself be a violation.
    """
    # html.parser, not lxml: lxml silently wraps every fragment in <html><body>,
    # so those synthetic wrappers would be reported as non-whitelisted tags.
    soup = BeautifulSoup(html, "html.parser")
    for node in soup.find_all(string=lambda s: isinstance(s, Comment)):
        node.extract()
    # <head> and its contents are page furniture with no article meaning, so they
    # are dropped outright.  Unwrapping would keep <meta> and <title> in the tree,
    # which is exactly the false failure this function exists to prevent.
    for node in soup.find_all(["head", "meta", "title", "link"]):
        node.decompose()
    # These wrappers are transparent: the content inside them *is* the article.
    for wrapper in soup.find_all(["html", "body", "article"]):
        wrapper.unwrap()
    return soup


def validate_fragment(html: str) -> list[Check]:
    """Run every conformance check against a paste-ready HTML fragment.

    Also accepts a full preview page; the page furniture is stripped first.
    """
    checks: list[Check] = []
    soup = _to_article_body(html)

    # 1 -- tags WeChat removes outright --------------------------------
    offenders = [el for el in soup.find_all(True) if el.name in HARD_FORBIDDEN]
    checks.append(Check(
        "no_forbidden_tags",
        "不含公众号禁止或会破坏排版的标签（script/style/iframe/h1/div/pre/code/svg…）",
        not offenders,
        _sample(offenders),
    ))

    # 2 -- anything outside the allowed tag list ------------------------
    extras = [el for el in soup.find_all(True) if el.name not in ALLOWED_TAGS]
    checks.append(Check(
        "allowed_tags_only",
        "只使用公众号白名单标签（p/h2/h3/ul/ol/li/span/img/a/table/tr/th/td/br）",
        not extras,
        _sample(extras),
    ))

    # 3 -- class / id -----------------------------------------------------
    offenders = [el for el in soup.find_all(True)
                 if el.has_attr("class") or el.has_attr("id")]
    checks.append(Check(
        "no_class_or_id",
        "没有 class / id 属性（公众号没有样式表，class 会被整体丢弃）",
        not offenders,
        _sample(offenders),
    ))

    # 4 -- inline event handlers -----------------------------------------
    offenders = [el for el in soup.find_all(True)
                 if any(a.startswith("on") for a in el.attrs)]
    checks.append(Check(
        "no_event_handlers",
        "没有 onclick 等内联事件（公众号会移除全部 JavaScript）",
        not offenders,
        _sample(offenders),
    ))

    # 5 -- every block carries an inline style ---------------------------
    offenders = [el for el in soup.find_all(MUST_HAVE_STYLE)
                 if not str(el.get("style", "")).strip()]
    checks.append(Check(
        "inline_styles_present",
        "所有块级元素都带 inline style（公众号只认 style 属性）",
        not offenders,
        _sample(offenders),
    ))

    # 6 -- no leftover semantic markup --------------------------------
    offenders = soup.find_all(list(INLINE_MARKUP))
    checks.append(Check(
        "no_semantic_inline_tags",
        "strong/em 等语义标签已转为带样式的 span",
        not offenders,
        _sample(offenders),
    ))

    # 7 -- CSS properties WeChat strips ---------------------------------
    offenders = []
    for el in soup.find_all(True):
        style = str(el.get("style", ""))
        for part in style.split(";"):
            if ":" not in part:
                continue
            prop = part.split(":", 1)[0].strip().lower()
            if prop in FORBIDDEN_CSS_PROPS or (prop and prop not in ALLOWED_CSS_PROPS):
                offenders.append("%s{%s}" % (el.name, prop))
    checks.append(Check(
        "css_props_supported",
        "样式只使用公众号支持的属性（无 position/float/flex/动画/阴影）",
        not offenders,
        _sample(offenders),
    ))

    # 8 -- images survive the round trip ---------------------------------
    bad_images = []
    for img in soup.find_all("img"):
        src = str(img.get("src", ""))
        if src.startswith("data:image/svg") or src.lower().endswith(".svg"):
            bad_images.append("SVG: %s" % src[:40])
        elif not src:
            bad_images.append("empty src")
        elif src.startswith(("http://", "https://")):
            bad_images.append("remote: %s" % src[:40])
    checks.append(Check(
        "images_embedded_or_remote_flagged",
        "图片为 data: URI（可自动进入公众号图库），无 SVG、无空地址",
        not bad_images,
        _sample(bad_images),
        severity="warning",
    ))

    # 9 -- no <p> inside <p>, no orphan cells ----------------------------
    nesting = [p for p in soup.find_all("p") if p.find("p", recursive=False)]
    orphan_cells = [el for el in soup.find_all(["td", "th"])
                    if el.find_parent("table") is None]
    checks.append(Check(
        "well_formed_structure",
        "结构合法：没有 p 嵌套 p，单元格都在 table 内",
        not nesting and not orphan_cells,
        _sample(nesting + orphan_cells),
    ))

    # 10 -- tables have rows with cells -----------------------------------
    broken = []
    for table in soup.find_all("table"):
        if table.find("tr") is None:
            broken.append(table)
        elif not table.find(["td", "th"]):
            broken.append(table)
    checks.append(Check(
        "tables_have_cells",
        "每个表格都有 tr 与单元格（避免粘贴后变成空白块）",
        not broken,
        _sample(broken),
    ))

    # 11 -- images must not overflow the phone column ----------------------
    unsized = [img for img in soup.find_all("img")
               if "max-width" not in str(img.get("style", ""))]
    checks.append(Check(
        "images_bounded",
        "图片带 max-width，避免超出手机宽度被裁切",
        not unsized,
        _sample(unsized),
        severity="warning",
    ))

    # 12 -- there is actually content ------------------------------------
    text = soup.get_text().strip()
    checks.append(Check(
        "has_content",
        "输出包含正文内容（非空）",
        len(text) > 20,
        "%d 个字符" % len(text),
    ))

    # 13 -- length limit ---------------------------------------------------
    checks.append(Check(
        "within_length_limit",
        "正文长度在公众号单篇上限内（约 %d 字）" % MAX_ARTICLE_CHARS,
        len(text) <= MAX_ARTICLE_CHARS,
        "%d 字" % len(text),
        severity="warning",
    ))

    # 14 -- no stray Markdown artifacts -----------------------------------
    leftovers = _find_markdown_leftovers(soup)
    checks.append(Check(
        "no_markdown_leftovers",
        "没有未被转换的 Markdown 记号（**、[]()、行首 #、行首 [!NOTE]）",
        not leftovers,
        _sample(leftovers),
    ))

    return checks


def _prose_without_code(el: Tag) -> str:
    """Text of *el* with inline-code spans removed.

    An article that *documents* this pipeline legitimately contains strings like
    ``[!TIP]`` or ``**`` inside code spans.  Testing the raw text would flag
    correct output as broken, so code-styled descendants are excluded first.
    """
    clone = BeautifulSoup(str(el), "html.parser")
    for span in clone.find_all("span"):
        if "monospace" in str(span.get("style", "")):
            span.decompose()
    return clone.get_text()


def _find_markdown_leftovers(soup: BeautifulSoup) -> list[str]:
    """Locate constructs that only survive if a transform silently failed.

    Checked structurally rather than with one big regex, because the *position*
    of the marker is what distinguishes a bug from legitimate prose: an
    unconverted alert always sits at the very start of a paragraph, whereas a
    documented `[!NOTE]` sits mid-sentence inside a code span.
    """
    leftovers: list[str] = []
    for el in soup.find_all(["p", "h2", "h3", "li", "td"]):
        if "monospace" in str(el.get("style", "")):
            continue
        text = _prose_without_code(el).strip()
        if not text:
            continue
        if re.match(r"\[!\w+\]", text):
            leftovers.append("未转换的提示框：%s" % text[:60])
        elif re.search(r"\*\*|^#{1,6}\s+\S|!\[|\]\([^)]*\)", text):
            leftovers.append(text[:60])
    return leftovers


def summarize(checks: list[Check]) -> dict:
    failed = [c for c in checks if not c.passed and c.severity == "error"]
    warned = [c for c in checks if not c.passed and c.severity == "warning"]
    return {
        "total": len(checks),
        "passed": sum(1 for c in checks if c.passed),
        "failed": len(failed),
        "warnings": len(warned),
        "ok": not failed,
        "failed_ids": [c.id for c in failed],
        "warning_ids": [c.id for c in warned],
    }


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    as_json = "--json" in argv
    paths = [a for a in argv if not a.startswith("-")]
    if not paths:
        print(__doc__)
        print("Usage: python wechat_validate.py <output.html|fragment.html> [--json]")
        print("\n两种输入都可以：转换器输出的预览页（out.html），或 --fragment 生成的"
              "纯片段（out.fragment.html）。预览外壳会在校验前被剥离。")
        return 1

    exit_code = 0
    for path in paths:
        html = Path(path).read_text(encoding="utf-8")
        checks = validate_fragment(html)
        summary = summarize(checks)
        if as_json:
            print(json.dumps({"file": path, "summary": summary,
                              "checks": [c.to_dict() for c in checks]},
                             ensure_ascii=False, indent=2))
        else:
            print("\n=== %s ===" % path)
            for check in checks:
                mark = "PASS" if check.passed else (
                    "FAIL" if check.severity == "error" else "WARN")
                print("[%s] %s — %s" % (mark, check.id, check.description))
                if not check.passed and check.evidence:
                    print("       %s" % check.evidence)
            print("\n%d/%d 通过，%d 项错误，%d 项警告"
                  % (summary["passed"], summary["total"],
                     summary["failed"], summary["warnings"]))
        if not summary["ok"]:
            exit_code = 1
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
