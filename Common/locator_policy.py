# -*- coding: utf-8 -*-
"""
==========================================================================
 元素定位规范检查（新人阅读顺序：第 20 个，写新定位前扫一眼）
==========================================================================

【一句话说明】
    静态扫描 Common/elementPage.py，统计定位写得好不好，并给出改进建议。
    它**不启动浏览器**，纯读源码，所以可以随时跑、在 CI 里跑。

【为什么需要它】
    元素定位是 UI 自动化里维护成本最高的一环。经验规律：
        用 id / 语义文字定位   -> 前端改版通常不受影响
        用长链路的 xpath       -> 前端随便挪一层 div 就失效
        用 /html/body/div[4]   -> 基本等于"写死"，改版必挂
    这类劣化是**渐进**的：每次赶工期随手复制一条 xpath，单看都没问题，
    半年后整个元素表就没法维护了。所以要么定期体检，要么设门禁拦住增量。

【在框架中的位置】
    Common/elementPage.py      被扫描的对象（元素定位总表）
        └─> Common/locator_policy.py   <- 本文件（只读，不改任何东西）
              ├─> tests/test_locator_policy.py  门禁：脆弱定位不得增加
              └─> python -m Common.locator_policy  人工查看完整报告

【怎么用】
    # 看当前健康度
    python -m Common.locator_policy

    # 只看有问题的条目
    python -m Common.locator_policy --issues

【四级评级】
    GOOD        id / css / 按文字或属性定位 —— 推荐，改版不易失效
    INDEXED     含 [n] 下标，如 .../form/div[2]/div/div/input
    DEEP_INDEX  下标出现在 3 段以上，链路一旦变动必然失效
    ABSOLUTE    以 /html 或 / 开头的绝对路径 —— 最脆弱，应尽快替换

【新人注意】
    1. 本模块**只读源码**，不 import 元素表（避免触发 selenium 依赖），
       所以它能在任何环境下运行。
    2. 新增定位时的优先级：id > name > 可见文字 > 占位提示 > 属性 > css > 相对 xpath。
       绝对路径 xpath 一律不要写。
    3. 门禁的基线记在 tests/test_locator_policy.py，改善后请把基线调低
       （只降不升）—— 这样规范才是一步步收紧，而不是一次性写完就烂掉。
==========================================================================
"""

import argparse
import ast
import os
import re
import sys
from typing import Dict

# 定位条目形如：
#     Username = ['xpath', "//input[@type='text']"]      # 用户名输入框
#     组 1=名称  组 2=定位方式  组 3=定位值  组 4=行内注释（可空）
LOCATOR_RE = re.compile(
    r"""^\s*([A-Za-z_]\w*)\s*=\s*\[\s*['"]([a-z_]+)['"]\s*,\s*(.+?)\s*\]\s*(#\s*(.*))?$"""
)

# 定位条目的"开头部分"，用于识别把定位值拆成多行的写法：
#     submission = ['xpath',
#                   "//*[@id='app']/..."
#                   "/table/tbody/..."]
# 长 xpath 拆行是为了不超出行长限制，属于合法写法，检查工具必须认得。
HEAD_RE = re.compile(r"""^\s*([A-Za-z_]\w*)\s*=\s*\[\s*['"]([a-z_]+)['"]\s*,""")

# 下标索引：[2] / [1] 这种"第 n 个"的写法，是脆弱的核心信号
INDEX_RE = re.compile(r'\[\s*\d+\s*\]')

# 定位方式里哪些算"稳健"（不依赖 DOM 层级）
STABLE_KINDS = ('id', 'name', 'css', 'link_text', 'partial_link_text')

# 评级常量
GOOD = 'GOOD'
INDEXED = 'INDEXED'
DEEP_INDEX = 'DEEP_INDEX'
ABSOLUTE = 'ABSOLUTE'

#: 下标出现几段以上算"深链路"
DEEP_INDEX_THRESHOLD = 3


def default_source_path():
    """元素表的默认路径：Common/elementPage.py（与本文件同目录）。"""
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), 'elementPage.py')


def _strip_quotes(text):
    """去掉最外层成对的引号（单引号或双引号）。"""
    if len(text) >= 2 and text[0] == text[-1] and text[0] in '"\'':
        return text[1:-1]
    return text


def _eval_value(inner, has_by=True):
    """从 `'xpath', "//a" "//b"` 这样的片段里取出定位值。

    :param inner:  待解析的片段
    :param has_by: True 表示片段开头还带着定位方式（`'xpath', ...`），要先切掉

    多行写法下，定位值会被写成若干相邻的字符串字面量，
    交给 ast.literal_eval 求值即可 —— Python 本身就会把相邻字面量拼起来。
    求值失败（值不是纯字面量）时退回"去掉引号"的粗糙处理，保证不炸。
    """
    rest = inner
    if has_by:
        if ',' not in inner:
            return _strip_quotes(inner.strip())
        rest = inner.split(',', 1)[1]
    rest = rest.strip()
    try:
        return str(ast.literal_eval(rest))
    except (ValueError, SyntaxError):
        return _strip_quotes(rest)


