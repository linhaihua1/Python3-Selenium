# -*- coding: utf-8 -*-
"""
==========================================================================
 单元测试：Common/preflight.py（运行环境自检）
==========================================================================

这个文件最需要注意的是**不能依赖跑测的机器**：
    自检本身就是在查"这台机器有没有浏览器、驱动版本对不对"，
    如果测试直接调用真实探测，那么在没装 Chrome 的机器上就会红 ——
    而那不是代码坏了，是机器不同。

所以这里的原则是：
    - 纯解析逻辑（版本号、目录名）直接测真实函数
    - 涉及机器状态的探测（找浏览器、跑 --version）一律打桩
    - 只有"目录可写"这类可以用临时目录模拟的，才走真实代码

覆盖：
    1. 版本号解析（含 Chrome / ChromeDriver 两种输出格式）
    2. Python / selenium 版本门槛
    3. 浏览器查找：显式路径优先、路径不存在时明确报错
    4. 浏览器主版本探测的三条途径
    5. ★ 驱动版本比对——本模块存在的理由
    6. 目录可写性
    7. 结论渲染与命令行退出码
    8. 接入 runner 后的行为：致命项 -> exit 2，且不打开浏览器
==========================================================================
"""

import contextlib
import io
import os
import unittest
from unittest import mock

from Common import preflight
from Common.preflight import (
    LEVEL_ERROR, LEVEL_OK, LEVEL_WARN, Finding, browser_major, check_browser,
    check_dirs, check_driver, check_python, check_selenium, collect, format_report,
    has_error, main, worst_level,
)
from tests.helpers import CASE_SOURCE_PASS, make_sandbox, patch_config, patch_dirs


class TestMajor(unittest.TestCase):
    """版本号解析：真实世界的输出格式都得认出来。"""

    def test_标准三段版本(self):
        self.assertEqual(preflight._major('Google Chrome 154.0.8037.57'), 154)

    def test_带反引号括号的驱动输出(self):
        text = 'ChromeDriver 114.0.5735.90 (386bc09e8f4f2e025eddae123f36f6263096ae49-refs/branch-heads/5735)'
        self.assertEqual(preflight._major(text), 114)

    def test_只有主版本号也认(self):
        self.assertEqual(preflight._major('ChromeDriver 114'), 114)

    def test_空值返回None(self):
        for value in ('', None, 'no version here'):
            self.assertIsNone(preflight._major(value), '不应从 %r 中解析出版本' % (value,))


class TestCheckPython(unittest.TestCase):
    """① Python 版本门槛。"""

    def test_当前解释器应当通过(self):
        finding = check_python()
        self.assertEqual(finding.level, LEVEL_OK)
        self.assertIn('3.', finding.detail)

    def test_门槛高于当前版本时报错(self):
        finding = check_python(min_version=(99, 0))
        self.assertEqual(finding.level, LEVEL_ERROR)
        self.assertIn('99.0', finding.detail)
        self.assertTrue(finding.hint, '报错时必须给出修复方向')


class TestCheckSelenium(unittest.TestCase):
    """② selenium 可用性与大版本。"""

    def test_本机装了selenium应当通过(self):
        finding = check_selenium()
        self.assertEqual(finding.level, LEVEL_OK)
        self.assertRegex(finding.detail, r'^\d+\.')

    def test_未安装时判为错误并给出安装命令(self):
        with mock.patch.dict('sys.modules', {'selenium': None}):
            finding = check_selenium()
        self.assertEqual(finding.level, LEVEL_ERROR)
        self.assertIn('requirements.txt', finding.hint)

    def test_selenium3判为错误(self):
        fake = mock.Mock()
        fake.__version__ = '3.141.0'
        with mock.patch.dict('sys.modules', {'selenium': fake}):
            finding = check_selenium()
        self.assertEqual(finding.level, LEVEL_ERROR)
        self.assertIn('3.141.0', finding.detail)

    def test_读不出版本号时只警告(self):
        """只有 __version__ 缺失时才走这支，不该直接判死刑。"""
        fake = mock.Mock(spec=[])       # 不含 __version__ 属性
        with mock.patch.dict('sys.modules', {'selenium': fake}):
            finding = check_selenium()
        self.assertEqual(finding.level, LEVEL_WARN)


