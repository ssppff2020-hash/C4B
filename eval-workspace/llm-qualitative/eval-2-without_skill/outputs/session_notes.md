# session_notes — messy Word/WeChat HTML → 公众号 paste-ready HTML

Task given: *"这是从 Word 粘出来的 HTML，直接发公众号很难看，帮我整理一下"* — the result
must be HTML that can be copy-pasted into the mp.weixin.qq.com editor and look decent on a phone.

There was no existing skill or tool, so I wrote `convert.py` from scratch (stdlib only, no
BeautifulSoup / lxml dependency).

## Files produced

| file | what it is |
|---|---|
| `convert.py` | the converter. `python -I convert.py <in> <out.wechat.html> [preview.html]` |
| `messy_export.wechat.html` | **the deliverable** — the article fragment you paste into WeChat |
| `preview.html` | a standalone page that renders that fragment at WeChat's 677px content width so you can eyeball it, Ctrl+A / Ctrl+C and paste |

Input: `skill/wechat-publisher-pro/evals/cases/messy_export.md`

## What the input actually contained, and what I did with each problem

The file is a small HTML fragment that deliberately contains every classic
"copied out of Word" defect:

| # | problem in the source | treatment |
|---|---|---|
| 1 | `<div class="content">` wrapper | unwrapped — WeChat has no use for it, it only adds `class` noise |
| 2 | `<style>.article{font-size:15px;color:#666}</style>` | deleted entirely. WeChat strips `<style>` on paste, so a stylesheet is dead weight — the appearance had to be re-expressed as inline styles |
| 3 | `<script>console.log(...)</script>` | deleted entirely, children included. Also verified the script text does not leak into the output as visible text |
| 4 | half-width punctuation in Chinese text (`，` written as `,`) | converted to full-width **only when a CJK character is adjacent**, so `3.14` and `v1.2` survive untouched |
| 5 | no spacing between Chinese and Latin/digits (`用Python写第3个`) | inserted the conventional thin gap → `用 Python 写第 3 个` |
| 6 | 全角空格 (U+3000) at line start | stripped, along with U+00A0 and the other Unicode space look-alikes (see *uncertainties* — the sample did not actually contain one) |
| 7 | `<img src="https://example.com/photo.png">` — external image | kept, but restyled to `max-width:100%` and stripped of any width/height. See *uncertainties* — WeChat will not hotlink this |
| 8 | `<h4>` — "公众号只稳定支持两级标题" | collapsed to WeChat's two heading levels (see below) |
| 9 | `<h1>` document title | kept as a styled `<h1>` lead heading, centred |

## Design of the output

Everything is inline-styled, because that is the only styling that survives the WeChat
editor's sanitiser. No `class`, no `id`, no `style` block, no event handlers — the final
output contains only `style`, `src` and `alt` attributes.

Typography: 15px / line-height 1.8 / `letter-spacing:.5px` / `text-align:justify` — the
house style for Chinese 公众号 body copy. Accent colour is WeChat green `#07C160`.
Container is a `<section>` (what the WeChat editor itself emits), not a `<div>`.

**Heading levels.** `<h1>` is treated as the document title. Content headings `h2..h6`
are clamped onto two levels: `h2` → level 1 (18px bold with a green left bar), `h3` and
deeper → level 2 (16px bold with a small green dot). So the source's `<h4>` became a
level-2 heading.

**Images.** An image becomes `<p style="…text-align:center;line-height:0"><img …></p>`, i.e.
a centred block with `max-width:100%;height:auto`. No fixed width/height is emitted, so a
dead image collapses to a tiny placeholder instead of leaving a huge blank box. I checked
this by rendering the real file — `example.com` genuinely does not resolve, so the broken
state is what the screenshot shows, and the paragraph after it ("如果图片挂了，这一段也应该还能读。")
stays fully readable. `alt` is preserved, so the browser's broken-image fallback still
shows "远程图片".

