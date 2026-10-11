# -*- coding: utf-8 -*-
"""
==========================================================================
 单元测试公共基座（桩对象 + 隔离工具）
==========================================================================

【这个文件提供什么】
    1. FakeElement / FakeDriver —— 假的 Selenium 元素与浏览器。
       让 BasePage 的代码"以为自己真的在操作浏览器"，但实际只是记录调用，
       从而使单元测试可以在无浏览器、无桌面的环境下毫秒级跑完。
    2. patch_config()  —— 把工程配置重定向到临时 config.ini，测读写不碰真文件。
    3. patch_dirs()    —— 把 Logs / img / Report / 用例目录重定向到临时目录。
    4. make_sandbox()  —— 临时沙盒工程（config.ini + 用例包），
       供 runner.run() 的端到端测试使用，测完即弃。
    5. load_module()   —— 加载工程根目录下的顶层模块（如 run.py）。

【为什么必须隔离】
    工程的 config.ini 里是生产环境地址与真实账号；Logs/img/Report 是真实产物。
    单元测试如果直接操作它们，轻则污染工程目录，重则误触发真实业务动作。
    所有隔离都在这里做掉，具体测试文件里只需 with 一下。

【新人写新测试时的模板】
    class TestXxx(unittest.TestCase):
        def test_something(self):
            with patch_config() as ini:          # 需要配置时
                with patch_dirs() as root:       # 需要文件产出时
                    ...                          # 用 FakeDriver 构造对象
==========================================================================
"""

import atexit
import contextlib
import os
import shutil
import sys
import tempfile
import time
import unittest
from unittest import mock

# --- 让测试无论从哪个目录启动，都能 import 到工程模块 ---
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from selenium.common.exceptions import (   # noqa: E402  必须在 sys.path 处理之后导入
    NoSuchElementException,
    TimeoutException,
    WebDriverException,
)
from selenium.webdriver.common.by import By   # noqa: E402

from Common.configOverWriter import ConfigOverWrite   # noqa: E402


# ==========================================================================
# 临时配置文件
# ==========================================================================
# 这份配置覆盖了工程用到的全部段位，且刻意放了几个"容易踩坑"的值：
#   - login_password 含 %      -> 验证 ConfigParser 的 % 插值确实被关掉
#   - upload_file 用 ~ 开头    -> 验证 get_upload_file 会展开用户目录
#   - [addressed] 键是中文     -> 验证键名大小写/中文都不会被改写
DEFAULT_INI = """\
[environment]
url = http://test-env.local/sso-portal
browser = chrome

[testcase]
login_username = unit_user
login_password = p%ss%word
upload_file = ~/video/demo.mp4
upload_mode = send_keys
video_author = 张三
phone = 13800000000
reporting = 深圳

[report]
title = 单元测试报告
filename = unit-report.html
tester = unit-tester
description = 单元测试描述

[ci]
headless = false
element_timeout = 7
implicit_wait = 2
smoke_cases = test_1login,test_2select_scxt
junit_xml = Report/junit-results.xml
extra_chrome_args =
chrome_binary =
# ★ 单元测试必须关掉运行环境自检。
#   自检会去查这台机器有没有装浏览器、PATH 上的驱动版本对不对 ——
#   那属于"机器状态"，不是"代码行为"。开着它就等于让单测结果依赖跑测的机器，
#   没装 Chrome 的机器上会一片红，而这跟被测代码毫无关系。
#   自检本身的行为由 tests/test_preflight.py 单独覆盖（那里把探测函数打桩）。
preflight = false

[sender]
username = 单元测试发件人
email = sender@example.com
password = smtp-token

[addressed]
张三 = zhangsan@example.com
李四 = lisi@example.com
"""


