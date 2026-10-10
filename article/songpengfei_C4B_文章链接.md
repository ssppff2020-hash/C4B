# 公众号发布包 / Publishing package

> **状态：已发布，线上核验通过。** 正文是渲染后的 HTML：185 个 inline style、
> 14 个框（提示框 / 目录 / 代码框）、26 行代码、1 张图片已进 CDN、0 个残留 data URI。
> 唯一遗留项是标题栏（后台字段）仍是占位符，改一下即可，见第 3 节。

---

## 1. 文章信息 / Article metadata

| 项目 | 内容 |
|---|---|
| 标题（填到公众号标题栏） | 公众号排版这件小事，我用一条命令解决了 |
| 摘要（digest） | 公众号编辑器有 7 类东西会被静默丢掉——不报错，只在发布后才发现。我把这些规则写进了一个技能，现在一条命令就能出稿。 |
| 作者 | 宋鹏飞 |
| 正文字数 | 约 3230 字 |
| 图片 | 1 张（内嵌 base64，粘贴后自动进入公众号图库） |
| 建议封面 | `article/images/what-wechat-drops.png`（正文首图，也可直接用作封面） |
| 标签建议 | AI 工具、效率、公众号排版 |

## 2. 发布 SOP / Step by step

```
□ 1. 双击打开  article/songpengfei_C4B_output.html
       浏览器会以 640px 宽度显示，接近手机阅读宽度。
       如果看起来不对，先别往下走——回到第 6 节排查。

       ⛔ 千万不要打开 article/songpengfei_C4B_文章源文件.md 来复制。
          浏览器把 .md 当纯文本渲染，复制走的是原始 Markdown，
          粘进公众号就会显示 ---、title:、## 这些记号。
          【首次发布踩的就是这个坑】

   ✅ 复制前先看一眼页面，确认「打开对了」：
      · 标题左侧有一道蓝色竖条
      · 正文里有带底色的彩色提示框（📘 💡 ⚠️）
      · 全文找不到 --- 、## 、** 这些东西
      只要看到 --- 或 ## 开头，说明打开的是源文件，马上换回 .html。

□ 2. 在页面里按 Ctrl+A 全选，Ctrl+C 复制。
       注意：<head> 里的注释和预览外壳不会被复制，复制到的就是正文。

□ 3. 打开 mp.weixin.qq.com，登录后进入「草稿箱 → 新的创作 → 图文消息」。

□ 4. 把标题填进标题栏（上面第 1 节的标题）。
       正文区域 Ctrl+V 粘贴。
       ⚠️ 如果编辑器提示存在外部图片，按提示点一次「上传」即可，
          内嵌图片会自动进入公众号图库。

□ 5. 在页面底部填写「摘要」（上面第 1 节的 digest）。
       公众号摘要上限 120 字，这段摘要是 59 字。

□ 6. 选封面图 → 建议选正文首图，或上传 article/images/what-wechat-drops.png。

□ 7. 点「预览」，发送到自己的微信，在手机上确认：
       - 目录、提示框、表格边框是否都在
       - 图片是否显示
       - 代码块有没有塌成一行（最容易出问题的一处）

□ 8. 手机上确认无误 → 回到后台 → 点「群发 / 发表」。

□ 9. 发表后把链接填进下面第 3 节，并截图留存。

□ 10. 【必做】核验线上内容——这是唯一能看到「真实结果」的检查：
        python skill/wechat-publisher-pro/scripts/check_published.py "<刚发布的链接>"
        看到 ✅ 正文是渲染后的 HTML，排版元素在位 才算成功。
        如果报 ❌ 正文是 Markdown 源码，说明粘错了文件，按第 3 节重发。
```

## 3. 发布记录 / Publication record

> **状态：已发布，线上核验通过。** 唯一遗留项是**标题栏**仍是占位符「第一篇」——
> 标题是后台单独填的字段，不在正文里，改一下即可。

**核验证据**（`python skill/wechat-publisher-pro/scripts/check_published.py <链接>`）：

```
── 是否贴成了 Markdown 源码？ ──
  ✅ 没有发现 Markdown 记号
── 排版是否活着？ ──
  ✅ inline-styled elements   185
  ✅ table (callout / 目录 / 代码框)   14
  ✅ monospace code block     26
  ✅ image on the WeChat CDN  1
── 图片 ──
  data: URI 残留  0      ← base64 图片已被公众号成功转存到 CDN
  CDN 图片        1
```

正文逐项复核：8 个章节标题齐全、署名「宋鹏飞」在位、目录「目 录」+ 7 条编号条目、
提示框标签 10 处、内嵌流程图 1 张已进 CDN、页脚版权在位。

