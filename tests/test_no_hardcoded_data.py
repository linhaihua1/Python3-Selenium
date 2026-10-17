# -*- coding: utf-8 -*-
"""
==========================================================================
 单元测试：业务数据硬编码的「规则级」防劣化门禁（★ 本次改造的核心）
==========================================================================

【为什么这个文件必须存在 —— 一句话说清它比旧门禁强在哪】

    旧门禁（枚举黑名单）：
        BANNED_LITERALS = ('统一门户', '云媒资', '党建云', '融媒体生产系统', ...)
        —— 只认这 6 个词。换一套业务名（比如「教务管理系统」「财务核算平台」），
           硬编码照样能混进去，门禁形同虚设。

    本门禁（规则白名单）：
        用 AST 把源码切成"注释 / 文档字符串 / 可执行代码"三块，
        只在**可执行代码**里找字符串字面量，再按"是否允许出现在用例层"过滤。
        —— 不依赖任何具体业务词，换任何系统都照样生效。

【被检查的范围】
    TestSuites/*.py    用例层（业务数据的重灾区）
    PageObject/*.py    页面对象层
    排除 __init__.py

【判定规则：什么样的字面量算"违规"】
    在可执行代码里出现的中文字符串字面量，且**不**属于以下三类：
      ① 注释与模块/类/函数文档字符串（说明文字，不是数据）
      ② 诊断文案：日志消息、失败消息模板、跳过原因
      ③ 显式豁免：用例显示名、框架约定的控件标识键

    判定 ② 的关键在于**参数位置**（这是本门禁最容易写错的地方）：
        self.assertEqual(actual, '旧系统标题', '标题不符')
                                  ↑序号1：期望值 = 业务数据 -> **拦**
                                               ↑序号2：失败消息 = 诊断文案 -> 放
        self.check_title('上传视频', expected)
                       ↑序号0：用例名（描述这条用例叫什么）-> 放
        log1.info('执行：%s' % x)   单参数调用 -> 放

    把"首参数"和"末参数"一并放行、只拦中间位置，才能既不漏报
    （期望值）又不误报（消息与用例名）。

【明确不算违规的（本门禁不误伤，让它保持可用）】
    - 注释与文档字符串：说明文字，不是数据
    - 日志/异常/断言消息模板：给人读的诊断文案，换系统后照样成立
    - 用例显示名（case_name）：描述「这条用例在测什么」，从不与被测系统比对
    - query_form_ready 的控件标识键：框架内部约定，只用于报告"少了哪一个"

【为什么"诊断文案"和"业务数据"要分开】
    业务数据 = 拿去和被测系统比对的**值**（期望标题、查询关键字、手机号…）。
              它一旦写死，换系统忘了改就会产生"期望[旧值] 实际[新值]"的假失败。
    诊断文案 = 出问题时人看的**说明**（"素材列表当前行数：%d"）。
              换系统后这句话照样准确，不该也不能改成配置项。
    两者都含中文，但**只有前者**是硬编码缺陷 —— 门禁必须分得清，
    否则就是一个让人天天想关掉的噪音门禁。

【被测系统元素定位的例外】
    PageObject/ 与 Common/elementPage.py 里必须出现元素定位值 ——
    定位值是"怎么找到元素"，属于**示例业务的定位表**，不是测试数据。
    但 Common/elementPage.py 已支持 config.ini [elements] 段覆盖，
    真正的数据来源是配置（见该文件的配置覆盖层）。
==========================================================================
"""

import ast
import os
import unittest

from tests.helpers import BASE_DIR

# ---------------------------------------------------------------------------
# 被扫描的目录
# ---------------------------------------------------------------------------
SCAN_DIRS = ('TestSuites', 'PageObject')