# ==========================================================================
# 临时目录管理
#   单元测试会创建大量临时目录。若每次都 mkdtemp + rmtree，
#   Windows 上光删目录就能占到总耗时的一大半。所以这里改成：
#     - 配置用的临时根目录全进程共享，只增删 ini 文件本身
#     - 其余临时目录统一登记到 _TEMP_DIRS，进程退出时一次性清理
#   效果：整套 328 项测试的耗时从约 110 秒降到约 25 秒（同一台机器实测）。
#
#   ★ 凡是新建临时目录的地方都必须登记，否则会在系统临时目录里留垃圾。
# ==========================================================================
_TEMP_DIRS = []
_SHARED_CONFIG_DIR = [None]
_SEQ = [0]


@atexit.register
def _cleanup_temp_dirs():
    """测试进程退出时统一清理临时目录。"""
    for path in _TEMP_DIRS:
        shutil.rmtree(path, ignore_errors=True)
    del _TEMP_DIRS[:]


def _register_temp_dir(path):
    """登记一个临时目录，交给 atexit 统一删除。"""
    _TEMP_DIRS.append(path)
    return path


def _next_seq():
    _SEQ[0] += 1
    return _SEQ[0]


def _shared_config_dir():
    if _SHARED_CONFIG_DIR[0] is None or not os.path.isdir(_SHARED_CONFIG_DIR[0]):
        _SHARED_CONFIG_DIR[0] = _register_temp_dir(
            tempfile.mkdtemp(prefix='ut_config_'))
    return _SHARED_CONFIG_DIR[0]


@contextlib.contextmanager
def patch_config(ini_text=None, ini_path=None):
    """把 Common/config.py 的配置来源换成临时文件。

    :param ini_text: 配置内容；不传用 DEFAULT_INI
    :param ini_path: 显式指定 ini 路径（例如指向沙盒工程里的那份）
    :return: 生成出来的 ini 文件绝对路径

    同时替换两个模块级全局：
        config_path  写操作（set_value/config_delete）落盘的位置
        config       读操作使用的解析器实例

    说明：未显式指定 ini_path 时，文件建在共享临时目录里、退出上下文即删除；
    显式指定时该文件归调用方所有，本函数不删。
    """
    owns_file = ini_path is None
    if owns_file:
        ini_path = os.path.join(_shared_config_dir(), 'config_%d.ini' % _next_seq())

    text = DEFAULT_INI if ini_text is None else ini_text
    with open(ini_path, 'w', encoding='utf-8') as fp:
        fp.write(text)

    parser = ConfigOverWrite()
    parser.read(ini_path, encoding='utf-8-sig')

    import Common.config as config_module
    with mock.patch.object(config_module, 'config_path', ini_path), \
            mock.patch.object(config_module, 'config', parser):
        yield ini_path

    if owns_file:
        with contextlib.suppress(OSError):
            os.remove(ini_path)


# ==========================================================================
# 二、临时目录（日志 / 截图 / 报告 / 用例）
# ==========================================================================
class _FakeGetcwd:
    """替换 getcwd 模块：让 get_cwd() 返回测试指定的临时根目录。"""

    def __init__(self, root):
        self._root = root

    def get_cwd(self):
        return self._root