class TestFindBrowser(unittest.TestCase):
    """③ 浏览器定位。全部打桩，不依赖机器上装了什么。"""

    def test_显式路径优先且必须存在(self):
        with mock.patch.object(preflight.os.path, 'isfile', return_value=True):
            found = preflight.find_browser('chrome', r'D:\custom\chrome.exe')
        self.assertEqual(found, r'D:\custom\chrome.exe')

    def test_显式路径不存在时返回None(self):
        with mock.patch.object(preflight.os.path, 'isfile', return_value=False):
            self.assertIsNone(preflight.find_browser('chrome', r'D:\nope\chrome.exe'))

    def test_没有显式路径时按默认位置找(self):
        fake_paths = {'chrome': {'nt': ['/fake/chrome'], 'posix': ['/fake/chrome']}}
        with mock.patch.object(preflight, '_BROWSER_PATHS', fake_paths), \
                mock.patch.object(preflight.os.path, 'isfile',
                                  side_effect=lambda p: p == '/fake/chrome'):
            found = preflight.find_browser('chrome')
        self.assertEqual(found, '/fake/chrome')

    def test_默认位置都没有时退回PATH查找(self):
        with mock.patch.object(preflight.os.path, 'isfile', return_value=False), \
                mock.patch.object(preflight, '_find_on_path',
                                  side_effect=lambda name: '/usr/bin/' + name
                                  if name == 'chromium' else None):
            found = preflight.find_browser('chrome')
        self.assertEqual(found, '/usr/bin/chromium')

    def test_完全找不到时返回None(self):
        with mock.patch.object(preflight.os.path, 'isfile', return_value=False), \
                mock.patch.object(preflight, '_find_on_path', return_value=None):
            self.assertIsNone(preflight.find_browser('chrome'))


class TestCheckBrowser(unittest.TestCase):
    """③ 包装成 Finding 后的措辞是否可执行。"""

    def test_找不到浏览器时的提示要能照做(self):
        with mock.patch.object(preflight, 'find_browser', return_value=None):
            finding, path = check_browser('chrome')
        self.assertEqual(finding.level, LEVEL_ERROR)
        self.assertIsNone(path)
        self.assertIn('chrome_binary', finding.hint)

    def test_显式路径配错时的提示指向配置项(self):
        with mock.patch.object(preflight, 'find_browser', return_value=None):
            finding, _ = check_browser('chrome', browser_binary='/no/such/chromium')
        self.assertEqual(finding.level, LEVEL_ERROR)
        self.assertIn('/no/such/chromium', finding.detail)

    def test_找到了就带上路径(self):
        with mock.patch.object(preflight, 'find_browser', return_value='/usr/bin/chromium'):
            finding, path = check_browser('chrome')
        self.assertEqual(finding.level, LEVEL_OK)
        self.assertEqual(path, '/usr/bin/chromium')