#: 允许出现中文业务字面量的属性名 / 变量名。
#: 这些是**分层职责**相关的键（如 query_form_ready 返回的控件名），
#: 它们是框架与用例之间的约定标识，不是被测系统的业务数据。
#: 之所以要显式列出而不是不管，是为了让"例外"可见、可审计 ——
#: 有人往里加东西时，会在这个列表里留下一条能被 review 到的记录。
ALLOWED_KEYS = frozenset({
    # loginPage.query_form_ready 返回的 dict 键：
    # 它们只是"查询区控件的内部标识"，用于失败时报告"少了哪一个"，
    # 不参与与被测系统比对 —— 用例层拿到的是 dict，只看 True/False。
    '关键字输入框', '查询按钮', '重置按钮',
})

#: 允许承载诊断文案的模块级常量名（大写命名）。
#: 这类常量的内容是"跳过原因""提示语"这类**给人看的说明**，
#: 不是拿去与被测系统比对的业务值（用例名、诊断文案都属于此类）。
#: 判定依据是命名约定：模块级全大写 = 常量 = 说明性内容。
#: 反过来说，任何**小写变量**（业务值惯用的命名）都不会因为这条被放过。
_TOLERATED_CONSTANT_SUFFIXES = ('REASON', 'MESSAGE', 'TITLE_PREFIX', 'HINT')

#: 允许承载**用例显示名**的变量名。
#: 用例名（'上传视频'/'关键字查询'）描述的是「这条用例在测什么」，
#: 它只出现在日志与报告里，**从不与被测系统比对**，
#: 所以它不属于"换系统后忘了改配置就会产生假失败"的业务数据。
#: 反过来看：期望值、查询关键字、表单字段值这些真正拿去比对的值，
#: 它们的变量名一律是 expected / keyword / phone 之类，不在此列 ——
#: 所以这条豁免不会给真正的业务数据开后门。
ALLOWED_CASE_NAME_VARS = frozenset({'case_name'})

#: 允许中文业务字面量的调用链前缀（诊断文案出口）。
#: 这些调用的**最后一个**参数是给人看的消息模板，含 %s 占位符。
#: ★ 注意"最后一个"很重要：assertEqual(actual, expected, msg) 里
#:   msg 是诊断文案（放行），但 expected 是业务数据（必须拦下）——
#:   把两者混为一谈会让门禁既漏报又误报。
DIAGNOSTIC_CALLS = frozenset({
    'log1.info', 'log1.error', 'log1.warning', 'log1.debug', 'log1.critical',
    'self.assertTrue', 'self.assertFalse', 'self.assertEqual',
    'self.assertIn', 'self.assertNotIn', 'self.assertIs',
    'self.assertIsNone', 'self.assertIsNotNone', 'self.assertNotEqual',
    'self.assertGreater', 'self.assertLess', 'self.assertRegex',
    'self.assertIsInstance', 'self.assertNotIsInstance',
    'self.fail', 'self.skipTest', 'skipTest',
})

#: 项目自定义的断言封装。
#: testLogin.py 把"校验标题"收敛成了 check_title(用例名, 期望值)，
#: 失败消息由它内部统一生成 —— 所以调用点上的第一个参数是**用例名**，
#: 不是业务数据。这类方法不参与下面的"末参数是消息"判定，直接整条放行。
CUSTOM_ASSERT_CALLS = frozenset({
    'self.check_title', 'self.check_no_console_error',
})

#: 配置读取类调用：它们的字符串参数是**用途说明**（给人看的），
#: 值本身来自配置文件，不是硬编码的业务数据。
#:   Config.get_required('system', 'login_button_text', '登录按钮文字')
#: 第三个参数是"用途说明"，允许中文；键名本身不含中文。
CONFIG_CALLS = frozenset({
    'Config.get_required', 'Config.get_required_list',
    'Config.get_assert_value', 'Config.get_form_field',
})


def _has_chinese(text):
    """判断字符串里是否含中文字符。"""
    return any('\u4e00' <= ch <= '\u9fff' for ch in text)


