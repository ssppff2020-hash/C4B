#!/usr/bin/env python3
"""
wechat-publisher-pro -- convert Markdown / Word / HTML into WeChat-ready HTML.

    python convert_to_wechat.py article.md article.html
    python convert_to_wechat.py article.md article.html --theme ink --toc always
    python convert_to_wechat.py drafts/*.md --outdir dist/
    python convert_to_wechat.py --new my_post.md --template tech-tutorial --title "标题"

Then: open the output in a browser -> Ctrl+A -> Ctrl+C -> paste into
mp.weixin.qq.com.  Only the article body is copied; the preview shell stays
behind.

Run with --help for the full option list, or --list-themes / --list-templates.
"""

from __future__ import annotations

import argparse
import importlib
import json
import sys
from pathlib import Path

# The script's own directory must come first on sys.path: these are sibling
# modules, and resolving them relatively would break the moment someone runs the
# file from another working directory.
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

REQUIRED = {
    "markdown": "markdown",
    "bs4": "beautifulsoup4",
    "lxml": "lxml",
    "docx": "python-docx",
}
OPTIONAL = {
    "matplotlib": "matplotlib   # 公式渲染为 PNG（--math png，默认开启）",
    "pygments": "pygments     # 代码块语法高亮（--no-highlight 可关闭）",
}

# Every option that may be set either on the command line or in the article's
# front matter.  Imported rather than redeclared so the CLI and the eval harness
# resolve settings identically.
from render import FM_KEYS  # noqa: E402  (path set up above)


# --------------------------------------------------------------------------
# Dependencies
# --------------------------------------------------------------------------
def _importable(module: str) -> bool:
    try:
        importlib.import_module(module)
        return True
    except ImportError:
        return False


def check_dependencies(auto_install: bool) -> bool:
    """Report missing packages with the exact command, instead of guessing.

    The starter kit silently ran ``pip install`` on first use.  That is
    convenient right up until it is not: in a managed environment it either fails
    confusingly or installs something the user never asked for.  Printing the
    command keeps the decision with the person who owns the machine.
    """
    missing = [package for module, package in REQUIRED.items()
               if not _importable(module)]
    if not missing:
        return True

    if auto_install:
        import subprocess
        print("正在安装缺失依赖：%s" % ", ".join(missing))
        subprocess.check_call([sys.executable or "python", "-m", "pip",
                               "install", *missing])
        return True

    print("缺少必需依赖：%s\n" % ", ".join(missing))
    print("请先运行：\n    %s -m pip install %s\n"
          % (sys.executable or "python", " ".join(missing)))
    print("（或加上 --install-missing 让本脚本代为安装）")
    return False


def report_optional():
    absent = [desc for module, desc in OPTIONAL.items() if not _importable(module)]
    if absent:
        print("可选依赖缺失，相关功能会自动降级：")
        for desc in absent:
            print("    pip install %s" % desc.split("#")[0].strip())
        print()


# --------------------------------------------------------------------------
# Argument parsing
# --------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="convert_to_wechat.py",
        description="Markdown / Word / HTML → 微信公众号可粘贴 HTML",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
