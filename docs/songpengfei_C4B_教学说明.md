# 教学说明 / How to install and use this skill

面向第一次拿到这个技能的人。目标：**五分钟内跑通，然后用自己的文章试一次。**

## 一、安装

### 方式 A：装成 Claude 技能（推荐）

```bash
# 把技能目录拷进你的 Claude 技能目录
cp -r skill/wechat-publisher-pro ~/.claude/skills/

# 或者用打包好的 .skill 文件
# dist/songpengfei_C4B_wechat-publisher.skill  —— 解压即得到同名目录
```

拷好之后重启 Claude Code。之后你说「帮我把这篇文章排成公众号格式」，
Claude 会自动调用它——不需要记任何命令。

### 方式 B：当命令行工具用

不需要 Claude，也不需要安装：

```bash
cd skill/wechat-publisher-pro
python scripts/convert_to_wechat.py article.md out.html
```

### 依赖

```bash
# 必需
python -m pip install markdown beautifulsoup4 lxml python-docx

# 可选（缺了会自动降级，但建议装）
python -m pip install matplotlib   # 公式渲染成 PNG
python -m pip install pygments     # 代码块语法高亮
```

脚本启动时会检查依赖，**打印**该跑的安装命令，而不会自动安装。
想让它代劳就加 `--install-missing`。

## 二、三十秒上手

```bash
cd skill/wechat-publisher-pro

# 1. 先跑样例，确认环境通了
python scripts/convert_to_wechat.py examples/sample_article.md out.html

# 2. 浏览器打开 out.html，Ctrl+A 全选，Ctrl+C 复制
# 3. mp.weixin.qq.com → 新建图文 → Ctrl+V 粘贴
```

就这样。`out.html` 是完整预览页，复制到的是正文片段——`<head>` 和预览外壳不会被复制。

## 三、换成你自己的文章

1. 写一个 `.md` 文件。**一段一行，段间空行**，这是中文写作的常见习惯，也是本工具
   的默认解析方式。
2. 文件开头可以写元数据（可全部省略）：

```markdown
---
title: 文章标题
author: 你的名字
date: 2026-10-08
digest: 摘要，会显示在标题下方
theme: accent
toc: always
---

## 正文从这里开始
```

3. 转换：

```bash
python scripts/convert_to_wechat.py 我的文章.md 我的文章.html --validate
```

`--validate` 会跑 14 项合规校验，通过的话最后一行是 `校验：14/14 通过`。

## 四、命令速查

### 最常用的五条

```bash
# 基本转换（默认设置就是能发布的设置）
python scripts/convert_to_wechat.py in.md out.html

# 换主题
python scripts/convert_to_wechat.py in.md out.html --theme ink

# 查看有哪些主题 / 模板
python scripts/convert_to_wechat.py --list-themes
python scripts/convert_to_wechat.py --list-templates

# 批量转换一个目录
python scripts/convert_to_wechat.py drafts/*.md --outdir dist/

# 一稿多投：同时出知乎版和纯文本版
python scripts/convert_to_wechat.py in.md out.html --also zhihu,plain
```

### 用模板起草新文章

```bash
python scripts/convert_to_wechat.py --new 新文章.md \
       --template tech-tutorial --title "用三行命令搭好检索"
```

五种模板：`tech-tutorial`（技术教程）、`learning-notes`（学习心得）、
`skill-showcase`（工具介绍）、`product-intro`（产品介绍）、`weekly-report`（周报复盘）。
每个模板都是一份带小标题骨架和提示框占位的 Markdown，直接改内容即可。

### 写提示框

```markdown
> [!NOTE] 知识点
> 正文，可以继续写第二行。

> [!WARNING] 注意
> 九种类型，见 references/callouts.md
```

## 五、常见任务

| 想做的事 | 怎么做 |
|---|---|
| 文章很长，想要目录 | 默认标题 ≥4 个就自动加。强制加：front matter 写 `toc: always` |
| 文章里有公式 | 直接写 `$E = mc^2$` 或 `$$...$$`，会自动渲染成 PNG |
| 公式一直渲染不出来 | `pip install matplotlib`，或改用 `--math unicode` 降级成文本 |
| 想换主色但不换主题 | `--accent "#0f766e"` |
| 从 Word 文档转 | 直接传 `.docx`，表格和图片都会保留 |
| 外链在公众号点不了 | `--links footnote` 把链接收在文末 |
| 字号太小/太大 | `--font-size 17`，整套字号会一起缩放 |
| 想同时发知乎 | `--also zhihu` 会生成 `.zhihu.md` |
| 代码块太长折行难看 | 无解，公众号不支持横向滚动。把长行手动折一下 |

## 六、别人怎么用它写自己的文章

这是这个技能最核心的用法——**你不需要懂它的内部结构，只要会写 Markdown。**

最小工作流：

```bash
# 1. 起草
python scripts/convert_to_wechat.py --new my_post.md --template learning-notes --title "我的标题"

# 2. 用任何编辑器改 my_post.md
# 3. 转换 + 校验
python scripts/convert_to_wechat.py my_post.md my_post.html --validate
# 4. 打开 my_post.html，全选复制，粘贴进公众号
```

想换风格就加一个参数，不用改任何内容：

```bash
for t in default accent warm minimal tech ink; do
  python scripts/convert_to_wechat.py my_post.md "preview_$t.html" --theme $t
done
# 六个文件都打开看一眼，挑一个
```

## 七、验证它在你机器上是好的

```bash
# 跑完整评测：3 个用例，每个都对比「用技能」和「不用技能」
python scripts/run_eval.py --workspace ../../eval-workspace

# 只校验一个已有文件（预览页或纯片段都可以）
python scripts/wechat_validate.py out.html --json
```

评测预期结果：`with_skill 25/25`，`without_skill 4/25`。

> **注意：** 评测用例只在**源码目录**里有。如果你是从
> `dist/songpengfei_C4B_wechat-publisher.skill` 安装的，`evals/` 不会被打包进去
> （`skill-creator` 有意排除开发用产物），`run_eval.py` 会明确告诉你这一点。
> 转换和校验功能不受影响——要跑评测请用 `C4B/skill/wechat-publisher-pro/`。

## 八、出问题了

先跑校验，它会指出具体是哪个元素有问题：

```bash
python scripts/wechat_validate.py out.html
```

发布之后才发现问题的话，查 `references/troubleshooting.md`——
按「现象 → 原因 → 处理」编排，覆盖了粘贴后图片消失、链接失效、
提示框变成 `[!NOTE]` 字样等十几种情况。

## 九、想改造它

| 想改什么 | 改哪里 |
|---|---|
| 加一套配色 | `scripts/themes.py` 的 `PALETTES`，只写你要改的 token |
| 加一种提示框 | `scripts/themes.py` 的 `CALLOUT_TYPES`（+ 需要时加 `CALLOUT_COLORS`） |
| 加一个文章模板 | `scripts/templates.py` 的 `TEMPLATES` |
| 改转换流程 | `scripts/render.py`。**注意阶段顺序，见模块开头的注释** |
| 加一条校验规则 | `scripts/wechat_validate.py` 的 `validate_fragment()` |

改完请跑一遍 `python scripts/run_eval.py`，确认 25/25 没掉。
