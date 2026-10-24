# -*- coding: utf-8 -*-
"""
==========================================================================
 失败自动归因（把"失败了"变成"为什么失败"）
==========================================================================

【解决什么问题】
    改造前 CI 上的失败长这样：
        FAILED: test_6submitted —— AssertionError
    然后值班的人要自己判断：是定位失效？环境问题？业务真的坏了？
    这个判断每次都要重新做一遍，而且依赖个人经验。

【做法】
    按**异常类型 + 堆栈 + 失败信息**自动归类到有限的几类，
    每类都给出「下一步该做什么」。归类是规则驱动的（可单测、可解释），
    不是猜的。

【分类与对应的处理人】
    LOCATOR      定位失效      -> 前端改版了，改 elementPage（自动化维护者）
    ENVIRONMENT  环境/驱动问题  -> 找运维或平台组（不是用例问题）
    CONFIG       配置缺失/错误  -> 配置的人自己改（最省事，但最常发生）
    BUSINESS     业务断言失败   -> 可能是真 bug，找开发（最有价值的一类）
    DATA         测试数据问题   -> 造数/清理没做好
    TIMEOUT      超时          -> 可能是性能退化，也可能是等待策略不当
    UNKNOWN      无法归类      -> 需要人工判断，同时说明规则该补了

【为什么值得做】
    归因把"每次都要重新判断"变成"看一眼分类就知道找谁"。
    在回归规模上去之后（几百条用例），这是排错效率的分水岭。
==========================================================================
"""

import re
from typing import Any, Dict

# 分类常量
LOCATOR = 'locator'
ENVIRONMENT = 'environment'
CONFIG = 'config'
BUSINESS = 'business'
DATA = 'data'
TIMEOUT = 'timeout'
UNKNOWN = 'unknown'

#: 分类 -> (中文名, 处理建议)。顺序即展示顺序。
CATEGORY_INFO = {
    LOCATOR: (
        '定位失效',
        '页面结构可能变了：检查 Common/elementPage.py 对应条目，优先改用按可见文字/属性定位',
    ),
    ENVIRONMENT: (
        '环境或驱动问题',
        '不是用例问题：先跑 python run.py --preflight 体检，把结论给运维或平台组',
    ),
    CONFIG: (
        '配置缺失或错误',
        '照着报错里给的修复方式改 config.ini；CI 上检查环境变量与凭据是否注入',
    ),
    BUSINESS: (
        '业务断言失败',
        '★ 这类最有价值：可能是真实缺陷。先看失败截图与页面源码，再决定是否提缺陷单',
    ),
    DATA: (
        '测试数据问题',
        '造数/清理没做好：检查 upload_file 是否存在、前置数据是否被其它用例改掉',
    ),
    TIMEOUT: (
        '超时',
        '可能是性能退化，也可能是等待策略不当：先确认页面/接口是否变慢，再考虑调大超时',
    ),
    UNKNOWN: (
        '未归类',
        '需要人工判断。若这类频繁出现，说明归因规则该补充了'
        '（见 Common/failureClassifier.py）',
    ),
}

#: 关键字规则：(分类, [正则...])。**从上往下匹配，先命中先算**。
#: 每条规则都要有明确理由 —— 没理由的规则半年后就没人敢动了。
_RULES = [
    # ---- 配置问题：最省事的一类，且提示信息已经很明确 ----
    (CONFIG, [
        r'缺少必填配置',
        r'未配置',
        r'请填写',
        r'NoSectionError',
        r'NoOptionError',
    ]),
    # ---- 定位失效：元素找不到 ----
    (LOCATOR, [
        r'没有定位到元素',
        r'NoSuchElementException',
        r'未找到',
        r'元素不存在',
        r'Message:.*no such element',
        r'stale element reference',
        r'元素已失效',
    ]),
    # ---- 环境/驱动：浏览器都起不来，与用例无关 ----
    (ENVIRONMENT, [
        r'session not created',
        r'chrome.*not reachable',
        r'ChromeDriver.*only supports',
        r'Unable to find.*driver',
        r'找不到.*(浏览器|可执行文件)',
        r'WebDriverException.*chrome',
        r'环境守卫',
        r'运行环境自检未通过',
    ]),
    # ---- 数据问题 ----
    (DATA, [
        r'上传文件不存在',
        r'FileNotFoundError',
        r'未配置.*upload_file',
    ]),
    # ---- 超时 ----
    (TIMEOUT, [
        r'TimeoutException',
        r'等待.*超时',
        r'timed out',
        r'超时\(',
    ]),
]