@contextlib.contextmanager
def patch_dirs(root=None):
    """把工程里的各种产出目录重定向到临时目录。

    :param root: 临时工程根；不传则新建
    :return: 临时根目录路径

    重定向清单：
        Common/basePage.getcwd   -> 截图目录 img/
        Common/log.getcwd        -> 日志目录 Logs/
        Common/runner 的 base_dir / htmlreport_dir / testcases_dir
        Common/dir_config 的同名常量（失败取证等模块在运行期读它，必须一起改）
        Common/sentMail.htmlreport_dir

    目录归属：不传 root 时由本函数新建并登记，进程退出统一删除；
    显式传入 root（例如沙盒工程根）时视为调用方所有，本函数不动它。
    """
    root = root or _register_temp_dir(tempfile.mkdtemp(prefix='ut_root_'))
    fake_getcwd = _FakeGetcwd(root)
    report_dir = os.path.join(root, 'Report')
    cases_dir = os.path.join(root, 'TestSuites')
    artifacts_dir = os.path.join(report_dir, 'artifacts')

    import Common.basePage as base_page
    import Common.dir_config as dir_config_module
    import Common.log as log_module
    import Common.runner as runner_module
    import Common.sentMail as mail_module

    # UI_LOG_DIR 是"进程级"的日志目录覆盖（tests/__init__.py 用它避免污染工程 Logs/），
    # 优先级高于下面给 Common.log.getcwd 打的桩。用例级别要接管日志目录，
    # 就得先把它摘掉，退出上下文时再原样放回，否则 test_log.py 会写到共享临时目录去。
    saved_log_dir = os.environ.pop('UI_LOG_DIR', None)
    try:
        with mock.patch.object(base_page, 'getcwd', fake_getcwd), \
                mock.patch.object(log_module, 'getcwd', fake_getcwd), \
                mock.patch.object(runner_module, 'base_dir', root), \
                mock.patch.object(runner_module, 'htmlreport_dir', report_dir), \
                mock.patch.object(runner_module, 'testcases_dir', cases_dir), \
                mock.patch.object(dir_config_module, 'base_dir', root), \
                mock.patch.object(dir_config_module, 'htmlreport_dir', report_dir), \
                mock.patch.object(dir_config_module, 'artifacts_dir', artifacts_dir), \
                mock.patch.object(mail_module, 'htmlreport_dir', report_dir):
            yield root
    finally:
        if saved_log_dir is not None:
            os.environ['UI_LOG_DIR'] = saved_log_dir

    # 不在这里 rmtree：测试会创建几十个临时目录，Windows 上删目录很慢，
    # 统一交给 atexit 清理（见 _cleanup_temp_dirs）


# ==========================================================================
# 三、沙盒工程（供 runner.run 端到端测试）
# ==========================================================================
_sandbox_seq = [0]


def make_sandbox(case_source=None, with_init=True, pkg_prefix='Cases',
                 ini_text=None, case_filename='demo_test.py'):
    """建一个临时的"迷你工程"：临时根 + 配置 + 用例包。

    :param case_source:  用例模块源码；None 表示不放用例
    :param with_init:    用例包是否放 __init__.py（False 用于验证收集失败场景）
    :param pkg_prefix:   用例包名前缀，用来保证多次调用互不冲突
    :param ini_text:     配置内容，默认 DEFAULT_INI
    :param case_filename: 用例文件名
    :return: (root, cases_dir, pkg_name)

    ★ 包名刻意不叫 TestSuites：
      工程里已存在真实的 TestSuites 包，同名会让 unittest.discover 拿到
      缓存里的旧模块而收错用例。这里用唯一包名彻底规避该干扰。
    """
    _sandbox_seq[0] += 1
    pkg_name = '%s%d_%d' % (pkg_prefix, _sandbox_seq[0], int(time.time() * 1000) % 100000)

    root = _register_temp_dir(tempfile.mkdtemp(prefix='ut_sandbox_'))
    cases_dir = os.path.join(root, pkg_name)
    os.makedirs(cases_dir)

    with open(os.path.join(root, 'config.ini'), 'w', encoding='utf-8') as fp:
        fp.write(DEFAULT_INI if ini_text is None else ini_text)

    if with_init:
        with open(os.path.join(cases_dir, '__init__.py'), 'w', encoding='utf-8') as fp:
            fp.write('# -*- coding: utf-8 -*-\n')
    if case_source is not None:
        with open(os.path.join(cases_dir, case_filename), 'w', encoding='utf-8') as fp:
            fp.write(case_source)

    return root, cases_dir, pkg_name


def drop_modules(*module_names):
    """把指定模块名从 sys.modules 中清掉，避免沙盒用例被缓存复用。"""
    for name in module_names:
        sys.modules.pop(name, None)


# 常用的沙盒用例源码
CASE_SOURCE_PASS = """\
import unittest


class DemoPass(unittest.TestCase):
    def test_a_pass(self):
        self.assertEqual(1, 1)

    def test_b_pass(self):
        pass
"""

CASE_SOURCE_MIXED = """\
import unittest


class DemoMixed(unittest.TestCase):
    def test_a_pass(self):
        self.assertTrue(True)

    def test_b_fail(self):
        self.assertEqual(1, 2, '故意失败')
"""