def _dotted_name(node):
    """把 AST 节点还原成点分名称（能还原多少算多少，还原不了返回 None）。

    例：log1.info(...) -> 'log1.info'；self.assertTrue(...) -> 'self.assertTrue'
    """
    parts = []
    current = node
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if isinstance(current, ast.Name):
        parts.append(current.id)
        return '.'.join(reversed(parts))
    return None


def _is_transparent(node):
    """这个节点只是"把值往上传"的中转站，不改变语义。

    `'文案 %s' % keyword` 这种写法里，字符串常量是 BinOp 的左操作数，
    它到调用之间隔着 BinOp —— 判定"这个字面量属于哪个参数"时必须穿过它，
    否则会误判成"这个字符串不在任何调用的参数里"。
    """
    return isinstance(node, (ast.BinOp, ast.Starred, ast.FormattedValue))


class _Visitor(ast.NodeVisitor):
    """遍历 AST，找出可执行代码里的中文业务字面量。

    ★ 关键：必须先剔除注释与文档字符串，否则门禁会被满屏中文说明文字淹没。
      注释**根本不会**出现在 AST 里（tokenize 那一步只是辅助校验），
      文档字符串则是模块/类/函数的第一个表达式语句，可靠位置识别。
  """

    def __init__(self):
        #: 违规记录：(行号, 字面量)
        self.offenders = []
        #: 文档字符串节点 id
        self._docstrings = set()
        #: 子节点 id -> 父节点列表
        self._parents = {}

    # ---- 识别文档字符串 -------------------------------------------------- #
    def collect_docstrings(self, tree):
        """把模块/类/函数的 docstring 登记下来，后续遍历时跳过。"""
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.ClassDef,
                                 ast.FunctionDef, ast.AsyncFunctionDef)):
                body = getattr(node, 'body', None)
                if not body:
                    continue
                first = body[0]
                # docstring 判定：表达式语句 + 字符串常量
                if (isinstance(first, ast.Expr)
                        and isinstance(first.value, ast.Constant)
                        and isinstance(first.value.value, str)):
                    self._docstrings.add(id(first.value))

    # ---- 建立父子关系 ---------------------------------------------------- #
    def build_parents(self, tree):
        self._parents = {}
        for node in ast.walk(tree):
            for child in ast.iter_child_nodes(node):
                self._parents.setdefault(id(child), []).append(node)

    # ---- 定位一个字面量属于哪个调用的第几个参数 ---------------------------- #
    def _locate_call_arg(self, node):
        """从字面量向上找到它所属的调用及其参数序号。

        :return: (Call 节点, 参数序号)；找不到返回 (None, None)

        必须穿过 BinOp 等中转节点，否则
            log1.info('执行：%s' % x)
        里的字符串会因为"不是调用的直接参数"而被漏判。
        """
        current = node
        while True:
            parents = self._parents.get(id(current), ())
            nxt = None
            for parent in parents:
                # 先穿过中转节点
                if _is_transparent(parent):
                    nxt = parent
                    break
                if isinstance(parent, ast.Call):
                    # 在该调用的参数列表里找序号
                    for index, arg in enumerate(parent.args):
                        if arg is current:
                            return parent, index
                    for keyword_node in parent.keywords:
                        if keyword_node.value is current:
                            return parent, 'kw:' + str(keyword_node.arg)
                    return parent, None
                # 其他容器（Dict / List / Tuple）不属于"调用参数"，交给调用方判断
                return parent, None
            if nxt is None:
                return None, None
            current = nxt

    # ---- 判定是否允许 ---------------------------------------------------- #
    def _is_allowed(self, node):
        """这个中文字符串字面量是否属于"允许"的诊断文案/文档/键名。"""
        # 1) 文档字符串与模块说明
        if id(node) in self._docstrings:
            return True

        # 2) 沿父链上溯，看它落在哪个调用的哪个参数上
        call, index = self._locate_call_arg(node)
        name = _dotted_name(call.func) if isinstance(call, ast.Call) else None

        # 2a) 配置读取类调用：字符串是用途说明，放行
        if name in CONFIG_CALLS:
            return True

        # 2a2) 项目自定义的断言封装：调用点上的中文是用例名，
        #      真正的期望值作为第二个参数传进去（那个值来自配置，不是字面量）
        if name in CUSTOM_ASSERT_CALLS:
            return True

        # 2b) 日志/断言类调用：判断这个字面量处于什么位置
        #     · 首参数（序号 0）：用例名/名称，如 self.check_title('上传视频', expected)
        #       —— 描述「这条用例叫什么」，不参与比对，放行
        #     · 末参数：失败消息模板（含 %s），纯给人看，放行
        #     · 中间的位置：**参与比对**的期望值，必须拦下
        #       例：self.assertEqual(actual, '旧系统标题', '标题不符')
        #           序号 1 = 期望值（业务数据，拦）；序号 2 = 消息（放行）
        if name in DIAGNOSTIC_CALLS:
            positional = list(call.args)
            if index == 'kw:msg':
                return True
            if isinstance(index, int):
                if len(positional) <= 1:
                    # 单参数调用：log1.info('x') / self.skipTest('理由')
                    return True
                if index == 0 or index == len(positional) - 1:
                    return True
            # 明确落在中间位置 -> 是拿来比对的业务数据
            return False

        # 2c) raise 语句的异常消息：`raise ValueError('缺少必填配置...')`
        #     这里的字符串是诊断文案，必须放行。
        #     注意 Raise 不是 Call，走 _locate_call_arg 时会原样返回 Raise 节点。
        if isinstance(call, ast.Raise):
            return True

        # 3) 白名单键（dict 键 / 赋值目标）
        for parent in self._parents.get(id(node), ()):
            if isinstance(parent, ast.Dict) and node in getattr(parent, 'keys', []):
                if node.value in ALLOWED_KEYS:
                    return True
            if isinstance(parent, ast.Assign):
                for target in parent.targets:
                    if isinstance(target, ast.Name) and target.id in ALLOWED_KEYS:
                        return True
                    # 用例显示名：描述「这条用例在测什么」，不参与与被测系统比对
                    if (isinstance(target, ast.Name)
                            and target.id in ALLOWED_CASE_NAME_VARS):
                        return True
                    # 模块级说明性常量（SKIP_REASON / ERROR_MESSAGE …）
                    if (isinstance(target, ast.Name)
                            and target.id.isupper()
                            and target.id.endswith(_TOLERATED_CONSTANT_SUFFIXES)):
                        return True
        return False

    # ---- 遍历 ------------------------------------------------------------ #
    def visit_Constant(self, node):
        """只检查字符串常量；非字符串常量照常往子节点走。"""
        value = node.value
        if isinstance(value, str) and _has_chinese(value) and not self._is_allowed(node):
            self.offenders.append((node.lineno, value))
        self.generic_visit(node)


