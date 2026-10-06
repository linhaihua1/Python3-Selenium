# -*- coding: utf-8 -*-
"""
==========================================================================
 环境守卫（新人阅读顺序：第 17 个，出事故时才意识到它重要）
==========================================================================

【一句话说明】
    测试真正开跑**之前**的最后一道闸门：检查"这次要打的地址"和"这次要跑的用例"
    搭不搭 —— 不搭就直接拒绝执行（退出码 2），而不是硬跑。
    它拦的是自动化最关键的一类事故：**本该打测试环境，结果打到了生产环境**。

【在框架中的位置】
    run.py
      └─> Common/runner.py 的 run()   <- 在收集用例之后、开浏览器之前调用
            └─> Common/env_guard.py   <- 本文件（纯判断，不碰浏览器）

【四道检查（按顺序，任意一条不过就中止）】
    ① 地址是否配置了        —— url 为空或还是占位符（如 http://测试环境地址/）
    ② 地址是否在白名单内    —— 配了 url_must_match 正则就必须匹配
    ③ 地址是否像生产环境    —— 命中 url_blocklist 关键字（prod / 线上 / 正式 …）
    ④ 环境能不能跑写用例    —— 生产特征 + allow_write=false + 本次含写用例 = 拦截

【配置（config.ini -> [safety]）】
    guard          = true        总开关，false 则下面全部跳过
    url_must_match =             地址必须匹配的正则；留空不校验
    url_blocklist  = prod,...    命中任一关键字即视为生产环境
    allow_write    = false       是否允许跑写用例（上传/报送/保存）

【新人注意】
    1. 本模块**只做判断**，不抛异常、不打印、不落盘 —— 由调用方决定怎么处理。
       这样它才能被单元测试直接调用，不需要起浏览器。
    2. 拦截时返回的 reason 是给"值班的人"看的，要能直接读懂哪里配错了，
       不要写 "guard failed" 这种没有信息量的话。
    3. 第 ④ 条判断依赖用例作用域标记（见 Common/testcase_meta.py）。
==========================================================================
"""

import re

from Common.log import log1

#: 常见的"还没填真实地址"的占位痕迹。命中即认为环境没配好。
PLACEHOLDER_MARKERS = (
    '测试环境地址',
    '生产环境地址',
    '被测地址',
    'your_',
    'your-',
    'example.com',
    'changeme',
    '请填写',
    'xxxxx',
)

#: 默认的生产环境关键字（config.ini 没配 url_blocklist 时用）
DEFAULT_BLOCKLIST = ('prod', 'production', '线上', '正式', '生产')


class GuardVerdict:
    """守卫结论。除了"过不过"，还带上足够定位问题的说明。

    属性：
        ok           —— True 表示放行
        code         —— 'ok' / 'guard_off' / 'no_url' / 'placeholder' /
                        'bad_pattern' / 'not_allowed' / 'prod_blocked'
        reason       —— 人话说明，直接写进日志与退出提示
        prod_like    —— 地址是否命中生产特征（放行时也会用到，用于打警告）
    """

    def __init__(self, ok, code, reason, prod_like=False):
        self.ok = ok
        self.code = code
        self.reason = reason
        self.prod_like = prod_like

    def __bool__(self):
        """让 `if check(...):` 直接能用来判断是否放行。"""
        return self.ok

    def __repr__(self):
        return 'GuardVerdict(ok=%s, code=%s, prod_like=%s)' % (
            self.ok, self.code, self.prod_like)


def looks_like_placeholder(url):
    """地址是否还是"没填真实值"的占位内容。

    为什么单独做一步：这是**最常见**的配置事故 ——
    照抄了 config.ini.example 却没改地址，于是测试去打一个不存在的域名，
    报出来的是"浏览器超时/找不到元素"这类**看起来像用例问题**的错误，
    真实原因（地址没配）反而被掩盖。
    """
    text = (url or '').strip().lower()
    if not text:
        return True
    return any(marker.lower() in text for marker in PLACEHOLDER_MARKERS)


def looks_like_production(url, blocklist=None):
    """地址是否带有"生产环境"特征。命中任一关键字即认为像生产。

    :param blocklist: 关键字列表；None 时用 DEFAULT_BLOCKLIST
    :return: (是否像生产, 命中的关键字或 None)
    """
    text = (url or '').strip().lower()
    if not text:
        return False, None
    for word in (blocklist if blocklist is not None else DEFAULT_BLOCKLIST):
        word = str(word).strip().lower()
        if word and word in text:
            return True, word
    return False, None


def check(url, allow_write=False, url_must_match='', url_blocklist=None,
          has_write_cases=False, guard=True):
    """执行四道检查，返回 GuardVerdict。

    :param url:              本次要访问的被测地址
    :param allow_write:      True 表示"我确认可以在这里跑写用例"
    :param url_must_match:   地址白名单正则；空字符串表示不校验
    :param url_blocklist:    生产特征关键字列表；None 用默认值
    :param has_write_cases:  本次待执行的用例里是否含有写用例
    :param guard:            总开关，False 直接放行（仅记日志）
    :return: GuardVerdict

    注意：本函数是纯函数，可以在单元测试里随意调用，不需要浏览器与网络。
    """
    if not guard:
        return GuardVerdict(True, 'guard_off',
                            '环境守卫已关闭（[safety] guard = false），跳过全部检查')

    # ---- ① 地址是否配置了 ----
    if looks_like_placeholder(url):
        shown = (url or '').strip() or '（空）'
        return GuardVerdict(
            False, 'no_url',
            '被测地址未正确配置：当前值 [%s]。'
            '请在 config.ini [environment] url 填入真实地址，'
            '或用 run.py --url / --env 指定；'
            '若从 config.ini.example 复制而来，请确认占位内容已替换' % shown)

    # ---- ② 地址是否落在白名单内 ----
    pattern = str(url_must_match or '').strip()
    if pattern:
        try:
            matched = re.search(pattern, url) is not None
        except re.error as exc:
            return GuardVerdict(
                False, 'bad_pattern',
                '[safety] url_must_match 不是合法正则：%s（%s）' % (pattern, exc))
        if not matched:
            return GuardVerdict(
                False, 'not_allowed',
                '被测地址不在白名单内：%s 不匹配 [safety] url_must_match = %s。'
                '这是为了防止"本该打测试环境、实际打了别的环境"，'
                '若确认无误请修正白名单正则' % (url, pattern))

    # ---- ③④ 生产特征 + 写用例 ----
    # 空列表视为"没配"，退回内置默认关键字 —— 安全默认永远取"更严"的那一侧，
    # 否则把配置项清空就成了绕过守卫的捷径
    blocklist = list(url_blocklist) if url_blocklist else None
    prod_like, hit_word = looks_like_production(url, blocklist)
    if prod_like:
        if has_write_cases and not allow_write:
            return GuardVerdict(
                False, 'prod_blocked',
                '疑似生产环境（地址含关键字「%s」）且本次包含写操作用例，已拦截。'
                '写用例会真实上传/报送数据。'
                '确认无误请设置 [safety] allow_write = true 或 UI_SAFETY_ALLOW_WRITE=true'
                % hit_word, prod_like=True)
        if allow_write:
            log1.warning('环境守卫：地址 %s 疑似生产（关键字「%s」），'
                         '但已显式开启 allow_write，放行执行' % (url, hit_word))
        else:
            log1.info('环境守卫：地址 %s 疑似生产（关键字「%s」），'
                      '本次全为只读用例，放行' % (url, hit_word))

    return GuardVerdict(True, 'ok', '环境检查通过', prod_like=prod_like)