def _matching_bracket(chunk):
    """返回与首个 `[` 配对的 `]` 的位置；找不到返回 -1。

    为什么不能用 chunk.find(']')：定位值内部自己就带方括号
    （xpath 里的 `div[2]`、`@id='app']`），取第一个会**把定位值截断**，
    统计出来的值就变了样。这里老老实实做一次配对计数。
    """
    depth = 0
    for pos, char in enumerate(chunk):
        if char == '[':
            depth += 1
        elif char == ']':
            depth -= 1
            if depth == 0:
                return pos
    return -1


def _make_entry(name, by, value, comment, lineno):
    """组装一条定位记录，顺带评级。"""
    rating, reasons = rate_locator(by, value)
    return {
        'name': name,
        'by': by,
        'value': value,
        'comment': (comment or '').strip(),
        'line': lineno,
        'rating': rating,
        'reasons': reasons,
    }


def parse_locators(source_text):
    """从元素表源码里解析出所有定位条目。

    :param source_text: elementPage.py 的源码文本
    :return: 列表，每项为字典：
        {'name', 'by', 'value', 'comment', 'line', 'rating', 'reasons'}

    用正则而不是 ast 解析：这里的格式高度规整（一行一条），
    正则更短、报错更直观，也避免了 import 元素表带来的 selenium 依赖。

    两个必须处理的写法差异（否则会漏统计）：
      1. 注释可以在行内（`X = [...]  # 说明`），也可以在上一行（`# 说明` 换行 `X = [...]`）。
         两种都算"有注释"，只认行内会把已经写清楚的条目误判成"缺注释"。
      2. 定位值允许拆成多行（长 xpath 为了不超行长限制）。
         漏掉这种写法会让统计凭空少几条，门禁的基线也就失真了。
    """
    lines = source_text.splitlines()
    entries = []
    pending_comment = ''
    index = 0

    while index < len(lines):
        raw_line = lines[index]
        stripped = raw_line.strip()

        # 累积紧邻上方的注释；遇到空行清空，避免把很远处的注释算到本条头上
        if stripped.startswith('#'):
            pending_comment = stripped.lstrip('#').strip()
            index += 1
            continue
        if not stripped:
            pending_comment = ''
            index += 1
            continue

        # ---- 快路径：常规的单行写法 ----
        match = LOCATOR_RE.match(raw_line)
        if match:
            name, by, _raw, _mark, comment = match.groups()
            value = _eval_value(_raw, has_by=False)
            entries.append(_make_entry(name, by, value,
                                       comment or pending_comment, index + 1))
            pending_comment = ''
            index += 1
            continue

        # ---- 慢路径：定位值跨了多行 ----
        head = HEAD_RE.match(raw_line)
        if not head:
            pending_comment = ''
            index += 1
            continue

        chunk = raw_line[raw_line.index('['):]
        last = index
        # 按方括号配对把整条定位读全
        while chunk.count('[') > chunk.count(']') and last + 1 < len(lines):
            last += 1
            chunk += ' ' + lines[last].strip()
        close = _matching_bracket(chunk)
        inner = chunk[1:close] if close >= 0 else chunk[1:]
        value = _eval_value(inner)
        tail = chunk[close + 1:] if close >= 0 else ''
        inline = tail.split('#', 1)[1].strip() if '#' in tail else ''
        entries.append(_make_entry(head.group(1), head.group(2), value,
                                   inline or pending_comment, index + 1))
        pending_comment = ''
        index = last + 1

    return entries


def rate_locator(by, value):
    """给单条定位评级。

    :return: (评级常量, 原因列表)
    """
    kind = str(by).strip().lower()
    text = str(value).strip()
    reasons = []

    # 非 xpath 且是已知的稳健方式 -> GOOD
    if kind in STABLE_KINDS:
        return GOOD, ['使用 %s 定位，不依赖 DOM 层级' % kind]

    if kind != 'xpath':
        # 未知方式（拼错的 by）单列出来，避免它被当成"稳健方式"混过去
        return INDEXED, ['未知的定位方式 %s，应为 id/css/xpath 等' % kind]

    # ---- 以下都是 xpath 的分级 ----
    # 绝对路径：从根节点逐层写下来，例如 /html/body/div[4]/section/...
    # ★ 注意区分：//div 是"从任意位置查找"，不是绝对路径，别判错
    if text.startswith('/') and not text.startswith('//'):
        reasons.append('绝对路径 xpath：从根节点逐层写死，层级一调整必然失效')
        if INDEX_RE.search(text):
            reasons.append('同时含下标索引，位置变动即失效')
        return ABSOLUTE, reasons

    indexes = INDEX_RE.findall(text)
    if len(indexes) >= DEEP_INDEX_THRESHOLD:
        return DEEP_INDEX, ['含 %d 段下标索引，链路长且脆弱' % len(indexes)]
    if indexes:
        # 用文字锚定的 xpath 虽然也有下标，但锚在可见文字上，相对稳一些
        anchor = ('text()' in text) or ('contains(' in text)
        if anchor:
            return GOOD, ['xpath 但以可见文字锚定，相对稳健']
        return INDEXED, ['含 %d 段下标索引' % len(indexes)]

    # 相对 xpath 且无下标：可接受（例如 //input[@type='file']）
    return GOOD, ['相对 xpath，未使用下标索引']