def scan_file(path):
    """扫描单个 .py 文件，返回 [(行号, 字面量), ...]。

    :param path: 文件绝对路径
    :return: 违规字面量列表；文件解析失败时抛出（语法错误由 flake8 负责报）
    """
    with open(path, encoding='utf-8') as fp:
        source = fp.read()

    tree = ast.parse(source)
    visitor = _Visitor()
    visitor.build_parents(tree)
    visitor.collect_docstrings(tree)
    visitor.visit(tree)
    return visitor.offenders


def _target_files():
    """列出全部被扫描的文件。"""
    out = []
    for sub in SCAN_DIRS:
        directory = os.path.join(BASE_DIR, sub)
        if not os.path.isdir(directory):
            continue
        for name in sorted(os.listdir(directory)):
            if not name.endswith('.py') or name.startswith('__'):
                continue
            out.append(os.path.join(directory, name))
    return out


class TestNoHardcodedBusinessData(unittest.TestCase):
    """★ 规则级门禁：可执行代码里不许出现中文业务数据字面量。"""

    def test_用例层与页面对象层无业务字面量(self):
        offenders = []
        for path in _target_files():
            for lineno, literal in scan_file(path):
                offenders.append('%s:%d -> %r'
                                 % (os.path.basename(path), lineno, literal))
        self.assertEqual(
            offenders, [],
            '以下业务数据被硬编码在代码里（%d 处），必须搬到 config.ini：\n    %s\n\n'
            '    原因：换系统后忘了改配置，框架会拿着旧值去比对，'
            '报出"期望[旧值] 实际[新值]"这种看不出原因的失败。\n'
            '    正确写法：\n'
            '      Config.get_required(\'段\', \'键\', \'用途说明\')\n'
            '      Config.get_assert_value(\'title_login\', \'登录后首页标题\')\n'
            '      Config.get_form_field(\'phone\', \'上传表单的手机号\')'
            % (len(offenders), '\n    '.join(offenders)))

    def test_门禁自身真的能检出违规(self):
        """★★ 反向断言：门禁不能是"永远绿"的假门禁。

        这是本文件最重要的一条。旧门禁的问题是"换了业务名就失效"，
        但更糟的情况是**规则本身写错了也照样绿** —— 那等于没有门禁。
        这里拿一段真实的违规代码喂给自己的扫描器，
        它必须报错；再拿一段合规代码（值来自配置）喂进去，它必须放行。
        """
        # --- 违规样例：业务数据写死 ---
        bad_source = (
            'def demo():\n'
            '    keyword = "融媒体素材库"\n'          # 违规：赋值的中文字面量
            '    return click("查询", keyword)\n'   # 违规：作为调用参数的中文字面量
        )
        bad_hits = self._scan_text(bad_source)
        self.assertEqual(len(bad_hits), 2,
                         '扫描器必须同时抓到"赋值"和"调用参数"两种违规写法，实际抓到 %r'
                         % bad_hits)

        # --- 合规样例：值来自配置、日志与断言消息是中文 ---
        good_source = (
            'from Common.config import Config\n'
            '\n'
            '\n'
            'def demo():\n'
            '    """文档字符串里有中文：素材库，不该被算成违规。"""\n'
            '    keyword = Config.get_form_field(\'query_keyword\', \'查询关键字\')\n'
            '    log1.info(\'执行查询：%s\' % keyword)\n'
            '    self.assertTrue(ok, \'查询未命中：%s\' % keyword)\n'
            '    # 注释里的中文也不该被算成违规：素材库\n'
            '    return keyword\n'
        )
        self.assertEqual(self._scan_text(good_source), [],
                         '合规代码不该被误报（文档/注释/日志/断言消息里的中文都要放行）')

    def test_诊断文案与业务数据能区分开(self):
        """中文断言消息允许，但中文**期望值**不允许 —— 两者必须分得清。"""
        source = (
            'def demo(self):\n'
            '    self.assertEqual(actual, \'旧系统标题\', \'标题不符\')\n'
        )
        # 期望值位置（第 3 个参数）是业务数据，必须抓到
        hits = self._scan_text(source)
        self.assertTrue(
            any('旧系统标题' in hit[1] for hit in hits),
            'assertEqual 的**期望值**是业务数据，必须被门禁拦下，实际：%r' % hits)
        # 消息位置（第 4 个参数）是诊断文案，必须放行
        self.assertFalse(
            any('标题不符' in hit[1] for hit in hits),
            'assertEqual 的**失败消息**是诊断文案，不该被拦下，实际：%r' % hits)

    def test_白名单里的控件名不算业务数据(self):
        """query_form_ready 返回的控件标识是框架约定，不是被测系统数据。"""
        source = (
            'def query_form_ready(self):\n'
            '    return {\n'
            '        \'关键字输入框\': ok1,\n'
            '        \'查询按钮\': ok2,\n'
            '        \'重置按钮\': ok3,\n'
            '    }\n'
        )
        self.assertEqual(self._scan_text(source), [],
                         'ALLOWED_KEYS 里的控件标识不该被算成业务数据')

    def test_白名单是有限且显式的(self):
        """白名单本身要克制 —— 每多一条，就多一个藏业务数据的地方。"""
        self.assertLessEqual(
            len(ALLOWED_KEYS), 10,
            'ALLOWED_KEYS 超过 10 条说明它在被当成垃圾桶用，'
            '请把真正的业务数据搬到 config.ini，而不是往白名单里加词')

    # ---- 工具 ------------------------------------------------------------ #
    @staticmethod
    def _scan_text(source):
        """扫描一段源码文本（供反向断言使用），返回 [(行号, 字面量), ...]。"""
        tree = ast.parse(source)
        visitor = _Visitor()
        visitor.build_parents(tree)
        visitor.collect_docstrings(tree)
        visitor.visit(tree)
        return visitor.offenders


