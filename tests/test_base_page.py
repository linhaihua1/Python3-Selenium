# -*- coding: utf-8 -*-
"""
单元测试：Common/basePage.py（框架地基）

这是整个工程最核心、也最容易出问题的一层 —— 所有 Selenium 调用都经它封装。
因此这里用 FakeDriver 全面替换真实浏览器，逐条验证：

    - 元素定位参数的解析（非法参数的容错）
    - 显式等待 / 快速通道 / 超时返回 None 三种模式
    - 点击的「原生失败 -> JS 兜底」降级链路
    - 窗口与 iframe 切换
    - 文件上传的前置校验（文件不存在必须报错，不能"假成功"）
    - open_browser 的各分支（无头参数、浏览器类型、binary、无地址保护）

★ 全部测试不启动浏览器、不联网，毫秒级完成。
"""

import os
import shutil
import tempfile
import unittest
from unittest import mock

from selenium.common.exceptions import (
    NoSuchElementException,
    TimeoutException,
    WebDriverException,
)
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

from tests.helpers import (
    FakeDriver,
    FakeElement,
    FakeWebDriverFactory,
    patch_config,
    patch_dirs,
)
from Common import basePage as base_page
from Common.basePage import DEFAULT_TIMEOUT, BasePage, HEADLESS_ARGS


class _PageTestCase(unittest.TestCase):
    """基类：提供「配置已隔离 + my_sleep 已禁用」的 BasePage 环境。"""

    def setUp(self):
        self._config = patch_config()
        self.ini_path = self._config.__enter__()
        # 强制等待会拖慢测试，统一替换为空操作
        self._sleep = mock.patch.object(BasePage, 'my_sleep', return_value=None)
        self._sleep.start()

    def tearDown(self):
        self._sleep.stop()
        self._config.__exit__(None, None, None)

    def make_page(self, driver=None, timeout=None):
        return BasePage(driver=driver if driver is not None else FakeDriver(),
                        timeout=timeout)


# ==========================================================================
# 一、元素定位参数的解析
# ==========================================================================
class TestParseSelector(unittest.TestCase):

    def test_正确的xpath描述(self):
        self.assertEqual(BasePage._parse_selector(['xpath', '//div']), (By.XPATH, '//div'))

    def test_定位方式大小写不敏感(self):
        self.assertEqual(BasePage._parse_selector(['XPATH', '//div']), (By.XPATH, '//div'))
        self.assertEqual(BasePage._parse_selector(['Id', 'x']), (By.ID, 'x'))

    def test_各种定位方式都能识别(self):
        for name, expected in (('id', By.ID), ('name', By.NAME), ('class', By.CLASS_NAME),
                               ('tag', By.TAG_NAME), ('link', By.LINK_TEXT),
                               ('plink', By.PARTIAL_LINK_TEXT), ('css', By.CSS_SELECTOR)):
            self.assertEqual(BasePage._parse_selector([name, 'v']), (expected, 'v'))

    def test_元组也能用(self):
        self.assertEqual(BasePage._parse_selector(('css', '#a')), (By.CSS_SELECTOR, '#a'))

    def test_不支持的定位方式返回None(self):
        self.assertEqual(BasePage._parse_selector(['sizzle', '#a']), (None, None))

    def test_传入字符串而非列表时安全返回None(self):
        """历史上最容易写错的用法：忘了写成 ['xpath', '...']。"""
        self.assertEqual(BasePage._parse_selector('xpath'), (None, None))

    def test_传入None或空时安全返回None(self):
        self.assertEqual(BasePage._parse_selector(None), (None, None))
        self.assertEqual(BasePage._parse_selector([]), (None, None))
        self.assertEqual(BasePage._parse_selector(['xpath']), (None, None))


class TestExtraChromeArgs(unittest.TestCase):
    """config.ini -> [ci] extra_chrome_args 的解析。"""

    def test_默认为空列表(self):
        with patch_config():
            self.assertEqual(BasePage._extra_chrome_args(), [])

    def test_支持逗号分号与换行分隔(self):
        # ini 的换行值必须用「缩进续行」写法，顶格写会让 configparser 直接解析失败
        ini = '[ci]\nextra_chrome_args = --a, --b;--c\n    --d\n'
        with patch_config(ini_text=ini):
            self.assertEqual(
                BasePage._extra_chrome_args(), ['--a', '--b', '--c', '--d']
            )

    def test_自动去掉空白项(self):
        ini = '[ci]\nextra_chrome_args =  --a ,  , --b  \n'
        with patch_config(ini_text=ini):
            self.assertEqual(BasePage._extra_chrome_args(), ['--a', '--b'])


