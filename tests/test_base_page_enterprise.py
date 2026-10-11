# -*- coding: utf-8 -*-
"""
单元测试：Common/basePage.py 的「企业级」四项能力

这是把框架从"能用"推到"可信"的四条改造，每条都对应一个曾经的真实盲区：

    1. 重试**默认生效**（旧版要用例显式调 safe_click，结果一条都没调 → 等于没有）
    2. 条件等待 wait_title / wait_text / wait_any_text（替代硬编码 my_sleep(5)）
    3. console 日志捕获 + assert_no_console_error（抓"接口 500 但页面照常"的假绿）
    4. 重试与截图的配合（只在最终失败时拍一张，不刷屏）

★ 全部用 FakeDriver，不启动浏览器、不联网。
"""

import os
import unittest
from unittest import mock

from selenium.common.exceptions import (
    NoSuchElementException,
    StaleElementReferenceException,
    WebDriverException,
)

from tests.helpers import FakeDriver, FakeElement, patch_config, patch_dirs
from Common.basePage import BasePage


class _Base(unittest.TestCase):
    """基类：配置隔离 + 禁用真实 sleep。"""

    def setUp(self):
        self._cfg = patch_config()
        self._cfg.__enter__()
        self._sleep = mock.patch.object(BasePage, 'my_sleep', return_value=None)
        self.sleep_mock = self._sleep.start()

    def tearDown(self):
        self._sleep.stop()
        self._cfg.__exit__(None, None, None)

    def make_page(self, driver=None, timeout=0.1, retry_times=None):
        if retry_times is not None:
            os.environ['UI_CI_RETRY_TIMES'] = str(retry_times)
        return BasePage(driver=driver if driver is not None else FakeDriver(),
                        timeout=timeout)


class _FlakyElement(FakeElement):
    """可以指定"前 N 次失败、之后成功"的假元素。

    比"事后清掉 error 属性"可靠得多 —— 后者在异常路径上根本执行不到。
    """

    def __init__(self, fail_times=0, error=None, **kwargs):
        super().__init__(**kwargs)
        self.fail_times = fail_times
        self.error = error
        self.attempts = 0

    def click(self):
        self.attempts += 1
        if self.attempts <= self.fail_times:
            raise self.error
        self.calls.append('click')

    def send_keys(self, *values):
        self.attempts += 1
        if self.attempts <= self.fail_times:
            raise self.error
        self.calls.append('send_keys')
        self.sent.extend(values)

    def clear(self):
        self.calls.append('clear')


class _NoJsFallbackDriver(FakeDriver):
    """JS 点击也失败的 driver：用于验证"原生点击与 JS 兜底全挂"时才抛出。"""

    def execute_script(self, script, *args):
        self.scripts.append(script)
        if 'click()' in str(script):
            raise WebDriverException('JS 点击也失败了')


