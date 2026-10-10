"""
Theme system for wechat-publisher-pro.

A *theme* is a palette (colour tokens) plus a small set of structural choices
(heading decoration, callout shape).  Styles are **generated** from the palette
rather than hard-coded per theme, so a user can add a new look by supplying a
handful of hex values instead of writing 30 CSS strings.

Everything emitted here is inline CSS with properties WeChat's editor keeps.
We deliberately use longhand ``margin-top`` / ``margin-bottom`` instead of the
``margin`` shorthand: WeChat's editor re-writes the shorthand inconsistently
across pastes, which produces uneven vertical rhythm in the published article.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

# --------------------------------------------------------------------------
# Colour tokens
# --------------------------------------------------------------------------
# Every palette must define these keys.  `derive_palette` fills in anything a
# custom palette leaves out, so a user only has to supply what they care about.
REQUIRED_TOKENS = (
    "text", "text_soft", "heading", "accent", "accent_soft",
    "border", "code_bg", "code_text", "code_inline_bg", "code_inline_text",
    "quote_bg", "quote_border", "table_head_bg", "link",
)

PALETTES: dict[str, dict] = {
    "default": {
        "label": "默认 · 中性灰蓝",
        "text": "#333333",
        "text_soft": "#8a8f99",
        "heading": "#22262b",
        "accent": "#4a6fa5",
        "accent_soft": "#eef2f8",
        "border": "#e4e7ec",
        "code_bg": "#f6f8fa",
        "code_text": "#24292e",
        "code_inline_bg": "#f2f4f7",
        "code_inline_text": "#c7254e",
        "quote_bg": "#f8f9fb",
        "quote_border": "#b9c2d0",
        "table_head_bg": "#f2f4f7",
        "link": "#4a6fa5",
        "heading_style": "bar",
        "body_align": "justify",
    },
    "accent": {
        "label": "蓝调 · 科技清晰",
        "text": "#2c3038",
        "text_soft": "#8b93a1",
        "heading": "#12263f",
        "accent": "#1a73e8",
        "accent_soft": "#eaf2fe",
        "border": "#dde6f2",
        "code_bg": "#f5f8fd",
        "code_text": "#1f2937",
        "code_inline_bg": "#eef3fb",
        "code_inline_text": "#c7254e",
        "quote_bg": "#f4f8ff",
        "quote_border": "#1a73e8",
        "table_head_bg": "#eaf2fe",
        "link": "#1a73e8",
        "heading_style": "bar",
        "body_align": "justify",
    },
    "warm": {
        "label": "暖阳 · 亲切随笔",
        "text": "#3a3229",
        "text_soft": "#9c8d7b",
        "heading": "#6b3a11",
        "accent": "#d2691e",
        "accent_soft": "#fdf3e8",
        "border": "#f0e2cf",
        "code_bg": "#fbf7f1",
        "code_text": "#4a3f33",
        "code_inline_bg": "#f7efe4",
        "code_inline_text": "#b5482c",
        "quote_bg": "#fdf7ef",
        "quote_border": "#e0a458",
        "table_head_bg": "#fdf3e8",
        "link": "#c2641a",
        "heading_style": "underline",
        "body_align": "justify",
    },
    "minimal": {
        "label": "极简 · 黑白留白",
        "text": "#2b2b2b",
        "text_soft": "#9a9a9a",
        "heading": "#111111",
        "accent": "#111111",
        "accent_soft": "#f5f5f5",
        "border": "#e6e6e6",
        "code_bg": "#fafafa",
        "code_text": "#2b2b2b",
        "code_inline_bg": "#f2f2f2",
        "code_inline_text": "#2b2b2b",
        "quote_bg": "#fafafa",
        "quote_border": "#c4c4c4",
        "table_head_bg": "#f5f5f5",
        "link": "#111111",
        "heading_style": "plain",
        "body_align": "left",
    },
    "tech": {
        "label": "终端 · 开发者向",
        "text": "#24292f",
        "text_soft": "#7d8590",
        "heading": "#0d1117",
        "accent": "#1f883d",
        "accent_soft": "#eaf6ed",
        "border": "#d8dee4",
        "code_bg": "#f0f3f6",
        "code_text": "#24292f",
        "code_inline_bg": "#eef1f4",
        "code_inline_text": "#cf222e",
        "quote_bg": "#f4f8f5",
        "quote_border": "#1f883d",
        "table_head_bg": "#eaf6ed",
        "link": "#0969da",
        "heading_style": "bar",
        "body_align": "left",
    },
    "ink": {
        "label": "墨韵 · 中文书卷",
        "text": "#2f2b28",
        "text_soft": "#8d857a",
        "heading": "#1f1b18",
        "accent": "#8c2f39",
        "accent_soft": "#f7efee",
        "border": "#e6ddd3",
        "code_bg": "#f7f4ef",
        "code_text": "#3b352e",
        "code_inline_bg": "#f3eee7",
        "code_inline_text": "#8c2f39",
        "quote_bg": "#faf5f0",
        "quote_border": "#c9a227",
        "table_head_bg": "#f7efee",
        "link": "#8c2f39",
        "heading_style": "underline",
        "body_align": "justify",
    },
}

DEFAULT_THEME = "default"

# Callout types.  `emoji` is prepended to the label; `token` names the palette
# colour family used for the box.  Keeping this table data-driven means adding a
# new callout kind is a one-line change.
CALLOUT_TYPES: dict[str, dict] = {
    "note":    {"emoji": "📘", "label": "知识点", "token": "accent"},
    "tip":     {"emoji": "💡", "label": "提示",   "token": "green"},
    "key":     {"emoji": "🔑", "label": "重点",   "token": "accent"},
    "warning": {"emoji": "⚠️", "label": "注意",   "token": "amber"},
    "danger":  {"emoji": "🚨", "label": "警告",   "token": "red"},
    "quote":   {"emoji": "💬", "label": "引用",   "token": "neutral"},
    "example": {"emoji": "🧪", "label": "示例",   "token": "violet"},
    "confused": {"emoji": "🤔", "label": "疑问",  "token": "amber"},
    "success":  {"emoji": "✅", "label": "结论",  "token": "green"},
}

# Fixed semantic colours for callouts — these deliberately do *not* follow the
# theme accent, because "warning must be amber / danger must be red" is a
# meaning that should survive a palette swap.
CALLOUT_COLORS: dict[str, tuple[str, str, str]] = {
    # token -> (background, border, label colour)
    "accent":  ("#eef4fe", "#1a73e8", "#12509e"),
    "green":   ("#eaf7ee", "#2e9e4f", "#1d6b36"),
    "amber":   ("#fdf6e3", "#d9910b", "#8a5b00"),
    "red":     ("#fdeceb", "#d93025", "#a1251c"),
    "violet":  ("#f3eefc", "#7b52c9", "#513687"),
    "neutral": ("#f4f5f7", "#9aa2ad", "#5b636e"),
}


def list_themes() -> list[tuple[str, str]]:
    """Return ``(name, label)`` pairs for all built-in themes."""
    return [(name, p.get("label", name)) for name, p in PALETTES.items()]


def derive_palette(name_or_dict) -> dict:
    """Resolve a theme name (or dict) into a complete palette.

    Missing tokens are filled from ``default`` so that a user-supplied theme
    file only has to state the colours it actually changes.
    """
    base = copy.deepcopy(PALETTES[DEFAULT_THEME])
    if isinstance(name_or_dict, str):
        if name_or_dict not in PALETTES:
            raise KeyError(
                f"Unknown theme '{name_or_dict}'. Available: {', '.join(PALETTES)}"
            )
        base.update(PALETTES[name_or_dict])
        base["name"] = name_or_dict
    else:
        # Custom palette: keep everything the user gave us (including extra
        # keys they may reference from `heading_style`), fill the rest.
        supplied = {k: v for k, v in name_or_dict.items() if v is not None}
        base.update(supplied)
        base["name"] = supplied.get("name", "custom")
    for token in REQUIRED_TOKENS:
        if not base.get(token):
            raise KeyError(f"Theme is missing required token '{token}'")
    return base


def palette_from_file(path: str | Path) -> dict:
    """Load a palette from a JSON file (or a ``theme:`` block inside one)."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if "theme" in data and isinstance(data["theme"], dict):
        data = data["theme"]
    return derive_palette(data)