# ==========================================================================
# 二、超时配置
# ==========================================================================
class TestTimeoutConfig(_PageTestCase):

    def test_默认超时来自配置文件(self):
        page = self.make_page()
        self.assertEqual(page.timeout, 7)      # DEFAULT_INI 里 element_timeout = 7

    def test_构造参数优先于配置(self):
        self.assertEqual(self.make_page(timeout=3).timeout, 3)

    def test_缺配置时退到代码默认值(self):
        with patch_config(ini_text='[environment]\nurl = http://x\n'):
            self.assertEqual(BasePage().timeout, DEFAULT_TIMEOUT)


# ==========================================================================
# 三、元素定位
# ==========================================================================
class TestGetElement(_PageTestCase):

    def test_显式等待模式返回元素(self):
        driver = FakeDriver()
        page = self.make_page(driver)
        element = page.get_element(['xpath', "//input[@type='text']"])
        self.assertIs(element, driver._element)
        self.assertIn(('find_element', By.XPATH, "//input[@type='text']"), driver.calls)

    def test_快速通道不等待直接查找(self):
        driver = FakeDriver()
        page = self.make_page(driver)
        page.get_element(['id', 'btn'], timeout=0)
        self.assertEqual(driver.calls[0], ('find_element', By.ID, 'btn'))

    def test_元素不存在时返回None而不抛异常(self):
        driver = FakeDriver(find_error=NoSuchElementException('没有'))
        page = self.make_page(driver)
        self.assertIsNone(page.get_element(['id', 'nope'], timeout=0.05))

    def test_等待超时后返回None(self):
        driver = FakeDriver(find_error=TimeoutException('超时'))
        page = self.make_page(driver)
        self.assertIsNone(page.get_element(['id', 'nope'], timeout=0.05))

    def test_非法定位参数返回None(self):
        page = self.make_page()
        self.assertIsNone(page.get_element('xpath'))

    def test_visible参数使用可见性条件(self):
        driver = FakeDriver()
        page = self.make_page(driver)
        self.assertIsNotNone(page.get_element(['id', 'x'], visible=True))

    def test_get_elements快速通道(self):
        elements = [FakeElement(text='a'), FakeElement(text='b')]
        driver = FakeDriver(elements=elements)
        page = self.make_page(driver)
        self.assertEqual(page.get_elements(['tag', 'tr'], timeout=0), elements)

    def test_get_elements找不到时返回空列表(self):
        driver = FakeDriver(find_error=NoSuchElementException('无'))
        page = self.make_page(driver)
        self.assertEqual(page.get_elements(['tag', 'tr'], timeout=0.05), [])

    def test_get_elements非法参数返回空列表(self):
        self.assertEqual(self.make_page().get_elements('bad'), [])

    def test_wait_element等价于get_element(self):
        driver = FakeDriver()
        page = self.make_page(driver)
        self.assertIs(page.wait_element(['id', 'x'], timeout=0.05), driver._element)


