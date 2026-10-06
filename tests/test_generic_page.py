# -*- coding: utf-8 -*-
"""
单元测试：跨系统通用能力（BasePage 第七节）+ GenericPage 系统适配层

验证目标：
    - 按文本定位/点击（含 JS 降级、找不到返回 None/False）
    - 按属性（placeholder）定位与输入
    - 表格行按单元格文本查找
    - 等待加载遮罩消失（存在/不存在/超时三态）
    - GenericPage.login 配置驱动的通用登录流程
全部不启动浏览器、不联网。
"""

import unittest
from unittest import mock

from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.common.by import By

from tests.helpers import FakeDriver, FakeElement, patch_config
from Common.basePage import BasePage
from PageObject.genericPage import GenericPage


class _PageEnv(unittest.TestCase):
    """隔离配置 + 禁用 sleep 的公共环境。"""

    def setUp(self):
        self._cfg = patch_config()
        self._cfg.__enter__()
        self._sleep = mock.patch.object(BasePage, 'my_sleep', return_value=None)
        self._sleep.start()

    def tearDown(self):
        self._sleep.stop()
        self._cfg.__exit__(None, None, None)


# ==========================================================================
# 一、按文本定位 / 点击
# ==========================================================================
class TestGetElementByText(_PageEnv):

    def test_按文本定位成功(self):
        driver = FakeDriver()
        page = BasePage(driver=driver, timeout=1)
        el = page.get_element_by_text('登录')
        self.assertIs(el, driver._element)
        self.assertEqual(driver.calls[0][0], 'find_element')
        self.assertEqual(driver.calls[0][1], By.XPATH)

    def test_找不到返回None不抛异常(self):
        # find_element 抛 NoSuchElement 时，WebDriverWait 会重试直到超时
        driver = FakeDriver(find_error=NoSuchElementException('no such'))
        page = BasePage(driver=driver, timeout=0.2)
        self.assertIsNone(page.get_element_by_text('不存在'))


class TestClickByText(_PageEnv):

    def test_点击成功返回True(self):
        page = BasePage(driver=FakeDriver(), timeout=1)
        self.assertTrue(page.click_by_text('确定'))

    def test_找不到返回False(self):
        page = BasePage(driver=FakeDriver(find_error=NoSuchElementException('no such')), timeout=0.2)
        self.assertFalse(page.click_by_text('不存在'))

    def test_原生点击失败降级JS(self):
        from selenium.common.exceptions import WebDriverException
        el = FakeElement(click_error=WebDriverException('被遮罩挡住'))
        page = BasePage(driver=FakeDriver(element=el), timeout=1)
        self.assertTrue(page.click_by_text('保存'))   # JS 兜底成功
        self.assertEqual(el.calls, ['click'])          # 原生点击确实尝试过


# ==========================================================================
# 二、按属性定位 / 按 placeholder 输入
# ==========================================================================
class TestTypeByPlaceholder(_PageEnv):

    def test_正常输入(self):
        el = FakeElement()
        page = BasePage(driver=FakeDriver(element=el), timeout=1)
        page.type_by_placeholder('请输入用户名', 'admin')
        self.assertIn('clear', el.calls)
        self.assertIn('send_keys', el.calls)
        self.assertIn('admin', el.sent)

    def test_找不到抛NoSuchElement(self):
        page = BasePage(driver=FakeDriver(find_error=NoSuchElementException('no such')), timeout=0.2)
        with self.assertRaises(NoSuchElementException):
            page.type_by_placeholder('不存在的框', 'x')


# ==========================================================================
# 三、表格行按单元格文本查找
# ==========================================================================
class TestFindRowByCell(_PageEnv):

    def test_找到匹配行(self):
        rows = [FakeElement(text='张三 13800000000'),
                FakeElement(text='李四 13900000000')]
        page = BasePage(driver=FakeDriver(elements=rows), timeout=1)
        # get_table_rows 走 driver.find_elements('xpath','//tr')
        row = page.find_row_by_cell_text('李四')
        self.assertEqual(row.text, rows[1].text)

    def test_无匹配返回None(self):
        rows = [FakeElement(text='张三')]
        page = BasePage(driver=FakeDriver(elements=rows), timeout=1)
        self.assertIsNone(page.find_row_by_cell_text('王五'))


# ==========================================================================
# 四、等待加载遮罩消失
# ==========================================================================
class TestWaitLoading(_PageEnv):

    def test_无遮罩直接返回True(self):
        page = BasePage(driver=FakeDriver(elements=[]), timeout=0.2)
        self.assertTrue(page.wait_loading_gone(timeout=0.2))

    def test_遮罩超时返回False不抛异常(self):
        # 一直有一个显示中的遮罩元素
        page = BasePage(driver=FakeDriver(elements=[FakeElement(displayed=True)]), timeout=0.2)
        self.assertFalse(page.wait_loading_gone(timeout=0.2, poll_frequency=0.05))


# ==========================================================================
# 五、GenericPage 通用登录（配置驱动）
# ==========================================================================
class TestGenericLogin(_PageEnv):

    def test_login_按配置输入并点击(self):
        el = FakeElement()
        driver = FakeDriver(element=el)
        gp = GenericPage(driver=driver, timeout=1)
        # 给 success_text 一个能定位到的元素，避免等待
        gp.login('admin', '123456')
        # 两个输入框 + 登录按钮定位 + success_text 定位，至少发生多次查找
        self.assertTrue(len(driver.calls) >= 3)
        self.assertIn('admin', el.sent)
        self.assertIn('123456', el.sent)


# ==========================================================================
# 二、配置了「成功标识」时的等待分支
#   这是接入新系统时最常用的配置（[system] success_text），
#   但之前一直没有测试覆盖，导致里面一个拼写错误潜伏了很久。
# ==========================================================================
class TestGenericLoginSuccessText(unittest.TestCase):
    """success_text 非空 -> 走「等成功标识出现」而不是「等加载遮罩消失」。"""

    INI = """\
[ci]
element_timeout = 9

[system]
username_placeholder = 请输入用户名
password_placeholder = 请输入密码
login_button_text = 登录
success_text = 退 出
"""

    def test_配置了成功标识时按其等待且不报错(self):
        """★ 回归保护：本分支曾把 Config.get_int 误写成 Config.getint，
        执行到这一行直接抛 AttributeError，而用例只在这条配置非空时才走到。

        修法已落到 PageObject/genericPage.py；本用例负责不让它再溜回来。
        """
        el = FakeElement()
        driver = FakeDriver(element=el)
        with patch_config(ini_text=self.INI):
            gp = GenericPage(driver=driver, timeout=1)
            with mock.patch.object(BasePage, 'my_sleep', return_value=None):
                gp.login('admin', '123456')      # 不抛异常即通过
        self.assertIn('admin', el.sent)

    def test_Config的整数读取方法名是get_int(self):
        """明确钉住方法名：Config 没有 getint()，写错了只在该分支才炸。"""
        from Common.config import Config

        self.assertTrue(hasattr(Config, 'get_int'), '整数读取方法应为 get_int')
        self.assertFalse(
            hasattr(Config, 'getint'),
            'Config.getint 不存在；请用 get_int（若要保留别名需显式添加）',
        )


if __name__ == '__main__':
    unittest.main()