| 项目 | 值 |
|---|---|
| **正式链接（已核验）** | <https://mp.weixin.qq.com/s?__biz=MzY4MzQ3ODA1NA==&chksm=f3b3dc42c4c45554aacc3e5979aa7ad29e76450066ef3ad0af3401b91bfc1092c6ec6e20a627&lang=zh_CN> |
| 发布时间 | 2026-10-10 |
| 公众号名称 | 木先生来了的回忆录（已确认本人账号） |
| 线上正文 | ✅ 渲染后的 HTML（185 个 inline style / 14 个框 / 26 行代码 / 1 张 CDN 图） |
| 线上标题 | ⚠️ 仍为「第一篇」，需改为 **公众号排版这件小事，我用一条命令解决了** |
| 首次失败链接（已废弃） | 首次发布粘的是 Markdown 源文件，正文显示为原始记号；该篇应删除 |
| 手机预览截图 | `<待填写：evidence/published_mobile_preview.png>` |
| 已发布页面截图 | `<待填写：evidence/published_live.png>` |

### 唯一遗留项：改标题

标题栏是公众号自己的字段，**不在正文里**，所以不必重发正文：

1. 后台 → **已发表** → 找到这篇 → 编辑
2. 标题栏改成：`公众号排版这件小事，我用一条命令解决了`
3. 正文一个字都不用动（它已经是对的）

公众号对已发表文章的修改次数有限制，所以一次改对。如果这号不允许改已发表文章，
再走一遍「新建图文 → 粘贴 → 发表」（粘贴步骤见第 2 节，务必用 `.html` 预览页）。

## 4. 传播与数据追踪 / Distribution and tracking

发布不是终点。挑战的「传播设计」维度看的是**渠道是否合理、有没有数据追踪、有没有互动**，
所以下面这张表请在发布后 24 小时和 7 天各填一次。

| 指标 | 24 小时 | 7 天 | 备注 |
|---|---|---|---|
| 阅读量 | | | 公众号后台 → 内容分析 → 图文分析 |
| 点赞 / 在看 | | | |
| 转发 / 分享 | | | |
| 新增关注 | | | |
| 留言条数 | | | |

**渠道安排：**

1. **公众号首发** —— 主渠道。
2. **Elite20 群** —— 发链接 + 一句话说明「附完整技能包，可直接用」。
   群里的人是你的第一批真实用户，他们的反馈最有价值。
3. **知乎同步** —— 用 `article/songpengfei_C4B_output.zhihu.md`（技能自动导出的
   知乎版 Markdown），内容相同、格式适配知乎。
4. **朋友圈 / 其他技术群** —— 一周后发，配一句「用了一周的实测数据」。

**互动设计**（发布前就写进文章或留言区，别等发布后再想）：

- 留言区置顶一个问题：「你最想让公众号自动处理的是什么？」
- 承诺回复所有留言，并把高频问题整理成下一篇。

## 5. 复现这份发布结果 / Reproduce

```bash
# 重新生成正文 HTML（会覆盖，改完源文件后重跑即可）
python skill/wechat-publisher-pro/scripts/convert_to_wechat.py \
       article/songpengfei_C4B_文章源文件.md \
       article/songpengfei_C4B_output.html \
       --fragment --report --validate --also zhihu,plain

# 只看合规校验
python skill/wechat-publisher-pro/scripts/wechat_validate.py \
       article/songpengfei_C4B_output.fragment.html
```

预期输出结尾是 `校验：14/14 通过`。

## 6. 预览不对怎么办 / If the preview looks wrong

| 现象 | 原因 | 处理 |
|---|---|---|
| 图片显示为橙色提示框 | 图片路径不对 | 确认 `article/images/what-wechat-drops.png` 存在 |
| 提示框变成 `[!NOTE]` 字样 | 标记拼写错误 | 对照 `references/callouts.md` 的类型表 |
| 公式变成乱码文本 | 缺 matplotlib | `pip install matplotlib`，或改用 `--math unicode` |
| 中英文之间没有空格 | 源文件里本来就是连着的 | 正常，转换时会自动补上 |
| 提示「外部图片链接」 | 正文里有 http 图片 | 换成同目录本地图片 |

其他情况见 `skill/wechat-publisher-pro/references/troubleshooting.md`。

---

## 附：发布前必须确认的事实

文章里有几处具体数字和陈述，发布前请你自己核对一遍：

- 「四千多行 Python」—— 实际 `scripts/*.py` 共 4565 行（`wc -l` 可复核）。
- 「25/25 vs 4/25」—— 来自 `eval-workspace/iteration-2/benchmark.json`，可重跑复现。
  第一轮（19 条断言）是 19/19 vs 4/19，后来把发现的缺陷补成回归用例，断言增至 25 条。
- 「14 项自动校验」—— 见 `skill/wechat-publisher-pro/scripts/wechat_validate.py`。
- 「六套主题」—— `--list-themes` 可复核。
- 第一人称叙述（「上周我把写好的一篇稿子从 Word 粘进公众号编辑器」）是**写作素材**，
  请按你的真实经历调整。这是你的署名文章，事实和语气都应该由你把关。