# ==========================================================================
# 四、交互动作
# ==========================================================================
class TestInteraction(_PageTestCase):

    def test_type会先清空再输入(self):
        element = FakeElement()
        page = self.make_page(FakeDriver(element=element))
        page.type(['id', 'user'], 'zhangsan')
        self.assertEqual(element.calls, ['clear', 'send_keys'])
        self.assertEqual(element.sent, ['zhangsan'])

    def test_type元素不存在时抛出异常(self):
        """必须抛异常：静默跳过会让用例"假成功"。"""
        driver = FakeDriver(find_error=NoSuchElementException('无'))
        page = self.make_page(driver)
        with self.assertRaises(NoSuchElementException):
            page.type(['id', 'user'], 'x', timeout=0.05)

    def test_type在clear失败时退化为全选删除(self):
        element = FakeElement(clear_error=WebDriverException('clear 不支持'))
        page = self.make_page(FakeDriver(element=element))
        page.type(['id', 'user'], 'abc')
        # clear 失败 -> 全选(2 个键) -> 删除 -> 再输入，共 3 次 send_keys
        self.assertEqual(element.calls, ['clear', 'send_keys', 'send_keys', 'send_keys'])
        self.assertIn(Keys.CONTROL, element.sent)
        self.assertIn(Keys.DELETE, element.sent)
        self.assertIn('abc', element.sent)

    def test_type输入失败时截图并向上抛(self):
        element = FakeElement(send_keys_error=WebDriverException('输入失败'))
        page = self.make_page(FakeDriver(element=element))
        with patch_dirs():
            with self.assertRaises(WebDriverException):
                page.type(['id', 'user'], 'x')
            self.assertEqual(len(page.driver.screenshots), 1, '输入失败应自动截图')

    def test_click成功(self):
        element = FakeElement()
        driver = FakeDriver(element=element)
        page = self.make_page(driver)
        page.click(['id', 'btn'])
        self.assertIn('click', element.calls)
        # 点击前会先滚动到可视区
        self.assertTrue(any('scrollIntoView' in script for script in driver.scripts))

    def test_click原生失败时降级为JS点击(self):
        element = FakeElement(click_error=WebDriverException('被遮挡'))
        driver = FakeDriver(element=element)
        page = self.make_page(driver)
        page.click(['id', 'btn'])
        js_clicks = [s for s in driver.scripts if 'click()' in s]
        self.assertEqual(len(js_clicks), 1, '原生点击失败应触发 JS 点击兜底')

    def test_click元素不存在时抛出异常(self):
        driver = FakeDriver(find_error=NoSuchElementException('无'))
        page = self.make_page(driver)
        with self.assertRaises(NoSuchElementException):
            page.click(['id', 'btn'], timeout=0.05)

    def test_滚动失败不影响后续点击(self):
        element = FakeElement()
        driver = FakeDriver(element=element)
        page = self.make_page(driver)
        with mock.patch.object(driver, 'execute_script',
                               side_effect=[WebDriverException('滚动失败'), None]):
            page.click(['id', 'btn'])
        self.assertIn('click', element.calls)

    def test_get_title(self):
        page = self.make_page(FakeDriver(title='统一门户'))
        self.assertEqual(page.get_title(), '统一门户')

    def test_get_text(self):
        page = self.make_page(FakeDriver(element=FakeElement(text='素材库')))
        self.assertEqual(page.get_text(['id', 'x']), '素材库')

    def test_get_text元素不存在时抛出异常(self):
        driver = FakeDriver(find_error=NoSuchElementException('无'))
        page = self.make_page(driver)
        with self.assertRaises(NoSuchElementException):
            page.get_text(['id', 'x'], timeout=0.05)

    def test_get_value读的是value属性而不是显示文字(self):
        """get_text 取显示文字、get_value 取 value，两者不能混用。

        典型场景：输入框里填了字，它的 .text 是空的，只能靠 value 读回来。
        """
        element = FakeElement(text='', attributes={'value': '测试关键字'})
        page = self.make_page(FakeDriver(element=element))
        self.assertEqual(page.get_value(['id', 'kw']), '测试关键字')
        self.assertEqual(element.attributes_read, ['value'])

    def test_get_value在属性缺失时返回None(self):
        page = self.make_page(FakeDriver(element=FakeElement(attributes={})))
        self.assertIsNone(page.get_value(['id', 'kw']))

    def test_get_value元素不存在时抛出异常(self):
        """必须抛异常：静默返回 None 会让"输入是否生效"的断言假通过。"""
        driver = FakeDriver(find_error=NoSuchElementException('无'))
        page = self.make_page(driver)
        with self.assertRaises(NoSuchElementException):
            page.get_value(['id', 'kw'], timeout=0.05)

    def test_use_js执行成功(self):
        driver = FakeDriver()
        page = self.make_page(driver)
        page.use_js('return 1')
        self.assertEqual(driver.scripts, ['return 1'])

    def test_use_js失败时向上抛(self):
        driver = FakeDriver()
        page = self.make_page(driver)
        with mock.patch.object(driver, 'execute_script',
                               side_effect=WebDriverException('js 报错')):
            with self.assertRaises(WebDriverException):
                page.use_js('bad()')

    def test_isdisplayed处理None与异常(self):
        self.assertFalse(BasePage.isdisplayed(None))
        self.assertTrue(BasePage.isdisplayed(FakeElement(displayed=True)))
        self.assertFalse(BasePage.isdisplayed(FakeElement(displayed=False)))


class TestMySleep(unittest.TestCase):
    """my_sleep 的等待行为。

    单独成一个类：因为它需要使用**未被打桩**的真实实现，
    而 _PageTestCase 为了跑得快会把 my_sleep 换成空操作。
    """

    def test_按秒数调用真实等待(self):
        with mock.patch.object(base_page.time, 'sleep') as fake_sleep:
            BasePage.my_sleep(0.5)
        fake_sleep.assert_called_once_with(0.5)