class TestLocatorIsConfigDriven(unittest.TestCase):
    """★ 元素定位必须能被 config.ini 覆盖 —— 这是"零代码换系统"的前提。"""

    def test_元素表支持配置覆盖(self):
        self.assertTrue(
            callable(getattr(__import__('Common.elementPage',
                                        fromlist=['x']).apply_config_overrides,
                             '__call__', None)),
            'elementPage 应提供 apply_config_overrides()，让定位值可由配置覆盖')

    def test_定位规格解析正确(self):
        from Common.elementPage import parse_locator_spec
        cases = {
            'id:login-btn': ['id', 'login-btn'],
            'css:#app .btn': ['css', '#app .btn'],
            'xpath://input[@type="text"]': ['xpath', '//input[@type="text"]'],
            # 省略前缀 -> 按 xpath 解析
            '//div[@id="app"]': ['xpath', '//div[@id="app"]'],
        }
        for spec, expected in cases.items():
            self.assertEqual(parse_locator_spec(spec), expected,
                             '解析 %r 应得到 %r' % (spec, expected))

    def test_xpath值里的冒号不被误切(self):
        """xpath 常含冒号，只应在第一个冒号处切分。"""
        from Common.elementPage import parse_locator_spec
        self.assertEqual(
            parse_locator_spec("xpath://a[@href='http://x.com']"),
            ['xpath', "//a[@href='http://x.com']"])

    def test_空定位配置报错(self):
        from Common.elementPage import parse_locator_spec
        with self.assertRaises(ValueError):
            parse_locator_spec('   ')

    def test_配置覆盖真的生效(self):
        """端到端：配了 [elements] 就该覆盖代码默认值。"""
        from Common import elementPage
        from tests.helpers import patch_config

        original = elementPage.Element1.Username
        try:
            with patch_config(ini_text='[elements]\nUsername = id:my-user-input\n'):
                elementPage.apply_config_overrides()
                self.assertEqual(elementPage.Element1.Username, ['id', 'my-user-input'],
                                 '配了 [elements] Username 就该覆盖代码默认值')
        finally:
            elementPage.Element1.Username = original

    def test_未配置的键保持代码默认值(self):
        """没配的元素必须保持默认值 —— 接入新系统时不必抄整张表。"""
        from Common import elementPage
        from tests.helpers import patch_config

        original = elementPage.Element1.Password
        try:
            with patch_config(ini_text='[elements]\nUsername = id:x\n'):
                elementPage.apply_config_overrides()
                self.assertEqual(elementPage.Element1.Password, original,
                                 '未在 [elements] 出现的元素必须保持默认值')
        finally:
            elementPage.Element1.Password = original

    def test_配置里键名拼错会告警而非静默(self):
        """键名拼错是最常见的配置失误，必须给出明确提示。"""
        from Common import elementPage
        from tests.helpers import patch_config

        original = elementPage.Element1.Username
        try:
            with patch_config(ini_text='[elements]\nUsernameXxx = id:x\n'):
                overridden = elementPage.apply_config_overrides()
                self.assertEqual(overridden, [],
                                 '不存在的键名不应被当成有效覆盖')
                self.assertEqual(elementPage.Element1.Username, original)
        finally:
            elementPage.Element1.Username = original

    def test_配置模板包含elements段(self):
        """config.ini.example 必须讲清 [elements] 的用法，否则新人不知道能这么改。"""
        path = os.path.join(BASE_DIR, 'config.ini.example')
        with open(path, encoding='utf-8') as fp:
            text = fp.read()
        self.assertIn('[elements]', text, '模板应包含 [elements] 段')
        self.assertIn('UI_ELEMENTS_', text, '模板应给出 [elements] 的环境变量覆盖示例')


