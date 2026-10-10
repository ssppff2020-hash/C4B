# C4B — 公众号文章生成技能 / WeChat Article Pipeline

把 Markdown / Word / HTML 变成**可以直接粘贴进公众号编辑器**的排版 HTML。

一条命令：

```bash
python skill/wechat-publisher-pro/scripts/convert_to_wechat.py article.md article.html
```

打开 `article.html` → `Ctrl+A` → `Ctrl+C` → 粘贴进 `mp.weixin.qq.com`。

> **当前状态 / Status**
>
> | 级别 | 状态 |
> |---|---|
> | Level 1 跑通 + 微调 | ✅ |
> | Level 2 用 skill-creator 改造（新增 10 项能力） | ✅ |
> | Level 3 发布真实文章 | ✅ **已发布并线上核验** —— 正文是渲染后的 HTML（185 个 inline style / 14 个框 / 26 行代码 / 1 张 CDN 图）。标题栏仍为占位符，待改。见 [`article/songpengfei_C4B_文章链接.md`](article/songpengfei_C4B_文章链接.md) |
> | Level 4 完整流水线 | ✅ 模板起草 · 多格式导出 · 批量转换 · 自动校验 · 评测 |

---

## 1. 这个技能解决什么问题

公众号编辑器不是一个浏览器。它没有样式表、没有 class，粘贴时会**静默**做这些事：

| 你写的 | 实际发布出来的 |
|---|---|
| `<script>` `<iframe>` | 什么都没有 |
| `<style>` 块、`class="…"` | 标签还在，样式全丢 |
| `<h1>` | 降级（h1 被公众号留给文章标题） |
| `<div>` | 被拆平 |
| `<pre><code>` 换行 | 塌成一行 |
| SVG 图片 | 保存时消失 |
| 外部 `http://` 链接 | 变成纯文本 |

**每一条都不报错。** 这个技能把这些规则写进代码，再加上 14 项自动校验——
因为「浏览器里看着没问题」和「发布后没问题」是两件事。

---

## 2. 安装

需要 Python 3.9+。

```bash
# 必需依赖
python -m pip install markdown beautifulsoup4 lxml python-docx

# 可选（缺了会自动降级，但建议装）
python -m pip install matplotlib   # LaTeX 公式 → PNG
python -m pip install pygments     # 代码块语法高亮
```

安装方式二选一：

**A. 作为 Claude 技能**（之后说「帮我排成公众号格式」就会自动调用）

```bash
cp -r skill/wechat-publisher-pro ~/.claude/skills/
# 或者：解压 dist/songpengfei_C4B_wechat-publisher.skill
```

**B. 只当命令行工具**（不需要 Claude，不需要安装）

直接用仓库里的脚本即可，见下一节。

---

## 3. 运行命令

所有命令都在 `skill/wechat-publisher-pro/` 目录下执行。

```bash
cd skill/wechat-publisher-pro

# 转换
python scripts/convert_to_wechat.py 文章.md 输出.html

# 转换 + 合规校验（推荐）
python scripts/convert_to_wechat.py 文章.md 输出.html --validate

# 换主题 / 看有哪些主题
python scripts/convert_to_wechat.py 文章.md 输出.html --theme ink
python scripts/convert_to_wechat.py --list-themes

# 一稿多投：同时导出知乎版和纯文本版
python scripts/convert_to_wechat.py 文章.md 输出.html --also zhihu,plain

# 批量
python scripts/convert_to_wechat.py drafts/*.md --outdir dist/

# 用模板起草新文章
python scripts/convert_to_wechat.py --new 新文章.md --template tech-tutorial --title "标题"

# 单独校验一个已有文件
python scripts/wechat_validate.py 输出.html --json

# 跑评测（3 个用例 × 有技能/无技能对照）
python scripts/run_eval.py --workspace ../../eval-workspace
```

**先跑样例确认环境没问题：**

```bash
python scripts/convert_to_wechat.py examples/sample_article.md out.html --validate
# 预期结尾：校验：14/14 通过
```