def classify_message(message):
    """按失败信息文本归类。

    :param message: 异常消息（可含堆栈）
    :return: 分类常量
    """
    text = str(message or '')
    for category, patterns in _RULES:
        for pattern in patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return category
    # 断言失败但没命中更具体的规则 -> 归为业务断言
    if re.search(r'AssertionError', text):
        return BUSINESS
    return UNKNOWN


def classify(case_result):
    """按一条用例的结果记录归类。

    :param case_result: JUnitResult.cases 里的一条，形如
        {'name':..., 'status':..., 'message':..., 'detail':...}
    :return: (分类常量, 处理建议)
    """
    if not case_result or case_result.get('status') == 'success':
        return None, ''

    # 先按 message，再按 detail（堆栈里往往有更具体的线索）
    category = classify_message(case_result.get('message'))
    if category == UNKNOWN:
        category = classify_message(case_result.get('detail'))
    return category, CATEGORY_INFO[category][1]


def summarize(cases):
    """把一批用例结果按分类汇总。

    :param cases: JUnitResult.cases 列表
    :return: {
        'total_failed': 3,
        'categories': {分类: [用例名, ...]},
        'advice': {分类: 处理建议},
        'primary': 最主要的分分类（数量最多的那个，用于一句话结论）,
    }

    用途：在控制台与报告里给出「这批失败主要是什么性质」——
    看一行就知道该找谁，不必逐条读堆栈。
    """
    # 显式标注：字典里混着 int / dict / None，不标注会被推断成 dict[str, object]，
    # 于是 += 1、setdefault 这类正常操作全被类型检查判错。
    result: Dict[str, Any] = {
        'total_failed': 0,
        'categories': {},
        'advice': {},
        'primary': None,
    }
    for item in cases or []:
        if item.get('status') not in ('failure', 'error'):
            continue
        result['total_failed'] += 1
        category, advice = classify(item)
        result['categories'].setdefault(category, []).append(item.get('name'))
        result['advice'][category] = advice

    if result['categories']:
        # 数量最多的那类作为"主要性质"；数量相同时按 CATEGORY_INFO 顺序取更靠前的
        order = {name: index for index, name in enumerate(CATEGORY_INFO)}
        result['primary'] = sorted(
            result['categories'],
            key=lambda name: (-len(result['categories'][name]), order.get(name, 99))
        )[0]
    return result


def format_digest(cases):
    """把归因结果渲染成一段可打印文本（放到控制台与 CI 日志里）。

    :return: 文本；没有失败时返回空串
    """
    summary = summarize(cases)
    if not summary['total_failed']:
        return ''

    lines = ['', '==================== 失败归因 ====================']
    for category, names in sorted(
            summary['categories'].items(),
            key=lambda kv: -len(kv[1])):
        label = CATEGORY_INFO[category][0]
        lines.append('[%s] %d 条：%s' % (label, len(names), '、'.join(names[:8])))
        lines.append('    建议：%s' % summary['advice'][category])

    primary_label = CATEGORY_INFO[summary['primary']][0]
    lines.append('')
    lines.append('结论：这批失败主要是「%s」，共 %d 条用例未通过'
                 % (primary_label, summary['total_failed']))
    lines.append('==================================================')
    lines.append('')
    return '\n'.join(lines)
