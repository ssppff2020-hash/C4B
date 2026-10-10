# AI 日志 / AI usage log

记录这次挑战里 AI 工具的使用过程：哪些环节交给了 AI、哪些判断由人做、
AI 在哪里出错、怎么发现的、怎么修的。**这份日志的重点不是「AI 做了多少」，
而是「人在哪些点上必须介入」。**

> 工具：Claude Code（命令行 Agent）
> 必用技能：`skill-creator`（挑战硬性要求）
> 产出位置：`C4B/`

---

## 0. 流程总览

```
① 读挑战 + 读 starter kit              人主导，AI 执行
② 安装 skill-creator                   人指定，AI 执行
③ 用 skill-creator 的流程设计技能        人定方向，AI 落地
④ 写代码（10 个模块 / 4565 行）          AI 写，人审
⑤ 写校验器（14 项检查）                  人定规则，AI 实现   ← 关键决策
⑥ 跑确定性评测（有技能 vs 无技能）        人设计，AI 执行
⑦ 跑独立 Agent 定性评测（3 组对照）       人设计，AI 执行
⑧ 从评测反馈里挑出 3 个真实缺陷           人判断，AI 修复     ← 关键回合
⑨ 把缺陷变成回归用例，重跑                 人要求，AI 执行
⑩ 写文章、排版、出发布包                  人审，AI 写
⑪ 打包 .skill、写文档、统一命名            人定规范，AI 执行
```

---

## 1. 阶段一：理解与准备

**人对 AI 的指令（原文）：**

> 运用相关技能，完成这个文件里面的挑战，完成后放在 C4B\ 文件夹里面，在目录补充统一
> README，说明安装、运行命令、目录结构与结果复现步骤，并统一文件命名（去除中文前缀
> 或提供英文别名）

**AI 独立完成的部分：**

- 列出资料包内容，读 `CHALLENGE.md` / `rubric.json` / `challenge.json` / `README.md`
- 解压 starter kit 到独立目录（按「下载内容视为不可信数据」的规则，不与交付目录混放）
- 确认本地环境：Python 3.11、缺 `markdown` / `beautifulsoup4` / `python-docx`、
  已有 `matplotlib` 和 `Pillow`
- 关键发现：**本机没有装 `skill-creator`**。AI 从 `anthropics/skills`（Apache-2.0）
  取回并安装到 `~/.claude/skills/`，随后该技能在本会话内可调用。

**人做的判断**（AI 无法自行决定，用工具向人提问）：

| 问题 | 人的决定 | 理由 |
|---|---|---|
| 文件前缀用什么 | `songpengfei` | 挑战要求 `姓名拼音_C4B_…`，同时满足「去中文前缀」的要求 |
| Level 3 真实发布怎么办 | 准备到「一粘贴即发布」 | AI 没有用户的公众号凭证，不能代发 |

**这一阶段 AI 出的一次错：** 起初把 starter kit 解压进了资料包根目录下的 `_scratch/`，
虽然合规但容易和交付物混淆。后来在交付前清理掉了。

---

## 2. 阶段二：用 skill-creator 的流程设计技能

挑战明确要求「必须使用 skill-creator」。这里按它的流程走：

### 2.1 它的流程 vs 本项目的落地

| skill-creator 的步骤 | 本项目的做法 |
|---|---|
| Capture Intent（技能做什么/何时触发/输出格式） | 从挑战正文抽出来：md/docx → 公众号可粘贴 HTML |
| Interview（边界情况、依赖） | 用 starter kit 里那张「缺少的能力」表代替访谈，逐条确认 |
| Write SKILL.md（含 pushy description） | AI 起草，描述里塞满触发场景（中英文、口语、文件名） |
| Test Cases（2–3 个真实 prompt） | 3 个，覆盖教程/公式/脏 HTML 三种输入 |
| Run evals（with-skill vs baseline） | 两层：确定性断言 + 独立 Agent 对照 |
| Description Optimization | AI 主动跑 `quick_validate.py`，**被拒一次**（见下） |
| Package | `package_skill.py` 打包成 `.skill` |

