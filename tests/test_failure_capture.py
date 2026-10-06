# -*- coding: utf-8 -*-
"""
==========================================================================
单元测试：Common/failureCapture.py + Common/driverRegistry.py（失败自动取证）
==========================================================================

失败取证的**核心价值**是"跑挂了自动留下现场"，所以测试的重心不是
"能不能截出图"，而是**它绝不把测试本身搞坏**：
用例失败了，取证再出什么问题，都不能让失败信息丢失、也不能改变测试结果。

覆盖：
    1. 文件名安全化（用例 id 里的点号等非法字符）
    2. 开关与目录解析（[ci] artifacts / artifacts_dir）
    3. 正常取证：截图 + 页面源码都落盘
    4. 取不到浏览器时安静跳过（用例在开浏览器之前就挂了，属正常情况）
    5. 截图失败、读源码失败、目录不可写 —— 一律不抛异常
    6. 浏览器实例登记处的登记 / 注销 / 取用 / 清空

产出全部重定向到临时目录，不写工程的 Report/。
==========================================================================
"""

import os
import unittest

from Common import driverRegistry
from Common.failureCapture import MAX_SOURCE_CHARS, capture, resolve_dir, safe_name
from tests.helpers import FakeDriver, patch_config, patch_dirs


class TestSafeName(unittest.TestCase):
    """用例 id -> 合法文件名。"""

    def test_点号换成下划线(self):
        self.assertEqual(
            safe_name('TestSuites.testLogin.TestLogin.test_1login'),
            'TestSuites_testLogin_TestLogin_test_1login')

    def test_非法字符被替换(self):
        """Windows 上这些字符不能出现在文件名里，必须提前换掉。"""
        cleaned = safe_name('a<b>c:d"e/f\\g|h?i*j')
        for char in '<>:"/\\|?*':
            self.assertNotIn(char, cleaned)

    def test_空白字符被替换(self):
        self.assertNotIn(' ', safe_name('setUpClass (TestSuites.testLogin.TestLogin)'))


class TestResolveDir(unittest.TestCase):
    """取证目录与开关。"""

    def test_默认按日期分子目录(self):
        with patch_config(), patch_dirs() as root:
            folder, enabled = resolve_dir()
            self.assertTrue(enabled)
            self.assertTrue(folder.startswith(root), '必须落在被重定向的临时根目录下')
            self.assertRegex(os.path.basename(folder), r'^\d{4}-\d{2}-\d{2}$')

    def test_可以关闭取证(self):
        ini = '[ci]\nartifacts = false\n'
        with patch_config(ini_text=ini), patch_dirs():
            folder, enabled = resolve_dir()
            self.assertFalse(enabled, '[ci] artifacts = false 时应关闭')
            self.assertIsNone(folder)

    def test_可以自定义目录(self):
        ini = '[ci]\nartifacts_dir = Report/my-artifacts\n'
        with patch_config(ini_text=ini), patch_dirs() as root:
            folder, enabled = resolve_dir()
            self.assertTrue(enabled)
            expected = os.path.normpath(os.path.join(root, 'Report', 'my-artifacts'))
            self.assertTrue(folder.startswith(expected),
                            '取证目录应落在配置指定的位置，实际=%s' % folder)

    def test_绝对路径不再拼工程根(self):
        """配置里写绝对路径时不能被二次拼接 —— 否则路径会变成一坨。"""
        import tempfile
        absolute = tempfile.mkdtemp(prefix='ut_artifacts_')
        self.addCleanup(lambda: __import__('shutil').rmtree(absolute, ignore_errors=True))
        with patch_config(), patch_dirs():
            folder, enabled = resolve_dir(out_dir=absolute)
            self.assertTrue(enabled)
            self.assertTrue(folder.startswith(absolute))


