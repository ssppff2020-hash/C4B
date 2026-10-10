# CLI reference

Every option, its default, and when to reach for it. Run
`python scripts/convert_to_wechat.py --help` for the same list on the command
line.

## Invocation

```bash
python scripts/convert_to_wechat.py <input> [output]
python scripts/convert_to_wechat.py <input...> --outdir <dir>
```

With one path, the output is written beside the input with an `.html`
extension. With two paths, the second is the output. Three or more paths require
`--outdir`.

`argparse` cannot combine a greedy positional list with an optional one — the
list swallows both — so the script accepts a flat list and treats the last path
as the output only when exactly two are given. That is why there is no separate
`output` argument in `--help`.

## Theme and typography

| Option | Default | Notes |
|---|---|---|
| `--theme NAME` | `default` | `default`, `accent`, `warm`, `minimal`, `tech`, `ink` |
| `--theme-file FILE` | — | JSON palette; missing tokens fall back to `default` |
| `--accent HEX` | — | Override just the accent colour |
| `--font-size N` | `16` | Body size in px; the whole scale shifts with it |
| `--heading-style` | from theme | `bar` (left rule), `underline`, `plain` |
| `--indent` | `none` | `2em` for the traditional first-line indent. WeChat articles normally use `none` |
| `--letter-spacing X` | `0.4` | px between characters. Above ~1px reads as loose for Chinese |
| `--divider` | `dots` | How `---` renders: `dots` (· · ·), `rule` (hairline), `none` |

## Chinese typography

| Option | Default | Notes |
|---|---|---|
| `--cjk-spacing` / `--no-cjk-spacing` | on | Space between CJK and Latin/digits |
| `--punct` | `safe` | `safe`: ellipses, stray ideographic spaces, and half-width `,;:!?` adjacent to Chinese characters (the Word-export case). `aggressive` adds half-width parentheses around Chinese content. `off` disables |
| `--nl2br` / `--no-nl2br` | on | A single newline becomes a line break. Matches the Chinese habit of one paragraph per source line |

The default `safe` level converts a half-width mark only when it is directly
adjacent to a Chinese character, which is never correct in Chinese prose and is
never ambiguous: `粘出来,没有空格` becomes `粘出来，没有空格`, while `a,b,c` and
`1,000` are left alone because their neighbours are Latin or digits, not Chinese.

`aggressive` adds half-width parentheses around Chinese content, which is opt-in
because a parenthesis may be a deliberate citation of code or a formula rather
than sloppy typing.

## Structure

| Option | Default | Notes |
|---|---|---|
| `--toc` | `auto` | `auto` inserts a TOC when the article has ≥4 headings |
| `--toc-min N` | `4` | Threshold for `auto` |
| `--numbered-toc` / `--plain-toc` | numbered | `1` / `1.1` versus dot-indented levels |
| `--header` | `auto` | `auto` = byline + digest; `full` also repeats the title; `off` = nothing |
| `--footer TEXT` | generated | Use `\n` for line breaks |
| `--no-footer` | — | Omit the footer entirely |

The TOC deliberately contains **no links**. WeChat strips `id` attributes, so
anchor targets cannot exist after publishing; a link that does nothing is worse
than a plain index. If a destination platform keeps anchors (Zhihu, a blog),
regenerate from the same Markdown there.

## Images, formulas, code

| Option | Default | Notes |
|---|---|---|
| `--image-mode` | `embed` | `embed` reads local files and inlines base64; `keep` leaves relative paths (only useful when a downstream tool rewrites them) |
| `--image-caption` / `--no-caption` | on | Alt text that reads like a sentence becomes a caption |
| `--math` | `png` | `png` renders via matplotlib; `unicode` converts macros to Unicode; `off` shows raw `$...$` in a code span |
| `--math-font-size N` | `18` | pt. Glyph size in the article is derived from this plus DPI |
| `--math-dpi N` | `200` | Higher is crisper and larger; 200 keeps a page of formulas under ~1 MB |
| `--highlight` / `--no-highlight` | on | Pygments with inline colours |
| `--callout-style` | `table` | `plain` emits a left-ruled paragraph run for editors that mangle tables |
| `--links` | `keep` | `keep` leaves `<a>` (WeChat de-links on save), `plain` inlines the URL, `footnote` collects them at the end, `strip` removes them |

## Output

| Option | Notes |
|---|---|
| `--outdir DIR` | Batch destination; output named after each source |
| `--also zhihu,plain` | Also write `.zhihu.md` and/or `.txt` |
| `--fragment` | Also write `<name>.fragment.html` — the paste-ready body without the preview shell, for automated paste or validation |
| `--report` | Also write `<name>.report.json` with stats, warnings and validation results |
| `--validate` | Run the compliance checks and print failures |
| `--validate-only` | Validate an existing HTML file instead of converting |
| `--quiet` | Suppress progress output; warnings still go to the report |

## Tools

| Option | Notes |
|---|---|
| `--list-themes` | Print built-in theme names |
| `--list-templates` | Print article templates |
| `--new FILE --template NAME --title "标题"` | Scaffold a draft with front matter and section skeleton |
| `--new-theme FILE` | Write a starter theme JSON to edit |
| `--author NAME` | Author for a scaffolded draft |
| `--install-missing` | Let the script pip-install missing dependencies |

## Verifying a published article

```bash
python scripts/check_published.py "https://mp.weixin.qq.com/s?__biz=..."
```

Fetches a live WeChat article and reports whether what went live is the rendered
HTML or raw Markdown. Exit code is non-zero if the paste was the source file
rather than the preview page. This is the only check that runs after the
clipboard, which is where the worst silent failure happens.

## Front matter

Any of the keys above can also be set per article. Command-line flags win, so a
one-off `--theme ink` does not require editing the file.

```yaml
---
title: 文章标题              # WeChat's own title field; used for <title> and --header full
author: 宋鹏飞
date: 2026-10-08
digest: 摘要会显示在标题下方，也是公众号的「摘要」字段
theme: accent
toc: always                  # auto | always | never
header: auto                 # auto | full | off
footer: |
  © 2026 宋鹏飞
  转载请联系授权
math: png
links: footnote
heading_numbers: true
---
```

`footer: |` preserves line breaks; `footer: >` folds them into one line.

## Exit codes

| Code | Meaning |
|---|---|
| 0 | Success |
| 1 | Conversion or validation failure |
| 2 | Missing required dependency |