# ==========================================================================
# 五、输入回车（搜索框场景）
# ==========================================================================
class TestInputEnter(_PageTestCase):

    def test_按回车(self):
        element = FakeElement()
        page = self.make_page(FakeDriver(element=element))
        page.input_enter('关键词', "//input[@id='q']")
        self.assertIn(Keys.ENTER, element.sent)
        self.assertIn('关键词', element.sent)

    def test_也可直接传selector(self):
        element = FakeElement()
        page = self.make_page(FakeDriver(element=element))
        page.input_enter('关键词', None, selector=['id', 'q'])
        self.assertIn(Keys.ENTER, element.sent)

    def test_元素不存在时抛出异常(self):
        driver = FakeDriver(find_error=NoSuchElementException('无'))
        page = self.make_page(driver)
        with self.assertRaises(NoSuchElementException):
            page.input_enter('x', "//input")


# ==========================================================================
# 六、窗口与 frame 切换
# ==========================================================================
class TestWindowAndFrame(_PageTestCase):

    def test_切换到另一个标签页(self):
        driver = FakeDriver(window_handles=['w1', 'w2'])
        page = self.make_page(driver)
        self.assertEqual(page.switch_other_window(), 'w2')
        self.assertEqual(driver.current_window_handle, 'w2')

    def test_只有一个窗口时返回None(self):
        driver = FakeDriver(window_handles=['only'])
        page = self.make_page(driver)
        self.assertIsNone(page.switch_other_window())

    def test_未传handle时自动取当前窗口(self):
        driver = FakeDriver(window_handles=['w1', 'w2'])
        page = self.make_page(driver)
        self.assertEqual(page.switch_other_window(None), 'w2')

    def test_get_handle(self):
        driver = FakeDriver(window_handles=['abc'])
        self.assertEqual(self.make_page(driver).get_handle(), 'abc')

    def test_旧别名chage_handle仍可用(self):
        driver = FakeDriver(window_handles=['w1', 'w2'])
        page = self.make_page(driver)
        self.assertEqual(page.chage_handle('w1'), 'w2')

    def test_切换iframe(self):
        driver = FakeDriver()
        page = self.make_page(driver)
        element = driver._element
        page.switch_iframe(['tag', 'iframe'])
        self.assertEqual(driver.switched_frames, [element])

    def test_切换iframe元素不存在时抛出异常(self):
        driver = FakeDriver()
        page = self.make_page(driver)
        # 直接让定位返回 None，避免真的等满超时拖慢测试
        with mock.patch.object(page, 'get_element', return_value=None):
            with self.assertRaises(NoSuchElementException):
                page.switch_iframe(['tag', 'iframe'])

    def test_回到最外层文档(self):
        driver = FakeDriver()
        page = self.make_page(driver)
        page.switch_default_content()
        self.assertEqual(driver.default_content_count, 1)

    def test_旧别名switch_ifarme指向同一实现(self):
        self.assertEqual(BasePage.switch_ifarme, BasePage.switch_iframe)

    def test_接受弹窗(self):
        driver = FakeDriver()
        page = self.make_page(driver)
        page.popout()
        self.assertTrue(driver.alert.accepted)


# ==========================================================================
# 七、文件上传
# ==========================================================================
class TestFilesUpload(_PageTestCase):

    def setUp(self):
        super().setUp()
        self.tmpdir = tempfile.mkdtemp(prefix='ut_upload_')
        self.video = os.path.join(self.tmpdir, 'demo.mp4')
        with open(self.video, 'wb') as fp:
            fp.write(b'fake-video')

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)
        super().tearDown()

    def test_上传成功时给file控件赋值(self):
        element = FakeElement()
        page = self.make_page(FakeDriver(element=element))
        page.files_upload(['xpath', "//input[@type='file']"], self.video)
        self.assertEqual(element.sent, [self.video])

    def test_未配置且未传路径时抛出ValueError(self):
        ini = '[testcase]\nupload_file =\n'
        element = FakeElement()
        with patch_config(ini_text=ini):
            page = BasePage(driver=FakeDriver(element=element))
            with self.assertRaises(ValueError):
                page.files_upload(['xpath', "//input[@type='file']"])

    def test_文件不存在时抛出FileNotFoundError(self):
        """必须报错，否则用例会在没有真实上传的情况下"通过"。"""
        page = self.make_page(FakeDriver(element=FakeElement()))
        with self.assertRaises(FileNotFoundError):
            page.files_upload(['xpath', "//input[@type='file']"],
                              os.path.join(self.tmpdir, '没有这个文件.mp4'))

    def test_未找到上传控件时抛出异常(self):
        page = self.make_page(FakeDriver())
        with mock.patch.object(page, 'get_element', return_value=None):
            with self.assertRaises(NoSuchElementException):
                page.files_upload(['xpath', "//input[@type='file']"], self.video)

    def test_未安装autoit时给出可操作的报错(self):
        with mock.patch.object(base_page, 'AUTOIT_AVAILABLE', False):
            page = self.make_page()
            with self.assertRaises(RuntimeError) as ctx:
                page.upload_by_autoit(self.video)
            self.assertIn('PyAutoIt', str(ctx.exception))


