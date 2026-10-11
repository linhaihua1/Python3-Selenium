# -*- coding: utf-8 -*-
"""
单元测试：TestSuites/testLogin.py（UI 用例层）

UI 用例本身要开浏览器、连真实环境，无法在单元测试里跑。
所以这里只验证用例层的「结构约定」与「自定义断言」——这些恰恰是
长期维护中最容易被破坏、又最难发现的部分：

    - 执行顺序靠方法名 test_N 前缀固定，改名会改变顺序 -> 用测试锁住
    - 参数全部来自 config.ini，不允许硬编码账号/路径/期望标题
    - ★ 断言期望值走必填读取（get_assert_value），配置缺失即报错中止
    - check_title 失败时必须截图并抛出，成功时不能误报
    - 类级前置只开一次浏览器、类级后置必须关掉浏览器

★ 不启动浏览器：所有依赖都替换成假对象。
"""

import ast
import inspect
import os
import unittest
from unittest import mock

from tests.helpers import patch_config
from TestSuites import testLogin as login_suite
from TestSuites.testLogin import TestLogin


# 用例执行顺序（由方法名的字母序决定，即 test_1 .. test_6）
EXPECTED_ORDER = [
    'test_1login',
    'test_2select_scxt',
    'test_3material',
    'test_4uplaodbutton',
    'test_5keyword',
    'test_6submitted',
]


class TestCaseStructure(unittest.TestCase):
    """用例类自身的结构约定。"""

    def test_用例数量与顺序固定(self):
        names = unittest.TestLoader().getTestCaseNames(TestLogin)
        self.assertEqual(
            names, EXPECTED_ORDER,
            '用例执行顺序由方法名决定，改动方法名会改变执行顺序并导致失败',
        )

    def test_所有用例方法都以test下划线加序号开头(self):
        for name in unittest.TestLoader().getTestCaseNames(TestLogin):
            self.assertRegex(name, r'^test_\d',
                             '用例方法名必须是 test_数字 形式，否则无法固定执行顺序')

    def test_每条用例都有中文docstring(self):
        """新人靠 docstring 理解每条用例在测什么。"""
        for name in EXPECTED_ORDER:
            doc = getattr(TestLogin, name).__doc__
            self.assertTrue(doc and doc.strip(), '用例 %s 缺少说明' % name)

    def test_浏览器在类级前置后置中管理(self):
        """6 条用例共用一次浏览器会话 —— 拆成每条都开会多登 6 次且更不稳。"""
        self.assertTrue(callable(getattr(TestLogin, 'setUpClass', None)))
        self.assertTrue(callable(getattr(TestLogin, 'tearDownClass', None)))
        self.assertIsNone(TestLogin.driver, '类属性 driver 初始应为 None')

    def test_用例里不硬编码账号与路径(self):
        """账号、上传文件路径必须来自配置，代码里不该出现明文。"""
        source = inspect.getsource(login_suite)
        for banned in ('linhaihua', 'qwer1234', 'BGXF', '.mp4'):
            self.assertNotIn(banned, source, '用例层不应硬编码：%s' % banned)

    def test_用例里不硬编码业务数据(self):
        """★ 断言期望值、查询关键字等业务数据必须来自 config.ini。

        代码里留业务字面量是本工程明令禁止的：换系统后忘了改配置，
        框架会拿旧值去比对，报出看不出原因的失败。
        详细规则见 tests/test_config_required.py。
        """
        source = inspect.getsource(login_suite)
        for banned in ('统一门户', '云媒资', '党建云', '融媒体'):
            self.assertNotIn(banned, source,
                             '用例层不应硬编码业务数据「%s」—— '
                             '应改用 Config.get_assert_value / get_form_field' % banned)

    def test_用例层不直接写xpath(self):
        source = inspect.getsource(login_suite)
        self.assertNotIn('//', source)


