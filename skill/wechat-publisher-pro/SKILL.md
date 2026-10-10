---
name: wechat-publisher-pro
description: >
  Convert Markdown, Word (.docx) or HTML into publication-ready WeChat Official
  Account (公众号) article HTML that survives paste → save → publish: six themes,
  callout boxes, LaTeX to PNG formulas, syntax-highlighted code, auto table of
  contents, CJK typography, base64 image embedding, a compliance validator, plus
  Zhihu Markdown and plain-text exports from one source.
  Use this skill whenever the user wants to publish, format or typeset an article
  for a WeChat Official Account (公众号 / 微信公众平台 / mp.weixin.qq.com), even if
  they only say "帮我排版"、"转成公众号格式"、"发公众号"、"make this publishable on
  WeChat", or hand over a .md/.docx file and mention 公众号、推送、订阅号、服务号、
  图文消息. Also use it to turn Markdown into inline-CSS HTML for any rich-text
  editor, add a table of contents to a long post, make LaTeX survive an editor
  that strips MathML and SVG, or export one article to several platforms. Prefer
  it over hand-writing HTML for WeChat: the editor silently destroys scripts,
  styles, classes, divs, h1s and SVG.
---

# wechat-publisher-pro

Turn a Markdown or Word document into WeChat-ready HTML, then paste it into
`mp.weixin.qq.com` and publish.

```bash
python scripts/convert_to_wechat.py article.md article.html
```

Open `article.html` → `Ctrl+A` → `Ctrl+C` → paste into the WeChat editor.

## Why a converter is needed at all

The WeChat editor is not a browser. It has no stylesheet, no `<style>` tag, and
no CSS classes. On paste it silently:

| You write | What actually gets published |
|---|---|
| `<script>`, `<iframe>` | nothing |
| `<style>` block, `class="..."` | the tag, stripped of all its rules |
| `<h1>` | demoted — WeChat reserves h1 for the article title |
| `<div>` | flattened away |
| `<pre><code>` with newlines | collapses to one unreadable line |
| `<img src="data:image/svg+xml,...">` | disappears on save |
| any normal `http://` hyperlink | becomes plain text (only 公众号 links stay clickable) |

Because every element must carry its own `style="..."`, and because WeChat keeps
borders and padding on a **table cell** but drops them from an empty styled
`<p>`, this skill renders every framed element — callout, code block, TOC,
divider — as a single-cell table. That is the same technique the commercial
WeChat layout editors use, and it is why the output looks like a designed page
rather than a wall of paragraphs.

## Workflow

1. **Write** in Markdown. One paragraph per line, blank line between paragraphs.
   Optional YAML front matter carries title / author / date / digest / theme.
2. **Convert** with one command. The default settings are already the ones that
   publish well.
3. **Validate** with `--validate`. An article can look perfect in a browser and
   still be destroyed by the editor; this checks the rules that actually matter.
4. **Preview** the output HTML in a browser at phone width, then paste it into
   the WeChat editor and check it on a real phone.

Add `--fragment` when something downstream needs the article body on its own —
a scripted paste, a diff, or a validator run in CI. It writes
`<name>.fragment.html` alongside the preview page. `--also zhihu,plain` exports
the same article for other platforms, and `--report` writes machine-readable
stats and warnings.

## What this adds over a plain Markdown→HTML step

| Capability | How |
|---|---|
| Theme system | `--theme default\|accent\|warm\|minimal\|tech\|ink`, or `--theme-file my.json`, or `--accent "#0f766e"` |
| Callout boxes | `> [!NOTE] 标题` → framed box (9 kinds: note/tip/key/warning/danger/success/example/confused/quote) |
| Auto table of contents | Generated when a post has ≥4 headings (`--toc` / front matter `toc:` override the threshold); no dead anchor links |
| LaTeX formulas | `$x$` / `$$x$$` → base64 **PNG**, the only format WeChat keeps |
| Syntax-highlighted code | Pygments, colours inlined per token (class-based themes would be stripped) |
| Chinese typography | CJK↔Latin spacing, ellipsis normalisation, and the half-width `,;:!?` that Word exports leave behind when they sit next to Chinese characters |
| Image handling | Local files → base64 so they land in the WeChat media library; alt text → captions; missing files flagged in place |
| Article metadata | Front matter → byline, digest box, `<title>` |
| Footer / copyright | Generated from the author name or set explicitly |
| Compliance validation | 14 structural checks, each naming the offending element |
| Batch conversion | `convert_to_wechat.py drafts/*.md --outdir dist/` |
| Multi-platform export | `--also zhihu,plain` from one source |
| Article templates | `--new post.md --template tech-tutorial` scaffolds structure |
| Word documents | Tables, lists, and embedded images keep their position |

## Callout syntax

```markdown
> [!NOTE] 可选标题
> 正文，可以有多段。
> 同一个框里继续写。
```

Consecutive callouts in one block are handled correctly — Markdown merges them
into a single blockquote, and the converter splits them back out. Full list of
kinds and how to add your own: `references/callouts.md`.

