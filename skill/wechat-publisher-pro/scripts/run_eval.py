#!/usr/bin/env python3
"""
Run the skill's eval suite and compare it against a no-skill baseline.

Why a deterministic harness instead of an LLM judge: this skill's output is
mechanically checkable.  "Does every code line survive?", "did the formula become
a PNG and not an SVG?", "is there a class attribute anywhere?" -- none of these
need judgement, and a script answers them the same way on every run, on every
machine.  That also makes the suite usable as a regression test after any change
to the pipeline.

The with-skill runs go through the **command line interface as a subprocess**,
not through the library API.  That distinction matters: the documented interface
is what users and CI actually call, and an earlier library-only harness reported
19/19 while the CLI itself had a fatal argument-parsing bug.

The baseline is what you get with **no skill at all**: the standard Markdown
conversion, wrapped in a minimal page, with none of WeChat's rules applied.  That
is the honest comparison -- it is what the user would have produced by hand.

Workspace layout follows the skill-creator convention so its review viewer can
read the results directly::

    <workspace>/iteration-1/
        benchmark.json / benchmark.md
        eval-0-tutorial-with-code/
            eval_metadata.json
            with_skill/outputs/…, grading.json, timing.json
            without_skill/outputs/…, grading.json, timing.json

Usage::

    python scripts/run_eval.py                       # iteration-1, full suite
    python scripts/run_eval.py --iteration 2
    python scripts/run_eval.py --only 0,2
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

SKILL_DIR = _HERE.parent
EVALS_PATH = SKILL_DIR / "evals" / "evals.json"
CASES_DIR = SKILL_DIR / "evals" / "cases"

from converters import read_text, split_front_matter          # noqa: E402
from wechat_validate import summarize, validate_fragment      # noqa: E402

NAIVE_SHELL = """<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>%s</title></head>
<body>
%s
</body></html>
"""


# --------------------------------------------------------------------------
# Baseline: plain Markdown -> HTML, no WeChat handling
# --------------------------------------------------------------------------
def baseline_convert(source: Path) -> str:
    """What a straightforward Markdown-to-HTML step produces."""
    import markdown

    raw = read_text(source)
    if source.suffix.lower() == ".docx":
        from converters import read_docx
        html_text = read_docx(source)
    elif source.suffix.lower() in (".html", ".htm"):
        html_text = raw
    else:
        _meta, body = split_front_matter(raw)
        html_text = markdown.markdown(
            body, extensions=["extra", "fenced_code", "nl2br"])
    return NAIVE_SHELL % (source.stem, html_text)


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
def _plain_text(fragment: str) -> str:
    """Tag-stripped text with HTML entities resolved and nbsp normalised.

    Without the unescape step a source line containing ``>`` can never match:
    the rendered code escapes it to ``&gt;``, so a correct conversion would be
    reported as a failure.
    """
    text = re.sub(r"<[^>]+>", "", fragment)
    text = html.unescape(text)
    return text.replace("\xa0", " ")


def _png_data_uris(fragment: str) -> int:
    return len(re.findall(r'src="data:image/png;base64,', fragment))


# --------------------------------------------------------------------------
# Eval-specific assertions.  Signature: (source, fragment, extras) -> (bool, str)
# --------------------------------------------------------------------------
def _code_lines_preserved(source, fragment, extras):
    """Every non-empty source line of a fenced block must reach the output.

    Regression test for the starter kit's worst bug: it put a whole code block
    into one ``<p>``, WeChat collapsed the newlines, and the sample came out as a
    single unreadable line.
    """
    raw = read_text(source)
    blocks = re.findall(r"```[^\n]*\n(.*?)```", raw, re.S)
    if not blocks:
        return True, "no fenced code in source"
    text = re.sub(r"\s+", " ", _plain_text(fragment))
    missing = []
    for block in blocks:
        for line in block.split("\n"):
            stripped = re.sub(r"\s+", " ", line.strip())
            if len(stripped) > 3 and stripped not in text:
                missing.append(stripped[:40])
    return (not missing,
            "all lines present" if not missing else "missing: %s" % missing[:3])


def _formula_rendered_as_png(source, fragment, extras):
    raw = read_text(source)
    formulas = re.findall(r"\$\$(.+?)\$\$", raw, re.S) + \
        re.findall(r"(?<!\$)\$(?!\$)([^$\n]{1,400}?)\$(?!\$)", raw)
    if not formulas:
        return True, "no formulas in source"
    found = _png_data_uris(fragment)
    return found >= len(formulas), \
        "source %d formulas, output %d PNG data URIs" % (len(formulas), found)


def _no_svg_images(source, fragment, extras):
    bad = re.findall(r'data:image/svg\+xml|\.svg"', fragment)
    return not bad, "none" if not bad else "found %d" % len(bad)


def _toc_generated(source, fragment, extras):
    ok = "目 录" in fragment or "目录" in fragment
    return ok, "toc present" if ok else "no toc block found"


def _callout_count_at_least(n):
    def check(source, fragment, extras):
        raw = read_text(source)
        declared = len(re.findall(r"^\s*>?\s*\[!\w+\]", raw, re.M))
        rendered = len(re.findall(r"(📘|💡|🔑|⚠️|🚨|✅|🧪|🤔|💬)\s", fragment))
        ok = rendered >= n and rendered >= declared
        return ok, "source %d callouts, rendered %d (need >=%d)" % (
            declared, rendered, n)
    return check


def _tables_styled(source, fragment, extras):
    tables = re.findall(r"<table[^>]*>", fragment)
    styled = [t for t in tables if "style=" in t]
    user = [t for t in tables if "border-collapse" in t]
    ok = bool(user) and len(styled) == len(tables)
    return ok, "%d tables, %d with inline style" % (len(tables), len(styled))


def _h1_demoted(source, fragment, extras):
    ok = "<h1" not in fragment
    return ok, "h1 removed" if ok else "h1 survived"


def _h4_merged(source, fragment, extras):
    raw = read_text(source)
    if re.search(r"^\s*####\s+\S|<h4", raw, re.M) is None:
        return True, "no h4 in source"
    ok = "<h4" not in fragment and "<h3" in fragment
    return ok, "merged into h3" if ok else "h4 handling wrong"


def _cjk_spacing_applied(source, fragment, extras):
    """Every CJK-Latin boundary must have gained a space."""
    text = _plain_text(fragment)
    joined = re.findall(r"[一-鿿][A-Za-z0-9]", text)
    spaced = re.findall(r"[一-鿿] [A-Za-z0-9]", text)
    ok = bool(spaced) and not joined
    return ok, "spaced=%d, unspaced=%d" % (len(spaced), len(joined))


def _punct_cleaned(source, fragment, extras):
    """No half-width sentence punctuation left adjacent to a Chinese character.

    Found by an independent tester: the default ``--punct safe`` used to skip
    these, so an article pasted out of Word kept its ``粘出来,没有空格`` and the
    user reasonably concluded the converter had not done its job.
    """
    text = _plain_text(fragment)
    offenders = re.findall("[一-鿿][,;:!?]", text)
    return not offenders, "none" if not offenders \
        else "still half-width: %s" % offenders[:5]


def _preview_page_validates(source, fragment, extras):
    """The validator must pass on the *preview page*, not just the fragment.

    Found by three independent testers: ``wechat_validate.py out.html`` used to
    report the preview's ``<head>``/``<meta>``/``<title>``/``<article>`` as
    violations and exit non-zero on a correct article.
    """
    preview = extras.get("preview")
    if not preview:
        return False, "preview page was not produced"
    summary = summarize(validate_fragment(preview))
    return summary["ok"], "preview %d/%d passed" % (summary["passed"],
                                                    summary["total"])


def _zhihu_export_is_markdown(source, fragment, extras):
    """The Zhihu export must be Markdown even when the input was raw HTML.

    Found by an independent tester: HTML input was copied verbatim into the
    ``.zhihu.md`` file, ``<script>``, ``<style>`` and ``<h1>`` included.
    """
    path = extras.get("zhihu_md")
    if path is None:
        return False, "no zhihu export was written"
    text = Path(path).read_text(encoding="utf-8")
    if not text.strip():
        return False, "zhihu export is empty"
    bad = [t for t in ("<script", "<style", "<h1", "<div", "class=") if t in text]
    return not bad, "clean markdown" if not bad else "contains %s" % bad


def _remote_image_flagged(source, fragment, extras):
    """A remote image must produce an explicit warning, not silence.

    WeChat does not fetch remote images, so the picture disappears on publish.
    An author who is told at conversion time can click "upload" once; an author
    who is not told finds out from a reader.
    """
    raw = read_text(source)
    if not re.search(r'<img[^>]+src=["\']https?://', raw):
        return True, "no remote image in source"
    console = extras.get("console", "")
    ok = "外部图片" in console
    return ok, "warning raised" if ok else "no warning in console output"


ASSERTIONS = {
    "code_lines_preserved": (_code_lines_preserved,
                             "代码块每一行都完整保留（未被公众号折叠成一行）"),
    "callout_count_at_least": (_callout_count_at_least,
                               "源文件中声明的 callout 全部渲染成方框"),
    "formula_rendered_as_png": (_formula_rendered_as_png,
                                "所有公式都渲染为 base64 PNG"),
    "no_svg_images": (_no_svg_images, "输出中没有 SVG 图片"),
    "toc_generated": (_toc_generated, "长文自动生成目录"),
    "tables_styled": (_tables_styled, "表格带 inline 样式与表头"),
    "h1_demoted": (_h1_demoted, "h1 已降级为 h2"),
    "h4_merged": (_h4_merged, "h4 及更深的标题已归并为 h3"),
    "cjk_spacing_applied": (_cjk_spacing_applied, "中英文之间已自动补空格"),
    "punct_cleaned": (_punct_cleaned, "中文旁的半角标点已规范为全角"),
    "preview_page_validates": (_preview_page_validates,
                               "校验器直接跑预览页也能通过（不误报页面外壳）"),
    "zhihu_export_is_markdown": (_zhihu_export_is_markdown,
                                 "知乎导出是干净的 Markdown（即使输入是 HTML）"),
    "remote_image_flagged": (_remote_image_flagged,
                             "远程图片会给出明确提示（否则发布后才发现丢图）"),
}


# --------------------------------------------------------------------------
# Grading
# --------------------------------------------------------------------------
def grade(fragment: str, source: Path, assertion_ids: list[str],
          extras: dict | None = None) -> list[dict]:
    """Return one ``{text, passed, evidence}`` record per assertion.

    Structural assertion ids are answered by the shipped validator, so the eval
    and the user-facing ``--validate`` cannot drift apart.
    """
    extras = extras or {}
    checks = {c.id: c for c in validate_fragment(fragment)}
    results: list[dict] = []
    for raw_id in assertion_ids:
        name, _, arg = raw_id.partition(":")
        entry = ASSERTIONS.get(name)
        if entry is not None:
            # Parameterised assertions are factories: "callout_count_at_least:3"
            # calls the factory with 3 to obtain the actual check.
            func = entry[0](int(arg)) if arg else entry[0]
            passed, evidence = func(source, fragment, extras)
        else:
            check = checks.get(name)
            if check is None:
                passed, evidence = False, "unknown assertion"
            else:
                passed, evidence = check.passed, (check.evidence or "ok")
        results.append({"text": raw_id, "passed": bool(passed),
                        "evidence": evidence})
    return results


# --------------------------------------------------------------------------
# Runner
# --------------------------------------------------------------------------
def _run_cli(source: Path, out_html: Path) -> tuple[int, str, float]:
    """Invoke the converter exactly as the documentation tells a user to."""
    cmd = [sys.executable, str(_HERE / "convert_to_wechat.py"),
           str(source), str(out_html),
           "--fragment", "--report", "--validate", "--also", "zhihu,plain"]
    env = dict(os.environ, PYTHONIOENCODING="utf-8", MPLBACKEND="Agg",
               PYTHONUTF8="1")
    started = time.perf_counter()
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", env=env, cwd=str(SKILL_DIR))
    return proc.returncode, (proc.stdout or "") + (proc.stderr or ""), \
        time.perf_counter() - started


def run_suite(workspace: Path, iteration: int, only: list[int] | None = None):
    spec = json.loads(EVALS_PATH.read_text(encoding="utf-8"))
    out_root = workspace / ("iteration-%d" % iteration)
    out_root.mkdir(parents=True, exist_ok=True)

    records = []
    for case in spec["evals"]:
        if only and case["id"] not in only:
            continue
        source = CASES_DIR / Path(case["files"][0]).name
        case_dir = out_root / ("eval-%d-%s" % (case["id"], case["name"]))
        case_dir.mkdir(parents=True, exist_ok=True)

        (case_dir / "eval_metadata.json").write_text(json.dumps({
            "eval_id": case["id"],
            "eval_name": case["name"],
            "prompt": case["prompt"],
            "assertions": case["assertions"],
        }, ensure_ascii=False, indent=2), encoding="utf-8")

        # ---- with skill, through the documented CLI ----------------------
        ws = case_dir / "with_skill"
        outputs = ws / "outputs"
        outputs.mkdir(parents=True, exist_ok=True)
        out_html = outputs / (source.stem + ".html")
        code, console, elapsed = _run_cli(source, out_html)

        (outputs / "console.txt").write_text(console, encoding="utf-8")
        fragment_path = outputs / (source.stem + ".fragment.html")
        fragment = fragment_path.read_text(encoding="utf-8") \
            if fragment_path.exists() else ""
        preview = out_html.read_text(encoding="utf-8") if out_html.exists() else ""
        zhihu = outputs / (source.stem + ".zhihu.md")

        extras = {"preview": preview,
                  "zhihu_md": zhihu if zhihu.exists() else None,
                  "console": console}
        w_grades = grade(fragment, source, case["assertions"], extras)
        (ws / "grading.json").write_text(json.dumps(
            {"expectations": w_grades}, ensure_ascii=False, indent=2),
            encoding="utf-8")
        (ws / "timing.json").write_text(json.dumps(
            {"duration_ms": round(elapsed * 1000), "exit_code": code}, indent=2),
            encoding="utf-8")

        # ---- baseline ----------------------------------------------------
        started = time.perf_counter()
        base_html = baseline_convert(source)
        elapsed_b = time.perf_counter() - started
        body = re.search(r"<body>(.*)</body>", base_html, re.S)
        base_fragment = re.sub(r"<!--.*?-->", "",
                               body.group(1) if body else base_html, flags=re.S)

        bs = case_dir / "without_skill"
        (bs / "outputs").mkdir(parents=True, exist_ok=True)
        (bs / "outputs" / (source.stem + ".html")).write_text(
            base_html, encoding="utf-8")
        b_grades = grade(base_fragment, source, case["assertions"])
        (bs / "grading.json").write_text(json.dumps(
            {"expectations": b_grades}, ensure_ascii=False, indent=2),
            encoding="utf-8")
        (bs / "timing.json").write_text(json.dumps(
            {"duration_ms": round(elapsed_b * 1000)}, indent=2), encoding="utf-8")

        w_pass = sum(1 for g in w_grades if g["passed"])
        b_pass = sum(1 for g in b_grades if g["passed"])
        records.append({
            "eval_id": case["id"], "eval_name": case["name"],
            "assertions": len(case["assertions"]),
            "cli_exit_code": code,
            "with_skill": {"passed": w_pass, "total": len(w_grades),
                           "duration_ms": round(elapsed * 1000), "exit_code": code},
            "without_skill": {"passed": b_pass, "total": len(b_grades),
                              "duration_ms": round(elapsed_b * 1000)},
        })

        flag = "" if code == 0 else "  ⚠ CLI exit %d" % code
        print("eval-%d %-24s with_skill %d/%d   baseline %d/%d%s"
              % (case["id"], case["name"], w_pass, len(w_grades),
                 b_pass, len(b_grades), flag))
        for g in w_grades:
            if not g["passed"]:
                print("      ✗ %s — %s" % (g["text"], g["evidence"]))

    # ---- benchmark ------------------------------------------------------
    total_w = sum(r["with_skill"]["passed"] for r in records)
    total_n = sum(r["assertions"] for r in records)
    total_b = sum(r["without_skill"]["passed"] for r in records)
    benchmark = {
        "skill_name": spec["skill_name"],
        "iteration": iteration,
        "runs": records,
        "summary": {
            "with_skill": {"passed": total_w, "total": total_n,
                           "pass_rate": round(total_w / total_n, 4) if total_n else 0},
            "without_skill": {"passed": total_b, "total": total_n,
                              "pass_rate": round(total_b / total_n, 4) if total_n else 0},
        },
    }
    benchmark["summary"]["delta"] = round(
        benchmark["summary"]["with_skill"]["pass_rate"]
        - benchmark["summary"]["without_skill"]["pass_rate"], 4)
    (out_root / "benchmark.json").write_text(
        json.dumps(benchmark, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = ["# Benchmark — %s (iteration %d)" % (spec["skill_name"], iteration),
             "",
             "| Configuration | Assertions passed | Pass rate |",
             "|---|---|---|",
             "| with_skill (via the documented CLI) | %d/%d | %.1f%% |"
             % (total_w, total_n,
                100 * benchmark["summary"]["with_skill"]["pass_rate"]),
             "| without_skill (plain Markdown→HTML) | %d/%d | %.1f%% |"
             % (total_b, total_n,
                100 * benchmark["summary"]["without_skill"]["pass_rate"]),
             "",
             "**Delta: %+.1f percentage points**"
             % (100 * benchmark["summary"]["delta"]),
             "", "## Per case", "",
             "| Case | with_skill | without_skill | CLI exit |",
             "|---|---|---|---|"]
    for r in records:
        lines.append("| %s | %d/%d | %d/%d | %d |"
                     % (r["eval_name"], r["with_skill"]["passed"], r["assertions"],
                        r["without_skill"]["passed"], r["assertions"],
                        r["cli_exit_code"]))
    (out_root / "benchmark.md").write_text("\n".join(lines) + "\n",
                                           encoding="utf-8")

    print("\n%s" % "\n".join(lines))
    print("\nworkspace: %s" % out_root)
    return out_root


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Run the wechat-publisher-pro eval suite.")
    parser.add_argument("--workspace",
                        default=str(SKILL_DIR.parent / "eval-workspace"))
    parser.add_argument("--iteration", type=int, default=1)
    parser.add_argument("--only", help="逗号分隔的 eval id")
    args = parser.parse_args(argv)

    if not EVALS_PATH.exists():
        # skill-creator's packager excludes `evals/` from the distributable
        # .skill -- the eval suite is a development artifact, not something an
        # installed skill needs.  Say that plainly, rather than raising
        # FileNotFoundError at someone who only wanted to check their install.
        print("找不到评测定义：%s" % EVALS_PATH)
        print()
        print("评测用例不随 .skill 包分发（skill-creator 打包时会排除 evals/）。")
        print("要跑评测，请使用源码目录里的 skill：C4B/skill/wechat-publisher-pro/")
        print()
        print("转换功能不受影响：")
        print("    python scripts/convert_to_wechat.py examples/sample_article.md out.html --validate")
        return 2

    only = [int(x) for x in args.only.split(",")] if args.only else None
    # Resolve before handing paths to the subprocess: the CLI runs with a
    # different working directory, so a relative workspace would put every output
    # somewhere unexpected.
    run_suite(Path(args.workspace).resolve(), args.iteration, only)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