class TestSetUpClass(unittest.TestCase):
    """类级前置：参数来自配置，且只开一次浏览器。"""

    def setUp(self):
        self._config = patch_config()
        self._config.__enter__()
        # ★ 只还原 setUpClass 真正会写的属性。
        #   表单字段与查询关键字已改为在用例方法里现取（不挂类属性），
        #   因为冒烟集只跑前 3 条，不该要求先配好手机号、上报单位这些。
        self._saved = {key: getattr(TestLogin, key, None)
                       for key in ('username', 'password',
                                   'title_login', 'title_workbench', 'title_material',
                                   'base', 'driver', 'login_page')}

    def tearDown(self):
        # 还原类属性：setUpClass 会往类上挂 username/driver 等，别污染其它测试
        for key, value in self._saved.items():
            setattr(TestLogin, key, value)
        self._config.__exit__(None, None, None)

    def test_参数全部来自配置(self):
        fake_config = mock.MagicMock()
        fake_config.get_account.return_value = ('cfg_user', 'cfg_pwd')
        fake_config.get_assert_value.side_effect = {
            'title_login': '配置里的首页标题',
            'title_workbench': '配置里的工作台标题',
            'title_material': '配置里的业务页标题',
        }.get

        fake_base = mock.MagicMock()
        fake_driver = mock.MagicMock(name='driver')
        fake_base.open_browser.return_value = fake_driver

        with mock.patch.object(login_suite, 'Config', fake_config), \
                mock.patch.object(login_suite, 'BasePage', return_value=fake_base), \
                mock.patch.object(login_suite, 'LoginPage') as fake_login_page:
            TestLogin.setUpClass()

        self.assertEqual(TestLogin.username, 'cfg_user')
        self.assertEqual(TestLogin.password, 'cfg_pwd')
        # ★ 断言期望值必须来自配置，不允许有代码兜底
        self.assertEqual(TestLogin.title_login, '配置里的首页标题')
        self.assertEqual(TestLogin.title_workbench, '配置里的工作台标题')
        self.assertEqual(TestLogin.title_material, '配置里的业务页标题')
        self.assertEqual(TestLogin.driver, fake_driver)
        self.assertEqual(fake_base.open_browser.call_count, 1,
                         '整个类只应打开一次浏览器')
        fake_login_page.assert_called_once_with(fake_driver)

    def test_必填配置缺失时中止且不开浏览器(self):
        """★ 失败安全：配置不全就该立刻停，不该开浏览器再报一堆元素定位失败。"""
        fake_config = mock.MagicMock()
        fake_config.get_account.side_effect = ValueError(
            '缺少必填配置 [assert] title_login（登录后首页标题）')

        fake_base = mock.MagicMock()
        with mock.patch.object(login_suite, 'Config', fake_config), \
                mock.patch.object(login_suite, 'BasePage', return_value=fake_base), \
                mock.patch.object(login_suite, 'LoginPage'):
            with self.assertRaises(ValueError):
                TestLogin.setUpClass()

        self.assertEqual(fake_base.open_browser.call_count, 0,
                         '配置校验没过就不该开浏览器')

    def test_类级后置关闭浏览器(self):
        fake_base = mock.MagicMock()
        TestLogin.base = fake_base
        TestLogin.tearDownClass()
        self.assertEqual(fake_base.dr_quit.call_count, 1)


