# Callouts

A callout is a framed box that sets a passage apart from the body: a definition,
a warning, a conclusion. In a WeChat article they carry most of the visual
rhythm, because headings alone give the reader nowhere to rest.

## Syntax

GitHub's alert syntax, which most authors already know:

```markdown
> [!NOTE] 可选标题
> 正文第一段。
> 正文第二段——同一行内换行会变成换行。
```

The title after the kind is optional. If omitted, the kind's default label is
used.

## Available kinds

| Marker | Label | Colour family | Use for |
|---|---|---|---|
| `[!NOTE]` | 📘 知识点 | accent (blue) | Background a reader needs |
| `[!TIP]` | 💡 提示 | green | A shortcut or a better habit |
| `[!KEY]` | 🔑 重点 | accent (blue) | The one sentence to remember |
| `[!WARNING]` | ⚠️ 注意 | amber | A likely mistake |
| `[!DANGER]` | 🚨 警告 | red | Data loss, irreversibility |
| `[!SUCCESS]` | ✅ 结论 | green | The takeaway at the end of a section |
| `[!EXAMPLE]` | 🧪 示例 | violet | A worked example |
| `[!CONFUSED]` | 🤔 疑问 | amber | The point where you got stuck |
| `[!QUOTE]` | 💬 引用 | neutral grey | Somebody else's words |

Box colours are fixed per kind and do **not** follow the theme. A warning should
read as amber whether the article is blue or ink-washed — the colour is a
meaning, not decoration. Only the accent-family boxes (`NOTE`, `KEY`) track the
theme.

## What goes inside

The first line is the label; everything after it is body. Because `--nl2br` is
on, each source line becomes its own paragraph inside the box, so a callout can
hold several paragraphs:

```markdown
> [!WARNING] 上传图片的两个坑
> 第一，外部链接的图片不会被自动抓取。
>
> 第二，SVG 在保存时会被丢弃，必须换成 PNG。
```

Lists work too:

```markdown
> [!TIP] 发布前检查
> - 手机上预览一次
> - 确认摘要不超过 120 字
> - 确认封面图已选
```

### Known limitations

- **No code blocks inside a callout.** Markdown flattens a fenced block inside a
  blockquote. Put the sample just after the box instead.
- **No nested callouts.** A box inside a box has no visual hierarchy in an
  inline-CSS world, and WeChat renders nested tables inconsistently.

## Consecutive callouts

Markdown merges consecutive `>` blocks into a single `<blockquote>` holding one
`<p>` per alert. The converter splits them back apart by scanning every
top-level paragraph, so this works:

```markdown
> [!NOTE] 第一个
> 内容

> [!WARNING] 第二个
> 内容
```

A paragraph that follows a callout without starting a new `[!TYPE]` is absorbed
as another paragraph of the *same* box. That is usually what the author means;
if it is not, insert an HTML comment or a horizontal rule between them.

## Adding a new kind

Two edits in `scripts/themes.py`.

1. Register the kind in `CALLOUT_TYPES`:

```python
"dangerzone": {"emoji": "☢️", "label": "危险区", "token": "red"},
```

2. If it needs a colour family that does not exist yet, add one to
   `CALLOUT_COLORS` as `token: (background, border, label_colour)` and the
   generated styles follow automatically:

```python
"teal": ("#e6f7f7", "#0d9488", "#0f5f5a"),
```

No HTML or CSS needs writing — `build_styles` emits a
`callout_*_<token>` style for every entry in `CALLOUT_COLORS`, and the renderer
looks them up by name.

## When a kind is unknown

An unrecognised marker is left as an ordinary quote and reported:

```
⚠️ 未知的 callout 类型 [!NOTEE]，已按普通引用处理
```

Nothing is lost, and the warning names the typo.

## `--callout-style plain`

Some desktop rich-text editors flatten tables badly. `--callout-style plain`
swaps the table box for a left-ruled paragraph run instead, keeping the border
colour and the label. It looks less like a box and more like a pull-quote; use
it only if tables misbehave on the destination platform.
