# eval-1 (with_skill) — session notes

Task as given: "这篇有公式的文章要发公众号，帮我转成公众号格式：
...\skill\wechat-publisher-pro\evals\cases\formulas_and_tables.md"

Skill path: `...\C4B\skill\wechat-publisher-pro`
Procedure followed: read `SKILL.md` first, used only the commands it documents
(plus `--help` once, see Ambiguity #1). The sibling Python source was not read.

Input: `skill/wechat-publisher-pro/evals/cases/formulas_and_tables.md`
- 2 display equations (`$$...$$`), 3 inline (`$n-1$`, `$s^2$`, `$\bar{x} \pm s$`)
- 1 × 3-column table, 2 callouts (`[!KEY]`, `[!SUCCESS]`), 3 × `##` headings
- front matter: theme `minimal`, `toc: always`

## Commands run (in order)

All run from `...\C4B\skill\wechat-publisher-pro`, prefixed `PYTHONIOENCODING=utf-8 MPLBACKEND=Agg`.

```bash
mkdir -p "D:/.../eval-workspace/llm-qualitative/eval-1-with_skill/outputs"

# 1. SKILL.md quick start (§ line 29)
python scripts/convert_to_wechat.py evals/cases/formulas_and_tables.md "<OUT>/formulas_and_tables.html"

# 2. Inspect flags (see Ambiguity #1 — SKILL.md never mentions --fragment)
python scripts/convert_to_wechat.py --help

# 3. Final run: fragment + validate + report
python scripts/convert_to_wechat.py evals/cases/formulas_and_tables.md "<OUT>/formulas_and_tables.html" \
    --fragment --validate --report

# 4. SKILL.md §Verification, exact command
python scripts/wechat_validate.py "<OUT>/formulas_and_tables.html" --json          # exit 1
python scripts/wechat_validate.py "<OUT>/formulas_and_tables.fragment.html"        # exit 0
```

## Console output

Step 1:

```
✅ formulas_and_tables.md → formulas_and_tables.html
   主题 极简 · 黑白留白 ｜ 正文 333 字 ｜ 标题 3 ｜ 公式 5 ｜ 图片 0 ｜ callout 2 ｜ 框 4
   已写出：formulas_and_tables.html
```

Step 3 (exit 0):

```
✅ formulas_and_tables.md → formulas_and_tables.html
   主题 极简 · 黑白留白 ｜ 正文 333 字 ｜ 标题 3 ｜ 公式 5 ｜ 图片 0 ｜ callout 2 ｜ 框 4
   校验：14/14 通过
   已写出：formulas_and_tables.html，formulas_and_tables.fragment.html，formulas_and_tables.report.json
```

Step 4, standalone validator on `formulas_and_tables.html`:

```
"summary": {"total": 14, "passed": 13, "failed": 1, "warnings": 0, "ok": false,
            "failed_ids": ["allowed_tags_only"], ...}
"evidence": "<meta charset=\"utf-8\"/> | <meta content=\"width=device-width, ...\"/> |
             <title>用三个统计量判断数据是否可信</title> | … 共 4 处"
EXIT=1
```

Step 4, standalone validator on `formulas_and_tables.fragment.html`:

```
14/14 通过，0 项错误，0 项警告
EXIT=0
```

`formulas_and_tables.report.json` statistics:

```json
{"theme":"极简 · 黑白留白",
 "stats":{"headings":3,"paragraphs":16,"images":0,"formulas":5,"formulas_as_png":5,
          "embedded_images":5,"callouts":2,"user_tables":1,"toc_entries":3,
          "characters":333,"boxes":4},
 "warnings":[],
 "validation":{"total":14,"passed":14,"failed":0,"ok":true}}
```

## Formula handling — the question asked

**Outcome: correct. 5/5 formulas became embedded base64 PNG images. No raw text, no SVG.**

Verified by direct inspection of `formulas_and_tables.fragment.html`:

| Signal | Result |
|---|---|
| `<img>` tags | 5 |
| `data:image/png;base64,` data URIs | 5 |
| `svg` anywhere (case-insensitive) | absent |
| raw `$$` delimiters | absent |
| raw `\bar`, `\frac` | absent |
| MathML (`<math`) | absent |
| KaTeX/MathJax | absent |
| `report.json` → `formulas_as_png` | 5 / `formulas`: 5 |

Sizing looks sane — display equations are `display:block; max-width:100%; margin:16px auto 18px auto`
(widths 53px and 106px), inline ones `display:inline-block; vertical-align:middle` (10–22px).
LaTeX source is preserved losslessly in the `alt` attribute, e.g.
`alt="\bar{x} = \frac{1}{n}\sum_{i=1}^{n} x_i"`. Original LaTeX is therefore recoverable,
but note it also means the `alt` text is LaTeX, not a human-readable description — acceptable,
and SKILL.md does not claim otherwise.

No formula-related warnings were emitted, so nothing degraded to Unicode.

## Validation result

- Converter's own `--validate`: **14/14 pass, exit 0**.
- Standalone `wechat_validate.py` on the **fragment**: **14/14 pass, exit 0**.
- Standalone `wechat_validate.py` on the **full `formulas_and_tables.html`**: **13/14, exit 1** — see below.

## Ambiguity / defect found in SKILL.md

**#1 — `wechat_validate.py out.html` fails on the converter's own output.**

SKILL.md §Verification (lines 144–153) gives two interchangeable commands:

```bash
python scripts/convert_to_wechat.py article.md out.html --validate
python scripts/wechat_validate.py out.html --json
```

and states "Exit code is non-zero on failure, so it works in a CI step." But the second form
run against the file the quick start tells you to produce (`out.html`) fails with
`allowed_tags_only`, because `out.html` is a *full preview document* containing the
`<!DOCTYPE html> / <html> / <head> / <meta>×2 / <title> / <body> / <article>` scaffold
(the scaffold is deliberate — the preview file is meant to be opened in a browser).
The validator's whitelist is the WeChat-editor whitelist (`p/h2/h3/ul/ol/li/span/img/a/table/tr/th/td/br`),
so `meta`, `title` and `article` are reported as errors. Result: a correct article,
non-zero exit, CI red. The checker is only meaningful against the pasteable fragment.

The fix, which SKILL.md never states, is to validate the fragment file — which requires
`--fragment`, a flag **absent from SKILL.md entirely** (it appears only in `--help`, in
`references/cli_reference.md`, and as "额外输出纯片段文件（便于程序化粘贴与校验）").
`--validate` internally already does the right thing, so only the second documented command is affected.

Recommended wording: change line 146 to
`python scripts/wechat_validate.py out.fragment.html --json  # 需先加 --fragment 生成`
or note that the head scaffold is expected and must be excluded.

**#2 — "fragment html" is not a concept in SKILL.md.** The task asked for the fragment output;
SKILL.md's Workflow section only mentions one output file. A reader following SKILL.md alone
would produce only `out.html` and would hit #1. Minor, but it is what makes #1 easy to trip over.

**#3 — minor.** SKILL.md line 73 says "Auto table of contents | Generated when a post has ≥4 headings".
This source has 3 headings and still got a TOC (`toc_entries: 3`), because front matter set
`toc: always`. Correct behaviour, but the summary line reads as an absolute rule; the front-matter
`toc` key and the `--toc` flag override it and SKILL.md does not say so in that table
(it is covered only in `--help` / `references/cli_reference.md`).

Nothing else in SKILL.md was ambiguous; the quick start, theme resolution (front matter
`theme: minimal` → 极简 · 黑白留白), callout syntax and dependency handling all matched the
documented behaviour exactly. No warnings were emitted, so no dependencies were missing.

## Environment

Python 3.11.0 · markdown 3.11 · matplotlib 3.9.2 · pygments 2.18.0 · lxml, beautifulsoup4 present.
All optional deps available, so formulas rendered as PNG on the first try (no `--install-missing` needed).

## Steps taken

1. Read `SKILL.md` end to end.
2. Read the input `.md`; listed `scripts/` (did not open the Python sources).
3. Ran the documented quick-start conversion → success, 5 formulas detected.
4. Ran `--help` to find a way to emit the fragment the task asked for; found `--fragment`.
5. Re-ran with `--fragment --validate --report` → output dir now holds
   `formulas_and_tables.html`, `formulas_and_tables.fragment.html`, `formulas_and_tables.report.json`.
6. Ran the skill's own validation both ways (built-in and standalone, on both files).
7. Inspected the fragment programmatically for formula representation (PNG/SVG/text/MathML).

## Files saved to this directory

- `formulas_and_tables.html` — full preview document (what you open and Ctrl+A/Ctrl+C)
- `formulas_and_tables.fragment.html` — pasteable fragment (no head scaffold)
- `formulas_and_tables.report.json` — machine-readable stats + validation summary
- `session_notes.md` — this file

## Overall

Conversion **succeeded**. Formula requirement **met: 5/5 as embedded base64 PNG**. Validation
**14/14 on the fragment** (exit 0); the documented standalone command gives a false 13/14 /
exit 1 when pointed at the full preview file.