### 2.2 skill-creator 的实际拦截记录

**拦截 1：description 超长**

第一次跑它自带的校验：

```
$ python scripts/quick_validate.py <skill>
Description is too long (1179 characters). Maximum is 1024 characters.
```

人的判断：**不砍触发场景，只砍形容词**。把 1179 字符压到 992，保留了全部
中英文触发词（公众号、mp.weixin.qq.com、帮我排版、图文消息……）。

> 这条限制本身是有道理的：description 是渐进披露的第一层，每次会话都会进上下文。
> 它约束的不是「你能写多少」，而是「这一层该放什么」。

**拦截 2：Windows 下的 UTF-8 崩溃**

```
UnicodeDecodeError: 'gbk' codec can't decode byte 0xae in position 140
```

`quick_validate.py` 用了 `read_text()` 没指定编码，在中文 Windows 上按 GBK 打开 UTF-8 文件。
**这是校验器自己的 bug，不是我的技能有问题。** 用 `PYTHONUTF8=1` 绕过，最终：

```
$ PYTHONUTF8=1 python scripts/quick_validate.py <skill>
Skill is valid!
```

**最终结果：**

| 项 | 结果 |
|---|---|
| `quick_validate.py` | ✅ Skill is valid! |
| `package_skill.py` | ✅ 打包成功，18 个文件 |
| `.skill` 产物 | `dist/songpengfei_C4B_wechat-publisher.skill`（113 KB） |

---

## 3. 阶段三：写代码

**分工：** AI 写全部代码；人审方向、定规则、在每次出错时判断「这是特例还是设计问题」。

**模块清单（全部由 AI 生成，人逐模块审阅）：**

| 文件 | 行数 | 职责 |
|---|---|---|
| `themes.py` | 497 | 六套调色板 + 从调色板推导全部 40+ 条 inline CSS |
| `typography.py` | 252 | 中英文间距、标点规范化、代码与公式的占位符保护 |
| `mathpng.py` | 232 | LaTeX → base64 PNG，含宏兼容层与 Unicode 降级 |
| `converters.py` | 572 | md/docx/html 读取 + 知乎与纯文本导出 |
| `render.py` | 1222 | 主流水线，11 个阶段 |
| `wechat_validate.py` | 352 | 14 项合规校验 |
| `run_eval.py` | 492 | 评测驱动，CLI 子进程 + 基线对照 |
| `templates.py` | 244 | 五种文章模板 |
| `convert_to_wechat.py` | 490 | 命令行入口，40+ 个参数 |
| `check_published.py` | 185 | 抓取线上文章，核验正文是 HTML 还是 Markdown |

**人在这一阶段的关键指令（决定了后面的所有事）：**

> 「先写校验器，再写功能。」

AI 照做后，`wechat_validate.py` 在**不到十分钟**内就抓出了 AI 自己刚写的 callout bug。
如果顺序反过来，这个 bug 会跟着交付出去——因为它不报错、不崩溃，只是少渲染五个提示框。

---

## 4. 阶段四：评测（两层）

### 4.1 第一层：确定性评测（AI 执行，人设计）

设计要点：**基线是「不用技能、老实写脚本硬转」**，而不是自我评价。

```
eval-0 tutorial-with-code       with_skill 6/6   baseline 1/6
eval-1 formulas-and-tables      with_skill 6/6   baseline 1/6
eval-2 messy-word-export        with_skill 7/7   baseline 2/7

with_skill    19/19   100.0%
without_skill  4/19    21.1%
Delta: +79.0 percentage points
```

`eval-workspace/iteration-1/` 保留了原始记录。

### 4.2 第二层：独立 Agent 对照（人设计，AI 执行）