# ==========================================================================
# 八、截图与关闭
# ==========================================================================
class TestScreenshotAndQuit(_PageTestCase):

    def test_截图保存到日期目录(self):
        driver = FakeDriver()
        page = self.make_page(driver)
        with patch_dirs():
            path = page.get_img()
        self.assertTrue(path.endswith('.png'))
        self.assertEqual(len(driver.screenshots), 1)

    def test_截图失败不抛异常(self):
        """截图只是排查辅助手段，不能因为它失败就让用例挂掉。"""
        driver = FakeDriver()
        page = self.make_page(driver)
        with patch_dirs(), mock.patch.object(
                driver, 'get_screenshot_as_file', side_effect=WebDriverException('截图失败')):
            self.assertIsNone(page.get_img())

    def test_关闭浏览器(self):
        driver = FakeDriver()
        page = self.make_page(driver)
        page.dr_quit()
        self.assertTrue(driver.quit_called)
        self.assertIsNone(page.driver)

    def test_重复关闭不报错(self):
        page = self.make_page(FakeDriver())
        page.dr_quit()
        page.dr_quit()

    def test_关闭报错时仍清空引用(self):
        driver = FakeDriver()
        page = self.make_page(driver)
        with mock.patch.object(driver, 'quit', side_effect=WebDriverException('quit 失败')):
            page.dr_quit()
        self.assertIsNone(page.driver)


