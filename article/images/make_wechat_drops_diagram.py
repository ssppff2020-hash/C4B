#!/usr/bin/env python3
"""
Generate `what-wechat-drops.png`, the figure used by the published article.

The article's core claim is that the WeChat editor loses things *silently*, so
the figure is the evidence: what you write on the left, what the reader sees on
the right.

    python article/images/make_wechat_drops_diagram.py
"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

W, H = 1400, 730
BG = "#ffffff"
INK = "#12263f"
MUTED = "#6b7280"
GOOD = "#1f883d"
BAD = "#d93025"
PANEL = "#f7f9fc"
EDGE = "#dde6f2"

KEPT = [
    ("<p>", "段落"),
    ("<h2> <h3>", "两级标题"),
    ("<table>", "表格"),
    ("<img> data:image/png", "内嵌 PNG"),
]

LOST = [
    ("<script> <iframe>", "整个删除"),
    ("<style> 与 class", "样式全部失效"),
    ("<h1>", "降级为 h2"),
    ("<div>", "被拆平，样式丢失"),
    ("<pre> 代码块", "换行塌缩成一行"),
    ("<svg> / SVG 图片", "保存时消失"),
    ("外部 http 链接", "退化为纯文本"),
]


def font(size, bold=False):
    names = ("msyhbd.ttc", "msyh.ttc") if bold else ("msyh.ttc", "simhei.ttf")
    for name in names:
        for root in (r"C:\Windows\Fonts", "/usr/share/fonts/truetype/dejavu",
                     "/System/Library/Fonts"):
            path = Path(root) / name
            if path.exists():
                try:
                    return ImageFont.truetype(str(path), size)
                except OSError:
                    continue
    return ImageFont.load_default()


def main():
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    f_title = font(38, bold=True)
    f_sub = font(21)
    f_panel = font(26, bold=True)
    f_tag = font(24)
    f_note = font(22)

    d.text((70, 52), "公众号编辑器在粘贴时，静默做了什么", font=f_title, fill=INK)
    d.text((70, 108), "下面的每一条都不会报错，你只会在发布之后才发现。",
           font=f_sub, fill=MUTED)

    top = 175
    col_w = 600
    left_x, right_x = 70, W - 70 - col_w
    header_h, row_h = 78, 58

    # Both panels get the height of the taller column and centre their rows, so
    # the figure does not look lopsided. The tick and cross are drawn with
    # U+221A / U+00D7: the usual ✓/✗ codepoints have no glyph in the Windows
    # Chinese fonts and render as empty boxes.
    rows_max = max(len(KEPT), len(LOST))
    bottom = top + header_h + rows_max * row_h + 18

    def panel(x, title, colour, rule_colour, rows, note_colour):
        d.rounded_rectangle([x, top, x + col_w, bottom], radius=16,
                            fill=PANEL if colour == GOOD else "#fdf6f5",
                            outline=EDGE if colour == GOOD else "#f3d9d6",
                            width=2)
        d.text((x + 34, top + 22), title, font=f_panel, fill=colour)
        y = top + header_h + (rows_max - len(rows)) * row_h // 2
        for tag, note in rows:
            d.text((x + 34, y), tag, font=f_tag, fill=INK)
            d.text((x + col_w - 34, y + 3), note, font=f_note,
                   fill=note_colour, anchor="ra")
            d.line([x + 30, y + 42, x + col_w - 30, y + 42],
                   fill=rule_colour, width=1)
            y += row_h

    panel(left_x, "√  能活下来", GOOD, EDGE, KEPT, MUTED)
    panel(right_x, "×  会被改写或丢弃", BAD, "#f3d9d6", LOST, BAD)

    # ---- arrow between panels ----------------------------------------
    cx = (left_x + col_w + right_x) / 2
    mid = (top + bottom) / 2
    d.line([cx - 30, mid, cx + 30, mid], fill=MUTED, width=5)
    d.polygon([(cx + 30, mid - 12), (cx + 30, mid + 12), (cx + 50, mid)],
              fill=MUTED)

    out = Path(__file__).with_name("what-wechat-drops.png")
    img.save(out, "PNG", optimize=True)
    print("已生成 %s (%d bytes)" % (out, out.stat().st_size))


if __name__ == "__main__":
    main()
