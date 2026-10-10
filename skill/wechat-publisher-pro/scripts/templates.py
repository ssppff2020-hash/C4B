"""
Article templates -- scaffolding that turns an idea into a draft skeleton.

The hard part of publishing regularly is not the formatting, it is staring at an
empty file.  Each template below encodes an article *shape* that works for a
particular kind of post, complete with ready-made callout markers, so the author
starts from structure instead of from nothing.

Templates are plain Markdown with YAML front matter, so an author can edit one
freely; ``render_document`` reads the same front matter keys back.
"""

from __future__ import annotations

import datetime as _dt
from pathlib import Path

_TODAY = "%Y-%m-%d"

TEMPLATES: dict[str, dict] = {
    "tech-tutorial": {
        "label": "技术教程",
        "description": "一步一步带读者做出结果：问题 → 方案 → 步骤 → 验证 → 踩坑。",
        "body": """## 这篇解决什么问题

用两三句话讲清楚：读者读完能得到什么。**先给结果，再讲过程。**

## 准备工作

- 环境：
- 依赖：
- 预计耗时：

## 第一步：{step1}

> [!NOTE] 关键概念
> 这里解释一个读者必须理解的名词，否则后面的步骤会看不懂。

```bash
# 命令示例
```

说明这段命令做了什么。

## 第二步：{step2}

正文。

> [!WARNING] 容易踩的坑
> 这一步最常见的问题是……，如果遇到，先检查……

## 验证结果

怎么判断做对了？给出一个可观察的信号：

| 检查项 | 期望结果 |
|---|---|
| | |

## 小结

- 做成了什么
- 还能怎么改进
""",
    },
    "learning-notes": {
        "label": "学习心得",
        "description": "记录一次真实的学习过程：起点 → 卡点 → 突破 → 迁移。",
        "body": """## 起因

我为什么开始学这个？当时的具体处境是什么。

## 一开始我以为

写出你最初的错误预期。**真实的错误比正确的总结更有说服力。**

> [!CONFUSED] 我当时卡在这里
> 具体描述那个想不通的点。

## 转折点

是什么让你想通了？一句话、一次实验、一个人的提醒？

## 现在我的理解

用你自己的话重新讲一遍这个知识。检验标准：讲给外行听懂。

## 下一步

- 还想弄清楚：
- 打算怎么验证：
""",
    },
    "skill-showcase": {
        "label": "技能/工具介绍",
        "description": "介绍一个自己做的工具：为什么做 → 怎么用 → 效果如何。",
        "body": r"""## 它解决什么问题

描述一个具体到让人有痛感的场景。

## 一句话说明

> [!KEY] 核心
> 输入 X → 输出 Y。如果一个工具不能用一句话说清输入输出，说明它还不够聚焦。

## 怎么用

```bash
# 安装
pip install ...

# 运行
python run.py input output
```

## 效果对比

| | 手动做 | 用这个工具 |
|---|---|---|
| 耗时 | | |
| 出错率 | | |

## 设计取舍

我为什么不选另一条路？**写清楚取舍，比堆功能更能体现判断力。**

## 已知限制

- 限制一
- 限制二
""",
    },
    "product-intro": {
        "label": "产品介绍",
        "description": "面向用户介绍一个产品：场景 → 能力 → 差异 → 行动。",
        "body": """## 你是否有过这样的时刻

用一个具体场景开场，让目标用户认出自己。

## 它是什么

三句话内讲清楚。

## 三个核心能力

1. **能力一** —— 带来什么结果
2. **能力二** —— 带来什么结果
3. **能力三** —— 带来什么结果

## 和别的方案有什么不同

> [!NOTE] 差异点
> 只讲一个最关键的差异，讲透。

## 怎么开始

- 第一步：
- 第二步：

## 常见问题

**Q：**
A：
""",
    },
    "weekly-report": {
        "label": "周报 / 复盘",
        "description": "结构化的阶段总结：成果 → 数据 → 问题 → 下周计划。",
        "body": """## 本周成果

1. 成果一 —— 一句话说明价值
2. 成果二

## 关键数据

| 指标 | 本周 | 上周 | 变化 |
|---|---|---|---|
| | | | |

> [!SUCCESS] 最有价值的一件事
> 本周哪件事的投入产出比最高？为什么？

## 遇到的问题

> [!DANGER] 需要支持
> 明确写出卡点和需要的帮助，而不是笼统地说「有困难」。

## 下周计划

1. 计划一（预期产出：）
2. 计划二（预期产出：）

## 反思

如果重来一次，哪一步会做得不一样？
""",
    },
}

FRONT_MATTER_TEMPLATE = """---
title: {title}
author: {author}
date: {date}
digest: {digest}
theme: {theme}
toc: {toc}
footer: {footer}
---

"""


def list_templates() -> list[tuple[str, dict]]:
    return [(name, spec) for name, spec in TEMPLATES.items()]


def scaffold(template: str, title: str, path: str | Path, author: str = "",
             digest: str = "", theme: str = "accent", toc: str = "auto",
             footer: str = "") -> Path:
    """Write a ready-to-edit Markdown skeleton.

    The front matter is pre-filled with the keys the converter understands, so
    the author can adjust theme/author/footer without reading any documentation.
    """
    if template not in TEMPLATES:
        raise KeyError("Unknown template '%s'. Available: %s"
                       % (template, ", ".join(TEMPLATES)))
    spec = TEMPLATES[template]
    body = spec["body"].replace("{step1}", "……").replace("{step2}", "……")

    header = FRONT_MATTER_TEMPLATE.format(
        title=title or "在这里写标题",
        author=author or _dt.date.today().strftime(_TODAY),
        date=_dt.date.today().strftime(_TODAY),
        digest=digest or "一句话摘要，会显示在标题下方，也是公众号的「摘要」字段。",
        theme=theme,
        toc=toc,
        footer=footer or "",
    )
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(header + "# %s\n\n" % (title or "在这里写标题") + body,
                    encoding="utf-8")
    return path