CASE_SOURCE_SETUPCLASS_BOOM = """\
import unittest


class DemoBoom(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        raise RuntimeError('模拟浏览器起不来')

    def test_never_runs(self):
        pass
"""

CASE_SOURCE_SKIP = """\
import unittest


class DemoSkip(unittest.TestCase):
    @unittest.skip('不跑这条')
    def test_skipped(self):
        pass

    def test_ok(self):
        pass
"""


# ==========================================================================
# 四、假 Selenium 对象
# ==========================================================================
class FakeElement:
    """假的 WebElement。所有动作只记录到 calls，可指定某动作抛异常。"""

    def __init__(self, text='', displayed=True, click_error=None,
                 send_keys_error=None, clear_error=None, attributes=None):
        self.text = text
        self._displayed = displayed
        self.click_error = click_error
        self.send_keys_error = send_keys_error
        self.clear_error = clear_error
        self.attributes = dict(attributes or {})   # get_attribute() 的返回值来源
        self.calls = []          # 形如 ['clear', 'send_keys', 'click']
        self.sent = []           # send_keys 收到的内容
        self.attributes_read = []  # get_attribute 读过的属性名

    def clear(self):
        self.calls.append('clear')
        if self.clear_error:
            raise self.clear_error

    def send_keys(self, *values):
        self.calls.append('send_keys')
        self.sent.extend(values)
        if self.send_keys_error:
            raise self.send_keys_error

    def click(self):
        self.calls.append('click')
        if self.click_error:
            raise self.click_error

    def is_displayed(self):
        return self._displayed

    def get_attribute(self, name):
        self.attributes_read.append(name)
        return self.attributes.get(name)


class FakeSwitchTo:
    """假的 driver.switch_to，记录 frame / 窗口 / alert 的切换动作。"""

    def __init__(self, driver):
        self._driver = driver

    def frame(self, element):
        self._driver.switched_frames.append(element)

    def default_content(self):
        self._driver.default_content_count += 1

    def window(self, handle):
        self._driver.switched_windows.append(handle)
        self._driver.current_window_handle = handle

    @property
    def alert(self):
        return self._driver.alert


class FakeAlert:
    """假的浏览器原生弹窗。"""

    def __init__(self):
        self.accepted = False

    def accept(self):
        self.accepted = True


class FakeDriver:
    """假的 webdriver，覆盖 BasePage 实际会用到的全部 API。"""

    def __init__(self, title='', window_handles=None, element=None,
                 elements=None, find_error=None,
                 page_source='<html><body>假页面</body></html>',
                 source_error=None):
        self.title = title
        self._page_source = page_source
        # 让"读取页面源码失败"成为可造的场景（失败取证必须扛得住这种情况）
        self.source_error = source_error
        self._handles = list(window_handles or ['window-1'])
        self.current_window_handle = self._handles[0]
        self._element = element if element is not None else FakeElement()
        self._elements = elements if elements is not None else []
        self.find_error = find_error

        self.calls = []                # [('find_element', by, value), ...]
        self.scripts = []              # execute_script 的脚本内容
        self.screenshots = []          # 截图落盘路径
        self.visited = []              # get() 访问过的 url
        self.window_sizes = []         # set_window_size 的参数
        self.implicit_waits = []
        self.maximized = 0
        self.quit_called = False
        self.refreshed = 0
        self.switched_frames = []
        self.switched_windows = []
        self.default_content_count = 0
        self.alert = FakeAlert()
        self.switch_to = FakeSwitchTo(self)

    # ---- 元素查找 ----
    def find_element(self, by, value):
        self.calls.append(('find_element', by, value))
        if self.find_error:
            raise self.find_error
        return self._element

    def find_elements(self, by, value):
        self.calls.append(('find_elements', by, value))
        if self.find_error:
            raise self.find_error
        return self._elements

    # ---- 浏览器控制 ----
    def get(self, url):
        self.visited.append(url)

    def maximize_window(self):
        self.maximized += 1

    def set_window_size(self, width, height):
        self.window_sizes.append((width, height))

    def implicitly_wait(self, seconds):
        self.implicit_waits.append(seconds)

    def quit(self):
        self.quit_called = True

    def refresh(self):
        self.refreshed += 1

    def execute_script(self, script, *args):
        self.scripts.append(script)

    def get_screenshot_as_file(self, path):
        self.screenshots.append(path)
        with open(path, 'wb') as fp:
            fp.write(b'fake-png')
        return True

    def save_screenshot(self, path):
        """与 get_screenshot_as_file 等价。

        Selenium 的 WebDriver 同时提供这两个方法，真实项目里两种写法都有，
        失败取证用的是 save_screenshot()，所以假对象也得有，
        否则测出来的"取证成功"是假的。
        """
        return self.get_screenshot_as_file(path)

    @property
    def page_source(self):
        if self.source_error:
            raise self.source_error
        return self._page_source

    @property
    def window_handles(self):
        return list(self._handles)

    def add_window(self, handle):
        """测试辅助：模拟新开了一个标签页。"""
        self._handles.append(handle)