def _config_calls(path, section, key):
    """在源码里找出读取指定 (段, 键) 的所有配置调用及其参数个数。

    :return: [(调用名, 参数个数), ...]

    ★ 为什么用 AST 而不是字符串查找：
      真实代码里这次调用经常被折成多行（超出行长限制要拆行），
      写成   Config.get('system',\n               'username_placeholder',\n               '默认值')
      字符串匹配完全抓不到 —— 门禁一旦"看起来在管、实际抓不住"，
      比没有门禁更糟，因为它提供了虚假的安全感。
    """
    with open(path, encoding='utf-8') as fp:
        tree = ast.parse(fp.read())

    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = _dotted_name(node.func)
        if name not in ('Config.get', 'Config.config_read', 'Config.get_bool',
                        'Config.get_int', 'Config.get_list'):
            continue
        positional = [a.value if isinstance(a, ast.Constant) else None
                      for a in node.args]
        if len(positional) >= 2 and positional[0] == section and positional[1] == key:
            found.append((name, len(positional)))
    return found


def _uses_required(path, section, key):
    """源码里是否用 get_required 系列读取了指定的 (段, 键)。"""
    with open(path, encoding='utf-8') as fp:
        tree = ast.parse(fp.read())

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = _dotted_name(node.func)
        if name not in ('Config.get_required', 'Config.get_required_list',
                        'Config.get_assert_value', 'Config.get_form_field',
                        'Config.get_account'):
            continue
        positional = [a.value if isinstance(a, ast.Constant) else None
                      for a in node.args]
        # get_account() 不带段名参数，交给调用方另行判断
        if len(positional) >= 2 and positional[0] == section and positional[1] == key:
            return True
    return False