class TestBrowserMajor(unittest.TestCase):
    """④ 浏览器主版本的三条探测途径。"""

    def setUp(self):
        preflight._BROWSER_MAJOR_CACHE.clear()

    def test_Windows优先扫版本号目录(self):
        with mock.patch.object(preflight.os, 'name', 'nt'), \
                mock.patch.object(preflight, '_release_version_dirs', return_value=[154, 152, 149]):
            major = browser_major('chrome', r'C:\...\Application\chrome.exe')
        self.assertEqual(major, 154, '应当取最大的那个版本目录')

    def test_Windows扫不到时退回SeleniumManager缓存(self):
        with mock.patch.object(preflight.os, 'name', 'nt'), \
                mock.patch.object(preflight, '_release_version_dirs', return_value=[]), \
                mock.patch.object(preflight, '_selenium_manager_major', return_value=153):
            self.assertEqual(browser_major('chrome', r'C:\...\chrome.exe'), 153)

    def test_非Windows走version参数(self):
        with mock.patch.object(preflight.os, 'name', 'posix'), \
                mock.patch.object(preflight, '_selenium_manager_major', return_value=None), \
                mock.patch.object(preflight, '_run_version',
                                  return_value='Google Chrome 150.0.1.2'):
            self.assertEqual(browser_major('chrome', '/usr/bin/google-chrome'), 150)

    def test_都探不到时返回None(self):
        """探不到必须是 None 而不是编一个值出来 —— 后续比对会据此降级为警告。"""
        with mock.patch.object(preflight.os, 'name', 'posix'), \
                mock.patch.object(preflight, '_selenium_manager_major', return_value=None), \
                mock.patch.object(preflight, '_run_version', return_value=''):
            self.assertIsNone(browser_major('chrome', '/usr/bin/google-chrome'))

    def test_结果会被缓存(self):
        with mock.patch.object(preflight.os, 'name', 'nt'), \
                mock.patch.object(preflight, '_release_version_dirs',
                                  return_value=[154]) as probe:
            browser_major('chrome', r'C:\...\chrome.exe')
            browser_major('chrome', r'C:\...\chrome.exe')
        self.assertEqual(probe.call_count, 1, '同一次体检里不该反复探测')


class TestReleaseVersionDirs(unittest.TestCase):
    """Windows 上靠版本号子目录拿 Chrome 版本 —— 这是唯一不启动浏览器的手段。"""

    def test_只认四段版本号目录(self):
        entries = ['154.0.8037.57', '152.0.1.1', 'Installer', '154.0.8037.57.backup', 'abc']
        with mock.patch.object(preflight.os, 'listdir', return_value=entries), \
                mock.patch.object(preflight.os.path, 'isdir', return_value=True):
            majors = preflight._release_version_dirs(r'C:\...\Application')
        self.assertEqual(sorted(majors), [152, 154])

    def test_目录读不到时返回空(self):
        with mock.patch.object(preflight.os, 'listdir', side_effect=OSError('拒绝访问')):
            self.assertEqual(preflight._release_version_dirs(r'C:\...'), [])


class TestSeleniumManagerCache(unittest.TestCase):
    """从 Selenium Manager 的缓存里顺带取浏览器版本；拿不到不能炸。"""

    _CACHE = ('{"drivers": [{"driver_name": "chromedriver", '
              '"major_browser_version": "154"}]}')

    def _with_cache(self, content):
        def fake_open(path, *args, **kwargs):
            import io
            return io.StringIO(content)
        return mock.patch.object(preflight.os.path, 'isfile', return_value=True), \
            mock.patch('builtins.open', fake_open)

    def test_能读出主版本(self):
        isfile, opener = self._with_cache(self._CACHE)
        with isfile, opener:
            self.assertEqual(preflight._selenium_manager_major('chromedriver'), 154)

    def test_没有缓存文件时返回None(self):
        with mock.patch.object(preflight.os.path, 'isfile', return_value=False):
            self.assertIsNone(preflight._selenium_manager_major('chromedriver'))

    def test_文件内容坏了不抛异常(self):
        isfile, opener = self._with_cache('{不是合法 json')
        with isfile, opener:
            self.assertIsNone(preflight._selenium_manager_major('chromedriver'))

    def test_没有对应驱动时返回None(self):
        isfile, opener = self._with_cache('{"drivers": []}')
        with isfile, opener:
            self.assertIsNone(preflight._selenium_manager_major('chromedriver'))