class TestCheckTitle(unittest.TestCase):
    """自定义断言 check_title 的行为。

    ★ 2026-10-11 改造：check_title 从"读一次就比"改成"带条件等待"。
      原因是页面跳转是异步的，读完立刻比会偶发失败（CI 上尤其明显）；
      等一等再比既更稳，又比 my_sleep(5) 更快（标题对了就立刻返回）。
    """

    def _make_case(self, title, wait_ok=True):
        case = TestLogin('test_1login')
        case.login_page = mock.MagicMock()
        case.login_page.get_title.return_value = title
        # wait_title 返回 (是否等到, 最终实际标题)
        case.login_page.wait_title.return_value = (wait_ok, title)
        return case

    def test_标题一致时不抛异常(self):
        case = self._make_case('期望标题')
        case.check_title('登录成功', '期望标题')   # 不应抛出

    def test_标题不一致时断言失败(self):
        case = self._make_case('别的标题', wait_ok=False)
        with self.assertRaises(AssertionError):
            case.check_title('登录成功', '期望标题')

    def test_失败时自动截图(self):
        """失败瞬间的截图是排查问题最有效的证据。"""
        case = self._make_case('别的标题', wait_ok=False)
        with self.assertRaises(AssertionError):
            case.check_title('登录成功', '期望标题')
        self.assertEqual(case.login_page.get_img.call_count, 1)

    def test_成功时不截图(self):
        case = self._make_case('期望标题')
        case.check_title('登录成功', '期望标题')
        self.assertEqual(case.login_page.get_img.call_count, 0)

    def test_失败信息包含期望与实际(self):
        """失败消息必须同时给出期望值和实际值，否则无法定位。"""
        case = self._make_case('实际标题', wait_ok=False)
        with self.assertRaises(AssertionError) as ctx:
            case.check_title('登录成功', '期望标题')
        self.assertIn('期望标题', str(ctx.exception))
        self.assertIn('实际标题', str(ctx.exception))

    def test_使用条件等待而非固定sleep(self):
        """★ 确认改造没被回退：必须调 wait_title，而不是 get_title 读一次就比。"""
        import ast
        import inspect
        source = inspect.getsource(TestLogin.check_title)
        tree = ast.parse(_dedent(source))
        # 只看真正被调用的函数名，不看 docstring —— docstring 里会举例提到 my_sleep
        called = {node.func.attr for node in ast.walk(tree)
                  if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)}
        self.assertIn('wait_title', called,
                      'check_title 应使用 wait_title 条件等待，'
                      '而不是读完立刻比较（异步跳转会偶发失败）')
        self.assertNotIn('my_sleep', called,
                         'check_title 里不应出现固定等待')