class TestNoHardcodedDefaultInBusinessReaders(unittest.TestCase):
    """★ 业务数据不允许用"带默认值的读取"来取。

    这类调用比字面量更隐蔽：值可能来自配置，但配置缺失时会静默用一个默认值。
    对业务数据来说，静默兜底 = 产生误导性的断言失败。
    """

    #: 必须走必填读取的 (段, 键) 清单。
    #: 每加一项都是一条真实的踩坑记录，改前请想清楚它为什么不能有默认值。
    BIZ_KEYS = (
        ('system', 'username_placeholder'),
        ('system', 'password_placeholder'),
        ('system', 'login_button_text'),
        ('api', 'login_path'),
        ('api', 'token_field'),
    )

    def test_业务键不得带默认值读取(self):
        for sub in SCAN_DIRS:
            directory = os.path.join(BASE_DIR, sub)
            if not os.path.isdir(directory):
                continue
            for name in sorted(os.listdir(directory)):
                if not name.endswith('.py') or name.startswith('__'):
                    continue
                path = os.path.join(directory, name)
                for section, key in self.BIZ_KEYS:
                    for call_name, arg_count in _config_calls(path, section, key):
                        # get_bool/get_int/get_list 的签名里第三位是类型转换参数，
                        # 不是兜底默认值；这里只针对真正支持 fallback 的读法。
                        if call_name in ('Config.get', 'Config.config_read') \
                                and arg_count >= 3:
                            self.fail(
                                '%s 里用 %s(%r, %r, 默认值) 读了业务数据 —— '
                                '这类键必须用 Config.get_required()（缺失即报错），'
                                '不能用默认值兜底' % (name, call_name, section, key))

    def test_业务键确实改用了必填读取(self):
        """反向断言：不能只把默认值删掉，却忘了换成必填读取。

        否则配置缺失时会返回 None，定位时抛出一条看不懂的错。
        """
        generic = os.path.join(BASE_DIR, 'PageObject', 'genericPage.py')
        for section, key in (s for s in self.BIZ_KEYS if s[0] == 'system'):
            self.assertTrue(
                _uses_required(generic, section, key),
                'genericPage.py 读取 [system] %s 时应改用 get_required()' % key)

        api_suite = os.path.join(BASE_DIR, 'Common', 'apiClient.py')
        for section, key in (s for s in self.BIZ_KEYS if s[0] == 'api'):
            self.assertTrue(
                _uses_required(api_suite, section, key),
                'apiClient.py 读取 [api] %s 时应改用 get_required()' % key)


