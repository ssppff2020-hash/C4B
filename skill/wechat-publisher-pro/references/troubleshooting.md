# Troubleshooting

Symptoms first. Each entry says what you see, what actually causes it, and what
to do.

## After pasting into WeChat

### The callout boxes became literal `[!WARNING]` text

A paragraph inside a blockquote began with `[!SOMETHING]` that is not a known
kind, so it was left as a quote. Run with `--validate`: the
`no_markdown_leftovers` check names it. Check the spelling against the table in
`references/callouts.md` — the marker must be at the very start of the line, with
no leading space.

### All my images disappeared on publish

They were `https://` URLs. WeChat does not fetch remote images; you must click
"upload image" on each one in the editor. Use local paths instead and let the
converter embed them as base64 — those are re-uploaded to the WeChat CDN
automatically on paste. The run prints a warning when it sees a remote image.

If the images were already local and still vanished, they were SVG. WeChat
discards SVG on save. Export to PNG.

### Formula images disappeared

Same as SVG: the source was a data URI carrying SVG (for example an `<img>` you
already had in the HTML). Re-run from Markdown with `$...$` so the formula is
rendered to PNG, or `--math png`.

### My links are not clickable

Expected. Only links to `mp.weixin.qq.com` stay clickable. Use
`--links footnote` to collect the destinations under a "参考链接" heading at the
end of the article, or `--links plain` to write them inline.

### Spacing looks tighter or looser than the preview

The editor collapses block margins differently from a browser. The converter
compensates by using longhand `margin-top`/`margin-bottom` everywhere and by
carrying spacing on real elements rather than empty paragraphs. If a specific
block still looks wrong, set an explicit margin on it via the theme rather than
adding blank lines — the editor is free to delete an empty paragraph.

### Headings all look the same size

WeChat only styles two heading levels reliably. `h4` and deeper are merged into
`h3`, and the run reports how many. If you need a third visual level, use a
callout or a bold lead-in paragraph instead.

### Bolding lost its emphasis

`<strong>`/`<b>` are replaced by `<span style="font-weight: bold">` because
tag-based bolding renders inconsistently across WeChat themes. If a bold passage
still looks flat, the source may have used `__bold__` inside a table cell, which
Markdown's table extension handles less predictably — use `**bold**`.

## During conversion

### "None of my tables or images came through" (Word input)

Fixed in this version. The original starter walked `doc.paragraphs`, which
silently skips everything that is not a paragraph — every table and every
embedded picture. This converter walks the document body in order, so tables
keep their position and images are extracted from the document package as
base64.

### Formulas render as plain text like `x_i²`

matplotlib is missing, so the renderer fell back to Unicode. Either install it
(`python -m pip install matplotlib`) or accept the fallback — `--math unicode`
makes the choice explicit. Some formulas have no Unicode equivalent (matrices,
`\begin{align}`) and will stay partly literal; that is a real limit of the
fallback, not a bug.

### A formula failed but the rest worked

matplotlib's `mathtext` implements a large subset of LaTeX, not all of it. Common
macros are rewritten (`\dfrac` → `\frac`, `\text{...}` → `\mathrm{...}`), but
environments like `align` and anything needing `\usepackage` will not work. The
warning names the formula. Simplify it, or split it into separate `$$...$$`
blocks.

### `**` shows up literally, or italic text where I wanted maths

Markdown ate the markup. This is why the converter masks inline code and
formulas *before* parsing: without it, `a_1` loses its underscore to emphasis and
`a*b*c` turns italic. If you see this, you are looking at output from a version
before that masking, or from a different tool.

### Chinese text has stray spaces mid-sentence

Two possible causes.

- **A real inserted space** — check whether the boundary is CJK↔Latin. That space
  is intended and improves readability. `--no-cjk-spacing` turns it off.
- **Not a space at all** — ASCII quotes and brackets in a CJK font have wide side
  bearings. `，" 用` looks spaced in the browser but is not. Check the raw HTML
  before chasing it.

### `UnicodeDecodeError` or mojibake in the output

The source file is not UTF-8. The reader tries utf-8-sig, utf-8, gb18030, then
big5 before giving up, which covers Windows-exported Chinese documents; if the
text still looks wrong, re-save the source as UTF-8.

### The script tells me a dependency is missing instead of installing it

Deliberate. The starter kit ran `pip install` on first use, which either fails
confusingly or installs something you did not ask for in a managed environment.
Run the printed command, or pass `--install-missing` to opt in.

### "多个输入请用 --outdir 指定输出目录"

Three or more paths were passed without `--outdir`. With one path the output is
derived from the input; with two the second is the output; beyond that the
destination is ambiguous, so use `--outdir`.

### `run_eval.py` says it cannot find the eval definitions

You are running it from an installed `.skill` package. `evals/` is a development
artifact and `skill-creator`'s packager excludes it on purpose — an installed
skill does not need its own test suite. Run the eval from the source tree
(`C4B/skill/wechat-publisher-pro/`) instead. Conversion and validation work
normally either way.