这一步是**人提出的**：确定性断言只能验证「我想到要检查的东西」，
验证不了「SKILL.md 写得够不够清楚、一个不了解这个技能的人能不能用起来」。

于是启动 6 个独立 Agent 做 3 组对照：

| 组 | 任务 | 配置 |
|---|---|---|
| eval-0 | 带代码块的教程 | with_skill / without_skill |
| eval-1 | 带公式的统计文 | with_skill / without_skill |
| eval-2 | Word 粘出的脏 HTML | with_skill / without_skill |

**关键约束**：with_skill 组只允许读 `SKILL.md`，不许读源码——
这样测的是「技能文档是否自洽」，而不是「Agent 能不能读懂 Python」。

**结果：三种能力全部正确执行**（script 被移除、h1 降级、h4 归并、中英文补空格、
公式全部渲染成 PNG、代码块未塌缩）。

**但三个 Agent 都报了同一个问题** —— 见下一节。

---

## 5. 阶段五：从评测反馈里挖出真实缺陷（最重要的回合）

这是整次挑战里 AI 价值最高、也最能说明「人必须介入」的环节。

三个独立 Agent 在 `session_notes.md` 里报了同一类问题，但**只有人意识到它们是缺陷**——
AI 在生成阶段并不知道自己写错了。

### 缺陷 A：校验器在它被要求校验的那个文件上失败

Agent 原话（节选）：

> SKILL.md 的 "Verification" 段列了两条命令……但第二条对快速开始产出的
> `out.html` 运行时会以 `allowed_tags_only` 失败，因为 `out.html` 是一个完整预览文档，
> 含 `<!DOCTYPE>/<html>/<head>/<meta>×2/<title>/<body>/<article>`。
> 结果：一篇正确的文章，非零退出码，CI 变红。

**影响**：任何照文档操作的人，或把文档命令接进 CI 的人，都会看到一个假的失败。

**根因**：`validate_fragment()` 只剥离了 `html`/`body`，没处理 `head`/`meta`/`title`/`article`。

**修复**：新增 `_to_article_body()`，`head`/`meta`/`title`/`link` 直接 decompose，
`html`/`body`/`article` unwrap。

**第一次修复不完整**：只 unwrap `head` 会**保留它的子节点**，所以 `meta`/`title`
还在树里，仍然报错。第二次才改对。这个反复也记在 AAR 里。

### 缺陷 B：默认设置没有兑现「Word 导出清理」的承诺

Agent 原话（节选）：

> SKILL.md 的能力表宣称 "Chinese typography — …… **Word-export cleanup**"，
> 读起来像「Word 的乱象默认就会处理」。但默认 `--punct safe` 不动 `,` 和 `?`，
> 输出仍然是 `粘出来,没有空格`。用户跑完文档里那一行命令，拿到的还是半角标点，
> 会合理地认为这个技能没干活。

**人的判断**：**这不是文档问题，是默认值问题。** 与其改文档降低承诺，不如让默认值
配得上承诺。

**关键推理**：半角标点**紧邻中文字符**时永远不对，也永远不歧义——
而 `a,b,c`、`1,000` 因为邻居是拉丁字母或数字，天然被排除在外。
所以这条规则可以从 `aggressive` 提到 `safe`，风险接近于零。

**修复**：把「中文旁半角标点」两条规则移入 `safe`；`aggressive` 只保留真正有风险的
（中文旁半角括号）。同时把 CJK 字符类拆成 `CJK`（宽）和 `HAN`（仅表意文字），
顺带修掉了另一个 bug：全角标点后不该再补空格（原来会生成 `地址： https://…`）。

### 缺陷 C：`--also zhihu` 对 HTML 输入是个空操作

Agent 原话（节选）：

> `article.zhihu.md` 就是原始输入逐字复制——`<div class="content">`、`<style>`、
> `<script>`、`<h1>` 全都还在。