class TestCaseBodiesAreWired(unittest.TestCase):
    """每条用例都真实调用页面对象（防止空用例混进来）。

    ★ 2026-10-11 用例体改造后，每条用例都以 ensure_xxx() 开头（前置自愈），
      因此这里要把前置检查桩成"已就绪"，才能验证用例本体。
    """

    def _make_case(self, method_name):
        case = TestLogin(method_name)
        case.username = 'u'
        case.password = 'p'
        case.title_login = '配置里的首页标题'
        case.title_workbench = '配置里的工作台标题'
        case.title_material = '配置里的业务页标题'
        case.driver = mock.MagicMock()
        case.login_page = mock.MagicMock()

        # ---- 前置自愈：假装"已经在正确的位置"，跳过链路 ----
        case.login_page.wait_title.return_value = (True, 'x')
        # 注意：MagicMock 会把 assert_no_console_error 当成"断言方法"而拒绝赋值，
        # 必须显式给一个普通 Mock，否则用例一调用就 AttributeError。
        case.login_page.assert_no_console_error = mock.MagicMock(return_value=True)
        # ---- 业务断言所需的观察点返回值 ----
        case.login_page.wait_material_count.return_value = (True, 5)
        case.login_page.wait_status_changed.return_value = (True, '已报送')
        case.login_page.get_first_row_status.return_value = '待初审'
        case.login_page.query_form_ready.return_value = {
            '关键字输入框': True, '查询按钮': True, '重置按钮': True}

        fake_config = mock.MagicMock()
        fake_config.get_upload_file.return_value = '/tmp/a.mp4'
        fake_config.get_form_field.side_effect = {
            'video_author': '配置里的作者',
            'phone': '配置里的手机号',
            'reporting': '配置里的上报单位',
            'query_keyword': '配置里的关键字',
            'first_trial_person': '配置里的审核人',
        }.get
        return case, fake_config

    def _run(self, method_name):
        case, cfg = self._make_case(method_name)
        with mock.patch.object(login_suite, 'Config', cfg):
            getattr(case, method_name)()
        return case, cfg

    # ---- 前置自愈方法本身 ----

    def test_前置自愈_已就绪时不做多余操作(self):
        """顺序跑时 ensure_xxx 应立即返回，不能重复登录/跳页（否则白慢）。"""
        case, _ = self._make_case('test_1login')
        case.ensure_material_page()
        self.assertEqual(case.login_page.login.call_count, 0,
                         '已在目标页时不应重新登录')
        self.assertEqual(case.login_page.click_material.call_count, 0,
                         '已在目标页时不应重复点菜单')

    def test_前置自愈_未就绪时补齐链路(self):
        """★ 单条用例独立运行时，前置链路必须被自动补齐。

        探测顺序（都不就绪）：素材库 -> 工作台 -> 登录页，共 3 次探测失败；
        之后每补齐一步都会用 check_title 断言一次，共 3 次（登录/工作台/素材库）。
        """
        case, _ = self._make_case('test_1login')
        probes = {'n': 0}

        def wait_title(*_a, **_k):
            probes['n'] += 1
            if probes['n'] <= 3:          # 三次前置探测：哪一页都不是
                return False, '空白页'
            return True, 'x'              # 走完链路后，断言应当成功

        case.login_page.wait_title.side_effect = wait_title
        case.ensure_material_page()
        self.assertEqual(probes['n'], 6, '3 次前置探测 + 3 次补链后的断言')
        case.login_page.login.assert_called_once()
        case.login_page.click_sign_in.assert_called_once()
        case.login_page.switch_other_window.assert_called_once()
        case.login_page.click_material.assert_called_once()

    # ---- 各用例本体 ----

    def test_用例1调用登录(self):
        case, _ = self._run('test_1login')
        case.login_page.login.assert_called_once_with('u', 'p')

    def test_用例2切换标签页(self):
        case, _ = self._run('test_2select_scxt')
        case.login_page.click_sign_in.assert_called_once()
        case.login_page.switch_other_window.assert_called_once()

    def test_用例3进入素材库(self):
        case, _ = self._run('test_3material')
        case.login_page.click_material.assert_called_once()

    def test_用例3断言查询区控件齐全(self):
        """★ 业务断言：控件缺失必须让用例变红（旧用例只比标题，缺控件照样绿）。"""
        case, _ = self._make_case('test_3material')
        case.login_page.query_form_ready.return_value = {
            '关键字输入框': True, '查询按钮': False, '重置按钮': True}
        with mock.patch.object(login_suite, 'Config', mock.MagicMock()):
            with self.assertRaises(AssertionError) as ctx:
                case.test_3material()
        self.assertIn('查询按钮', str(ctx.exception), '失败信息要指出缺的是哪个控件')

    def test_用例4上传并填表单且字段来自配置(self):
        case, cfg = self._run('test_4uplaodbutton')
        case.login_page.upload_file.assert_called_once_with('/tmp/a.mp4')
        case.login_page.fill_upload_form.assert_called_once_with(
            '配置里的作者', '配置里的手机号', '配置里的上报单位')
        self.assertEqual(cfg.get_form_field.call_count, 3,
                         '三个表单字段都应现取自配置')

    def test_用例4断言上传后行数增加(self):
        """★★ 最关键的改造：上传失败必须让用例变红。

        旧用例只断言"标题没变"，上传失败/进度卡住/弹窗报错都会判绿。
        """
        case, _ = self._make_case('test_4uplaodbutton')
        case.login_page.wait_material_count.side_effect = [
            (True, 3),      # 上传前的基线：3 行
            (False, 3),     # 上传后等待超时：还是 3 行（没传上去）
        ]
        with mock.patch.object(login_suite, 'Config', mock.MagicMock(
                get_upload_file=mock.MagicMock(return_value='/tmp/a.mp4'),
                get_form_field=mock.MagicMock(return_value='v'))):
            with self.assertRaises(AssertionError) as ctx:
                case.test_4uplaodbutton()
        self.assertIn('行数未增加', str(ctx.exception))

    def test_用例5关键字来自配置(self):
        case, _ = self._run('test_5keyword')
        case.login_page.keyword_query.assert_called_once_with('配置里的关键字')

    def test_用例6刷新后报送(self):
        case, cfg = self._run('test_6submitted')
        case.login_page.submitted.assert_called_once()
        self.assertEqual(case.driver.refresh.call_count, 1,
                         '报送前必须刷新，确保列表里有刚上传的素材')

    def test_用例6断言报送后状态变化(self):
        """★ 业务断言：报送没生效必须让用例变红。

        旧用例只断言"标题没变"，报送被拒绝、选错人都会判绿。
        """
        case, _ = self._make_case('test_6submitted')
        case.login_page.get_first_row_status.return_value = '待初审'
        case.login_page.wait_status_changed.return_value = (False, '待初审')
        with mock.patch.object(login_suite, 'Config', mock.MagicMock()):
            with self.assertRaises(AssertionError) as ctx:
                case.test_6submitted()
        self.assertIn('状态未变化', str(ctx.exception))