## Themes

Six ship built in. A theme is a palette plus two structural choices, and the
inline CSS is *derived* from the palette, so changing `accent` moves the heading
rule, table header, quote border and TOC tint together.

```bash
python scripts/convert_to_wechat.py article.md out.html --list-themes
python scripts/convert_to_wechat.py article.md out.html --theme ink
python scripts/convert_to_wechat.py --new-theme my-theme.json   # then edit
python scripts/convert_to_wechat.py article.md out.html --theme-file my-theme.json
```

Callout colours are deliberately *not* themed: a warning is amber and a danger
box is red in every palette, because those are meanings, not decoration.
Details and the token list: `references/wechat_styles.md`.

## Formulas

`$E = mc^2$` inline, `$$...$$` on its own line for display. Rendered to PNG via
matplotlib's mathtext at 200 dpi and embedded as a data URI.

Sizing is a constant scale derived from the render DPI, so glyphs are the same
size in every formula regardless of how tall the formula is. Display equations
are set 25% larger than body text.

mathtext implements a large subset of LaTeX but not all of it — `\usepackage`,
`\begin{align}`, and custom macros will fail. Unsupported macros are rewritten
where an equivalent exists, and any formula that still fails degrades to Unicode
text with a warning rather than breaking the article. Use `--math unicode` to
skip matplotlib entirely.

## Images

`![一句话描述](images/diagram.png)` — a relative path is read and embedded as
base64, so the picture travels with the HTML and enters the WeChat media library
on paste. Alt text that reads like a sentence becomes a caption; alt text that
looks like a filename is ignored. Missing files are replaced by a visible amber
box naming the path, so you notice while the source is still open.

Remote `https://` images are kept as-is with a warning: WeChat will not fetch
them, so you must click "upload image" once in the editor or they vanish on
publish. Use local files to avoid this.

## Verification

```bash
# during conversion
python scripts/convert_to_wechat.py article.md out.html --validate

# or on an existing file, standalone
python scripts/wechat_validate.py out.html --json
```

Both spellings check the same 14 rules and accept either file: the preview page
(`out.html`) or the bare fragment (`--fragment` also writes `out.fragment.html`).
Page furniture — `<head>`, `<meta>`, `<title>`, the preview `<article>` wrapper —
is stripped before checking, so the preview page scores the same as its fragment.

The rules: no forbidden tag, class, id, event handler, or unsupported CSS
property survived; every block element is inline-styled; images are embedded or
flagged; no `<p>` nests a `<p>`; no Markdown marker was left unconverted (a failed
callout shows up as a literal `[!NOTE]`). Exit code is non-zero on failure, so it
works in a CI step.

### After publishing — check what actually went live

```bash
python scripts/check_published.py "https://mp.weixin.qq.com/s?__biz=..."
```

Everything above validates the file *before* it reaches WeChat. Nothing can see
what happens between the clipboard and the editor, and the failure mode there is
severe and silent: if the **source `.md` is copied instead of the rendered
`.html`**, the published post shows raw YAML front matter and literal `##`
headings. A browser renders `.md` as plain text, so copying from the wrong tab
produces exactly that.

This script fetches the published page and reports whether the body is rendered
HTML (tables, inline styles, CDN images present) or leftover Markdown (fenced
blocks, `**`, `[!NOTE]`). Run it once after publishing; it is the only check that
sees the real result.

## More detail

Read these only when the task needs them:

| File | Read it when |
|---|---|
| `references/cli_reference.md` | You need a flag that is not in the quick start — every option, with defaults |
| `references/wechat_restrictions.md` | You need to know exactly what WeChat allows, or the user asks why something was removed |
| `references/wechat_styles.md` | You are changing the look: palette tokens, typography scale, heading styles |
| `references/callouts.md` | You want a callout kind that does not exist, or need richer content inside a box |
| `references/troubleshooting.md` | Something looks wrong after pasting, or a formula/image/document did not convert as expected |

## Dependencies

```bash
python -m pip install markdown beautifulsoup4 lxml python-docx
python -m pip install matplotlib pygments   # optional: formulas, syntax colours
```

The converter checks these on start and prints the exact install command rather
than installing anything on its own — pass `--install-missing` to let it. Missing
optional packages degrade gracefully (formulas fall back to Unicode, code blocks
lose colour) and the run says so.

## Edge cases

| Situation | Behaviour |
|---|---|
| Empty file | Reported as an error; no empty HTML is written |
| Non-UTF-8 encoding | utf-8-sig → utf-8 → gb18030 → big5, in order |
| Article over ~20,000 characters | Converted, with a warning about WeChat's limit |
| Table wider than 5 columns | Converted, with a warning that it will be cramped on a phone |
| `h4` and deeper headings | Merged into `h3` with a warning — WeChat only styles two heading levels reliably |
| Unknown callout kind | Left as an ordinary quote, with a warning naming it |
| SVG image | Warning that WeChat discards SVG on save |
| External links | Warning that they will become plain text; `--links footnote` moves them to the end |
