---
title: 三行命令搭好本地知识库检索
author: 宋鹏飞
date: 2026-09-20
digest: 不装向量数据库，用一份 CSV 加一个脚本，先把检索跑起来再谈优化。
theme: accent
---

# 为什么要先用 CSV

很多人一上手就部署向量数据库，结果卡在环境上三天。**先用 CSV 验证检索逻辑**，确认思路对了再换存储。

> [!NOTE] 适用场景
> 文档总量在几千条以内、单机使用、不需要实时增量的场景。

## 准备数据

把语料整理成三列：

| 列名 | 含义 | 示例 |
|---|---|---|
| id | 唯一标识 | doc-001 |
| text | 正文 | 光合作用分两个阶段 |
| source | 出处 | 生物课本 P32 |

## 建立索引

```python
import csv

def load(path):
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))

def search(rows, query):
    # 最朴素的相关性：按字符重合度排序
    scored = [(sum(c in r["text"] for c in query), r) for r in rows]
    return [r for score, r in sorted(scored, reverse=True) if score > 0]
```

> [!WARNING] 字符重合度不是语义检索
> 它匹配的是字面重叠，同义词一律找不到。这只是用来验证「检索」这件事本身跑得通。

## 验证

```bash
python index.py "光合作用"
```

预期输出至少一条命中记录。

> [!DANGER] 不要直接上生产
> CSV 方案没有并发控制，多人同时写入会丢数据。
