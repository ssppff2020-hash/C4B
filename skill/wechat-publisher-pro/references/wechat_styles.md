# Themes and styles

A theme is a **palette** plus a few structural choices. Every inline-CSS string
is generated from the palette by `build_styles()`, so changing one colour moves
everything that should move together — heading rule, table header, quote border,
TOC tint, digest background.

## Built-in themes

| Name | Label | Character |
|---|---|---|
| `default` | 默认 · 中性灰蓝 | Neutral; safe for anything |
| `accent` | 蓝调 · 科技清晰 | Blue; technical and product writing |
| `warm` | 暖阳 · 亲切随笔 | Orange; essays and personal notes |
| `minimal` | 极简 · 黑白留白 | Monochrome; academic and formal |
| `tech` | 终端 · 开发者向 | Green accent, dark headings; developer posts |
| `ink` | 墨韵 · 中文书卷 | Ink red on warm paper; literary Chinese |

```bash
python scripts/convert_to_wechat.py --list-themes
python scripts/convert_to_wechat.py article.md out.html --theme ink
```

## Palette tokens

`derive_palette()` fills any token you omit from the `default` theme, so a custom
theme only states what it changes.

| Token | Role |
|---|---|
| `text` | Body copy |
| `text_soft` | Captions, bylines, footnotes, sub-TOC entries |
| `heading` | h2/h3 colour, table header text |
| `accent` | Heading rule, digest border, TOC title, callout accent family |
| `accent_soft` | Digest background, TOC background, table header background |
| `border` | Table borders, dividers, code block outline |
| `code_bg`, `code_text` | Code block background and text |
| `code_inline_bg`, `code_inline_text` | Inline `code` spans |
| `quote_bg`, `quote_border` | Plain blockquotes |
| `table_head_bg` | Table header fill |
| `link` | Hyperlink colour and underline |
| `heading_style` | `bar` \| `underline` \| `plain` |
| `body_align` | `justify` \| `left` |

## Custom theme

```bash
python scripts/convert_to_wechat.py --new-theme my-theme.json
```

```json
{
  "name": "forest",
  "label": "森林 · 沉稳绿",
  "accent": "#0f766e",
  "accent_soft": "#e6f5f3",
  "heading": "#0b3b38",
  "text": "#2f3a39",
  "border": "#d7e6e4",
  "heading_style": "bar",
  "body_align": "justify"
}
```

```bash
python scripts/convert_to_wechat.py article.md out.html --theme-file my-theme.json
```

A file may also nest the palette under a `theme` key, which lets one JSON file
hold a theme alongside other project settings. A theme file referenced in an
article's front matter is resolved relative to that article.

For a one-off colour change, skip the file: `--accent "#0f766e"`.

## Typography scale

| Role | Size | Line height |
|---|---|---|
| h2 | 20px + delta | 1.5 |
| h3 | 17px + delta | 1.5 |
| Body | 16px | 1.75 |
| Code | 13.5px + delta | 1.6 |
| Captions / byline / footer | 13px + delta | — |

`--font-size N` moves the whole scale by a common delta rather than changing
only the body. Shrinking body copy alone leaves headings looking oversized.

Why 16px and 1.75: below ~15px Chinese glyphs get muddy on a phone, and 1.75 is
the line height at which dense Chinese paragraphs stop feeling like a wall.
`letter-spacing: 0.4px` is a small amount of tracking that measurably helps CJK
legibility without looking spaced out.

Body alignment defaults to `justify` for CJK. Justified text in Latin produces
rivers, but Chinese glyphs are monospaced, so justification is clean and the
ragged right edge of right-aligned CJK looks accidental. `minimal` and `tech` use
`left` instead, which suits their editorial tone.

## Heading decorations

| Style | Rendering |
|---|---|
| `bar` | 4px (h2) / 3px (h3) accent rule on the left, 10px padding |
| `underline` | h2 gets a double bottom rule, h3 a solid one |
| `plain` | Bold and larger only |

## Callout colours

Callout families are **not** themed. They are fixed in `CALLOUT_COLORS` because
the colour carries meaning:

| Family | Used by | Roughly |
|---|---|---|
| `accent` | NOTE, KEY | theme blue |
| `green` | TIP, SUCCESS | #2e9e4f |
| `amber` | WARNING, CONFUSED | #d9910b |
| `red` | DANGER | #d93025 |
| `violet` | EXAMPLE | #7b52c9 |
| `neutral` | QUOTE | #9aa2ad |

To add a family, add one tuple to `CALLOUT_COLORS`; the per-element styles are
generated automatically.

## Mobile constraints

- The preview column is 640px, close to a phone's reading width — judge the
  layout there, not on a desktop monitor.
- Nothing wider than the column: images get `max-width: 100%`, display formulas
  are capped, and tables are warned about past five columns.
- Contrast: quote and caption text is lightened by at most 1.35× from the body
  colour. Past that, grey-on-white drops below 4.5:1 and becomes unreadable in
  daylight.