class TestCheckDriver(unittest.TestCase):
    """★ 驱动版本比对 —— 本模块存在的理由，也是最重要的一组断言。"""

    def test_PATH上没有驱动算正常(self):
        """没有 driver 是好事：Selenium Manager 会下匹配的那一个。"""
        with mock.patch.object(preflight, '_find_on_path', return_value=None):
            finding = check_driver('chrome')
        self.assertEqual(finding.level, LEVEL_OK)
        self.assertIn('Selenium Manager', finding.detail)

    def test_版本不匹配时判为致命并给出具体文件(self):
        with mock.patch.object(preflight, '_find_on_path',
                               return_value=r'C:\Python311\chromedriver.exe'), \
                mock.patch.object(preflight, '_run_version',
                                  return_value='ChromeDriver 114.0.5735.90 (refs)'), \
                mock.patch.object(preflight, 'browser_major', return_value=154):
            finding = check_driver('chrome', r'C:\...\chrome.exe')
        self.assertEqual(finding.level, LEVEL_ERROR)
        self.assertIn('114', finding.detail)
        self.assertIn('154', finding.detail)
        # 修复提示必须点到具体文件，否则等于没说
        self.assertIn('chromedriver.exe', finding.hint)

    def test_版本一致时算正常(self):
        with mock.patch.object(preflight, '_find_on_path',
                               return_value='/usr/local/bin/chromedriver'), \
                mock.patch.object(preflight, '_run_version',
                                  return_value='ChromeDriver 154.0.8037.92'), \
                mock.patch.object(preflight, 'browser_major', return_value=154):
            finding = check_driver('chrome', '/usr/bin/google-chrome')
        self.assertEqual(finding.level, LEVEL_OK)
        self.assertIn('154', finding.detail)

    def test_读不出驱动版本时降级为警告(self):
        """读不出就只是"不确定"，不能因此拦住整批用例。"""
        with mock.patch.object(preflight, '_find_on_path', return_value='/x/chromedriver'), \
                mock.patch.object(preflight, '_run_version', return_value=''):
            finding = check_driver('chrome', '/usr/bin/google-chrome')
        self.assertEqual(finding.level, LEVEL_WARN)
        self.assertIn('/x/chromedriver', finding.detail)

    def test_浏览器版本未知时降级为警告(self):
        with mock.patch.object(preflight, '_find_on_path', return_value='/x/chromedriver'), \
                mock.patch.object(preflight, '_run_version',
                                  return_value='ChromeDriver 114.0.1.1'), \
                mock.patch.object(preflight, 'browser_major', return_value=None):
            finding = check_driver('chrome', '/usr/bin/google-chrome')
        self.assertEqual(finding.level, LEVEL_WARN)
        self.assertIn('114', finding.detail)

    def test_按浏览器类型找对应的驱动(self):
        """firefox 要查 geckodriver，不能去查 chromedriver。"""
        seen = []

        def spy(name):
            seen.append(name)
            return None

        with mock.patch.object(preflight, '_find_on_path', side_effect=spy):
            check_driver('firefox')
            check_driver('edge')
        self.assertEqual(seen, ['geckodriver', 'msedgedriver'])


class TestCheckDirs(unittest.TestCase):
    """⑤ 目录可写性 —— 这一组可以走真实代码，因为临时目录是可控的。"""

    def test_临时工程根下应当全部可写(self):
        with patch_dirs():
            finding = check_dirs()
        self.assertEqual(finding.level, LEVEL_OK)

    def test_不可写的目录被识别出来(self):
        with patch_dirs():
            with mock.patch.object(preflight.os, 'access', return_value=False):
                finding = check_dirs()
        self.assertEqual(finding.level, LEVEL_ERROR)
        self.assertIn('不可写', finding.detail)
        self.assertTrue(finding.hint)

    def test_UI_LOG_DIR会顶替日志目录(self):
        """日志根目录可以被 UI_LOG_DIR 改掉，体检必须看同一个来源。

        这里刻意用一个不存在的盘符路径：check_dirs 会一路向上找到 'C:\\'，
        最终报出它不可写 —— 关键是"查的是 UI_LOG_DIR 指定的那棵树"，
        而不是工程自带的 Logs/。
        """
        with patch_dirs(), \
                mock.patch.dict(os.environ, {'UI_LOG_DIR': 'C:\\no\\such\\dir'}):
            with mock.patch.object(preflight.os, 'access', return_value=False):
                finding = check_dirs()
        self.assertEqual(finding.level, LEVEL_ERROR)
        self.assertIn('日志 Logs', finding.detail)
        self.assertIn('C:\\', finding.detail)