class TestGenericPageHasNoDefaultPlaceholder(unittest.TestCase):
    """★ GenericPage 的登录页文案必须是必填（这是本次修复的重点）。

    为什么这一条最优先：
        旧代码里是 Config.get('system', 'username_placeholder', '请输入用户名')。
        接新系统时如果忘了改配置，框架会拿着"请输入用户名"去定位 ——
        而新系统的提示文字多半是"请输入账号"，于是报出
        「没有定位到元素」这种完全看不出真实原因（其实是配置没跟着换）的失败。
    """

    def _generic_page_path(self):
        return os.path.join(BASE_DIR, 'PageObject', 'genericPage.py')

    def test_不再有登录页文案的兜底默认值(self):
        """三个定位特征必须走 get_required，不能带默认值。"""
        path = self._generic_page_path()
        for key in ('username_placeholder', 'password_placeholder',
                    'login_button_text'):
            for call_name, arg_count in _config_calls(path, 'system', key):
                self.assertLess(
                    arg_count, 3,
                    'genericPage.py 仍在用 %s(\'system\', %r, 默认值) —— '
                    '换系统后会拿旧文案去定位，必须改成 get_required()'
                    % (call_name, key))

    def test_登录页文案改为必填读取(self):
        """反向断言：必须真的用了 get_required，否则等于没改。"""
        path = self._generic_page_path()
        for key in ('username_placeholder', 'password_placeholder',
                    'login_button_text'):
            self.assertTrue(
                _uses_required(path, 'system', key),
                'genericPage.py 读取 [system] %s 时应改用 get_required()' % key)

    def test_账号密码不再静默取空串(self):
        """账号密码缺失时应明确报错，而不是拿着空串去登录再报"元素不存在"。"""
        path = self._generic_page_path()
        for key in ('login_username', 'login_password'):
            for call_name, arg_count in _config_calls(path, 'testcase', key):
                self.assertLess(
                    arg_count, 3,
                    "genericPage.py 仍用 %s('testcase', %r, '') 读账号 —— "
                    '缺配置时应立即报错，而不是拿着空串去登录'
                    % (call_name, key))

    def test_success_text允许留空(self):
        """唯一该允许留空的是 success_text：它留空表示改等遮罩消失。"""
        path = self._generic_page_path()
        # 它必须仍然是"带默认值且默认值为空串"的读法
        self.assertTrue(
            any(arg_count >= 3 for _, arg_count in _config_calls(path, 'system',
                                                                 'success_text')),
            'success_text 是可选判定条件，留空有明确语义，应继续允许带空默认值')

    def test_模板说明了必填(self):
        path = os.path.join(BASE_DIR, 'config.ini.example')
        with open(path, encoding='utf-8') as fp:
            text = fp.read()
        self.assertIn('必填', text, '模板应说明 [system] 段哪些键是必填的')


if __name__ == '__main__':
    unittest.main(verbosity=2)