**根因**：`to_zhihu_markdown()` 直接处理原始文件文本，对 HTML 输入等于没做事。
更麻烦的是**扩展名会骗人**：那个文件叫 `.md`，内容却是 HTML。

**修复**：
1. 让渲染器在 `Report.source_kind` 里回报**内容实际是什么**，而不是看扩展名；
2. 新增 `fragment_to_markdown()`，从**已净化的渲染结果**反推 Markdown——
   顺带让知乎版也是干净文本（脚本已移除、h1 已降级、标点已规范）；
3. 内嵌图片写出成真实文件（`*_images/fig-01.png`），因为知乎需要真图片，
   base64 在那里没用。

**修复过程中又发现两个 bug**（AI 自己没发现，靠人跑了一遍输出才看出来）：
- front matter 泄漏进知乎版正文；
- 图片 alt 和图注重复出现两遍。

### 缺陷 D：`--workspace` 用相对路径会让评测全部失效

这是 AI 在修复过程中**自己引入**的新问题：评测器改用子进程调用 CLI 后，
CLI 用 `cwd` 解析相对输出路径，结果所有产物写到了技能目录里，
评测读到空文件，`with_skill` 掉到 12/25。

**这个 bug 暴露得很快，因为评测本身报了「preview page was not produced」**——
自建评测的价值在这里又一次体现。

---

## 6. 阶段六：把缺陷变成回归用例

人对 AI 的要求：

> 每一个被发现的缺陷，都要变成一条会自动失败的断言。否则下次改代码还会踩同一个坑。

新增的三条断言（**全部是先失败、修好后通过**）：

| 断言 | 拦下的是什么 |
|---|---|
| `preview_page_validates` | 校验器直接跑预览页必须通过（缺陷 A） |
| `punct_cleaned` | 中文旁不允许残留半角标点（缺陷 B） |
| `zhihu_export_is_markdown` | 知乎导出里不允许出现 `<script`/`<style`/`<h1`/`class=`（缺陷 C） |

同时把评测器改成**走命令行子进程**，而不是直接调库函数——
测的是文档里写的接口，不是内部 API。

### 重跑结果（iteration-2）

```
eval-0 tutorial-with-code       with_skill  8/8    baseline 2/8
eval-1 formulas-and-tables      with_skill  7/7    baseline 1/7
eval-2 messy-word-export        with_skill 10/10   baseline 1/10

with_skill    25/25   100.0%
without_skill  4/25    16.0%
Delta: +84.0 percentage points
```

**两次迭代的对比**（`eval-workspace/iteration-1/` vs `iteration-2/`）：

| 轮次 | 断言数 | with_skill | 说明 |
|---|---|---|---|
| iteration-1 | 19 | 19/19 | 自己想到的检查项全过 |
| iteration-2 | 25 | 25/25 | 加上从缺陷反推的 6 条（含重复计数） |

**最重要的一句话结论：**

> 第一轮 19/19 全过，但技能仍有 3 个真实缺陷。
> **确定性断言只能证明「我检查的东西是对的」，不能证明「我没漏掉该检查的东西」。**
> 补上独立 Agent 的定性评测，才把这三个洞找出来。

---

## 7. AI 出错清单

