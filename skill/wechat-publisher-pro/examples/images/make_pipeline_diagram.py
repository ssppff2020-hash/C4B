#!/usr/bin/env python3
"""
Generate `pipeline.png`, the demo image used by examples/sample_article.md.

Kept alongside its output so the sample article's embedded picture is
reproducible rather than an opaque binary someone dropped in the repo::

    python examples/images/make_pipeline_diagram.py
"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

WIDTH, HEIGHT = 1400, 420
BG = "#ffffff"
BOX_FILL = "#eaf2fe"
BOX_EDGE = "#1a73e8"
TEXT = "#12263f"
MUTED = "#8b93a1"

STEPS = [
    ("Markdown / Word", "原始内容"),
    ("读取与分词", "保护代码与公式"),
    ("应用公众号规则", "inline CSS · 白名单标签"),
    ("排版增强", "主题 · callout · 目录"),
    ("可粘贴 HTML", "Ctrl+C 进编辑器"),
]


def load_font(size: int):
    for name in ("msyh.ttc", "msyhbd.ttc", "simhei.ttf", "arial.ttf",
                 "DejaVuSans.ttf"):
        for root in (r"C:\Windows\Fonts", "/usr/share/fonts/truetype/dejavu",
                     "/System/Library/Fonts"):
            candidate = Path(root) / name
            if candidate.exists():
                try:
                    return ImageFont.truetype(str(candidate), size)
                except OSError:
                    continue
    return ImageFont.load_default()


def main() -> None:
    image = Image.new("RGB", (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(image)
    title_font = load_font(30)
    step_font = load_font(22)
    sub_font = load_font(17)

    margin = 40
    gap = 26
    box_w = (WIDTH - margin * 2 - gap * (len(STEPS) - 1)) // len(STEPS)
    box_h = 150
    top = 150

    for i, (label, sub) in enumerate(STEPS):
        x0 = margin + i * (box_w + gap)
        x1, y1 = x0 + box_w, top + box_h
        draw.rounded_rectangle([x0, top, x1, y1], radius=14,
                               fill=BOX_FILL, outline=BOX_EDGE, width=3)
        draw.text(((x0 + x1) / 2, top + 46), label, font=step_font,
                  fill=TEXT, anchor="mm")
        draw.text(((x0 + x1) / 2, top + 96), sub, font=sub_font,
                  fill=MUTED, anchor="mm")
        if i < len(STEPS) - 1:
            cx = x1 + gap / 2
            draw.line([cx - 9, top + box_h / 2, cx + 5, top + box_h / 2],
                      fill=BOX_EDGE, width=4)
            draw.polygon([(cx + 5, top + box_h / 2 - 9),
                          (cx + 5, top + box_h / 2 + 9),
                          (cx + 17, top + box_h / 2)], fill=BOX_EDGE)

    draw.text((margin, 70), "wechat-publisher-pro 转换流水线", font=title_font,
              fill=TEXT)

    out = Path(__file__).with_name("pipeline.png")
    image.save(out, "PNG", optimize=True)
    print("已生成 %s (%d bytes)" % (out, out.stat().st_size))


if __name__ == "__main__":
    main()