class TestCapture(unittest.TestCase):
    """取证主体。"""

    def test_正常取证会同时留下截图与源码(self):
        driver = FakeDriver(page_source='<html><body>失败现场</body></html>')
        with patch_config(), patch_dirs() as root:
            info = capture('TestSuites.testLogin.TestLogin.test_1login', driver=driver)

            self.assertTrue(info['enabled'])
            self.assertIsNone(info['error'], '正常路径不该有错误：%s' % info['error'])
            self.assertTrue(os.path.isfile(info['screenshot']), '截图文件应存在')
            self.assertTrue(os.path.isfile(info['source']), '页面源码文件应存在')
            with open(info['source'], encoding='utf-8') as fp:
                self.assertIn('失败现场', fp.read())
            # 落盘位置必须在被重定向的临时目录里，且不能落到工程的 img/ 下
            self.assertTrue(info['screenshot'].startswith(root))
            self.assertNotIn(os.path.join('img', ''), info['screenshot'],
                             '失败取证写的是 Report/artifacts/，不该混进 img/')
            self.assertIn('test_1login', os.path.basename(info['screenshot']))

    def test_没有浏览器时安静跳过(self):
        """用例可能在打开浏览器之前就失败了（比如配置读不到），这不算错误。"""
        driverRegistry.clear()
        with patch_config(), patch_dirs():
            info = capture('TestSuites.xxx.test_a')
            self.assertTrue(info['enabled'])
            self.assertIsNone(info['screenshot'])
            self.assertIsNone(info['source'])
            self.assertIn('未找到可用的浏览器', info['error'])

    def test_截图失败也不抛异常(self):
        class BrokenDriver(FakeDriver):
            def save_screenshot(self, path):
                raise RuntimeError('会话已失效')

        driver = BrokenDriver()
        with patch_config(), patch_dirs():
            info = capture('TestSuites.xxx.test_a', driver=driver)
            self.assertIsNone(info['screenshot'])
            self.assertIsNotNone(info['source'], '截图失败不应影响源码保存')
            self.assertIn('截图失败', info['error'])

    def test_读源码失败也不抛异常(self):
        driver = FakeDriver(source_error=RuntimeError('页面已关闭'))
        with patch_config(), patch_dirs():
            info = capture('TestSuites.xxx.test_a', driver=driver)
            self.assertIsNotNone(info['screenshot'])
            self.assertIsNone(info['source'])
            self.assertIn('读取页面源码失败', info['error'])

    def test_两项都失败时保留两个原因(self):
        """错误信息不能被后一个盖掉前一个 —— 排查时两条线索都要有。"""
        class BrokenDriver(FakeDriver):
            def save_screenshot(self, path):
                raise RuntimeError('截图炸了')

        driver = BrokenDriver(source_error=RuntimeError('源码也炸了'))
        with patch_config(), patch_dirs():
            info = capture('TestSuites.xxx.test_a', driver=driver)
            self.assertIn('截图失败', info['error'])
            self.assertIn('读取页面源码失败', info['error'])

    def test_超长源码会截断(self):
        driver = FakeDriver(page_source='x' * (MAX_SOURCE_CHARS + 1000))
        with patch_config(), patch_dirs():
            info = capture('TestSuites.xxx.test_a', driver=driver)
            with open(info['source'], encoding='utf-8') as fp:
                content = fp.read()
            self.assertLessEqual(len(content), MAX_SOURCE_CHARS + 100)
            self.assertIn('已截断', content)

    def test_关闭取证时不产生任何文件(self):
        ini = '[ci]\nartifacts = false\n'
        driver = FakeDriver()
        with patch_config(ini_text=ini), patch_dirs():
            info = capture('TestSuites.xxx.test_a', driver=driver)
            self.assertFalse(info['enabled'])
            self.assertIsNone(info['screenshot'])
            self.assertEqual(driver.screenshots, [], '关闭后不该再调用截图')

    def test_同一用例多次取证不互相覆盖(self):
        """同一条用例重跑时，上一轮的现场不能被这一轮冲掉。"""
        driver = FakeDriver()
        with patch_config(), patch_dirs():
            first = capture('TestSuites.xxx.test_a', driver=driver, tag='failure')
            second = capture('TestSuites.xxx.test_a', driver=driver, tag='failure')
            self.assertNotEqual(first['screenshot'], second['screenshot'])
            self.assertTrue(os.path.isfile(first['screenshot']))
            self.assertTrue(os.path.isfile(second['screenshot']))


class TestDriverRegistry(unittest.TestCase):
    """浏览器实例登记处。"""

    def setUp(self):
        driverRegistry.clear()

    def tearDown(self):
        driverRegistry.clear()

    def test_登记后能取到(self):
        driver = FakeDriver()
        driverRegistry.register(driver)
        self.assertIs(driverRegistry.get_active(), driver)

    def test_取最近登记的那一个(self):
        first, second = FakeDriver(), FakeDriver()
        driverRegistry.register(first)
        driverRegistry.register(second)
        self.assertIs(driverRegistry.get_active(), second)

    def test_重复登记同一对象只保留一份(self):
        driver = FakeDriver()
        driverRegistry.register(driver)
        driverRegistry.register(driver)
        self.assertEqual(driverRegistry.count(), 1)

    def test_注销后取不到(self):
        driver = FakeDriver()
        driverRegistry.register(driver)
        driverRegistry.unregister(driver)
        self.assertIsNone(driverRegistry.get_active())

    def test_登记空对象是安全的(self):
        self.assertIsNone(driverRegistry.register(None))
        self.assertEqual(driverRegistry.count(), 0)

    def test_关闭浏览器后会注销(self):
        """这条测的是与 BasePage 的联动：dr_quit 后不该再被取证模块取到。

        否则取证时会去操作一个已关闭的浏览器，抛出的
        InvalidSessionIdException 会把真正的失败原因盖掉。
        """
        import Common.basePage as base_page

        with patch_config():
            page = base_page.BasePage(driver=FakeDriver())
            driverRegistry.register(page.driver)
            self.assertIsNotNone(driverRegistry.get_active())

            page.dr_quit()
            self.assertIsNone(driverRegistry.get_active(),
                              'dr_quit() 之后必须注销，避免取证操作已关闭的浏览器')


if __name__ == '__main__':
    unittest.main(verbosity=2)