完整参数见 [`skill/wechat-publisher-pro/references/cli_reference.md`](skill/wechat-publisher-pro/references/cli_reference.md)，
或 `--help`。

---

## 4. 目录结构

```
C4B/
├── README.md                          ← 本文件
│
├── skill/wechat-publisher-pro/        ← 交付物 ①：定制后的技能包
│   ├── SKILL.md                       技能主指令（Claude 读这个）
│   ├── scripts/                       10 个模块，4565 行
│   │   ├── convert_to_wechat.py       命令行入口（40+ 参数）
│   │   ├── render.py                  主流水线，11 个阶段
│   │   ├── themes.py                  六套主题，CSS 从调色板推导
│   │   ├── typography.py              中英文间距、标点规范化
│   │   ├── mathpng.py                 LaTeX → base64 PNG
│   │   ├── converters.py              md/docx/html 读取 + 知乎/纯文本导出
│   │   ├── templates.py               五种文章模板
│   │   ├── wechat_validate.py         14 项合规校验（发布前）
│   │   ├── check_published.py         线上核验（发布后）
│   │   └── run_eval.py                评测驱动（有技能 vs 无技能）
│   ├── references/                    按需加载的参考文档（5 篇）
│   ├── examples/                      示例文章 + 示例输出 + 配图
│   └── evals/                         3 个测试用例 + 断言定义
│
├── dist/
│   ├── songpengfei_C4B_wechat-publisher.skill   ← 交付物 ②：可分发的技能包
│   └── wechat-publisher-pro.skill               同一内容（原名副本）
│
├── article/                           ← 交付物 ③：文章与发布包
│   ├── songpengfei_C4B_文章源文件.md        文章源文件（Markdown）
│   ├── songpengfei_C4B_output.html      转换后的公众号 HTML（预览页）
│   ├── songpengfei_C4B_output.fragment.html  纯片段（可粘贴/可校验）
│   ├── songpengfei_C4B_output.zhihu.md  知乎版
│   ├── songpengfei_C4B_output.txt       纯文本版
│   ├── songpengfei_C4B_output.report.json 机器可读的报告
│   ├── songpengfei_C4B_文章链接.md          ← 交付物 ④：发布包（SOP + 链接待填）
│   └── images/                                  文章配图 + 生成脚本
│
├── docs/                              ← 交付物 ⑤：说明文档
│   ├── songpengfei_C4B_教学说明.md        教学说明（怎么装、怎么用）
│   ├── songpengfei_C4B_AI日志.md                AI 日志（必交项）
│   ├── songpengfei_C4B_拿来说明.md 拿来说明（改了什么、为什么）
│   └── songpengfei_C4B_AAR.md                   AAR 复盘（含 14 条失败记录）
│
├── eval-workspace/                    评测数据（可复核）
│   ├── review.html                    人工复核界面（skill-creator 生成）
│   ├── iteration-1/                   第一轮：19 条断言，19/19
│   ├── iteration-2/                   第二轮：加回归用例后 25/25
│   └── llm-qualitative/               6 个独立 Agent 的对照记录
│
└── evidence/
    └── article_p1.png, article_p2.png 文章预览截图（手机宽度）
```

---

## 5. 结果复现步骤

从零复现全部结论，按顺序执行即可。

### 步骤 0：环境

```bash
cd C4B
python -m pip install markdown beautifulsoup4 lxml python-docx matplotlib pygments
```

### 步骤 1：跑通转换（约 10 秒）

```bash
cd skill/wechat-publisher-pro
python scripts/convert_to_wechat.py examples/sample_article.md out.html --fragment --validate
```

**预期输出：**

```
✅ sample_article.md → out.html
   主题 蓝调 · 科技清晰 ｜ 正文 2300+ 字 ｜ 标题 10 ｜ 公式 3 ｜ 图片 1 ｜ callout 9 ｜ 框 15
   校验：14/14 通过
```

