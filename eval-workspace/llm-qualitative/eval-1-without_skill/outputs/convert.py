#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
convert.py
Markdown（含 LaTeX 行内/行间公式、表格、提示块、目录）-> 微信公众号编辑器可直接粘贴的 HTML

用法:
    python convert.py <input.md> <output.html>

微信侧的硬约束（决定了本脚本的实现方式，详见 session_notes.md）:
  1. 粘贴时只保留「行内 style」，<style>/<link>/class/外部字体 全部被丢弃
     -> 产出的每一个标签都自带完整行内样式，不依赖任何外部 CSS
  2. 不支持 MathML / MathJax / KaTeX，<img src="data:...">（base64）会被剥离
     -> 公式用「Unicode 数学符号 + 行内样式排版」就地重建：
        分式 = inline-block 上下堆叠 + border-bottom 分数线
        求和上下限 = inline-block 三行堆叠
        上下标 = <sup>/<sub> + vertical-align 行内样式双保险
  3. 会剥离 id/class，正文内锚点跳转在公众号里无效
     -> 目录渲染为无链接的文本导航
"""
import io
import os
import re
import sys
import html as _html

# ---------------------------------------------------------------- 逃逸/工具
def esc(t):
    return _html.escape(t, quote=False)


def nbsp():
    return '&nbsp;'


# ---------------------------------------------------------------- 全局样式
SANS = ("-apple-system,BlinkMacSystemFont,'Helvetica Neue','PingFang SC',"
        "'Hiragino Sans GB','Microsoft YaHei',sans-serif")
MATH_FONT = "'Cambria Math','Latin Modern Math','Times New Roman',Georgia,serif"

ACCENT = '#2f6fb0'      # 主色
INK = '#1a1a1a'         # 标题色
BODY = '#3f3f3f'        # 正文色
MUTED = '#9aa0a6'       # 辅助色
LINE = '#e6e6e6'

P_STYLE = ("margin:0 0 18px;font-size:16px;line-height:1.8;color:%s;"
           "letter-spacing:.6px;text-align:justify;" % BODY)


# ================================================================ 公式渲染器
_SYMBOLS = {
    # 小写希腊
    'alpha': 'α', 'beta': 'β', 'gamma': 'γ', 'delta': 'δ', 'epsilon': 'ε',
    'varepsilon': 'ε', 'zeta': 'ζ', 'eta': 'η', 'theta': 'θ', 'vartheta': 'ϑ',
    'iota': 'ι', 'kappa': 'κ', 'lambda': 'λ', 'mu': 'μ', 'nu': 'ν', 'xi': 'ξ',
    'pi': 'π', 'rho': 'ρ', 'sigma': 'σ', 'varsigma': 'ς', 'tau': 'τ',
    'upsilon': 'υ', 'phi': 'φ', 'varphi': 'φ', 'chi': 'χ', 'psi': 'ψ',
    'omega': 'ω',
    # 大写希腊
    'Gamma': 'Γ', 'Delta': 'Δ', 'Theta': 'Θ', 'Lambda': 'Λ', 'Xi': 'Ξ',
    'Pi': 'Π', 'Sigma': 'Σ', 'Upsilon': 'Υ', 'Phi': 'Φ', 'Psi': 'Ψ',
    'Omega': 'Ω',
    # 运算/关系
    'pm': '±', 'mp': '∓', 'times': '×', 'div': '÷', 'cdot': '·', 'ast': '∗',
    'star': '⋆', 'circ': '∘', 'bullet': '•',
    'le': '≤', 'leq': '≤', 'ge': '≥', 'geq': '≥', 'ne': '≠', 'neq': '≠',
    'approx': '≈', 'equiv': '≡', 'sim': '∼', 'simeq': '≃', 'propto': '∝',
    'll': '≪', 'gg': '≫', 'infty': '∞', 'partial': '∂', 'nabla': '∇',
    # 集合/逻辑
    'in': '∈', 'notin': '∉', 'subset': '⊂', 'subseteq': '⊆', 'supset': '⊃',
    'cup': '∪', 'cap': '∩', 'emptyset': '∅', 'forall': '∀', 'exists': '∃',
    'neg': '¬', 'land': '∧', 'lor': '∨', 'therefore': '∴', 'because': '∵',
    # 箭头
    'to': '→', 'rightarrow': '→', 'leftarrow': '←', 'Rightarrow': '⇒',
    'Leftarrow': '⇐', 'leftrightarrow': '↔', 'mapsto': '↦',
    # 其它符号
    'ldots': '…', 'dots': '…', 'cdots': '⋯', 'vdots': '⋮', 'ddots': '⋱',
    'prime': '′', 'angle': '∠', 'perp': '⊥', 'parallel': '∥', 'degree': '°',
    'int': '∫', 'iint': '∬', 'oint': '∮',
}
# 行间公式里上下限要「压」在符号正上/正下方的算子
_BIGOPS = {
    'sum': '∑', 'prod': '∏', 'coprod': '∐',
    'bigcup': '⋃', 'bigcap': '⋂', 'bigoplus': '⨁', 'bigotimes': '⨂',
    'lim': 'lim', 'max': 'max', 'min': 'min', 'sup': 'sup', 'inf': 'inf',
    'argmax': 'argmax', 'argmin': 'argmin', 'log': 'log', 'ln': 'ln',
}
_UPRIGHT_WORDS = {
    'text', 'mathrm', 'operatorname', 'mbox', 'textbf', 'mathsf',
}
_NOOP = {'left', 'right', 'big', 'Big', 'bigg', 'Bigg', 'displaystyle',
         'textstyle', 'limits', 'nolimits', 'thinspace', '!'}


def _sup(inner):
    return ('<sup style="vertical-align:super;font-size:.72em;line-height:0;">'
            '%s</sup>' % inner)


def _sub(inner):
    return ('<sub style="vertical-align:sub;font-size:.72em;line-height:0;">'
            '%s</sub>' % inner)


def _frac(num, den):
    """上下堆叠分式：微信保留 inline-block + border-bottom，这是各家排版工具通用做法"""
    return ('<span style="display:inline-block;vertical-align:middle;text-align:center;'
            'font-size:.95em;margin:0 .18em;white-space:nowrap;">'
            '<span style="display:block;padding:0 .38em .06em;'
            'border-bottom:1.2px solid #1a1a1a;line-height:1.35;">%s</span>'
            '<span style="display:block;padding:.06em .38em 0;line-height:1.35;">%s</span>'
            '</span>' % (num, den))


def _stack(sup, sym, sub):
    """求和号/极限号：上限 - 符号 - 下限 三行堆叠"""
    return ('<span style="display:inline-block;vertical-align:middle;text-align:center;'
            'line-height:1.05;margin:0 .14em;font-style:normal;">'
            '<span style="display:block;font-size:.58em;line-height:1.15;font-style:normal;">%s</span>'
            '<span style="display:block;font-size:1.5em;line-height:1;font-style:normal;">%s</span>'
            '<span style="display:block;font-size:.58em;line-height:1.15;font-style:normal;">%s</span>'
            '</span>' % (sup or nbsp(), sym, sub or nbsp()))


class _Math(object):
    """极简 LaTeX 子集解析器：只要能把常见统计/数学写法排版正确即可"""

    def __init__(self, src, display=False):
        self.s = src
        self.n = len(src)
        self.i = 0
        self.display = display

    # ---------- 基础 ----------
    def skip_spaces(self):
        while self.i < self.n and self.s[self.i] in ' \t\n':
            self.i += 1

    def atom_char(self, c):
        if c in ' \t':
            return {'html': nbsp(), 'scriptable': False}
        if c.isascii() and c.isalpha():
            # 数学变量按惯例用斜体
            return {'html': '<span style="font-style:italic;">%s</span>' % c,
                    'scriptable': True}
        return {'html': esc(c),
                'scriptable': c.isdigit() or c in ')]|'}

    def attach(self, items, kind, arg):
        """把 ^ / _ 挂到前一个原子（或前一个花括号组）上"""
        if items and items[-1].get('scriptable'):
            base = items.pop()
            bh = base['html']
        else:
            bh = ''
        sc = _sup(arg) if kind == '^' else _sub(arg)
        return items + [{'html': bh + sc, 'scriptable': False}]

    # ---------- 参数 ----------
    def arg_html(self):
        self.skip_spaces()
        if self.i < self.n and self.s[self.i] == '{':
            self.i += 1
            items = self.parse_list(stop='}')
            return ''.join(it['html'] for it in items)
        items = self.parse_one()
        return ''.join(it['html'] for it in items)

    def parse_one(self):
        if self.i >= self.n:
            return []
        c = self.s[self.i]
        if c == '\\':
            return self.atom_command()
        if c == '{':
            self.i += 1
            items = self.parse_list(stop='}')
            return [{'html': ''.join(it['html'] for it in items),
                     'scriptable': True}]
        self.i += 1
        return [self.atom_char(c)]

    # ---------- 命令 ----------
    def atom_command(self):
        self.i += 1                                   # 吃掉反斜杠
        if self.i >= self.n:
            return []
        m = re.match(r'[A-Za-z]+', self.s[self.i:])
        if not m:                                     # 单字符命令
            c = self.s[self.i]
            self.i += 1
            if c == '\\':                             # \\ 换行
                return [{'html': '<br>', 'scriptable': False}]
            if c == ',':                              # \, 细空格
                return [{'html': '<span style="display:inline-block;width:.17em;"></span>',
                         'scriptable': False}]
            if c in ';:':
                w = '.28em' if c == ';' else '.22em'
                return [{'html': '<span style="display:inline-block;width:%s;"></span>' % w,
                         'scriptable': False}]
            if c == ' ':
                return [{'html': nbsp(), 'scriptable': False}]
            return [{'html': esc(c), 'scriptable': False}]

        name = m.group(0)
        self.i += len(name)

        if name in _NOOP:                             # \left \right \big ...
            return []
        if name == 'frac' or name == 'dfrac' or name == 'tfrac':
            return [{'html': _frac(self.arg_html(), self.arg_html()), 'scriptable': True}]
        if name == 'sqrt':
            arg = self.arg_html()
            return [{'html': '√<span style="border-top:1px solid #1a1a1a;'
                             'padding:.05em .14em 0;">%s</span>' % arg,
                     'scriptable': True}]
        if name in ('bar', 'overline', 'hat', 'widehat', 'vec', 'tilde', 'dot'):
            arg = self.arg_html()
            return [{'html': '<span style="text-decoration:overline;">%s</span>' % arg,
                     'scriptable': True}]
        if name in _UPRIGHT_WORDS:
            arg = self.arg_html()
            return [{'html': '<span style="font-style:normal;">%s</span>' % arg,
                     'scriptable': True}]
        if name in _BIGOPS:
            sym = _BIGOPS[name]
            sub = sup = None
            while True:
                self.skip_spaces()
                if self.i < self.n and self.s[self.i] in '^_':
                    k = self.s[self.i]
                    self.i += 1
                    v = self.arg_html()
                    if k == '_':
                        sub = v
                    else:
                        sup = v
                else:
                    break
            if self.display:
                return [{'html': _stack(sup, sym, sub), 'scriptable': False}]
            h = '<span style="font-style:normal;">%s</span>' % sym
            if sub is not None:
                h += _sub(sub)
            if sup is not None:
                h += _sup(sup)
            return [{'html': h, 'scriptable': False}]
        if name in _SYMBOLS:
            return [{'html': '<span style="font-style:normal;">%s</span>' % _SYMBOLS[name],
                     'scriptable': True}]
        # 未知命令：优雅降级成直立文本，不丢信息也不崩
        return [{'html': '<span style="font-style:normal;">%s</span>' % esc(name),
                 'scriptable': True}]

    # ---------- 主循环 ----------
    def parse_list(self, stop=None):
        items = []
        while self.i < self.n:
            c = self.s[self.i]
            if stop is not None and c == stop:
                self.i += 1
                break
            if c == '}':                              # 花括号不配对时兜底
                self.i += 1
                break
            if c in '^_':
                self.i += 1
                items = self.attach(items, c, self.arg_html())
                continue
            if c == '\\':
                items.extend(self.atom_command())
                continue
            if c == '{':
                self.i += 1
                inner = self.parse_list(stop='}')
                items.append({'html': ''.join(it['html'] for it in inner),
                              'scriptable': True})
                continue
            self.i += 1
            items.append(self.atom_char(c))
        return items


def math_html(tex, display=False):
    """LaTeX 片段 -> 带内联样式的 HTML 片段"""
    src = tex.strip()
    try:
        body = ''.join(it['html'] for it in _Math(src, display).parse_list())
    except Exception:                                 # 解析失败也要能出稿
        body = esc(src)
    if display:
        return ('<span style="font-family:%s;font-style:normal;font-size:17px;'
                'color:%s;white-space:nowrap;">%s</span>' % (MATH_FONT, INK, body))
    return ('<span style="font-family:%s;font-style:normal;font-size:.96em;'
            'color:%s;white-space:nowrap;">%s</span>' % (MATH_FONT, INK, body))


# ================================================================ 行内 Markdown
_MATH_PLACE = re.compile(r'\$([^$\n]+?)\$')


def render_inline(text):
    stash = []

    def _stash(html_str):
        stash.append(html_str)
        return '\x00%d\x00' % (len(stash) - 1)

    # 1) 先摘出行内公式，避免被 Markdown/转义污染
    text = _MATH_PLACE.sub(lambda m: _stash(math_html(m.group(1), False)), text)
    # 2) 转义
    text = esc(text)
    # 3) 行内 Markdown
    text = re.sub(r'\*\*(.+?)\*\*',
                  r'<strong style="font-weight:bold;color:' + INK + r';">\1</strong>',
                  text)
    text = re.sub(r'`([^`]+?)`',
                  r'<code style="font-family:Consolas,Monaco,monospace;'
                  r'font-size:.92em;background:#f4f5f7;color:#c7254e;'
                  r'padding:1px 5px;border-radius:3px;">\1</code>', text)
    text = re.sub(r'(?<![*\w])\*(?!\s)([^*\n]+?)(?<!\s)\*(?!\*)', r'<em>\1</em>', text)
    text = re.sub(r'\[([^\]]+)\]\((https?://[^)\s]+)\)',
                  r'<a href="\2" style="color:' + ACCENT + r';'
                  r'text-decoration:underline;">\1</a>', text)
    # 4) 还原公式
    text = re.sub(r'\x00(\d+)\x00', lambda m: stash[int(m.group(1))], text)
    return text


# ================================================================ 块级渲染
def p(inner, style=None):
    return '<p style="%s">%s</p>' % (style or P_STYLE, inner)


def h2(index, title):
    return ('<h2 style="margin:38px 0 18px;padding:2px 0 2px 13px;'
            'border-left:4px solid %s;font-size:19px;line-height:1.5;'
            'font-weight:bold;color:%s;letter-spacing:.8px;">'
            '<span style="font-family:Georgia,serif;font-size:15px;color:%s;'
            'font-weight:bold;margin-right:9px;">%02d</span>%s</h2>'
            % (ACCENT, INK, ACCENT, index, render_inline(title)))


def formula_block(tex):
    return ('<p style="margin:22px 0;padding:0;text-align:center;line-height:2;'
            'font-size:17px;">%s</p>' % math_html(tex, display=True))


def table_block(rows):
    head, body = rows[0], rows[1:]
    ncol = max(len(head), max((len(r) for r in body), default=0))
    # table-layout:fixed 下由首行决定列宽：首列窄一些，其余均分
    first = 24
    rest = round((100 - first) / max(ncol - 1, 1), 2) if ncol > 1 else 100
    widths = [first] + [rest] * (ncol - 1)
    out = ['<table style="width:100%;border-collapse:collapse;margin:20px 0;'
           'font-size:14px;table-layout:fixed;">']
    out.append('<thead><tr>')
    for j, c in enumerate(head):
        out.append('<th style="width:%s%%;border:1px solid #dfe3e8;background:#f4f7fb;'
                   'padding:9px 6px;font-weight:bold;color:#2b4a6b;'
                   'text-align:center;line-height:1.5;font-size:14px;'
                   'word-break:break-word;">%s</th>'
                   % (widths[j] if j < len(widths) else rest, render_inline(c)))
    out.append('</tr></thead><tbody>')
    for r in body:
        out.append('<tr>')
        for j, c in enumerate(r):
            align = 'left' if j else 'center'
            weight = 'bold' if j == 0 else 'normal'
            color = '#2b4a6b' if j == 0 else '#45505c'
            out.append('<td style="border:1px solid #dfe3e8;padding:9px 7px;'
                       'color:%s;font-weight:%s;text-align:%s;line-height:1.6;'
                       'vertical-align:middle;word-break:break-word;">%s</td>'
                       % (color, weight, align, render_inline(c)))
        out.append('</tr>')
    out.append('</tbody></table>')
    return ''.join(out)


_CALLOUT = {
    'key': ('关键', '#b87503', '#fff8e6', '#e8a33d'),
    'success': ('结论', '#3d7a2e', '#f0f9eb', '#7ac756'),
    'note': ('提示', '#2f6fb0', '#f2f7fc', '#6aa6dd'),
}


def callout_block(kind, title, lines):
    label, fg, bg, bar = _CALLOUT.get(kind, _CALLOUT['note'])
    if title and title != label:          # 标题与标签同名时不重复（否则会出现「结论 · 结论」）
        head_text = label + ' · ' + render_inline(title)
    elif title:
        head_text = render_inline(title)
    else:
        head_text = label
    head = ('<p style="margin:0 0 7px;font-size:13px;font-weight:bold;'
            'color:%s;letter-spacing:1px;">%s</p>' % (fg, head_text))
    body = ''.join('<p style="margin:%s;font-size:15px;line-height:1.8;'
                   'color:#4a4a4a;letter-spacing:.5px;">%s</p>'
                   % ('0 0 8px' if k < len(lines) - 1 else '0', render_inline(t))
                   for k, t in enumerate(lines))
    return ('<section style="margin:20px 0;padding:15px 17px;background:%s;'
            'border-left:4px solid %s;border-radius:0 6px 6px 0;">%s%s</section>'
            % (bg, bar, head if (title or label) else '', body))


def quote_block(lines):
    body = ''.join('<p style="margin:%s;font-size:15px;line-height:1.8;'
                   'color:#5a6270;letter-spacing:.5px;">%s</p>'
                   % ('0 0 8px' if k < len(lines) - 1 else '0', render_inline(t))
                   for k, t in enumerate(lines))
    return ('<section style="margin:20px 0;padding:13px 16px;background:#f8f9fa;'
            'border-left:3px solid #cfd6de;border-radius:0 5px 5px 0;">%s</section>'
            % body)


def toc_block(items):
    rows = []
    for k, (idx, title) in enumerate(items):
        last = (k == len(items) - 1)
        rows.append('<p style="margin:%s;font-size:15px;line-height:1.9;'
                    'color:#4a5568;letter-spacing:.5px;">'
                    '<span style="color:%s;font-family:Georgia,serif;'
                    'font-size:13px;font-weight:bold;margin-right:9px;">%02d</span>'
                    '%s</p>'
                    % ('0 0 9px' if not last else '0', ACCENT, idx,
                       render_inline(title)))
    return ('<section style="margin:24px 0 30px;padding:16px 18px;background:#f7f9fc;'
            'border:1px solid #e6ecf3;border-radius:8px;">'
            '<p style="margin:0 0 11px;padding:0 0 9px;font-size:14px;'
            'font-weight:bold;color:%s;letter-spacing:2px;'
            'border-bottom:1px dashed #dbe3ec;">本 文 导 读</p>%s</section>'
            % (ACCENT, ''.join(rows)))


# ---------------------------------------------------------------- front matter
def parse_front_matter(text):
    meta = {}
    body = text
    if text.lstrip().startswith('---'):
        stripped = text.lstrip()
        end = stripped.find('\n---', 3)
        if end != -1:
            raw = stripped[3:end]
            body = stripped[end + 4:]
            for line in raw.splitlines():
                if ':' in line:
                    k, v = line.split(':', 1)
                    meta[k.strip()] = v.strip()
    return meta, body.lstrip('\n')


# ---------------------------------------------------------------- 主转换
def convert(md_text):
    meta, body = parse_front_matter(md_text)
    lines = body.replace('\r\n', '\n').split('\n')

    blocks = []      # ('h2', title) / ('html', str)
    headings = []
    i = 0
    while i < len(lines):
        raw = lines[i]
        line = raw.strip()

        if not line:
            i += 1
            continue

        # 行间公式
        if line.startswith('$$'):
            buf = []
            rest = line[2:]
            if rest.endswith('$$') and len(rest) > 2:
                buf.append(rest[:-2])
                i += 1
            else:
                if rest.strip():
                    buf.append(rest)
                i += 1
                while i < len(lines) and '$$' not in lines[i]:
                    buf.append(lines[i])
                    i += 1
                if i < len(lines):
                    buf.append(lines[i].split('$$')[0])
                    i += 1
            blocks.append(('html', formula_block('\n'.join(buf))))
            continue

        # 标题
        m = re.match(r'^(#{1,6})\s+(.*)$', line)
        if m:
            level = len(m.group(1))
            title = m.group(2).strip()
            if level <= 2:
                headings.append((len(headings) + 1, title))
                blocks.append(('h2', title))
            else:
                blocks.append(('html',
                               '<h3 style="margin:26px 0 14px;font-size:17px;'
                               'font-weight:bold;color:%s;line-height:1.5;">%s</h3>'
                               % (INK, render_inline(title))))
            i += 1
            continue

        # 分隔线
        if re.match(r'^(-{3,}|\*{3,}|_{3,})$', line):
            blocks.append(('html',
                           '<p style="margin:26px 0;text-align:center;color:#d5d9de;'
                           'font-size:14px;letter-spacing:8px;">◆ ◆ ◆</p>'))
            i += 1
            continue

        # 表格
        if line.startswith('|') and i + 1 < len(lines) and \
                re.match(r'^\|[\s:\-|]+\|$', lines[i + 1].strip()):
            rows = []
            while i < len(lines) and lines[i].strip().startswith('|'):
                cells = [c.strip() for c in lines[i].strip().strip('|').split('|')]
                if not re.match(r'^[\s:\-|]+$', lines[i].strip().strip('|')):
                    rows.append(cells)
                i += 1
            blocks.append(('html', table_block(rows)))
            continue

        # 引用 / 提示块
        if line.startswith('>'):
            buf = []
            while i < len(lines) and lines[i].strip().startswith('>'):
                buf.append(re.sub(r'^\s*>\s?', '', lines[i].rstrip()))
                i += 1
            head = buf[0].strip() if buf else ''
            m2 = re.match(r'^\[!(\w+)\]\s*(.*)$', head)
            if m2:
                blocks.append(('html',
                               callout_block(m2.group(1).lower(),
                                             m2.group(2).strip(),
                                             [b for b in buf[1:] if b.strip()])))
            else:
                blocks.append(('html', quote_block([b for b in buf if b.strip()])))
            continue

        # 有序/无序列表
        if re.match(r'^([-*+]|\d+\.)\s+', line):
            ordered = bool(re.match(r'^\d+\.', line))
            items = []
            while i < len(lines) and re.match(r'^([-*+]|\d+\.)\s+', lines[i].strip()):
                items.append(re.sub(r'^([-*+]|\d+\.)\s+', '', lines[i].strip()))
                i += 1
            tag = 'ol' if ordered else 'ul'
            lis = ''.join(
                '<li style="margin:0 0 9px;font-size:16px;line-height:1.8;'
                'color:%s;letter-spacing:.6px;">%s</li>' % (BODY, render_inline(t))
                for t in items)
            blocks.append(('html',
                           '<%s style="margin:0 0 18px;padding-left:24px;">%s</%s>'
                           % (tag, lis, tag)))
            continue

        # 普通段落（连续行合并）
        buf = [line]
        i += 1
        while i < len(lines):
            nxt = lines[i].strip()
            if (not nxt or nxt.startswith('#') or nxt.startswith('|')
                    or nxt.startswith('>') or nxt.startswith('$$')
                    or re.match(r'^([-*+]|\d+\.)\s+', nxt)
                    or re.match(r'^(-{3,}|\*{3,}|_{3,})$', nxt)):
                break
            buf.append(nxt)
            i += 1
        blocks.append(('html', p(render_inline(' '.join(buf)))))

    # ---------------- 组装文档 ----------------
    parts = []
    title = meta.get('title', '')
    if title:
        parts.append('<h1 style="margin:0 0 12px;font-size:22px;font-weight:bold;'
                     'color:%s;line-height:1.45;letter-spacing:.8px;">%s</h1>'
                     % (INK, render_inline(title)))
    meta_bits = [b for b in (meta.get('author'), meta.get('date')) if b]
    if meta_bits:
        parts.append('<p style="margin:0 0 4px;font-size:13px;color:%s;'
                     'letter-spacing:.8px;">%s</p>' % (MUTED, ' · '.join(meta_bits)))
    if title or meta_bits:
        parts.append('<p style="margin:0 0 24px;border-bottom:1px solid %s;'
                     'height:1px;font-size:0;line-height:0;">&nbsp;</p>' % LINE)
    if meta.get('digest'):
        parts.append('<p style="margin:0 0 24px;font-size:14px;line-height:1.8;'
                     'color:#7b838c;letter-spacing:.6px;padding:0 2px;">%s</p>'
                     % render_inline(meta['digest']))

    if headings and str(meta.get('toc', '')).lower() not in ('none', 'false', '0'):
        parts.append(toc_block(headings))

    for kind, val in blocks:
        if kind == 'h2':
            idx = next(n for n, t in headings if t == val)
            parts.append(h2(idx, val))
        else:
            parts.append(val)

    article = ('<section style="font-size:16px;line-height:1.8;color:%s;'
               'letter-spacing:.6px;font-family:%s;word-break:break-word;">%s</section>'
               % (BODY, SANS, ''.join(parts)))
    return meta, article


# ---------------------------------------------------------------- 自检
RISKY = [
    (r'class\s*=', 'class 属性（微信粘贴时会剥离，样式可能丢失）'),
    (r'<style', '<style> 块（微信粘贴时整块丢弃）'),
    (r'<link', '<link> 外链样式'),
    (r'position\s*:\s*(fixed|absolute|sticky)', 'position 定位（微信会剥离）'),
    (r'float\s*:', 'float（微信排版会错乱）'),
    (r'src\s*=\s*"data:', 'base64 图片（微信会剥离）'),
    (r'<script', '<script>'),
    (r'id\s*=\s*"', 'id 属性（微信会剥离）'),
    (r'@media|@import|var\(--', 'CSS 高级特性（微信不支持）'),
]


def audit(html_text):
    problems = []
    for pat, desc in RISKY:
        n = len(re.findall(pat, html_text, flags=re.I))
        if n:
            problems.append('%s x%d' % (desc, n))
    # 统计信息
    stats = {
        '公式块': len(re.findall(r'font-family:[^;"]*Times New Roman', html_text)),
        '分式': len(re.findall(r'border-bottom:1\.2px solid #1a1a1a', html_text)),
        '表格': len(re.findall(r'<table', html_text)),
        '上下标': len(re.findall(r'<su[bp]', html_text)),
        '内联样式标签': len(re.findall(r'style="', html_text)),
        '残留 LaTeX 反斜杠': len(re.findall(r'\\[a-zA-Z]+', html_text)),
        '残留 $ 符号': html_text.count('$'),
    }
    return problems, stats


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    src, dst = sys.argv[1], sys.argv[2]
    with io.open(src, 'r', encoding='utf-8') as f:
        md = f.read()

    meta, article = convert(md)

    out = (
        '<!DOCTYPE html>\n<html lang="zh-CN">\n<head>\n'
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width,initial-scale=1">\n'
        '<title>%s</title>\n'
        '<!-- 公众号发表时填表用：标题=%s / 摘要=%s -->\n'
        '</head>\n'
        # body 用纯白、零内边距：整页全选复制时不会把「预览用的灰底/留白」带进公众号
        '<body style="margin:0;padding:0;background:#ffffff;font-family:%s;">\n'
        '<section style="max-width:677px;margin:0 auto;padding:28px 22px;'
        'background:#ffffff;">\n%s\n</section>\n'
        '</body>\n</html>\n'
        % (esc(meta.get('title', '文章')), esc(meta.get('title', '')),
           esc(meta.get('digest', '')), SANS, article))

    os.makedirs(os.path.dirname(os.path.abspath(dst)) or '.', exist_ok=True)
    with io.open(dst, 'w', encoding='utf-8', newline='\n') as f:
        f.write(out)

    problems, stats = audit(article)
    print('已生成: %s  (%d 字符)' % (dst, len(out)))
    print('统计: ' + ', '.join('%s=%s' % kv for kv in stats.items()))
    if problems:
        print('风险项:')
        for x in problems:
            print('  ! ' + x)
    else:
        print('风险项: 无（未使用 class/<style>/定位/base64 等微信会剥离的写法）')
    return 0


if __name__ == '__main__':
    sys.exit(main())