def _shade(hex_color: str, factor: float) -> str:
    """Lighten (factor > 1) or darken (factor < 1) a ``#rrggbb`` colour."""
    hex_color = hex_color.lstrip("#")
    if len(hex_color) == 3:
        hex_color = "".join(c * 2 for c in hex_color)
    r, g, b = (int(hex_color[i:i + 2], 16) for i in (0, 2, 4))
    if factor >= 1:  # lighten toward white
        t = min(factor - 1.0, 1.0)
        r, g, b = (round(c + (255 - c) * t) for c in (r, g, b))
    else:            # darken toward black
        r, g, b = (round(c * factor) for c in (r, g, b))
    return "#{:02x}{:02x}{:02x}".format(
        max(0, min(255, r)), max(0, min(255, g)), max(0, min(255, b))
    )


# --------------------------------------------------------------------------
# Typography scale
# --------------------------------------------------------------------------
# Body copy is 16px / 1.75 — the mobile sweet spot for Chinese text.  Anything
# below 15px becomes hard to read on a phone; WeChat's own editor defaults to
# 17px for body text, but 16px is the widely used "breathe" size.
SCALE = {
    "h2": 20, "h3": 17, "h4": 16, "body": 16, "small": 13, "code": 13.5,
    "line": 1.75, "line_head": 1.5, "line_code": 1.6,
}