浏览器打开 `out.html`，应该看到：目录、9 个彩色提示框、3 个渲染成图片的公式、
带语法高亮的代码块、内嵌的流程图、页脚版权。

### 步骤 2：复现文章（约 30 秒）

```bash
cd C4B
python skill/wechat-publisher-pro/scripts/convert_to_wechat.py \
       article/songpengfei_C4B_文章源文件.md \
       article/songpengfei_C4B_output.html \
       --fragment --report --validate --also zhihu,plain
```

**预期输出：** `校验：14/14 通过`，并生成 5 个文件（html / fragment / zhihu.md / txt / report.json）。
`report.json` 里的 `stats` 应与本文档所引数字一致。

### 步骤 3：复现评测（约 40 秒）

```bash
cd skill/wechat-publisher-pro
python scripts/run_eval.py --workspace ../../eval-workspace --iteration 3
```

**预期输出：**

```
eval-0 tutorial-with-code       with_skill  8/8    baseline 2/8
eval-1 formulas-and-tables      with_skill  7/7    baseline 1/7
eval-2 messy-word-export        with_skill 10/10   baseline 1/10

with_skill (via the documented CLI)  25/25  100.0%
without_skill (plain Markdown→HTML)   4/25   16.0%
Delta: +84.0 percentage points
```

对照仓库里已有的结果：

| 轮次 | 目录 | with_skill | 说明 |
|---|---|---|---|
| 第一轮 | `eval-workspace/iteration-1/` | 19/19 | 初版，19 条断言 |
| 第二轮 | `eval-workspace/iteration-2/` | 25/25 | 从测试反馈补了 6 条回归断言 |

重新生成人工复核界面：

```bash
python ~/.claude/skills/skill-creator/eval-viewer/generate_review.py \
  ../../eval-workspace/iteration-2 \
  --skill-name wechat-publisher-pro \
  --benchmark ../../eval-workspace/iteration-2/benchmark.json \
  --previous-workspace ../../eval-workspace/iteration-1 \
  --static ../../eval-workspace/review.html
```

然后浏览器打开 `eval-workspace/review.html`。

### 步骤 4：复现技能包（约 5 秒）

```bash
pip install --user ~/.claude/skills/skill-creator 2>/dev/null || \
  cp -r /tmp/anthropic-skills/skills/skill-creator ~/.claude/skills/ 2>/dev/null

cd ~/.claude/skills/skill-creator
PYTHONUTF8=1 python scripts/quick_validate.py "<C4B>/skill/wechat-publisher-pro"
# 预期：Skill is valid!

PYTHONUTF8=1 python -m scripts.package_skill "<C4B>/skill/wechat-publisher-pro" "<C4B>/dist"
# 预期：✅ Successfully packaged skill to: …/dist/wechat-publisher-pro.skill
```

### 步骤 5：复现配图（可选，约 3 秒）

```bash
python article/images/make_wechat_drops_diagram.py            # 文章主图
python skill/wechat-publisher-pro/examples/images/make_pipeline_diagram.py
```

---

## 6. 文件命名规范

挑战要求的格式是 `姓名_C4B_内容描述.扩展名`。本项目的做法是：

**`姓名` 部分用拼音（`songpengfei`），描述部分保留挑战原文的中文用词。**

为什么描述部分必须是中文：EduSeed 平台按**文件名里的中文子串**判定必交件是否齐全。
`challenge.json` 的 `required_deliverables` 是 `*wechat-publisher*,*文章链接*,*AI日志*`——
文件名里不含 `文章链接` 或 `AI日志`，就会被判为缺失，内容再全也没用。

> 这条是实测结论，不是推测：项目一度把描述部分也改成英文
> （`..._article_link.md` / `..._ai_log.md`），平台随即报这两项 missing。
> 对照探针确认是**命名**问题而非内容问题——`文章链接` 那篇的**正文**里写着
> 「公众号文章链接」，照样被判缺失，可见匹配只针对文件名。
> 而 AI 日志那篇正文里写的是「AI 日志」（中间有空格），即使按内容匹配也不会命中。

