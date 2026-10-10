#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
convert.py -- Markdown -> 微信公众号富文本 HTML 转换器

用法:
    PYTHONIOENCODING=utf-8 python convert.py <input.md> [-o output.html]

设计目标 (微信公众号编辑器 / mp.weixin.qq.com):
    1. 全部样式写成 inline style —— 微信编辑器会剥掉 <style> 标签、class、id,
       所以任何依赖外部 CSS 的写法在粘贴后都会失效。
    2. 不使用 flex / grid / position —— 微信正文容器对这几类布局支持很差。
    3. 正文全部包在一个 <section> 里, 微信自己的模板也是用 section,
       粘贴时结构保留度最高。
    4. 代码块用 white-space:pre-wrap + overflow-wrap:break-word,
       手机上自动折行而不是横向滚动 (微信正文没有可靠的横向滚动条)。
    5. 字号用 px, 正文 16px / 行高 1.75, 这是手机端阅读的舒适区间。

支持语法:
    YAML frontmatter (title / author / date / digest / theme)
    标题 # ## ### / 段落 / 粗体 ** / 斜体 * / 行内代码 `
    ``` 围栏代码块 (带语言标签栏)
    | 表格 |
    > [!NOTE] / [!TIP] / [!IMPORTANT] / [!WARNING] / [!CAUTION] / [!DANGER] 提示框
    > 普通引用
    - 无序列表 (支持两级) / 1. 有序列表
    --- 分割线
    [文本](链接)
"""

import argparse
import html
import os
import re
import sys
from html.parser import HTMLParser

# --------------------------------------------------------------------------
# 调色板
# --------------------------------------------------------------------------
THEMES = {
    "accent": {
        "accent": "#0B63CE",
        "accent_dark": "#084A9E",
        "accent_soft": "#EBF3FD",
    },
    "warm": {
        "accent": "#C2410C",
        "accent_dark": "#9A3412",
        "accent_soft": "#FFF3EC",
    },
    "green": {
        "accent": "#0F766E",
        "accent_dark": "#115E59",
        "accent_soft": "#E9F7F5",
    },
}

INK = "#16233A"        # 正文主色
INK_SOFT = "#3D4A5C"   # 次要正文
MUTED = "#9AA4B2"      # 辅助信息
HAIRLINE = "#E8ECF2"
CODE_BG = "#1B2430"
CODE_FG = "#E6EDF3"
CODE_LABEL = "#8B9AAC"
TABLE_HEAD_BG = "#F4F7FB"
TABLE_ZEBRA = "#FAFBFD"
TABLE_BORDER = "#E6EBF2"

# 注意: 字体名一律用单引号。style="..." 是双引号属性, 里面再放双引号会把属性截断,
# 导致后续字体名被浏览器当成垃圾属性, 整个 inline style 失效。
FONT_SANS = ("-apple-system,BlinkMacSystemFont,'Helvetica Neue','PingFang SC',"
             "'Hiragino Sans GB','Microsoft YaHei',sans-serif")
FONT_MONO = ("'SF Mono',Menlo,Consolas,'Liberation Mono','Courier New',monospace")

# 提示框配色: (主色, 浅背景, 左侧色条)
CALLOUTS = {
    "NOTE":      ("#0B63CE", "#F1F7FE", "#5B9BF0", "说明"),
    "TIP":       ("#0F766E", "#EFFAF8", "#3DBFAC", "提示"),
    "IMPORTANT": ("#6D28D9", "#F6F3FE", "#A98BF0", "重点"),
    "WARNING":   ("#B45309", "#FFFAF0", "#F0B45B", "注意"),
    "CAUTION":   ("#B91C1C", "#FEF4F4", "#F08C8C", "当心"),
    "DANGER":    ("#B91C1C", "#FEF4F4", "#EF5350", "警告"),
}


# --------------------------------------------------------------------------
# 行内解析
# --------------------------------------------------------------------------
def esc(text):
    """转义文本内容 (保留引号可读性, 属性位置单独处理)。"""
    return html.escape(text, quote=False)


def render_inline(text, ctx):
    """把一行 markdown 行内语法转成带 inline style 的 HTML。"""
    out = esc(text)

    # 行内代码先抽出来, 避免内部内容被粗体/斜体规则误伤
    stash = []

    def _stash(m):
        stash.append(m.group(1))
        return "\x00%d\x00" % (len(stash) - 1)

    out = re.sub(r"`([^`]+)`", _stash, out)

    out = re.sub(
        r"\*\*(.+?)\*\*",
        lambda m: '<strong style="font-weight:700;color:%s;">%s</strong>'
                  % (INK, m.group(1)),
        out,
    )
    out = re.sub(
        r"(?<!\*)\*(?!\s)(.+?)(?<!\s)\*(?!\*)",
        lambda m: '<em style="font-style:italic;">%s</em>' % m.group(1),
        out,
    )
    out = re.sub(
        r"\[([^\]]+)\]\(([^)\s]+)\)",
        lambda m: '<a href="%s" style="color:%s;text-decoration:none;'
                  'border-bottom:1px solid %s;">%s</a>'
                  % (html.escape(m.group(2), quote=True), ctx["accent"],
                     ctx["accent"], m.group(1)),
        out,
    )

    for i, code in enumerate(stash):
        span = ('<code style="font-family:%s;font-size:14px;color:%s;'
                'background:#F1F4F8;padding:2px 5px;border-radius:4px;'
                'word-break:break-all;">%s</code>'
                % (FONT_MONO, ctx["accent_dark"], esc(code)))
        out = out.replace("\x00%d\x00" % i, span)
    return out


# --------------------------------------------------------------------------
# 块级渲染
# --------------------------------------------------------------------------
def h1(title, author, date):
    parts = ['<section style="margin:0 0 10px;font-size:23px;font-weight:800;'
             'line-height:1.4;color:%s;letter-spacing:.3px;">%s</section>'
             % (INK, esc(title))]
    meta = " · ".join(x for x in (author, date) if x)
    if meta:
        parts.append('<section style="margin:0 0 20px;font-size:13px;'
                     'color:%s;letter-spacing:.5px;">%s</section>'
                     % (MUTED, esc(meta)))
    return "".join(parts)


def digest_card(text, ctx):
    return ('<section style="margin:0 0 28px;padding:15px 17px;background:%s;'
            'border-radius:10px;">'
            '<section style="font-size:11px;font-weight:700;color:%s;'
            'letter-spacing:2px;margin-bottom:7px;">摘 要</section>'
            '<section style="font-size:14px;line-height:1.75;color:%s;">%s</section>'
            '</section>'
            % (ctx["accent_soft"], ctx["accent"],
               INK_SOFT, render_inline(text, ctx)))


def h2(text, ctx):
    return ('<section style="margin:34px 0 18px;">'
            '<section style="font-size:19px;font-weight:700;color:%s;'
            'line-height:1.5;letter-spacing:.3px;">%s</section>'
            '<section style="margin-top:9px;width:36px;height:3px;'
            'background:%s;border-radius:2px;"></section>'
            '</section>'
            % (INK, render_inline(text, ctx), ctx["accent"]))


def h3(text, ctx):
    return ('<section style="margin:26px 0 14px;font-size:16px;font-weight:700;'
            'color:%s;line-height:1.5;">'
            '<span style="display:inline-block;width:6px;height:6px;'
            'background:%s;border-radius:50%%;margin-right:8px;'
            'vertical-align:middle;"></span>%s</section>'
            % (INK, ctx["accent"], render_inline(text, ctx)))


def h4(text, ctx):
    return ('<section style="margin:22px 0 12px;font-size:15px;font-weight:700;'
            'color:%s;line-height:1.5;">%s</section>'
            % (ctx["accent_dark"], render_inline(text, ctx)))


CJK = r"一-鿿　-〿＀-￯"


def join_lines(buf):
    """合并段落内的软换行。

    规则: 中↔中之间直接拼接 (中文本来就不用空格); 其他情况保留一个空格,
    这样 "先用 CSV 验证" 这种中英混排的空格不会被吃掉。
    """
    text = " ".join(buf)
    text = re.sub(r"(?<=[%s])\s+(?=[%s])" % (CJK, CJK), "", text)
    return text.strip()


def paragraph(text, ctx):
    return ('<p style="margin:0 0 18px;font-size:16px;line-height:1.78;'
            'color:%s;letter-spacing:.2px;word-break:break-word;">%s</p>'
            % (INK_SOFT, render_inline(text, ctx)))


def code_block(lang, code, ctx):
    # 微信会过滤 text-transform, 所以语言名直接在大写化后输出
    label = esc(lang.strip() or "code").upper()
    body = esc(code.rstrip("\n"))
    return (
        '<section style="margin:0 0 22px;border-radius:10px;overflow:hidden;'
        'background:%s;">'
        '<section style="padding:9px 16px;font-size:11px;color:%s;'
        'letter-spacing:1.5px;text-transform:uppercase;font-family:%s;'
        'border-bottom:1px solid rgba(255,255,255,.08);">%s</section>'
        '<pre style="margin:0;padding:15px 16px;font-family:%s;font-size:13px;'
        'line-height:1.72;color:%s;white-space:pre-wrap;word-wrap:break-word;'
        'overflow-wrap:break-word;letter-spacing:0;">%s</pre>'
        '</section>'
        % (CODE_BG, CODE_LABEL, FONT_MONO, label, FONT_MONO, CODE_FG, body)
    )


def callout(kind, title, lines, ctx):
    color, bg, bar, default_title = CALLOUTS.get(kind, CALLOUTS["NOTE"])
    head = esc(title) if title else default_title
    body = "".join(
        '<section style="font-size:14px;line-height:1.75;color:%s;'
        'margin-top:6px;word-break:break-word;">%s</section>'
        % (INK_SOFT, render_inline(ln, ctx))
        for ln in lines if ln.strip()
    )
    # 用文字徽章而不是 emoji: emoji 在不同机型上字重/基线差异很大, 而且会打断
    # 标题的视觉节奏。徽章只用 border + color, 不依赖任何微信可能过滤的属性。
    badge = (None if kind in ("NOTE", "TIP", "IMPORTANT") else
             '<span style="display:inline-block;padding:0 6px;font-size:11px;'
             'font-weight:700;color:%s;border:1px solid %s;border-radius:4px;'
             'line-height:1.7;vertical-align:1px;">%s</span>&nbsp;'
             % (color, bar, default_title))
    return (
        '<section style="margin:0 0 22px;padding:14px 16px 15px 17px;'
        'background:%s;border-left:3px solid %s;border-radius:0 8px 8px 0;">'
        '<section style="font-size:13px;font-weight:700;color:%s;'
        'letter-spacing:.5px;line-height:1.6;">%s%s</section>%s</section>'
        % (bg, bar, color, badge or "", head, body)
    )


def blockquote(lines, ctx):
    body = "".join(
        '<section style="font-size:15px;line-height:1.78;color:%s;'
        'margin-top:6px;">%s</section>'
        % (INK_SOFT, render_inline(ln, ctx))
        for ln in lines if ln.strip()
    )
    return ('<section style="margin:0 0 22px;padding:2px 0 2px 15px;'
            'border-left:3px solid %s;">%s</section>'
            % (HAIRLINE, body))


def table(header, rows, ctx):
    thead = "".join(
        '<td style="padding:9px 10px;font-size:13px;font-weight:700;'
        'color:#FFFFFF;background:%s;border-right:1px solid rgba(255,255,255,.14);'
        'word-break:break-word;line-height:1.6;">%s</td>'
        % (ctx["accent"], render_inline(h, ctx))
        for h in header
    )
    thead = ('<tr style="background:%s;">%s</tr>' % (ctx["accent"], thead))

    trs = []
    for i, row in enumerate(rows):
        bg = TABLE_ZEBRA if i % 2 == 0 else "#FFFFFF"
        cells = "".join(
            '<td style="padding:9px 10px;font-size:13px;color:%s;'
            'background:%s;border-top:1px solid %s;border-right:1px solid %s;'
            'word-break:break-word;line-height:1.6;">%s</td>'
            % (INK_SOFT, bg, TABLE_BORDER, TABLE_BORDER, render_inline(c, ctx))
            for c in row
        )
        trs.append("<tr>%s</tr>" % cells)

    return ('<section style="margin:0 0 24px;overflow:hidden;border-radius:8px;'
            'border:1px solid %s;">'
            '<table style="width:100%%;border-collapse:collapse;'
            'table-layout:fixed;font-family:%s;">'
            '<tbody>%s%s</tbody></table></section>'
            % (TABLE_BORDER, FONT_SANS, thead, "".join(trs)))


def hr(ctx):
    return ('<section style="margin:30px 0;text-align:center;font-size:0;'
            'line-height:0;">'
            '<section style="display:inline-block;width:5px;height:5px;'
            'background:%s;border-radius:50%%;margin:0 5px;'
            'vertical-align:middle;"></section>'
            '<section style="display:inline-block;width:5px;height:5px;'
            'background:%s;border-radius:50%%;margin:0 5px;'
            'vertical-align:middle;"></section>'
            '<section style="display:inline-block;width:5px;height:5px;'
            'background:%s;border-radius:50%%;margin:0 5px;'
            'vertical-align:middle;"></section>'
            '</section>' % (HAIRLINE, ctx["accent"], HAIRLINE))


def bullets(items, ctx, ordered=False):
    """items: [(level, text), ...]  level 0 / 1

    用 text-indent 负值 + padding-left 做悬挂缩进, 比 flex/inline-block 表格化
    在微信正文里稳得多, 换行时第二行也能正确对齐。
    """
    out = ['<section style="margin:0 0 20px;">']
    counters = {0: 0, 1: 0}
    for level, text in items:
        pad = 1.2 if level == 0 else 2.6
        if ordered:
            if level == 0:
                counters[0] += 1
                counters[1] = 0
                marker = "%d." % counters[0]
            else:
                counters[1] += 1
                marker = "%s)" % chr(ord("a") + (counters[1] - 1) % 26)
        else:
            marker = "·" if level == 0 else "–"
        out.append(
            '<section style="margin:0 0 9px 0;padding-left:%.1fem;'
            'text-indent:-%.1fem;font-size:15px;line-height:1.78;color:%s;'
            'word-break:break-word;">'
            '<span style="color:%s;font-weight:700;">%s</span>&nbsp;%s</section>'
            % (pad, pad, INK_SOFT, ctx["accent"], marker, render_inline(text, ctx))
        )
    out.append("</section>")
    return "".join(out)


# --------------------------------------------------------------------------
# 解析器
# --------------------------------------------------------------------------
def parse_frontmatter(text):
    meta, body = {}, text
    m = re.match(r"^\s*---\s*\n(.*?)\n---\s*\n?", text, re.S)
    if m:
        for line in m.group(1).splitlines():
            if ":" in line and not line.strip().startswith("#"):
                k, v = line.split(":", 1)
                meta[k.strip()] = v.strip().strip('"').strip("'")
        body = text[m.end():]
    return meta, body


def split_row(line):
    line = line.strip()
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|"):
        line = line[:-1]
    return [c.strip() for c in line.split("|")]


def convert(md_text):
    meta, body = parse_frontmatter(md_text)
    theme = THEMES.get(meta.get("theme", "accent"), THEMES["accent"])
    ctx = dict(theme)

    lines = body.split("\n")
    blocks = []
    i, n = 0, len(lines)

    while i < n:
        line = lines[i]
        stripped = line.strip()

        # 空行
        if not stripped:
            i += 1
            continue

        # 围栏代码块
        fm = re.match(r"^\s*```(\S*)\s*$", line)
        if fm:
            lang = fm.group(1)
            i += 1
            buf = []
            while i < n and not re.match(r"^\s*```\s*$", lines[i]):
                buf.append(lines[i])
                i += 1
            i += 1  # 跳过结束围栏
            blocks.append(code_block(lang, "\n".join(buf), ctx))
            continue

        # 分割线
        if re.match(r"^\s*([-*_])\s*(\1\s*){2,}$", line):
            blocks.append(hr(ctx))
            i += 1
            continue

        # 标题
        hm = re.match(r"^(#{1,6})\s+(.*)$", line)
        if hm:
            level, text = len(hm.group(1)), hm.group(2).strip()
            blocks.append({1: h2, 2: h2, 3: h3}.get(level, h4)(text, ctx))
            i += 1
            continue

        # 表格
        if stripped.startswith("|") and i + 1 < n and \
                re.match(r"^\s*\|?[\s:|-]+\|[\s:|-]*$", lines[i + 1]):
            header = split_row(lines[i])
            i += 2
            rows = []
            while i < n and lines[i].strip().startswith("|"):
                rows.append(split_row(lines[i]))
                i += 1
            width = len(header)
            rows = [(r + [""] * width)[:width] for r in rows]
            blocks.append(table(header, rows, ctx))
            continue

        # 引用 / 提示框
        if stripped.startswith(">"):
            quoted = []
            while i < n and lines[i].strip().startswith(">"):
                quoted.append(re.sub(r"^\s*>\s?", "", lines[i]).rstrip())
                i += 1
            am = re.match(r"^\[!(\w+)\]\s*(.*)$", quoted[0].strip()) if quoted else None
            if am:
                kind = am.group(1).upper()
                blocks.append(callout(kind, am.group(2).strip(), quoted[1:], ctx))
            else:
                blocks.append(blockquote(quoted, ctx))
            continue

        # 列表
        lm = re.match(r"^(\s*)([-*+]|\d+[.)])\s+(.*)$", line)
        if lm:
            ordered = bool(re.match(r"\d+", lm.group(2)))
            items = []
            while i < n:
                m2 = re.match(r"^(\s*)([-*+]|\d+[.)])\s+(.*)$", lines[i])
                if not m2:
                    break
                lvl = 0 if len(m2.group(1)) < 2 else 1
                items.append((lvl, m2.group(3).strip()))
                i += 1
            blocks.append(bullets(items, ctx, ordered))
            continue

        # 段落
        buf = [stripped]
        i += 1
        while i < n:
            nxt = lines[i]
            if not nxt.strip():
                break
            if re.match(r"^\s*(#{1,6}\s|```|>|\||[-*+]\s|\d+[.)]\s)", nxt):
                break
            if re.match(r"^\s*([-*_])\s*(\1\s*){2,}$", nxt):
                break
            buf.append(nxt.strip())
            i += 1
        blocks.append(paragraph(join_lines(buf), ctx))

    head = []
    if meta.get("title"):
        head.append(h1(meta["title"], meta.get("author"), meta.get("date")))
    if meta.get("digest"):
        head.append(digest_card(meta["digest"], ctx))

    article = "".join(head) + "".join(blocks)
    return meta, article, ctx


PAGE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
</head>
<body style="margin:0;padding:0;background:#EEF1F5;">
<section id="wx-article" style="max-width:677px;margin:0 auto;padding:26px 18px 40px;background:#FFFFFF;font-family:{font};font-size:16px;color:{ink};-webkit-font-smoothing:antialiased;">
{article}
</section>
<section style="max-width:677px;margin:0 auto;padding:0 18px 40px;background:#EEF1F5;">
<section style="background:#FFFFFF;border-radius:10px;padding:16px 18px;font-size:13px;line-height:1.8;color:#6B7684;">
<strong style="color:#16233A;">如何复制到公众号</strong><br>
1. 用浏览器打开本文件; <br>
2. 点右上角 <strong>复制到公众号</strong> 按钮 (推荐), 或从大标题开始手动拖选到结尾后 Ctrl+C;<br>
3. 粘贴到 mp.weixin.qq.com 的正文编辑器。<br>
<span style="color:#9AA4B2;">说明: 正文顶部已内置大标题和「摘要」卡片, 让内容自成一篇。如果你打算把标题填进编辑器的「标题」栏, 粘贴后把正文顶部那行大标题删掉即可, 避免重复。本页底部的说明块不会被复制按钮选中。</span>
</section>
</section>
<section style="position:fixed;top:18px;right:18px;z-index:99;">
<button onclick="copyArticle()" style="cursor:pointer;border:0;border-radius:20px;padding:10px 18px;background:{accent};color:#FFFFFF;font-size:13px;font-weight:700;box-shadow:0 4px 14px rgba(11,99,206,.3);font-family:{font};">复制到公众号</button>
</section>
<script>
function copyArticle() {{
  var el = document.getElementById('wx-article');
  var range = document.createRange();
  range.selectNodeContents(el);
  var sel = window.getSelection();
  sel.removeAllRanges();
  sel.addRange(range);
  try {{
    document.execCommand('copy');
    var b = document.querySelector('button');
    b.innerHTML = '已复制 ✓';
    setTimeout(function () {{ b.innerHTML = '复制到公众号'; }}, 1600);
  }} catch (e) {{ alert('复制失败, 请手动拖选后 Ctrl+C'); }}
  sel.removeAllRanges();
}}
</script>
</body>
</html>
"""


class _AttrAudit(HTMLParser):
    """解析生成的正文, 找出被引号截断的 inline style 之类的属性错误。

    典型症状: style="-apple-system,..."Helvetica Neue"..." 里的双引号把属性提前
    闭合, 后面 "Helvetica" 之类被当成新属性名。浏览器不会报错, 只会静默丢弃样式,
    所以在生成阶段就必须拦住。
    """

    def __init__(self):
        HTMLParser.__init__(self, convert_charrefs=True)
        self.problems = []
        self.tags = set()

    def handle_starttag(self, tag, attrs):
        self.tags.add(tag)
        for name, value in attrs:
            if re.search(r"[\s,:'\"()/]", name):
                self.problems.append(
                    "<%s> 属性名异常 %r —— 多半是上游样式里的引号截断了属性" % (tag, name))
            if tag == "section" and name == "style" and not (value or "").strip():
                self.problems.append("<section> 存在空的 style 属性")


def validate(article):
    p = _AttrAudit()
    p.feed(article)
    problems = list(p.problems)
    for bad in ("class=", "<style", "<script"):
        if bad in article:
            problems.append("正文含 %s, 微信编辑器会剥掉" % bad)
    # 字符串里漏了 %s 之外的占位符时, Python 会把 None 直接渲染进 HTML
    if re.search(r">\s*None\s*<", article):
        problems.append("正文出现字面量 None —— 多半是 %-格式化漏了参数")
    if re.search(r">\s*\{%?[a-z_]+\}?\s*<", article):
        problems.append("正文出现未替换的模板占位符")
    if article.count('"') % 2:
        problems.append("正文双引号数量为奇数, HTML 很可能被截断")
    if not p.tags:
        problems.append("未解析出任何标签")
    return problems


def main():
    ap = argparse.ArgumentParser(description="Markdown -> 微信公众号 HTML")
    ap.add_argument("input")
    ap.add_argument("-o", "--output")
    args = ap.parse_args()

    with open(args.input, encoding="utf-8") as f:
        md_text = f.read()

    meta, article, ctx = convert(md_text)

    out_path = args.output or os.path.splitext(args.input)[0] + ".html"
    page = PAGE.format(title=html.escape(meta.get("title", "公众号文章")),
                       article=article, ink=INK, font=FONT_SANS,
                       accent=ctx["accent"])
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(page)

    print("输入 : %s" % args.input)
    print("输出 : %s" % out_path)
    print("标题 : %s" % meta.get("title", "(无)"))
    print("字数 : %d (HTML 字符数)" % len(page))
    # 自检: 公众号编辑器会剥掉 class/id, 保证正文里没有
    inner = article
    for bad in ("class=", ' id="', "<style", "<script"):
        if bad in inner:
            print("!! 自检失败: 正文包含 %s" % bad)
            sys.exit(1)
    print("自检 : 正文无 class/id/style/script, 全部样式已 inline")
    problems = validate(article)
    if problems:
        print("!! 自检失败:")
        for p in problems:
            print("   - %s" % p)
        sys.exit(1)
    print("自检 : 属性结构合法, 无被引号截断的 inline style")


if __name__ == "__main__":
    main()