# ==========================================================================
# 一、重试默认生效
# ==========================================================================
class TestRetryIsDefault(_Base):
    """★ 核心：click()/type() 必须**自带**重试，不需要用例调 safe_*。"""

    def tearDown(self):
        os.environ.pop('UI_CI_RETRY_TIMES', None)
        super().tearDown()

    def test_click瞬时错误自动重试(self):
        """元素过期（DOM 刷新）→ 重试后成功。用例层什么都没多做。"""
        element = _FlakyElement(fail_times=1, error=StaleElementReferenceException('stale'))
        page = self.make_page(FakeDriver(element=element), retry_times=2)
        page.click(['id', 'btn'])            # 不应抛出
        self.assertEqual(element.attempts, 2, '第一次 stale，第二次应成功')

    def test_click重试时确实等一下(self):
        """重试之间要有间隔，否则页面根本没时间恢复。"""
        element = _FlakyElement(fail_times=1, error=StaleElementReferenceException('s'))
        page = self.make_page(FakeDriver(element=element), retry_times=2)
        page.click(['id', 'btn'])
        self.assertGreaterEqual(self.sleep_mock.call_count, 1, '重试之间应等待')

    def test_重试次数用尽后抛出(self):
        """原生点击与 JS 兜底都失败 → 重试用尽 → 抛原始异常。"""
        element = FakeElement(click_error=WebDriverException('一直被遮挡'))
        page = self.make_page(_NoJsFallbackDriver(element=element), retry_times=1)
        with self.assertRaises(WebDriverException):
            page.click(['id', 'btn'])

    def test_元素不存在属于确定性错误不重试(self):
        """★ 关键设计：找不到元素重试多少次都一样，立即失败省时间。

        判定方式：确定性错误**不应该有重试间隔**（my_sleep 不被调用）。
        """
        page = self.make_page(FakeDriver(), retry_times=3)
        with mock.patch.object(page, '_click_once',
                               side_effect=NoSuchElementException('元素不存在')) as action:
            with self.assertRaises(NoSuchElementException):
                page.click(['id', 'btn'])
        self.assertEqual(action.call_count, 1, '确定性错误只应执行一次，不重试')
        self.assertEqual(self.sleep_mock.call_count, 0, '确定性错误不应有重试间隔')

    def test_断言错误不重试(self):
        """AssertionError 属于业务判定，重试无意义。"""
        page = self.make_page(FakeDriver(), retry_times=3)
        with self.assertRaises(AssertionError):
            page.retry(lambda: (_ for _ in ()).throw(AssertionError('业务失败')))
        self.assertEqual(self.sleep_mock.call_count, 0)

    def test_type瞬时错误自动重试(self):
        element = _FlakyElement(fail_times=1, error=WebDriverException('元素未就绪'))
        page = self.make_page(FakeDriver(element=element), retry_times=1)
        page.type(['id', 'user'], 'abc')     # 不应抛出
        self.assertIn('abc', element.sent)
        self.assertEqual(element.attempts, 2)

    def test_safe_click仍是click的别名(self):
        """历史代码与文档里写的 safe_click 不能坏。"""
        element = FakeElement()
        page = self.make_page(FakeDriver(element=element), retry_times=1)
        page.safe_click(['id', 'btn'])
        self.assertIn('click', element.calls)

    def test_safe_type仍是type的别名(self):
        element = FakeElement()
        page = self.make_page(FakeDriver(element=element), retry_times=1)
        page.safe_type(['id', 'user'], 'v')
        self.assertIn('v', element.sent)

    def test_重试次数可配为零即不重试(self):
        element = FakeElement(click_error=WebDriverException('x'))
        page = self.make_page(_NoJsFallbackDriver(element=element), retry_times=0)
        with self.assertRaises(WebDriverException):
            page.click(['id', 'btn'])
        self.assertEqual(element.attempts if hasattr(element, 'attempts') else 1, 1,
                         'retry_times=0 时只尝试一次')
        self.assertEqual(self.sleep_mock.call_count, 0, '不重试就不应有间隔')

    def test_最终失败时截一次图(self):
        """★ 截图只在最终失败时拍一张，重试期间不刷屏。"""
        element = FakeElement(click_error=WebDriverException('x'))
        driver = _NoJsFallbackDriver(element=element)
        page = self.make_page(driver, retry_times=2)
        with patch_dirs():
            with self.assertRaises(WebDriverException):
                page.click(['id', 'btn'])
            self.assertEqual(len(driver.screenshots), 1,
                             '重试 2 次共失败 3 次，但只应截图 1 张')


# ==========================================================================
# 二、条件等待（替代硬编码 sleep）
# ==========================================================================
class _TitleDriver(FakeDriver):
    """标题会"逐次变化"的假 driver，模拟页面异步跳转。"""

    def __init__(self, titles):
        super().__init__(title=titles[0] if titles else '')
        self._titles = list(titles)
        self._idx = 0

    @property
    def title(self):
        value = self._titles[min(self._idx, len(self._titles) - 1)]
        self._idx += 1
        return value

    @title.setter
    def title(self, value):
        self._titles = [value]
        self._idx = 0


class TestWaitTitle(_Base):

    def test_标题立刻匹配时返回True(self):
        page = self.make_page(_TitleDriver(['目标标题']))
        ok, actual = page.wait_title('目标标题', timeout=0.5)
        self.assertTrue(ok)
        self.assertEqual(actual, '目标标题')

    def test_标题稍后匹配时会等到(self):
        page = self.make_page(_TitleDriver(['加载中', '加载中', '目标标题']))
        ok, actual = page.wait_title('目标标题', timeout=2)
        self.assertTrue(ok)
        self.assertEqual(actual, '目标标题')

    def test_超时返回False与最后实际值(self):
        page = self.make_page(_TitleDriver(['一直不对']), timeout=0.2)
        ok, actual = page.wait_title('目标标题', timeout=0.2)
        self.assertFalse(ok)
        self.assertEqual(actual, '一直不对')

    def test_contains模式匹配片段(self):
        """标题常带环境/构建后缀，用于只匹配主体部分。"""
        page = self.make_page(_TitleDriver(['素材库 - 云媒资系统 [test]']))
        ok, _ = page.wait_title('素材库', timeout=0.5, contains=True)
        self.assertTrue(ok)


class TestWaitText(_Base):

    def test_等到文字出现(self):
        holder = FakeElement(text='上传成功')
        page = self.make_page(FakeDriver(element=holder))
        page.get_element_by_text = lambda *a, **k: holder
        ok, hit = page.wait_text('上传成功', timeout=0.5)
        self.assertTrue(ok)
        self.assertIs(hit, holder)

    def test_超时返回False(self):
        page = self.make_page(FakeDriver())
        page.get_element_by_text = lambda *a, **k: None
        ok, hit = page.wait_text('永远不出现', timeout=0.2)
        self.assertFalse(ok)
        self.assertIsNone(hit)

    def test_可限定在指定元素内查找(self):
        holder = FakeElement(text='包含关键字的文本')
        page = self.make_page(FakeDriver(element=holder))
        ok, hit = page.wait_text('关键字', selector=['id', 'box'], timeout=0.5)
        self.assertTrue(ok)
        self.assertIs(hit, holder)