def build_styles(p: dict, opts: dict | None = None) -> dict[str, str]:
    """Turn a palette into the full dict of inline-CSS strings.

    ``opts`` may override: ``indent`` ('none'|'2em'), ``letter_spacing`` (px),
    ``heading_style``, ``body_align``, ``max_width``.
    """
    opts = opts or {}
    heading_style = opts.get("heading_style") or p.get("heading_style", "bar")
    align = opts.get("body_align") or p.get("body_align", "justify")
    indent = opts.get("indent", "none")
    tracking = opts.get("letter_spacing", 0.4)
    accent, soft = p["accent"], p["accent_soft"]
    heading, text, soft_text = p["heading"], p["text"], p["text_soft"]

    # --font-size moves the whole scale together. Shrinking body copy on its own
    # would leave headings looking oversized, so they are derived, not fixed.
    body_px = int(opts.get("font_size") or SCALE["body"])
    delta = body_px - SCALE["body"]
    scale = {
        "h2": SCALE["h2"] + delta,
        "h3": SCALE["h3"] + delta,
        "h4": SCALE["h4"] + delta,
        "body": body_px,
        "small": max(11, SCALE["small"] + delta),
        "code": max(11.0, round(SCALE["code"] + delta * 0.75, 1)),
        "line": SCALE["line"],
        "line_head": SCALE["line_head"],
        "line_code": SCALE["line_code"],
    }

    body_common = (
        f"font-size: {scale['body']}px; line-height: {scale['line']}; "
        f"color: {text}; text-align: {align}; letter-spacing: {tracking}px;"
    )
    indent_css = "" if indent in ("none", "", None) else f" text-indent: {indent};"

    def heading_deco(level: int) -> str:
        if heading_style == "bar":
            width = 4 if level == 2 else 3
            return f" border-left: {width}px solid {accent}; padding-left: 10px;"
        if heading_style == "underline":
            width = 3 if level == 2 else 2
            bottom = "double" if level == 2 else "solid"
            return f" border-bottom: {width}px {bottom} {accent}; padding-bottom: 6px;"
        return ""

    styles = {
        # ---- headings -------------------------------------------------
        "h2": (
            f"font-size: {scale['h2']}px; font-weight: bold; "
            f"line-height: {scale['line_head']}; color: {heading};"
            f"{heading_deco(2)} margin-top: 32px; margin-bottom: 14px;"
        ),
        "h3": (
            f"font-size: {scale['h3']}px; font-weight: bold; "
            f"line-height: {scale['line_head']}; color: {heading};"
            f"{heading_deco(3)} margin-top: 24px; margin-bottom: 10px;"
        ),
        "h4": (
            f"font-size: {scale['h4']}px; font-weight: bold; "
            f"line-height: {scale['line_head']}; color: {heading}; "
            f"margin-top: 20px; margin-bottom: 8px;"
        ),
        # ---- body -----------------------------------------------------
        "p": f"{body_common}{indent_css} margin-top: 0; margin-bottom: 16px;",
        "li": f"{body_common} margin-top: 0; margin-bottom: 8px;",
        "ul": "margin-top: 0; margin-bottom: 16px; padding-left: 24px; list-style-type: disc;",
        "ol": "margin-top: 0; margin-bottom: 16px; padding-left: 24px; list-style-type: decimal;",
        "strong": f"font-weight: bold; color: {_shade(heading, 1.0)};",
        "em": "font-style: italic;",
        "del": f"text-decoration: line-through; color: {soft_text};",
        # ---- links ----------------------------------------------------
        "a": f"color: {p['link']}; text-decoration: none; border-bottom: 1px solid {p['link']};",
        # ---- code -----------------------------------------------------
        "code_inline": (
            f"background-color: {p['code_inline_bg']}; color: {p['code_inline_text']}; "
            f"font-size: {scale['code']}px; font-family: Consolas, Monaco, 'Courier New', monospace; "
            f"padding: 2px 5px; border-radius: 3px; word-break: break-all;"
        ),
        "code_wrap": (
            f"border-collapse: collapse; width: 100%; margin-top: 16px; "
            f"margin-bottom: 20px; background-color: {p['code_bg']}; "
            f"border-radius: 6px;"
        ),
        "code_cell": (
            f"background-color: {p['code_bg']}; padding: 14px 16px; "
            f"border-radius: 6px; border: 1px solid {p['border']};"
        ),
        "code_lang": (
            f"font-size: 11px; color: {soft_text}; letter-spacing: 1px; "
            f"text-transform: uppercase; margin-top: 0; margin-bottom: 10px; "
            f"border-bottom: 1px solid {p['border']}; padding-bottom: 6px;"
        ),
        "code_line": (
            f"font-size: {scale['code']}px; line-height: {scale['line_code']}; "
            f"color: {p['code_text']}; font-family: Consolas, Monaco, 'Courier New', monospace; "
            f"margin-top: 0; margin-bottom: 0; white-space: pre-wrap; word-break: break-all; "
            f"text-align: left; letter-spacing: 0;"
        ),
        # ---- structural ------------------------------------------------
        "blockquote": (
            # 1.35 is the largest lightening that still clears 4.5:1 contrast
            # against the quote background; 1.6 washed out to unreadable grey.
            f"background-color: {p['quote_bg']}; color: {_shade(text, 1.35)}; "
            f"border-left: 4px solid {p['quote_border']}; padding: 12px 16px; "
            f"margin-top: 0; margin-bottom: 16px; border-radius: 0 4px 4px 0; "
            f"font-size: {scale['body']}px; line-height: {scale['line']};"
        ),
        "table": (
            f"border-collapse: collapse; width: 100%; margin-top: 16px; "
            f"margin-bottom: 20px; font-size: 14px;"
        ),
        "th": (
            f"background-color: {p['table_head_bg']}; color: {heading}; font-weight: bold; "
            f"padding: 9px 10px; text-align: left; border: 1px solid {p['border']}; "
            f"font-size: 14px; line-height: 1.6;"
        ),
        "td": (
            f"padding: 9px 10px; border: 1px solid {p['border']}; color: {text}; "
            f"font-size: 14px; line-height: 1.6;"
        ),
        "hr": (
            f"border: none; border-top: 1px solid {p['border']}; "
            f"margin-top: 28px; margin-bottom: 28px; height: 0;"
        ),
        "img": "max-width: 100%; height: auto; display: block; margin-top: 18px; margin-bottom: 6px;",
        "caption": (
            f"font-size: {scale['small']}px; color: {soft_text}; text-align: center; "
            f"margin-top: 0; margin-bottom: 20px; line-height: 1.6;"
        ),
        # ---- containers rendered as single-cell tables -------------------
        # WeChat drops borders and padding from an empty <p> but keeps them on a
        # table cell, so every "box" in the article (TOC, code block, callout,
        # horizontal rule) is a one-cell table.  This is the same technique the
        # commercial WeChat layout editors use.
        "toc_table": (
            "border-collapse: collapse; width: 100%; "
            "margin-top: 4px; margin-bottom: 28px;"
        ),
        "divider_table": (
            "border-collapse: collapse; width: 100%; "
            "margin-top: 28px; margin-bottom: 28px;"
        ),
        "divider_cell": (
            f"border-top: 1px solid {p['border']}; padding: 0; "
            f"height: 0; font-size: 0; line-height: 0;"
        ),
        "divider_dots": (
            f"text-align: center; color: {_shade(p['border'], 0.8)}; "
            f"letter-spacing: 8px; font-size: 14px; "
            f"margin-top: 26px; margin-bottom: 26px;"
        ),
        # ---- article furniture ------------------------------------------
        "byline": (
            f"font-size: {scale['small']}px; color: {soft_text}; letter-spacing: 0.5px; "
            f"margin-top: 0; margin-bottom: 22px; text-align: left;"
        ),
        "digest": (
            f"background-color: {soft}; border-left: 4px solid {accent}; "
            f"color: {_shade(text, 1.35)}; font-size: 15px; line-height: 1.7; "
            f"padding: 14px 16px; border-radius: 0 6px 6px 0; "
            f"margin-top: 0; margin-bottom: 24px; text-align: justify;"
        ),
        "toc_wrap": (
            f"border: 1px solid {p['border']}; border-radius: 8px; "
            f"background-color: {soft}; padding: 16px 18px; "
            f"margin-top: 4px; margin-bottom: 28px;"
        ),
        "toc_title": (
            f"font-size: 14px; font-weight: bold; color: {accent}; "
            f"letter-spacing: 1px; margin-top: 0; margin-bottom: 10px;"
        ),
        "toc_item": (
            f"font-size: 14px; line-height: 1.9; color: {text}; "
            f"margin-top: 0; margin-bottom: 0; text-align: left;"
        ),
        "toc_item_sub": (
            f"font-size: 13px; line-height: 1.9; color: {soft_text}; "
            f"margin-top: 0; margin-bottom: 0; padding-left: 18px; text-align: left;"
        ),
        "footer": (
            f"font-size: {scale['small']}px; color: {soft_text}; line-height: 1.8; "
            f"text-align: center; margin-top: 0; margin-bottom: 6px;"
        ),
        "footer_rule": (
            f"border: none; border-top: 1px solid {p['border']}; "
            f"margin-top: 36px; margin-bottom: 16px; height: 0;"
        ),
        # ---- images / figures -------------------------------------------
        "figure_note": (
            f"font-size: 12px; color: {soft_text}; text-align: center; "
            f"margin-top: 6px; margin-bottom: 18px;"
        ),
    }

    # Callout box styles, one set per semantic token.
    for token, (bg, border, label_color) in CALLOUT_COLORS.items():
        styles[f"callout_wrap_{token}"] = (
            "border-collapse: collapse; width: 100%; "
            "margin-top: 18px; margin-bottom: 20px;"
        )
        styles[f"callout_cell_{token}"] = (
            f"background-color: {bg}; border-left: 4px solid {border}; "
            f"border-radius: 0 6px 6px 0; padding: 14px 16px;"
        )
        styles[f"callout_label_{token}"] = (
            f"font-size: 14px; font-weight: bold; color: {label_color}; "
            f"letter-spacing: 0.5px; margin-top: 0; margin-bottom: 8px; "
            f"line-height: 1.5; text-align: left;"
        )
        styles[f"callout_body_{token}"] = (
            f"font-size: 15px; line-height: 1.75; color: {text}; "
            f"margin-top: 0; margin-bottom: 8px; text-align: justify;"
        )
        styles[f"callout_body_last_{token}"] = (
            f"font-size: 15px; line-height: 1.75; color: {text}; "
            f"margin-top: 0; margin-bottom: 0; text-align: justify;"
        )

    return styles


def callout_style_key(token: str, semantic: str) -> str:
    """Small helper so the pipeline never builds style keys by hand."""
    return f"callout_{semantic}_{token}"


# --------------------------------------------------------------------------
# Theme file template (shipped so users can copy it)
# --------------------------------------------------------------------------
THEME_TEMPLATE = {
    "name": "my-theme",
    "label": "我的主题",
    "accent": "#0f766e",
    "accent_soft": "#e6f5f3",
    "heading": "#0b3b38",
    "text": "#2f3a39",
    "border": "#d7e6e4",
    "heading_style": "bar",
    "body_align": "justify",
}


def write_theme_template(path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(THEME_TEMPLATE, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path