### I scripted the copy step and my emoji turned into `?`

If you try to skip the browser's Ctrl+A/Ctrl+C by putting the article on the
clipboard from a script, do not use .NET's `Clipboard.SetText(text,
TextDataFormat.Html)`. On a Chinese Windows install it encodes the CF_HTML
payload with the **system ANSI codepage (GBK)**, and every emoji is replaced by
`?` -- `👍` (U+1F44D) becomes `0x3F 0x3F`. Measured, not theorised.

What makes it nasty is that **the length does not change**: a surrogate pair is
two UTF-16 units and becomes two `?` characters, so every size check still
passes. You would publish an article whose callout labels are `? 知识点`.

Two further traps in the same API: it does **not** add the CF_HTML header
(consumers then paste the literal tags), and passing a `byte[]` through
`DataObject.SetData` stringifies it -- the clipboard ends up holding the text
`System.Byte[]`.

**Just copy from the browser instead.** `Ctrl+A` → `Ctrl+C` on the preview page
produces standards-conformant UTF-8 CF_HTML, because that is what browsers write.
It is two keystrokes and it is correct; a home-made clipboard writer has to beat
that on both counts and usually does not.

If you do go down this path anyway, verify by reading the clipboard back and
slicing it with its own recorded `StartFragment`/`EndFragment` offsets -- and
check that an emoji survived, because that is the failure that hides.

### The published article shows raw Markdown (`---`, `##`, `**`)

The source `.md` was copied instead of the rendered `.html`. A browser renders
Markdown files as **plain text**, so opening `article.md` and pressing Ctrl+A /
Ctrl+C copies the literal source — front matter, fences, heading hashes and all.

Check it, then fix it:

```bash
python scripts/check_published.py "<the published URL>"
```

To avoid it: copy from the **preview page** (`*_output.html`), never from the
`.md`. You can tell you are on the right page before copying — the preview shows
blue accent bars on headings, coloured callout boxes and no `---` or `##`
anywhere. If you see `title:` or a line of hashes, you are on the wrong file.

Delete the bad post and re-publish; the URL and the account's send quota are the
only things lost.

## Validator reports a failure

Run `python scripts/wechat_validate.py out.html` for the readable form. Each
check names the offending element.

| Check | What it means | Fix |
|---|---|---|
| `no_forbidden_tags` | A `script`/`style`/`div`/`pre` survived | A transform failed — report it; nothing in the pipeline should emit these |
| `allowed_tags_only` | A tag outside the whitelist | Same as above |
| `no_class_or_id` | A class or id was left | Styling must be inline; check any custom post-processing |
| `inline_styles_present` | A block element has no `style` | It will fall back to the editor's defaults and break the rhythm |
| `css_props_supported` | An unsupported property | Move it into the theme, or drop it — WeChat strips it anyway |
| `images_embedded_or_remote_flagged` | An SVG, empty, or remote image | Warning only; see the image section above |
| `well_formed_structure` | A `<p>` contains a `<p>`, or a cell lost its table | Report it — the splitter should have handled this |
| `no_markdown_leftovers` | `**`, `](`, a leading `#`, or a leading `[!TYPE]` | A transform silently failed; the evidence string shows where |

### The validator disagrees with `--validate`

It should not, and if it does that is a bug worth reporting. Both accept either
the preview page or the fragment, and both strip the preview's `<head>`,
`<meta>`, `<title>` and `<article>` wrapper before checking. (An earlier version
only stripped `<html>`/`<body>`, so validating the preview page reported the page
furniture as violations and exited non-zero on a perfectly good article.)

The check reads code-styled spans as data, not prose, so an article that
*documents* this syntax (like `examples/sample_article.md`) passes cleanly.

## Extending the code

### Adding a theme

Add a palette to `PALETTES` in `scripts/themes.py`. Missing tokens are filled
from `default`. Do not write CSS by hand — `build_styles()` derives every string
from the palette, and hand-written styles will not follow a palette swap.

### Adding a callout kind

Two entries in `scripts/themes.py`: one in `CALLOUT_TYPES`, and a colour family
in `CALLOUT_COLORS` if none fits. See `references/callouts.md`.

### Why the pipeline order matters

Stages in `scripts/render.py` are ordered by dependency, not preference. In
particular:

- Formulas and inline code are masked **before** Markdown runs, or Markdown
  consumes their punctuation.
- Callouts are detected **before** blockquotes are flattened, or the `[!TYPE]`
  marker is already gone.
- Typography runs **after** generated furniture is tagged `data-wp-skip`, or it
  would re-space code lines and bylines.
- Generated boxes are tagged `data-wp-box` so the table stage does not restyle
  them, and the bookkeeping attributes are stripped in the final cleanup — none
  of them reach WeChat.

Reordering these without re-reading the module docstring will break something
that currently works.