class TestCollectAndVerdict(unittest.TestCase):
    """汇总：等级判定与"要不要中止"的规则。"""

    def test_全部正常时无致命项(self):
        findings = [Finding('A', LEVEL_OK, 'ok'), Finding('B', LEVEL_WARN, 'warn')]
        self.assertFalse(has_error(findings))
        self.assertEqual(worst_level(findings), LEVEL_WARN)

    def test_有错误项时判定为有致命问题(self):
        findings = [Finding('A', LEVEL_OK, 'ok'), Finding('B', LEVEL_ERROR, 'bad')]
        self.assertTrue(has_error(findings))
        self.assertEqual(worst_level(findings), LEVEL_ERROR)

    def test_空列表视为正常(self):
        self.assertFalse(has_error([]))
        self.assertEqual(worst_level([]), LEVEL_OK)

    def test_collect会带上警告项说明浏览器缺失(self):
        """浏览器没找到时不能只留一行空结论，要说明"驱动比对被跳过了"。"""
        with mock.patch.object(preflight, 'check_python',
                               return_value=Finding('Python', LEVEL_OK, 'ok')), \
                mock.patch.object(preflight, 'check_selenium',
                                  return_value=Finding('selenium', LEVEL_OK, 'ok')), \
                mock.patch.object(preflight, 'find_browser', return_value=None):
            findings = collect(check_dirs_too=False)
        names = [item.name for item in findings]
        self.assertEqual(names, ['Python', 'selenium', '浏览器', '驱动'])
        self.assertEqual(findings[-1].level, LEVEL_WARN)


class TestFormatReport(unittest.TestCase):
    """结论渲染：给人看的，措辞不能含糊。"""

    def setUp(self):
        self.findings = [
            Finding('Python', LEVEL_OK, '3.11.9'),
            Finding('驱动', LEVEL_WARN, '读不出驱动版本', hint='先删掉它'),
            Finding('浏览器', LEVEL_ERROR, '找不到 chrome', hint='装一个'),
        ]

    def test_全部列出(self):
        text = format_report(self.findings)
        for name in ('Python', '驱动', '浏览器'):
            self.assertIn(name, text)
        self.assertIn('修复：装一个', text)

    def test_只列问题时正常项被过滤(self):
        text = format_report(self.findings, only_problems=True)
        self.assertNotIn('Python', text)
        self.assertIn('浏览器', text)

    def test_全部正常时给出一句总结(self):
        text = format_report([Finding('Python', LEVEL_OK, '3.11.9')])
        self.assertIn('全部检查通过', text)


class TestCli(unittest.TestCase):
    """命令行入口：退出码必须与 runner 的环境异常码一致（2）。"""

    def test_无致命问题时返回0(self):
        with mock.patch.object(preflight, 'collect',
                               return_value=[Finding('Python', LEVEL_OK, 'ok')]), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main([]), 0)

    def test_有致命问题时返回2(self):
        with mock.patch.object(preflight, 'collect',
                               return_value=[Finding('浏览器', LEVEL_ERROR, '没有', '装')]), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main([]), 2)

    def test_quiet只显示问题(self):
        buffer = io.StringIO()
        with mock.patch.object(preflight, 'collect',
                               return_value=[Finding('Python', LEVEL_OK, '3.11.9')]), \
                contextlib.redirect_stdout(buffer):
            main(['--quiet'])
        self.assertNotIn('Python', buffer.getvalue())


