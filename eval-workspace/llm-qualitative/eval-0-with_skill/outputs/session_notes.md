# Session notes — wechat-publisher-pro, eval-0 (with skill)

## Task
Convert `evals/cases/tutorial_with_code.md` into WeChat-ready article HTML, following SKILL.md only.

## Environment
- cwd for commands: `.../C4B/skill/wechat-publisher-pro`
- Prefix: `PYTHONIOENCODING=utf-8 MPLBACKEND=Agg`
- Script paths given explicitly, as the skill requires.

## Commands run (in order)

1. `Read SKILL.md` — the only skill doc read before acting.
2. `ls` skill dir + `scripts/` and previewed the input `.md` (YAML front matter:
   title/author/date/digest, `theme: accent`; 4 h2 headings, 1 table, 2 code
   blocks, 3 callouts).
3. Conversion, first attempt (documented quick-start form):

   ```
   PYTHONIOENCODING=utf-8 MPLBACKEND=Agg python scripts/convert_to_wechat.py \
     evals/cases/tutorial_with_code.md \
     <outputs>/tutorial_with_code.html --validate
   ```

   Console output:

   ```
   ✅ tutorial_with_code.md → tutorial_with_code.html
      主题 蓝调 · 科技清晰 ｜ 正文 734 字 ｜ 标题 4 ｜ 公式 0 ｜ 图片 0 ｜ callout 3 ｜ 框 7
      校验：14/14 通过
      已写出：tutorial_with_code.html
   ```

4. Standalone validator (as documented in SKILL.md "Verification"):

   ```
   python scripts/wechat_validate.py <outputs>/tutorial_with_code.html --json
   ```

   Result: **exit 1, 13/14 passed**, one error:
   `allowed_tags_only` fails on `<meta>`, `<meta>`, `<title>` (4 occurrences) —
   i.e. the `<head>` of the preview shell, not the article body.

5. Searched `references/cli_reference.md` (the doc SKILL.md says to read when a
   flag is not in the quick start) for preview/fragment/validate flags.
   Found: `--fragment` — "Also write `<name>.fragment.html` — the paste-ready
   body without the preview shell, for automated paste or validation".

6. Re-ran conversion with `--fragment --validate`, then validated the fragment:

   ```
   python scripts/convert_to_wechat.py evals/cases/tutorial_with_code.md \
     <outputs>/tutorial_with_code.html --fragment --validate
   python scripts/wechat_validate.py <outputs>/tutorial_with_code.fragment.html
   ```

   Both the built-in `--validate` and the standalone validator on the fragment
   report **14/14 passed, 0 errors, 0 warnings, exit 0**.

## Files produced
- `tutorial_with_code.html` — preview page (640px shell, `<head>` + byline/digest/TOC, then the body)
- `tutorial_with_code.fragment.html` — paste-ready body only, no shell

## Steps / tool calls
7 steps total (1 Read, 6 Bash). Conversion itself: 2 command invocations
(1st without `--fragment`, 2nd with) + 2 validation invocations. A single
`--fragment --validate` run would have sufficed end-to-end.

## Ambiguities in SKILL.md (things I had to guess or that misled)

1. **`--fragment` is not in SKILL.md at all.** It is documented only in
   `references/cli_reference.md`. SKILL.md's quick start and Workflow sections
   never mention it, so the "produced fragment" is invisible to anyone following
   SKILL.md alone. I only found it by grepping the CLI reference after the
   validator failed.

2. **The documented standalone-validation command fails on the documented
   default output.** SKILL.md's "Verification" section lists
   `python scripts/wechat_validate.py out.html --json` right after the converter
   command, implying it validates that file — but `out.html` is the preview page,
   and its `<head>` (`meta`/`title`) trips the `allowed_tags_only` whitelist check
   (exit 1). This reads as a false failure; the validator is only meaningful on
   the `--fragment` body. SKILL.md would be much clearer if the Verification
   section either (a) showed `--fragment` alongside the converter invocation, or
   (b) said the standalone validator expects the fragment, not the preview page.

3. **Two validation results disagree with no explanation.** `convert --validate`
   on the preview page says 14/14 pass; `wechat_validate.py` on the same file
   says 13/14. Nothing in SKILL.md explains that the built-in check validates the
   body while the standalone one validates whatever file/whole document it is
   given. Resolved only by reading the CLI reference.

4. **Minor:** the callout/`blockquote` behaviour and most flags were clear;
   no other guessing needed. Front matter `theme: accent` was honoured
   (output theme "蓝调 · 科技清晰"). The "no external links" warning path was not
   exercised because the sample contains no links.

## Anything that went wrong
- Nothing destructive and no crashes. The only friction was item 2/3 above: the
  literal reading of SKILL.md's Verification section produces an exit-1
  validation on a perfectly good article, which would look like a skill failure
  to a user who does not open `cli_reference.md`.