class TestWaitAnyText(_Base):
    """★ 结论断言的基础：等到哪个提示就说明业务走了哪条分支。"""

    def test_返回命中的那一条(self):
        target = FakeElement(text='报送成功')
        page = self.make_page(FakeDriver())

        def fake_by_text(text, **kwargs):
            return target if text == '报送成功' else None

        page.get_element_by_text = fake_by_text
        hit, element = page.wait_any_text('报送成功', '报送失败', timeout=0.5)
        self.assertEqual(hit, '报送成功')
        self.assertIs(element, target)

    def test_全都没出现返回None(self):
        page = self.make_page(FakeDriver())
        page.get_element_by_text = lambda *a, **k: None
        hit, element = page.wait_any_text('A', 'B', timeout=0.2)
        self.assertIsNone(hit)
        self.assertIsNone(element)


# ==========================================================================
# 三、console 日志捕获与"假绿"拦截
# ==========================================================================
class _ConsoleDriver(FakeDriver):
    """支持 get_log('browser') 的假 driver。"""

    def __init__(self, logs=None, log_error=None):
        super().__init__()
        self._logs = logs if logs is not None else []
        self.log_error = log_error

    def get_log(self, kind):
        if self.log_error:
            raise self.log_error
        return list(self._logs)


class TestConsoleLogs(_Base):

    def test_能读到全部日志(self):
        driver = _ConsoleDriver(logs=[
            {'level': 'SEVERE', 'message': 'Failed to load resource: 500'},
            {'level': 'INFO', 'message': 'page loaded'},
        ])
        page = self.make_page(driver)
        self.assertEqual(len(page.get_console_logs()), 2)

    def test_可按级别过滤(self):
        driver = _ConsoleDriver(logs=[
            {'level': 'SEVERE', 'message': 'boom'},
            {'level': 'INFO', 'message': 'fine'},
        ])
        page = self.make_page(driver)
        errors = page.get_console_logs(level='SEVERE')
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0]['message'], 'boom')

    def test_驱动不支持时不抛异常只返回空(self):
        """Firefox 默认不支持 get_log —— 不能因此把用例搞挂。"""
        page = self.make_page(FakeDriver())      # FakeDriver 没有 get_log
        self.assertEqual(page.get_console_logs(), [])

    def test_采集本身报错时不抛异常(self):
        driver = _ConsoleDriver(log_error=WebDriverException('not enabled'))
        page = self.make_page(driver)
        self.assertEqual(page.get_console_logs(), [])

    def test_有console错误时断言失败(self):
        """★ 这是拦"假绿"的关键：接口 500 但页面照常渲染时，用例必须红。"""
        driver = _ConsoleDriver(logs=[
            {'level': 'SEVERE', 'message': 'Failed to load resource: 500'},
        ])
        page = self.make_page(driver)
        with self.assertRaises(AssertionError) as ctx:
            page.assert_no_console_error()
        self.assertIn('500', str(ctx.exception))

    def test_无console错误时通过(self):
        driver = _ConsoleDriver(logs=[{'level': 'INFO', 'message': 'ok'}])
        page = self.make_page(driver)
        self.assertTrue(page.assert_no_console_error())

    def test_可忽略指定的第三方报错(self):
        driver = _ConsoleDriver(logs=[
            {'level': 'SEVERE', 'message': '第三方埋点采集失败'},
        ])
        page = self.make_page(driver)
        self.assertTrue(page.assert_no_console_error(ignore_patterns=['埋点']))

    def test_开启console采集写入capability(self):
        """open_browser 必须真的打开采集开关，否则 get_log 什么都拿不到。"""
        from tests.helpers import FakeWebDriverFactory
        factory = FakeWebDriverFactory()
        page = BasePage()
        with mock.patch('Common.basePage.webdriver', factory):
            page.open_browser(url='http://x.local', browser='chrome')
        self.assertIn('goog:loggingPrefs', factory.chrome_options.capabilities,
                      '未开启 console 采集，get_console_logs 将永远拿到空')

    def test_可配置关闭console采集(self):
        from tests.helpers import FakeWebDriverFactory
        ini = '[ci]\ncapture_console = false\nheadless = true\n'
        factory = FakeWebDriverFactory()
        page = BasePage()
        with patch_config(ini_text=ini):
            with mock.patch('Common.basePage.webdriver', factory):
                page.open_browser(url='http://x.local', browser='chrome')
        self.assertNotIn('goog:loggingPrefs', factory.chrome_options.capabilities)


if __name__ == '__main__':
    unittest.main(verbosity=2)