| 挑战要求的名字 | 本项目文件 |
|---|---|
| `姓名_C4B_wechat-publisher.skill` | `dist/songpengfei_C4B_wechat-publisher.skill` |
| `姓名_C4B_文章链接.md` | `article/songpengfei_C4B_文章链接.md` |
| `姓名_C4B_文章源文件.md` | `article/songpengfei_C4B_文章源文件.md` |
| `姓名_C4B_output.html` | `article/songpengfei_C4B_output.html` |
| `姓名_C4B_教学说明.md` | `docs/songpengfei_C4B_教学说明.md` |
| `姓名_C4B_AI日志.md` | `docs/songpengfei_C4B_AI日志.md` |
| `姓名_C4B_拿来说明.md` | `docs/songpengfei_C4B_拿来说明.md` |
| （rubric 要求 AAR，CHALLENGE.md 未列） | `docs/songpengfei_C4B_AAR.md` |
| 定制后的技能目录 | `skill/wechat-publisher-pro/` |

**两条约定：**

1. `songpengfei_C4B_` 前缀用于「交付物文档与产物」，子目录按类型分
   （`article/` `docs/` `dist/`）。平台是递归扫描的——`dist/` 里的 `.skill`
   在子目录中也能被 `wechat-publisher` 这一项命中。
2. 技能**内部**文件（`SKILL.md`、`scripts/`、`references/`）保持社区通用的英文
   小写连字符命名，因为装进 `~/.claude/skills/` 时要符合技能命名规范；
   这些不是平台检查的交付件。

**自查命令**（复现平台的三项判定）：

```bash
python - <<'EOF'
import json, io
from pathlib import Path
req = json.load(io.open('../challenge.json', encoding='utf-8'))
names = [p.name for p in Path('.').rglob('*') if p.is_file()]
for t in [x.strip('* ') for x in req['required_deliverables'].split(',')]:
    print('  %-18s %s' % (t, 'OK' if any(t in n for n in names) else 'MISSING'))
EOF
```

---

## 7. 核心结论

| | 用技能 | 不用技能（手写脚本硬转） |
|---|---|---|
| 带代码块的教程 | 8/8 | 2/8 |
| 带公式的统计文 | 7/7 | 1/7 |
| Word 粘出的脏 HTML | 10/10 | 1/10 |
| **合计** | **25/25 (100%)** | **4/25 (16%)** |

差距不在「能不能转」，而在**知不知道会错在哪**。

---

## 8. 知道更多

| 想了解 | 看这里 |
|---|---|
| 怎么装、怎么用、能改什么 | [`docs/songpengfei_C4B_教学说明.md`](docs/songpengfei_C4B_教学说明.md) |
| 从 starter kit 拿了什么、改了什么 | [`docs/songpengfei_C4B_拿来说明.md`](docs/songpengfei_C4B_拿来说明.md) |
| AI 怎么用的、错在哪、怎么修的 | [`docs/songpengfei_C4B_AI日志.md`](docs/songpengfei_C4B_AI日志.md) |
| 14 条失败记录与改进方案 | [`docs/songpengfei_C4B_AAR.md`](docs/songpengfei_C4B_AAR.md) |
| 发布步骤与数据追踪表 | [`article/songpengfei_C4B_文章链接.md`](article/songpengfei_C4B_文章链接.md) |
| 公众号允许/禁止什么 | [`skill/wechat-publisher-pro/references/wechat_restrictions.md`](skill/wechat-publisher-pro/references/wechat_restrictions.md) |
| 出问题怎么办 | [`skill/wechat-publisher-pro/references/troubleshooting.md`](skill/wechat-publisher-pro/references/troubleshooting.md) |

---

## 9. 许可与出处

- 起点：挑战附带的 `c4b-wechat-publisher-starter.zip`（改造说明见「拿来说明」）
- 开发流程：`skill-creator`（Apache-2.0，来源 `github.com/anthropics/skills`）
- 本技能代码：由 `skill-creator` 流程驱动、AI 生成、人工审阅与迭代