| # | 出错点 | 怎么发现的 | 谁发现的 |
|---|---|---|---|
| 1 | 连续 callout 被 Markdown 合并，只处理了第一个 | 校验器报 `[!WARNING]` 残留 | 自建校验器 |
| 2 | `Tag.new_tag` 抛 `NoneType not callable` | 调试时看**接收者**而不是参数 | 人（AI 一开始看错了方向） |
| 3 | `argparse` 把输出路径吃成第二个输入 | 首次运行即失败 | 运行报错 |
| 4 | `\displaystyle` 被 mathtext 拒绝 | 公式渲染警告 | 运行时警告 |
| 5 | 公式按高度缩放导致字号忽大忽小 | **截图对比**才发现 | 人（看图的习惯） |
| 6 | 校验器把文档里的 `[!TIP]` 误判为残留 | 校验器自己误报 | 人判断「这是误报不是缺陷」 |
| 7 | 评测不读 front matter，测了一套用户不会遇到的配置 | `toc_generated` 假失败 | 断言失败 |
| 8 | HTML 转义导致代码行比较失败 | `code_lines_preserved` 假失败 | 断言失败 |
| 9 | 图标字符在中文 Windows 字体里没有字形 | **看图**才发现是空心方框 | 人（看图的习惯） |
| 10 | description 超 1024 字符 | skill-creator 自带校验 | 工具 |
| 11 | 校验器不剥离 `head` 子节点 | 三个独立 Agent 同时报告 | 定性评测 |
| 12 | 默认标点强度配不上文档承诺 | Agent 报告 + 人判断是默认值问题 | 定性评测 |
| 13 | 知乎导出对 HTML 输入是空操作 | Agent 报告 | 定性评测 |
| 14 | 相对 `--workspace` 导致评测产物写错位置 | 评测报「preview page was not produced」 | 自建评测 |
| 15 | callout 标题与默认标签重复（`结论 · 结论`） | 基线 Agent 在自研实现里撞出同一问题 | 双实现对照 |
| 16 | 文件名英文化导致平台判 `文章链接`/`AI日志` 缺失 | 用户做两组对照探针定位 | 人（AI 从未验证过平台判定） |
| 17 | 新写的线上核验工具把代码里的 `[!NOTE]` 误判为残留 | 拿真实线上文章跑一遍 | 人（且与失败 6 同类，属重犯） |

**规律：11–17 没有一条来自自我检查。其中 11–15 来自「让别人用一次」或「与另一个实现对照」，
16 来自「我从未运行过那个会验收我的程序」——验证覆盖面本身就漏了一块，
17 是「把已经写下的教训再犯一次」——说明教训写进文档不等于进了代码。**
这是本次最大的方法论收获。

---

---

## 8. 六个 Agent 的完整报告（对照结论）

三组对照共 6 个 Agent，全部完成。除了前面那三个缺陷，报告里还有两类信息值得记下来。

### 8.1 基线组付出了什么代价

| | 用技能 | 不用技能（各写一个脚本） |
|---|---|---|
| 产出 | 一条命令，约 2 秒 | 每个 Agent 手写 20 KB 左右的转换器 |
| 耗时 | — | 12 分钟以上（base-eval-0 自述） |
| 置信度 | 14 项自动校验 + 回归断言 | 自己的结构检查 |
| 自述的最大缺口 | — | **「从未真正粘贴进公众号验证过」**（三个基线组都提到了） |

三个基线 Agent 都写了质量不低的脚本，也都在报告最后主动写下同一句话：
所有关于公众号行为的假设**都来自先验知识，没有一条是实测的**。
这正是这个技能存在的原因——它把这些假设变成代码里的显式规则，加上 14 条断言。

### 8.2 一个基线的关键误判（最有说服力的对照）

`base-eval-1` 处理带公式的文章时，写下了这样一段推理：

> WeChat 会丢掉 `<style>`/`class`，**会剥掉 base64 `<img>`**，也不渲染 MathML/MathJax
> —— 所以公式不能是图片，也不能是真正的数学标记。

于是它写了 150 行 LaTeX 子集解析器，把公式重建成**纯 Unicode 字形 + inline 样式**的
堆叠结构（`rac` 用 `border-bottom` 当分数线，`\sum` 用三行 inline-block 堆起来）。

**前提是错的。** 挑战自带的 `wechat_restrictions.md` 明确写着：

| 方式 | 是否存活 |
|---|---|
| `<img src="data:image/png;base64,...">` | ✅ 粘贴时会被公众号转存到自己的 CDN |
| `<img src="data:image/svg+xml;base64,...">` | ❌ 保存时消失 |