class TestEnterpriseAssertions(unittest.TestCase):
    """★ 业务断言与用例独立性的「防回退」门禁。

    这批断言锁住 2026-10-11 的核心改造。任何一条变红都说明
    框架正在退回"只比标题"的旧状态 —— 那是"假绿"的根源。
    """

    def test_每条写用例都有业务结果断言(self):
        """★★ 上传/查询/报送必须断言业务结果，不能只比标题。

        旧状态：6 条用例只有 1 个 assertEqual（比标题），于是
        上传失败、报送被拒、接口 500 全都判绿。这一条就是防它回退。
        """
        required = {
            'test_4uplaodbutton': 'wait_material_count',
            'test_6submitted': 'wait_status_changed',
        }
        for method, marker in required.items():
            body = _method_source(login_suite, method)
            self.assertIn(
                marker, body,
                '%s 缺少业务结果断言（应调用 %s）。\n'
                '    只断言页面标题的话，功能坏了用例照样绿 —— 这是"假绿"。'
                % (method, marker))

    def test_存在console报错检查(self):
        """★ 前端 JS 报错必须能让用例变红。"""
        source = inspect.getsource(login_suite)
        self.assertIn('check_no_console_error', source,
                      '用例层应调用 check_no_console_error，'
                      '否则"接口 500 但页面照常渲染"这类故障会被判绿')

    def test_用例层不再有硬编码等待(self):
        """★★ 固定 sleep 是 flaky 与慢的根源，必须用条件等待替代。

        允许的例外：注释里提到（不算调用）。这里只扫真正的调用。
        """
        offenders = _fixed_sleep_calls(login_suite)
        self.assertEqual(
            offenders, [],
            '用例层仍有固定等待：%s\n'
            '    请改用 wait_title / wait_text / wait_loading_gone / '
            'wait_material_count 等条件等待 —— 对了就立刻返回，'
            '既更快也更稳' % offenders)

    def test_每条用例都能独立运行(self):
        """★★ 任意用例必须可单独执行（否则无法做 flaky 复跑与调试）。

        做法：每条用例都要以 ensure_xxx() 开头把前置链路补齐。
        旧设计只能从 test_1 顺序跑，`--cases test_5keyword` 必然失败。

        ★ 例外：test_1login 本身就是"登录"这个动作，它没有更早的前置，
          所以不能加 ensure_login（否则已登录时会被跳过，登录就测不到了）。
        """
        for name in EXPECTED_ORDER:
            if name == 'test_1login':
                continue
            body = _method_source(login_suite, name)
            self.assertIn(
                'ensure_', body,
                '%s 缺少前置自愈（ensure_login/ensure_workbench/ensure_material_page），'
                '\n    单独运行这条用例时会因为没有登录态而失败' % name)

    def test_登录用例本身不跳过登录(self):
        """test_1login 必须真的执行登录动作（它测的就是登录）。"""
        body = _method_source(login_suite, 'test_1login')
        self.assertIn('login(', body,
                      'test_1login 必须真实调用登录，否则这条用例没有测任何东西')
        self.assertNotIn('ensure_login', body,
                         'test_1login 不能加 ensure_login —— '
                         '已登录时会被幂等跳过，登录动作就测不到了')

    def test_提供了三级前置自愈方法(self):
        for name in ('ensure_login', 'ensure_workbench', 'ensure_material_page'):
            self.assertTrue(callable(getattr(TestLogin, name, None)),
                            '缺少前置自愈方法：%s' % name)

    def test_前置自愈是幂等的(self):
        """已在目标页时不应重复登录/跳页，否则顺序跑会白慢一大截。"""
        source = inspect.getsource(TestLogin.ensure_login)
        self.assertIn('timeout=1', source,
                      '前置自愈应先做一次短超时探测，已在目标页时立即返回')