示例
  python convert_to_wechat.py article.md out.html
  python convert_to_wechat.py article.md out.html --theme ink --indent 2em
  python convert_to_wechat.py report.docx out.html --math unicode
  python convert_to_wechat.py drafts/*.md --outdir dist/ --also zhihu,plain
  python convert_to_wechat.py out.html --validate-only
  python convert_to_wechat.py --new post.md --template skill-showcase --title "标题"
""",
    )
    parser.add_argument(
        "paths", nargs="*", metavar="input [output]",
        help="输入文件；给出第二个路径时视为输出 HTML。多输入请配合 --outdir",
    )

    g = parser.add_argument_group("主题与排版")
    g.add_argument("--theme", help="内置主题名，见 --list-themes（默认 default）")
    g.add_argument("--theme-file", dest="theme_file", help="自定义主题 JSON")
    g.add_argument("--accent", help="覆盖主题主色，如 #1a73e8")
    g.add_argument("--font-size", dest="font_size", type=int,
                   help="正文字号 px（默认 16）")
    g.add_argument("--heading-style", dest="heading_style",
                   choices=["bar", "underline", "plain"], help="标题装饰")
    g.add_argument("--indent", choices=["none", "2em"], help="首行缩进（默认 none）")
    g.add_argument("--letter-spacing", dest="letter_spacing", type=float,
                   help="字间距 px（默认 0.4）")
    g.add_argument("--divider", choices=["dots", "rule", "none"],
                   help="--- 分隔线样式（默认 dots）")

    g = parser.add_argument_group("中文排版")
    g.add_argument("--cjk-spacing", dest="cjk_spacing", action="store_true",
                   default=None, help="中英文之间自动加空格（默认开启）")
    g.add_argument("--no-cjk-spacing", dest="cjk_spacing", action="store_false",
                   help="关闭中英文自动空格")
    g.add_argument("--punct", choices=["safe", "aggressive", "off"],
                   help="标点规范化强度（默认 safe）")
    g.add_argument("--nl2br", dest="nl2br", action="store_true", default=None,
                   help="单换行转为换行（默认开启）")
    g.add_argument("--no-nl2br", dest="nl2br", action="store_false",
                   help="关闭单换行转换行")

    g = parser.add_argument_group("结构")
    g.add_argument("--toc", choices=["auto", "always", "never"],
                   help="目录（默认 auto：≥4 个标题时生成）")
    g.add_argument("--toc-min", dest="toc_min_headings", type=int,
                   help="auto 模式下生成目录的最少标题数（默认 4）")
    g.add_argument("--plain-toc", dest="heading_numbers", action="store_false",
                   default=None, help="目录不编号，改用圆点层级")
    g.add_argument("--numbered-toc", dest="heading_numbers", action="store_true",
                   help="目录使用 1 / 1.1 编号（默认）")
    g.add_argument("--header", choices=["auto", "full", "off"],
                   help="文首信息：auto 作者+摘要 / full 含标题 / off")
    g.add_argument("--footer", help="页脚文字，用 \\n 表示换行")
    g.add_argument("--no-footer", dest="footer_off", action="store_true",
                   default=None, help="不生成页脚")

    g = parser.add_argument_group("图片、公式、代码")
    g.add_argument("--image-mode", dest="image_mode", choices=["embed", "keep"],
                   help="embed：本地图片转 base64（默认）；keep：保留原地址")
    g.add_argument("--image-caption", dest="image_caption", action="store_true",
                   default=None, help="把图片 alt 渲染为图注（默认开启）")
    g.add_argument("--no-caption", dest="image_caption", action="store_false",
                   help="不生成图注")
    g.add_argument("--math", choices=["png", "unicode", "off"],
                   help="公式处理方式（默认 png）")
    g.add_argument("--math-font-size", dest="math_font_size", type=int,
                   help="公式字号 pt（默认 18）")
    g.add_argument("--math-dpi", dest="math_dpi", type=int,
                   help="公式渲染 DPI（默认 200，越大越清晰也越大）")
    g.add_argument("--no-highlight", dest="syntax_highlight", action="store_false",
                   default=None, help="关闭代码语法高亮")
    g.add_argument("--highlight", dest="syntax_highlight", action="store_true",
                   help="开启代码语法高亮（默认）")
    g.add_argument("--callout-style", dest="callout_style",
                   choices=["table", "plain"], help="callout 框实现方式（默认 table）")
    g.add_argument("--links", choices=["keep", "plain", "footnote", "strip"],
                   help="外链处理（默认 keep，会提示公众号会去链）")

    g = parser.add_argument_group("输出")
    g.add_argument("--outdir", help="批量输出目录")
    g.add_argument("--also", help="同时导出其它格式：zhihu,plain")
    g.add_argument("--fragment", action="store_true",
                   help="额外输出纯片段文件（便于程序化粘贴与校验）")
    g.add_argument("--report", action="store_true", help="输出 JSON 报告")
    g.add_argument("--validate", action="store_true",
                   help="生成后立即做公众号合规校验")
    g.add_argument("--validate-only", dest="validate_only", action="store_true",
                   help="只校验已有 HTML，不执行转换")
    g.add_argument("--quiet", action="store_true", help="安静模式")

    g = parser.add_argument_group("工具")
    g.add_argument("--list-themes", dest="list_themes", action="store_true",
                   help="列出内置主题")
    g.add_argument("--list-templates", dest="list_templates", action="store_true",
                   help="列出文章模板")
    g.add_argument("--new-theme", dest="new_theme", metavar="FILE",
                   help="导出一份主题模板 JSON")
    g.add_argument("--new", metavar="FILE", help="用模板新建文章草稿")
    g.add_argument("--template", default="tech-tutorial", help="--new 使用的模板")
    g.add_argument("--title", default="", help="--new 的文章标题")
    g.add_argument("--author", default="", help="--new 的作者署名")
    g.add_argument("--install-missing", dest="install_missing", action="store_true",
                   help="自动安装缺失依赖")
    return parser


def split_paths(paths: list[str], has_outdir: bool):
    """Decide which positional arguments are inputs and which is the output.

    ``argparse`` cannot combine ``nargs="*"`` with a following ``nargs="?"``
    positional -- the star swallows both and the output silently becomes an
    input.  Rather than exposing that wart, we accept a flat list and apply the
    usual CLI convention: with exactly two paths and no ``--outdir``, the last
    one is the output.
    """
    if not paths:
        return [], None
    if has_outdir:
        return paths, None
    if len(paths) == 1:
        return paths, None
    if len(paths) == 2:
        return [paths[0]], paths[1]
    print("多个输入请用 --outdir 指定输出目录（当前收到 %d 个路径）" % len(paths))
    return [], None


def expand_inputs(paths: list[str]) -> list[str]:
    """Expand glob patterns ourselves rather than relying on the shell.

    ``cmd.exe`` never expands globs, and a quoted pattern (``"drafts/*.md"``)
    arrives literally even in bash -- in both cases the tool would silently find
    nothing and report "0/0 succeeded", which reads as a failure of the
    conversion rather than of the quoting.  A pattern is only treated as a glob
    when it does not name an existing file, so a real filename containing ``[``
    still works.
    """
    import glob as _glob

    expanded: list[str] = []
    for path in paths:
        if any(ch in path for ch in "*?[") and not Path(path).exists():
            matches = sorted(_glob.glob(path, recursive=True))
            if not matches:
                print("⚠️  没有文件匹配：%s" % path)
            expanded.extend(matches)
        else:
            expanded.append(path)
    return expanded


# --------------------------------------------------------------------------
# Settings resolution
# --------------------------------------------------------------------------
def resolve_settings(meta: dict, args, base_dir: Path):
    """Merge defaults <- front matter <- command line.

    Only keys the user actually supplied on the command line are considered;
    argparse gives ``None`` for every optional flag that was not passed, which is
    exactly the "not specified" signal we need.  Without that distinction a
    ``--cjk-spacing`` could never override ``cjk_spacing: false`` in front
    matter.
    """
    from render import Options, front_matter_options

    data = front_matter_options(meta, base_dir)
    for key in FM_KEYS:
        value = getattr(args, key, None)
        if value is not None:
            data[key] = value
    if args.footer:
        data["footer"] = args.footer.replace("\\n", "\n")
    if args.footer_off:
        data["footer_off"] = True
    data["base_dir"] = base_dir
    return Options.from_dict(data)


# --------------------------------------------------------------------------
# Conversion driver
# --------------------------------------------------------------------------
def convert_one(source: Path, output: Path, args, quiet: bool) -> dict:
    from converters import (fragment_to_markdown, read_text, to_plain_text,
                            to_zhihu_markdown)
    from render import render_document

    raw = read_text(source)
    from converters import split_front_matter
    meta, body = split_front_matter(raw)
    effective = resolve_settings(meta, args, source.parent)

    preview, fragment, report, meta = render_document(
        source, effective, kind=None, raw_text=raw)

    if report.errors:
        for message in report.errors:
            print("  [错误] %s" % message)
        return {"source": str(source), "ok": False, "errors": report.errors}

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(preview, encoding="utf-8")
    written = [output]

    if args.fragment:
        path = output.with_suffix(".fragment.html")
        path.write_text(fragment, encoding="utf-8")
        written.append(path)

    for extra in (args.also or "").split(","):
        extra = extra.strip().lower()
        if extra == "zhihu":
            path = output.with_suffix(".zhihu.md")
            if report.source_kind == "markdown":
                # Markdown in, Markdown out: the source already has real image
                # paths and correct prose, so it is the best Zhihu version.
                path.write_text(to_zhihu_markdown(body, meta), encoding="utf-8")
            else:
                # HTML/Word input has no Markdown to reuse, and passing the raw
                # HTML through would ship <style> and <script> to Zhihu. Derive
                # it from the rendered fragment instead, which is also the
                # cleaned text, and write the images out as real files.
                image_dir = output.with_name(output.stem + "_images")
                path.write_text(
                    fragment_to_markdown(fragment, meta, image_dir=image_dir,
                                         image_prefix=image_dir.name),
                    encoding="utf-8")
                if image_dir.exists():
                    written.append(image_dir)
            written.append(path)
        elif extra == "plain":
            path = output.with_suffix(".txt")
            path.write_text(to_plain_text(fragment), encoding="utf-8")
            written.append(path)

    checks = None
    if args.validate or args.report:
        from wechat_validate import validate_fragment
        checks = validate_fragment(fragment)

    if args.report:
        from wechat_validate import summarize
        path = output.with_suffix(".report.json")
        path.write_text(json.dumps({
            "source": str(source),
            "output": str(output),
            "theme": report.theme,
            "stats": report.stats,
            "warnings": report.warnings,
            "validation": summarize(checks) if checks else None,
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        written.append(path)

    if checks:
        from wechat_validate import summarize
        summary = summarize(checks)
    else:
        summary = None

    if not quiet:
        stats = report.stats
        print("✅ %s → %s" % (source.name, output.name))
        print("   主题 %s ｜ 正文 %s 字 ｜ 标题 %s ｜ 公式 %s ｜ 图片 %s ｜ "
              "callout %s ｜ 框 %s"
              % (report.theme, stats.get("characters", "?"), stats.get("headings", "?"),
                 stats.get("formulas", "?"), stats.get("images", "?"),
                 stats.get("callouts", "?"), stats.get("boxes", "?")))
        for message in report.warnings:
            print("   ⚠️  %s" % message)
        if summary:
            print("   校验：%d/%d 通过%s"
                  % (summary["passed"], summary["total"],
                     "" if summary["ok"] else "（%d 项错误）" % summary["failed"]))
            for check in checks:
                if not check.passed:
                    print("      %s %s — %s"
                          % ("FAIL" if check.severity == "error" else "WARN",
                             check.id, check.evidence))
        print("   已写出：%s" % "，".join(p.name for p in written))

    return {"source": str(source), "output": str(output), "ok": True,
            "stats": report.stats, "warnings": report.warnings,
            "validation": summary}


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.list_themes:
        from themes import list_themes
        print("内置主题：")
        for name, label in list_themes():
            print("  %-10s %s" % (name, label))
        return 0

    if args.list_templates:
        from templates import list_templates
        print("文章模板：")
        for name, spec in list_templates():
            print("  %-16s %-12s %s" % (name, spec["label"], spec["description"]))
        return 0

    if args.new_theme:
        from themes import write_theme_template
        path = write_theme_template(args.new_theme)
        print("已写出主题模板：%s\n改好后用 --theme-file %s 使用。" % (path, path))
        return 0

    if args.new:
        from templates import scaffold
        path = scaffold(args.template, args.title, args.new, author=args.author,
                        theme=args.theme or "accent")
        print("已创建草稿：%s（模板 %s）" % (path, args.template))
        print("编辑后运行：python convert_to_wechat.py %s %s"
              % (path, Path(path).with_suffix(".html")))
        return 0

    if not check_dependencies(args.install_missing):
        return 2

    inputs, output_arg = split_paths(args.paths, bool(args.outdir))
    inputs = expand_inputs(inputs)
    if output_arg and any(ch in output_arg for ch in "*?["):
        print("输出路径不能是通配符：%s" % output_arg)
        return 1

    if args.validate_only:
        from wechat_validate import main as validate_main
        if not inputs:
            print("--validate-only 需要至少一个 HTML 文件")
            return 1
        return validate_main(inputs + (["--json"] if args.report else []))

    if not inputs:
        # A pattern that matched nothing already got a specific warning; dumping
        # the whole help text on top of it just buries the actual message.
        if not args.paths:
            build_parser().print_help()
        return 1

    if not args.quiet:
        report_optional()

    if len(inputs) > 1 or args.outdir:
        if not args.outdir:
            print("多个输入时必须指定 --outdir")
            return 1
        outdir = Path(args.outdir)
        results = []
        for item in inputs:
            source = Path(item).resolve()
            if not source.exists():
                print("跳过（不存在）：%s" % item)
                continue
            results.append(convert_one(source, outdir / (source.stem + ".html"),
                                       args, args.quiet))
        ok = sum(1 for r in results if r["ok"])
        print("\n批量完成：%d/%d 成功" % (ok, len(results)))
        return 0 if ok == len(results) else 1

    source = Path(inputs[0]).resolve()
    if not source.exists():
        print("❌ 找不到输入文件：%s" % source)
        return 1

    if output_arg:
        output = Path(output_arg)
        if not output.is_absolute():
            output = (Path.cwd() / output).resolve()
    else:
        output = source.with_suffix(".html")

    result = convert_one(source, output, args, args.quiet)
    if not args.quiet and result["ok"]:
        print("\n📋 下一步：")
        print("   1. 浏览器打开 %s 预览（宽度已按手机阅读优化）" % output.name)
        print("   2. Ctrl+A → Ctrl+C")
        print("   3. mp.weixin.qq.com → 新建图文 → Ctrl+V 粘贴")
        print("   4. 若编辑器提示「外部图片」，点一次上传即可进入公众号图库")
        print("   5. 用手机预览确认排版 → 发布")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