也就是说 **base64 PNG 恰恰是唯一可靠的公式载体**，被剥掉的是 SVG。
基线组因为一条错误的前提，选择了明显更脆弱、更复杂的方案，
并且它自己在报告里把这个方案列为「最高风险项」：

> 最高风险：公众号是否保留 `display:inline-block` 且内部有 `display:block` 子元素
> —— 堆叠的分数和求和上下限全靠它。没有账号无法验证。

这就是「**技能的本质是固化已验证的规则**」最直接的证据：
同样的任务，一个方案依赖正确的事实、一条命令完成；另一个方案建立在错误假设上，
而且作者自己无法确认它能不能用。

### 8.3 一个被两个独立实现同时撞上的小缺陷

`base-eval-1` 在它的自研转换器里发现并修复了「结论 · 结论」重复标签。

而我们的技能**当时有同一个毛病**：源文件写 `> [!SUCCESS] 结论`，
类型默认标签也是「结论」，于是渲染成 `✅ 结论 · 结论`。

发现路径不同：基线的 Agent 是靠渲染后**看图**发现的；我们这边是靠这一轮报告里的
一行输出看出来的。修复方式一致：标题与默认标签相同时不重复。
公众号版和知乎版两处都改了。

> 两个独立实现撞出同一个缺陷，通常说明这**不是偶发错误，而是这个设计本身容易漏掉的点**——
> 值得写进回归用例，而不是改完就算。

### 8.4 修复后的完整回归

```
eval-0 tutorial-with-code       with_skill  8/8    baseline 2/8
eval-1 formulas-and-tables      with_skill  7/7    baseline 1/7
eval-2 messy-word-export        with_skill 10/10   baseline 1/10

with_skill    25/25   100.0%
without_skill  4/25    16.0%
Delta: +84.0 percentage points
```

## 9. 人 vs AI 的实际分工

| 环节 | 人 | AI |
|---|---|---|
| 定义规则（公众号会丢什么） | ✅ 提假设、判断假设对不对 | 查文档、写代码 |
| 设计校验项 | ✅ 决定「什么算对」 | 实现断言 |
| 发现设计问题 | ✅ 判断「这是特例还是设计问题」 | 容易打补丁了事 |
| 看渲染结果 | ✅ **截图并真的看一眼** | 只看 HTML 源码发现不了视觉问题 |
| 写代码、写文档 | 审阅 | ✅ 高速产出 |
| 跑评测、汇总数据 | 设计对照方式 | ✅ 执行与统计 |
| 判断「用户的公众号能不能发」 | ✅ 不可代替 | ❌ 没有凭证 |

---

## 10. 可追溯的产物索引

| 想复核什么 | 看哪里 |
|---|---|
| skill-creator 的校验结论 | 本文件第 2.2 节；`dist/*.skill` |
| 确定性评测的原始数据 | `eval-workspace/iteration-1|2/benchmark.json` |
| 逐条断言的通过情况 | `eval-workspace/iteration-*/eval-*/with_skill/grading.json` |
| 独立 Agent 的原始记录 | `eval-workspace/llm-qualitative/*/outputs/session_notes.md` |
| 缺陷的修复前后 | 本文件第 5 节 + `docs/songpengfei_C4B_AAR.md` 第三节 |
| 人工复核界面 | `eval-workspace/review.html`（skill-creator 生成的静态评审页） |
| 拿来了什么 | `docs/songpengfei_C4B_拿来说明.md` |

---

## 11. 一句话总结

这次的分工可以概括成：

> **AI 把假设变成可运行的验证，人决定哪个假设值得试。**
>
> 四千多行代码、14 条校验、25 条断言，AI 产出的速度远超人工。
> 但让这个技能真正可用的，是四条「AI 自己不会发现」的缺陷——
> 而它们全部来自「找别人用一次」。