class TestModuleHygiene(unittest.TestCase):
    """模块级约定。"""

    def test_模块可被unittest收集到6条用例(self):
        import unittest as ut
        suite = ut.defaultTestLoader.loadTestsFromTestCase(TestLogin)
        self.assertEqual(suite.countTestCases(), 6)

    def test_样例模块不会被本工程用例目录收集(self):
        """tests/samples.py 只是测试数据，不应混进 TestSuites。"""
        self.assertFalse(os.path.exists(
            os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         'TestSuites', 'samples.py')))

    def test_用例类只依赖约定好的模块(self):
        tree = ast.parse(inspect.getsource(login_suite))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
        self.assertIn('Common.config', imported)
        self.assertIn('PageObject.loginPage', imported)


def _method_source(module, method_name):
    """取某个用例方法的源码（已去掉缩进，便于查找关键字）。"""
    import inspect
    method = getattr(module.TestLogin, method_name, None)
    if method is None:
        raise AssertionError('用例方法不存在：%s' % method_name)
    return inspect.getsource(method)


def _fixed_sleep_calls(module):
    """找出用例层里真正被调用的固定等待（my_sleep / time.sleep）。

    :return: ['test_4uplaodbutton: my_sleep', ...]

    只统计**调用**，不看注释与 docstring —— 说明文字里提到 my_sleep
    是正常的（我们在文档里解释"为什么不要用它"）。
    """
    import ast
    import inspect
    source = inspect.getsource(module)
    tree = ast.parse(source)
    offenders = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        for child in ast.walk(node):
            if not isinstance(child, ast.Call) or not isinstance(child.func, ast.Attribute):
                continue
            if child.func.attr in ('my_sleep', 'sleep'):
                offenders.append('%s: %s' % (node.name, child.func.attr))
    return sorted(set(offenders))


def _dedent(source):
    """把带缩进的方法源码还原成可解析的完整代码块。"""
    import textwrap
    return textwrap.dedent(source)


def load_tests(loader, standard_tests, pattern):
    """显式声明本模块要执行的测试类。

    【为什么必须这么写】
        本模块需要 import 真实用例类 TestLogin 来做结构校验，
        而 unittest 在加载模块时会把模块命名空间里**所有** TestCase 子类
        都当成用例收走 —— 那样 TestLogin 的 setUpClass 会被真的执行
        （尝试打开浏览器、连生产环境），测试直接崩。
        用 load_tests 只返回本文件自己的测试类，彻底避免误收集。

        同理，tests/samples.py 也是用「模块方式引用」来规避同一问题。
    """
    suite = unittest.TestSuite()
    for case in (TestCaseStructure, TestSetUpClass, TestCheckTitle,
                 TestCaseBodiesAreWired, TestEnterpriseAssertions,
                 TestModuleHygiene):
        suite.addTests(loader.loadTestsFromTestCase(case))
    return suite


if __name__ == '__main__':
    unittest.main(verbosity=2)
