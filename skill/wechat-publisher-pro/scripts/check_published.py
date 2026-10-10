#!/usr/bin/env python3
"""
Fetch a published WeChat article and check that what went live is the *rendered*
article, not the Markdown source.

This exists because of a real failure: the source `.md` was copied into the
editor instead of the preview `.html`, and the published post showed raw YAML
front matter and literal `##` headings. Nothing earlier in the pipeline could
catch that -- the mistake happens between the clipboard and WeChat -- so the only
reliable place to notice it is the published page itself.

    python check_published.py <url>
    python check_published.py <url> --expect-title "公众号排版这件小事，我用一条命令解决了"

Exit code: 0 clean, 1 the article is broken (raw Markdown or wrong title),
2 the page could not be fetched or parsed.

Two false positives this script deliberately avoids, both learned the hard way:

* Text inside a code-styled span is *documentation*, not a failed transform. An
  article explaining "write `> [!NOTE]` to make a box" contains `[!NOTE]` on
  purpose. Such spans are dropped before scanning. A raw-Markdown paste has no
  monospace styling at all, so nothing real can hide behind this.
* WeChat puts its own chrome (toolbars, QR footer, ad slots) in the page; the
  scan is limited to the `js_content` body region.
"""

from __future__ import annotations

import argparse
import re
import sys
import urllib.request

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

# Signals that the pasted text was Markdown rather than HTML.
MD_MARKERS = {
    "YAML front matter (`---` + `title:`)": re.compile(r"-{3}\s*title:"),
    "fenced code block (```)": re.compile(r"```"),
    "ATX heading at line start (##)": re.compile(r"(?:^|\n)#{1,6}\s+\S"),
    "bold markers (**...**)": re.compile(r"\*\*[^*\n]{1,40}\*\*"),
    "literal alert marker ([!NOTE])": re.compile(r"\[!\w+\]"),
    "table pipe row (| a | b |)": re.compile(r"^\s*\|.{3,}\|\s*$", re.M),
}

# Signals the converter's output survived the round trip.
RENDERED_SIGNALS = {
    "inline-styled elements": re.compile(r'style="[^"]{10,}"'),
    "table (callout / TOC / code box)": re.compile(r"<table"),
    "monospace code block": re.compile(r"font-family:\s*Consolas"),
    "image on the WeChat CDN": re.compile(r"mmbiz\.qpic\.cn|mmbiz\.qlogo\.cn"),
}

# Code-styled spans carry syntax examples on purpose and must not be read as
# leftover Markdown.
_CODE_SPAN_RE = re.compile(r"(?is)<span[^>]*monospace[^>]*>.*?</span>")


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=45) as resp:
        raw = resp.read()
    for enc in ("utf-8", "gb18030"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def article_body(html: str) -> str:
    """Slice out the `js_content` region where WeChat puts the post body."""
    start = html.find('id="js_content"')
    if start < 0:
        return ""
    end = len(html)
    for marker in ('id="js_article_bottom"', 'class="rich_media_tool',
                   'id="js_pc_qr_code"', "赞赏作者"):
        pos = html.find(marker, start)
        if pos > 0:
            end = min(end, pos)
    if end == len(html):
        end = min(len(html), start + 400_000)
    return html[start:end]


def strip_tags(html: str) -> str:
    html = _CODE_SPAN_RE.sub(" ", html)          # syntax examples, not failures
    text = re.sub(r"(?is)<(script|style).*?</\1>", " ", html)
    text = re.sub(r"<[^>]+>", "", text)
    for entity, char in (("&nbsp;", " "), ("&amp;", "&"), ("&lt;", "<"),
                         ("&gt;", ">"), ("&quot;", '"'), ("&#39;", "'")):
        text = text.replace(entity, char)
    return re.sub(r"[ \t]+", " ", text).strip()


def check(url: str, expect_title: str | None = None) -> int:
    print("抓取：%s\n" % url[:110])
    try:
        html = fetch(url)
    except Exception as exc:
        print("❌ 抓取失败：%s" % exc)
        return 2

    print("页面 %d 字节" % len(html))

    title_match = re.search(r'var msg_title = ["\'](.*?)["\']', html) or \
        re.search(r'<meta property="og:title" content="(.*?)"', html)
    title = title_match.group(1).strip() if title_match else ""
    print("标题   ：%s" % (title or "(未找到)"))

    body = article_body(html)
    if not body:
        print("❌ 没找到正文区（id=\"js_content\"）——链接可能失效或页面结构变了")
        return 2
    text = strip_tags(body)
    print("正文约 %d 字\n" % len(text))

    print("── 是否贴成了 Markdown 源码？ ──")
    md_hits = []
    for label, pattern in MD_MARKERS.items():
        n = len(pattern.findall(text))
        if n:
            md_hits.append(label)
            print("  ⚠️  %-38s %d 处" % (label, n))
    if not md_hits:
        print("  ✅ 没有发现 Markdown 记号")

    print("\n── 排版是否活着？ ──")
    render_counts = {}
    for label, pattern in RENDERED_SIGNALS.items():
        n = len(pattern.findall(body))
        render_counts[label] = n
        print("  %s %-38s %d" % ("✅" if n else "⚠️ ", label, n))

    print("\n── 图片 ──")
    leftover = len(re.findall(r'src="data:', body))
    cdn = len(re.findall(r"mmbiz\.qpic\.cn", body))
    print("  data: URI 残留（公众号没转存成功）：%d" % leftover)
    print("  CDN 图片（正常）：%d" % cdn)

    title_ok = True
    if expect_title:
        print("\n── 标题 ──")
        title_ok = title.strip() == expect_title.strip()
        print("  %s 线上标题：%s" % ("✅" if title_ok else "⚠️ ", title))
        if not title_ok:
            print("     期望标题：%s" % expect_title)

    raw_markdown = any(h.startswith(("YAML", "fenced", "ATX", "bold"))
                       for h in md_hits)
    has_structure = render_counts["table (callout / TOC / code box)"] > 0

    print("\n════ 结论 ════")
    if raw_markdown:
        print("❌ 正文是 Markdown 源码，不是渲染后的 HTML。")
        print("   原因：粘贴时复制的是源文件（.md），不是预览页（.html）。")
        print("   修法：浏览器打开 *_output.html，在**那一页** Ctrl+A → Ctrl+C，")
        print("         再粘贴；然后删除这篇重发。")
        return 1
    if not title_ok:
        print("⚠️  正文排版正确，但标题栏内容不对。")
        print("   标题是后台单独填的，不在正文里。改成期望值即可，不必重发正文。")
        return 1
    if not has_structure:
        print("⚠️  看不到表格结构：提示框 / 目录 / 代码框可能没粘过来。")
        print("   如果原文本就没有 callout、目录和代码块，这一条可以忽略。")
        return 0
    print("✅ 正文是渲染后的 HTML，排版元素在位。")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="核验已发布的公众号文章是渲染后的 HTML 还是 Markdown 源码。")
    parser.add_argument("url", help="已发布的文章链接")
    parser.add_argument("--expect-title", dest="expect_title",
                        help="期望的标题；不一致时以非零退出码报告")
    args = parser.parse_args(argv)
    return check(args.url, args.expect_title)


if __name__ == "__main__":
    raise SystemExit(main())