# ==========================================================================
# 五、假 webdriver 模块（供 open_browser 测试替换）
# ==========================================================================
class FakeChromeOptions:
    """假的 ChromeOptions，把 add_argument / add_experimental_option 记录下来。"""

    def __init__(self):
        self.arguments = []
        self.experimental = {}
        self.binary_location = None

    def add_argument(self, arg):
        self.arguments.append(arg)

    def add_experimental_option(self, name, value):
        self.experimental[name] = value


class FakeWebDriverFactory:
    """假的 webdriver 命名空间：Chrome/Firefox/Edge 都返回指定的 driver。"""

    def __init__(self, driver=None, chrome_error=None):
        self.driver = driver if driver is not None else FakeDriver()
        self.chrome_error = chrome_error
        self.chrome_options = None
        self.chrome_calls = 0
        self.firefox_calls = 0
        self.edge_calls = 0
        self.remote_calls = 0
        self.remote_urls = []
        self.remote_options = None
        self.ChromeOptions = FakeChromeOptions
        self.FirefoxOptions = FakeChromeOptions   # 假实现共用即可，能记录参数
        self.EdgeOptions = FakeChromeOptions

    def Chrome(self, options=None):            # noqa: N802 - 对齐 selenium 的命名
        self.chrome_calls += 1
        self.chrome_options = options
        if self.chrome_error:
            raise self.chrome_error
        return self.driver

    def Firefox(self, *args, **kwargs):        # noqa: N802
        self.firefox_calls += 1
        return self.driver

    def Edge(self, *args, **kwargs):           # noqa: N802
        self.edge_calls += 1
        return self.driver

    def Remote(self, command_executor=None, options=None, **kwargs):  # noqa: N802
        """模拟 Selenium Grid 远程驱动：记录 Hub 地址与 options，返回假 driver。"""
        self.remote_calls += 1
        self.remote_urls.append(command_executor)
        self.remote_options = options
        return self.driver


# ==========================================================================
# 六、加载工程根目录下的顶层模块
# ==========================================================================
def load_module(name, path):
    """按文件路径加载一个顶层模块并返回（不加入 sys.modules 缓存）。

    用途：测试 run.py 这类不在包里的入口脚本。
    它们都有 `if __name__ == '__main__'` 保护，import 不会触发执行。
    """
    import importlib.util

    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# 常用异常，方便测试文件直接引用
__all__ = [
    'BASE_DIR', 'DEFAULT_INI', 'patch_config', 'patch_dirs', 'make_sandbox',
    'drop_modules', 'FakeElement', 'FakeDriver', 'FakeAlert', 'FakeSwitchTo',
    'FakeChromeOptions', 'FakeWebDriverFactory', 'load_module',
    'CASE_SOURCE_PASS', 'CASE_SOURCE_MIXED', 'CASE_SOURCE_SETUPCLASS_BOOM',
    'CASE_SOURCE_SKIP', 'By', 'NoSuchElementException', 'TimeoutException',
    'WebDriverException', 'unittest',
]