## Robustness work (beyond the one sample)

The sample is tiny, so I also wrote a stress-test input and fixed two real bugs it exposed:

1. **An unclosed `<b>` swallowed the rest of the document.** Word exports forget closing
   tags constantly, and a single missing `</b>` turned every following paragraph bold.
   Fixed by implementing implied end tags: a block-level start tag now closes any still-open
   paragraph or inline element. `<img>` and `<br>` are deliberately excluded from that rule
   because they are legal inside a paragraph.
2. **A dead `<img>` produced an invisible paragraph**, because the image wrapper sets
   `line-height:0` for descender trimming. Now an image with no/`javascript:` `src` degrades
   to a normal paragraph containing its `alt` text, or is dropped if there is no alt.

The stress input also covers nested lists, blockquotes, tables with `colspan`, `<pre>`,
inline `<code>`, smart quotes, and `&lt;script&gt;` written as an HTML entity (correctly
re-escaped, not executed).

## Assumptions about the WeChat editor

These are the behaviours I designed against. They are the conventional wisdom for mp.weixin.qq.com
and match what I saw when rendering, but I could not paste into a live editor from here — treat
the first two as the ones most worth a manual smoke test.

- `<style>` blocks, `class`, `id`, `on*` and `<script>` do not survive a paste; inline
  `style=""` does. This drives the whole design.
- The tag vocabulary above is accepted (`section`, `p`, `h1`-`h6`, `img`, `a`, `strong`,
  `em`, `ul`/`ol`/`li`, `blockquote`, `table`, `pre`, `hr`).
- Body content width is ~677px, which is what `preview.html` uses for its phone frame.
- Copying *rendered* content from a browser carries inline styles but not the page's own
  CSS — hence `preview.html` puts its own styling on a wrapper that is outside the copy region.

## Things I am unsure about — worth checking

1. **The external image cannot work as-is.** WeChat rejects hot-linked third-party images
   on paste; the editor rewrites image `src` to its own CDN and, for a domain it cannot
   fetch, leaves it broken. The user must re-upload it through the editor's image button.
   I kept the placeholder rather than deleting it so it is obvious something belongs there,
   but this is a manual step I cannot do for them.
2. **WeChat's article *title* is a separate field.** The `<h1>` I preserved renders as an
   in-body heading. If the user sets the title in the editor's title box, they will end up
   with it twice and should delete the in-body `<h1>`.
3. **Whether the editor preserves `<h1>`-`<h6>` verbatim.** I styled them fully inline so the
   *look* survives even if the tag is normalised, but I have not confirmed the tag itself
   is retained. If it matters, swapping headings for styled `<section>`/`<p>` would be the
   safe fallback.
4. **The 全角空格 defect is described in the source prose but the sample file contains no
   U+3000 character.** I implemented the stripping anyway (real Word pastes are full of
   them) but it is untested against a real instance here.
5. **Smart quotes are speculative.** I convert ASCII `"` to `“”` inside CJK text with a
   pair-tracking toggle. The sample has no cases, and the pairing is per-block, so an
   unbalanced quote mark can flip the open/close state for the rest of that block.
6. **Heading clamping is a judgement call.** I mapped `h3..h6` all to level 2. An
   alternative reading of "只稳定支持两级标题" is to collapse by *document structure*
   (deepest heading becomes level 2 only if mid-levels exist). With this particular file
   there is only one content heading, so either rule looks fine — but on a long document
   with `h2/h3/h4` the difference would be visible.
7. **Emphasis inside headings/inline contexts** relies on `<strong>`/`<em>` being kept. A few
   WeChat themes restyle these; not something I could test.

## How to use it

```
python -I convert.py <messy.html> <out.wechat.html> [preview.html]
```

Then open `preview.html`, select inside the phone frame, copy, and paste into
mp.weixin.qq.com. Re-upload the image manually.