class TestRunnerIntegration(unittest.TestCase):
    """接入 runner 之后：致命项 -> exit 2，且绝不打开浏览器。

    这里跑的是真沙盒（临时用例包 + 临时配置），验证的是"闸门真的挡在开浏览器之前"，
    所以比打桩测 collect() 更有意义 —— 一旦有人在 runner 里把顺序改错，
    这两条会立刻红。
    """

    def setUp(self):
        self._stack = contextlib.ExitStack()
        self.addCleanup(self._stack.close)

    def _sandbox(self, enable_preflight=True):
        """建一个沙盒工程并接好配置/目录隔离，返回用例目录。"""
        ini = (
            '[environment]\n'
            'url = http://test-env.local/sso-portal\n'
            'browser = chrome\n\n'
            '[ci]\n'
            'headless = false\n'
            'preflight = %s\n'
            'junit_xml = \n'
            % ('true' if enable_preflight else 'false')
        )
        root, cases_dir, pkg = make_sandbox(CASE_SOURCE_PASS, ini_text=ini)
        self._stack.enter_context(
            patch_config(ini_text=ini, ini_path=os.path.join(root, 'config.ini')))
        self._stack.enter_context(patch_dirs(root=root))
        return cases_dir

    @staticmethod
    def _quiet_run(**kwargs):
        """执行 runner.run 并同时吞掉 stdout 与 stderr。

        stderr 也要吞：HTML 报告器跑完会往 stderr 打一行 'Time Elapsed'，
        不拦的话单测输出里会混进几行莫名其妙的计时。
        """
        from Common import runner
        with contextlib.redirect_stdout(io.StringIO()), \
                contextlib.redirect_stderr(io.StringIO()):
            return runner.run(**kwargs)

    def test_自检不通过时中止且退出码为2(self):
        from Common import runner

        cases_dir = self._sandbox(enable_preflight=True)
        bad = Finding('驱动', LEVEL_ERROR, 'PATH 上的 chromedriver 是 114，浏览器是 154',
                      hint='删掉它')
        with mock.patch.object(runner.preflight, 'collect', return_value=[bad]), \
                mock.patch.object(runner.HTMLTestRunner, 'run') as html_run:
            summary = self._quiet_run(tests_dir=cases_dir, pattern='demo_test.py')

        self.assertEqual(summary['exit_code'], 2)
        self.assertEqual(summary['tests_run'], 0)
        self.assertIn('114', summary['reason'])
        # 最关键的一条：被自检拦下时不能有任何用例被执行
        html_run.assert_not_called()

    def test_自检关闭时不影响执行(self):
        from Common import runner

        cases_dir = self._sandbox(enable_preflight=False)
        with mock.patch.object(runner.preflight, 'collect') as collect_mock:
            summary = self._quiet_run(tests_dir=cases_dir, pattern='demo_test.py')

        self.assertEqual(summary['exit_code'], 0)
        self.assertEqual(summary['tests_run'], 2)
        collect_mock.assert_not_called()

    def test_自检正常时照常执行(self):
        """自检通过（只给正常项）时不能误伤，用例该跑还得跑。"""
        from Common import runner

        cases_dir = self._sandbox(enable_preflight=True)
        ok = [Finding('Python', LEVEL_OK, '3.11.9'), Finding('驱动', LEVEL_OK, '一致')]
        with mock.patch.object(runner.preflight, 'collect', return_value=ok):
            summary = self._quiet_run(tests_dir=cases_dir, pattern='demo_test.py')

        self.assertEqual(summary['exit_code'], 0)
        self.assertEqual(summary['tests_run'], 2)


if __name__ == '__main__':
    unittest.main(verbosity=2)