# ==========================================================================
# 九、浏览器启动
# ==========================================================================
class TestOpenBrowser(_PageTestCase):

    def _factory(self, **kwargs):
        return FakeWebDriverFactory(**kwargs)

    def test_打开chrome并访问配置地址(self):
        factory = self._factory()
        page = self.make_page()
        with mock.patch.object(base_page, 'webdriver', factory):
            driver = page.open_browser()
        self.assertIs(driver, factory.driver)
        self.assertEqual(driver.visited, ['http://test-env.local/sso-portal'])
        self.assertEqual(driver.maximized, 1, '有界面模式应最大化窗口')
        self.assertEqual(driver.implicit_waits, [2], '隐式等待应取配置值')

    def test_无头模式附加必要参数(self):
        factory = self._factory()
        page = self.make_page()
        with mock.patch.object(base_page, 'webdriver', factory):
            driver = page.open_browser(headless=True)
        arguments = factory.chrome_options.arguments
        for arg in HEADLESS_ARGS:
            self.assertIn(arg, arguments, '无头模式必须带 %s' % arg)
        self.assertIn('--lang=zh-CN', arguments)
        self.assertEqual(driver.window_sizes, [(1920, 1080)])
        self.assertEqual(driver.maximized, 0, '无头模式不该调用 maximize_window')

    def test_去掉自动测试提示条(self):
        factory = self._factory()
        with mock.patch.object(base_page, 'webdriver', factory):
            self.make_page().open_browser()
        self.assertEqual(
            factory.chrome_options.experimental.get('excludeSwitches'),
            ['enable-automation'],
        )

    def test_参数优先于配置的地址与浏览器(self):
        factory = self._factory()
        page = self.make_page()
        with mock.patch.object(base_page, 'webdriver', factory):
            driver = page.open_browser(url='http://override.local/x', browser='chrome')
        self.assertEqual(driver.visited, ['http://override.local/x'])

    def test_选择firefox(self):
        factory = self._factory()
        with mock.patch.object(base_page, 'webdriver', factory):
            self.make_page().open_browser(browser='firefox')
        self.assertEqual(factory.firefox_calls, 1)

    def test_选择edge(self):
        factory = self._factory()
        with mock.patch.object(base_page, 'webdriver', factory):
            self.make_page().open_browser(browser='edge')
        self.assertEqual(factory.edge_calls, 1)

    def test_配置grid_url时走远程Remote而非本地浏览器(self):
        """Selenium Grid：配了 Hub 地址就把驱动交给远程，不调用本地 Chrome。"""
        ini = ('[environment]\nurl = http://x.local\nbrowser = chrome\n'
               '[ci]\ngrid_url = http://127.0.0.1:4444\n')
        factory = self._factory()
        with patch_config(ini_text=ini):
            page = BasePage(driver=FakeDriver())
            with mock.patch.object(base_page, 'webdriver', factory):
                page.open_browser()
        self.assertEqual(factory.remote_calls, 1)
        self.assertEqual(factory.remote_urls, ['http://127.0.0.1:4444'])
        self.assertEqual(factory.chrome_calls, 0, '走 Grid 时不应再调用本地 Chrome')

    def test_环境变量UI_CI_GRID_URL也能触发远程执行(self):
        """命令行 --grid 写到 UI_CI_GRID_URL，应同样触发远程驱动。"""
        factory = self._factory()
        with patch_config():
            with mock.patch.dict(os.environ, {'UI_CI_GRID_URL': 'http://hub:4444'}):
                with mock.patch.object(base_page, 'webdriver', factory):
                    self.make_page().open_browser(browser='firefox')
        self.assertEqual(factory.remote_calls, 1)
        self.assertEqual(factory.remote_urls, ['http://hub:4444'])

    def test_未配置grid时仍走本地浏览器(self):
        factory = self._factory()
        with patch_config():
            with mock.patch.object(base_page, 'webdriver', factory):
                self.make_page().open_browser(browser='chrome')
        self.assertEqual(factory.chrome_calls, 1)
        self.assertEqual(factory.remote_calls, 0)

    def test_浏览器类型大小写不敏感(self):
        factory = self._factory()
        with mock.patch.object(base_page, 'webdriver', factory):
            self.make_page().open_browser(browser='CHROME')
        self.assertEqual(factory.chrome_calls, 1)

    def test_浏览器类型非法时报错(self):
        page = self.make_page()
        with self.assertRaises(ValueError) as ctx:
            page.open_browser(browser='safari')
        self.assertIn('chrome', str(ctx.exception))

    def test_未配置地址时给出明确报错(self):
        """CI 首跑最常见的问题，必须是可读错误而不是一堆定位失败。"""
        ini = '[environment]\nbrowser = chrome\n'
        with patch_config(ini_text=ini):
            page = BasePage(driver=FakeDriver())
            with self.assertRaises(ValueError) as ctx:
                page.open_browser()
            self.assertIn('未配置被测地址', str(ctx.exception))

    def test_浏览器启动失败时向上抛(self):
        factory = self._factory(chrome_error=WebDriverException('驱动不匹配'))
        page = self.make_page()
        with mock.patch.object(base_page, 'webdriver', factory):
            with self.assertRaises(WebDriverException):
                page.open_browser()

    def test_读取额外启动参数(self):
        ini = ('[environment]\nurl = http://x.local\nbrowser = chrome\n'
               '[ci]\nextra_chrome_args = --disable-images, --allow-insecure-localhost\n')
        factory = self._factory()
        with patch_config(ini_text=ini):
            page = BasePage(driver=FakeDriver())
            with mock.patch.object(base_page, 'webdriver', factory):
                page.open_browser()
        self.assertIn('--disable-images', factory.chrome_options.arguments)
        self.assertIn('--allow-insecure-localhost', factory.chrome_options.arguments)

    def test_指定chrome可执行文件(self):
        ini = ('[environment]\nurl = http://x.local\nbrowser = chrome\n'
               '[ci]\nchrome_binary = /usr/bin/chromium\n')
        factory = self._factory()
        with patch_config(ini_text=ini):
            page = BasePage(driver=FakeDriver())
            with mock.patch.object(base_page, 'webdriver', factory):
                page.open_browser()
        self.assertEqual(factory.chrome_options.binary_location, '/usr/bin/chromium')

    def test_未装PyAutoIt时模块状态正确(self):
        """记录当前环境的 autoit 可用性，避免上传回退分支被误判。"""
        self.assertIsInstance(base_page.AUTOIT_AVAILABLE, bool)


if __name__ == '__main__':
    unittest.main(verbosity=2)
