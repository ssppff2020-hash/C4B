# What the WeChat editor actually does

A reference for the rules the converter enforces, and why each one exists.
Nearly every rule here is something the editor does **silently** — you find out
after publishing, if at all.

## Tags

### Kept

```
p  h2  h3  ul  ol  li  span  img  a  table  tr  th  td  br
```

That list is short on purpose. The editor is a rich-text component, not a
browser; anything outside it is either stripped or converted to something
unpredictable.

### Removed or rewritten

| Tag | What happens | What the converter does instead |
|---|---|---|
| `<script>` | Removed | Nothing to render; interactive content cannot survive |
| `<style>` | Removed | Every rule is inlined onto the elements it applied to |
| `<iframe>` | Removed | Converted to a note if the source had one |
| `<h1>` | Reserved for the article title | Demoted to `<h2>` |
| `<div>` | Flattened, styles lost | Block children are lifted out; text becomes `<p>` |
| `<pre>` | Newlines collapse | One `<p>` per line inside a single-cell table |
| `<code>` | No styling survives | `<span>` with monospace + background inlined |
| `<blockquote>` | Unreliable borders | Callout box (table) or a styled `<p>` |
| `<svg>` | **Disappears on save** | Not used. Formulas become PNG |
| `<video>` `<audio>` | Removed | Must use WeChat's own media embed |
| `<h4>`–`<h6>` | Only two heading levels style reliably | Merged into `<h3>` |
| `<strong>` `<em>` | Bolding is inconsistent across themes | Replaced by `<span style="font-weight:bold">` |

## Attributes

| Attribute | What happens | Handling |
|---|---|---|
| `class` | Kept as an attribute but **never applied** — there is no stylesheet | Removed; styles inlined |
| `id` | Stripped on save | Removed. This is why the TOC has no anchor links |
| `onclick` and friends | Removed with the script engine | Removed |
| `style` | Kept, but only supported properties survive | Filtered to the allowed list |

## CSS

### Property-level

Supported: colour, background, font size/weight/style/family, line-height,
text-align, text-indent, text-decoration, letter-spacing, word-break,
white-space, margins, paddings, borders, border-radius, border-collapse,
display, vertical-align, width/height and their max/min, box-sizing,
list-style-type, text-transform, opacity.

Stripped: everything positional (`position`, `top`, `left`, `float`, `clear`,
`z-index`), everything flex/grid, everything animated (`animation`,
`transition`, `transform`), `box-shadow`, `text-shadow`, `filter`.

Because shadows and transforms vanish, any design that depends on them has to
work without them. Inlining the *filtered* set means the browser preview shows
what will actually publish — a preview that looks better than the published
article is worse than no preview.

### Selector-level

There are no selectors. `p { color: red }` has nowhere to live. Every property
must be on the element it affects. Media queries do not exist, which is why the
output is designed for a ~375–420px column in the first place.

## Boxes need to be tables

An empty `<p>` with a border loses its padding and often its border on paste — a
paragraph needs text to have a box. A `<td>` keeps both. So every framed element
is a one-cell table:

```html
<table style="border-collapse: collapse; width: 100%;">
  <tr><td style="background-color:#eef4fe;border-left:4px solid #1a73e8;padding:14px 16px;">
    <p style="...">📘 知识点</p>
    <p style="...">正文</p>
  </td></tr>
</table>
```

## Images

| Method | Survives? | Notes |
|---|---|---|
| `<img src="data:image/png;base64,...">` | ✅ | The editor re-uploads it to the WeChat CDN on paste. **The only self-contained option that works.** |
| `<img src="https://...">` | ⚠️ | Not fetched automatically. You must click "upload image" in the editor or the picture is gone on publish |
| `<img src="data:image/svg+xml;base64,...">` | ❌ | Vanishes on save — WeChat cannot re-upload SVG |
| Inline `<svg>…</svg>` | ❌ | Stripped |

This is why formulas are rendered to PNG rather than embedded as SVG or MathML.

### Limits

| Limit | Value |
|---|---|
| Article length | ~20,000 characters |
| Images per article | 100 |
| Image size | 10 MB each |
| Formats | PNG, JPG, GIF |
| GIF size | 2 MB |

## Links

Only links to `mp.weixin.qq.com` remain clickable after publishing. Every other
`<a href>` survives as its text, without the link. The converter warns and offers
three alternatives:

- `--links keep` (default) — leave it; the text is still readable
- `--links plain` — write the URL inline: `示例（https://example.com）`
- `--links footnote` — collect them under a "参考链接" heading at the end

## Whitespace

The editor collapses whitespace differently from a browser: adjacent block
margins do not collapse the same way, and an empty paragraph may be dropped
entirely. Two consequences the converter accounts for:

- Vertical rhythm uses longhand `margin-top` / `margin-bottom`, never the
  `margin` shorthand — the shorthand gets rewritten inconsistently across pastes.
- Spacing between blocks is carried by explicit margins rather than by empty
  paragraphs, which the editor is free to delete.