def analyze(entries):
    """汇总统计，返回可直接展示的结构。"""
    total = len(entries) or 1
    by_kind: Dict[str, int] = {}
    rating_count: Dict[str, int] = {}
    for item in entries:
        by_kind[item['by']] = by_kind.get(item['by'], 0) + 1
        rating_count[item['rating']] = rating_count.get(item['rating'], 0) + 1

    flawed = [item for item in entries if item['rating'] in (INDEXED, DEEP_INDEX, ABSOLUTE)]
    return {
        'total': len(entries),
        'by_kind': by_kind,
        'rating': rating_count,
        'xpath_ratio': round(by_kind.get('xpath', 0) * 100.0 / total, 1),
        'absolute': len([i for i in entries if i['rating'] == ABSOLUTE]),
        'deep_index': len([i for i in entries if i['rating'] == DEEP_INDEX]),
        'indexed': len([i for i in entries if i['rating'] == INDEXED]),
        'flawed': len(flawed),
        'missing_comment': len([i for i in entries if not i['comment']]),
        'flawed_names': [i['name'] for i in flawed],
    }


def scan(path=None):
    """扫描元素表，返回 (条目列表, 统计字典)。"""
    path = path or default_source_path()
    with open(path, 'r', encoding='utf-8') as fp:
        source = fp.read()
    entries = parse_locators(source)
    return entries, analyze(entries)


def format_report(entries, stats, only_issues=False):
    """把扫描结果排版成便于阅读的文本报告。"""
    lines = []
    lines.append('元素定位健康报告')
    lines.append('=' * 62)
    lines.append('定位条目总数 : %d' % stats['total'])
    lines.append('定位方式分布 : %s' % '、'.join(
        '%s %d' % (k, v) for k, v in sorted(stats['by_kind'].items(), key=lambda x: -x[1])))
    lines.append('xpath 占比   : %.1f%%' % stats['xpath_ratio'])
    lines.append('')
    lines.append('评级分布：')
    lines.append('  GOOD       （推荐）%d 条' % stats['rating'].get(GOOD, 0))
    lines.append('  INDEXED    （含下标）%d 条' % stats['indexed'])
    lines.append('  DEEP_INDEX （长链路）%d 条' % stats['deep_index'])
    lines.append('  ABSOLUTE   （绝对路径）%d 条' % stats['absolute'])
    lines.append('缺注释       : %d 条' % stats['missing_comment'])
    lines.append('')

    targets = [i for i in entries if i['rating'] != GOOD] if only_issues else entries
    if targets:
        lines.append('-' * 62)
        lines.append('%s：' % ('需要改进的条目' if only_issues else '全部条目'))
        for item in targets:
            lines.append('  [%-10s] %-26s %s' % (item['rating'], item['name'], item['by']))
            lines.append('      %s' % _shorten(item['value'], 68))
            if item['reasons']:
                lines.append('      -> %s' % '；'.join(item['reasons']))
        lines.append('')

    lines.append('=' * 62)
    lines.append('改进优先级：ABSOLUTE > DEEP_INDEX > INDEXED')
    lines.append('替换顺序建议：id > name > 可见文字 > 占位提示 > 属性 > css > 相对 xpath')
    return '\n'.join(lines)


def _shorten(text, limit):
    text = str(text)
    return text if len(text) <= limit else text[:limit - 3] + '...'


def main(argv=None):
    parser = argparse.ArgumentParser(description='元素定位规范检查（只读，不启动浏览器）')
    parser.add_argument('--issues', action='store_true', help='只列出需要改进的条目')
    parser.add_argument('--path', help='元素表路径，默认 Common/elementPage.py')
    parser.add_argument('--fail-over', type=int,
                        help='脆弱定位超过该数量时退出码为 1，供 CI 当门禁用')
    args = parser.parse_args(argv)

    entries, stats = scan(args.path)
    print(format_report(entries, stats, only_issues=args.issues))

    if args.fail_over is not None and stats['flawed'] > args.fail_over:
        print('脆弱定位 %d 条，超过阈值 %d -> 失败'
              % (stats['flawed'], args.fail_over))
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
