# -*- coding: utf-8 -*-
"""
==========================================================================
 测试基类 BasePage —— 整个框架的地基（新人阅读顺序：第 5 个）
==========================================================================

【一句话说明】
    所有页面对象的父类，也是对 Selenium 原生 API 的唯一封装层。
    整个工程里只有这个文件会直接调用 webdriver，其他文件一律通过它操作浏览器。

【在框架中的位置】
    TestSuites/testLogin.py        用例层：写业务断言
        └─> PageObject/loginPage.py  页面对象：写"在这个页面做什么"
              └─> Common/basePage.py <- 本文件：写"怎么操作浏览器"
                    └─> selenium webdriver

【本文件的四类能力】
    1. 浏览器生命周期   open_browser / dr_quit
    2. 元素定位          get_element / get_elements / wait_element / _parse_selector
    3. 常用交互          type / click / get_text / get_title / use_js / my_sleep
    4. 场景化能力        switch_*（窗口与frame）/ files_upload（上传）/ get_img（截图）

【新人必读：元素定位的写法】
    工程统一用「二元列表」描述元素，格式 [定位方式, 定位值]，例如：
        ['xpath', "//input[@type='text']"]     -> 用户名输入框
        ['id', 'global-uploader-btn']          -> 按 id 定位
    这些描述集中在 Common/elementPage.py，本文件负责把字符串 'xpath'
    翻译成 Selenium 4 需要的 By.XPATH（见下方 BY_MAP）。

【新人必读：Selenium 3 与 4 的差异（本文件已按 4 写）】
    driver.find_element_by_id('x')      -> driver.find_element(By.ID, 'x')
    webdriver.Chrome(chrome_options=..) -> webdriver.Chrome(options=..)
    driver.switch_to_default_content()  -> driver.switch_to.default_content()
    如果从网上抄到旧写法，会在 Selenium 4 下直接报 AttributeError。

【标注说明】
    方法注释末尾带「【在用】」的，表示当前用例实际会走到；
    带「【预留】」的表示框架能力储备，暂时没有用例调用，改动前先搜索确认。

【新人必读：CI/CD 相关的三个开关】
    本文件是"浏览器到底怎么起"的唯一地方，流水线上要跑得起来，靠的是这三项：
    1. 无头模式   config.ini -> [ci] headless，或环境变量 UI_CI_HEADLESS=true
                  Jenkins 节点没有桌面，必须开启，否则 Chrome 起不来
    2. 元素超时   config.ini -> [ci] element_timeout，默认 15 秒
                  CI 机器通常比开发机慢，页面加载慢时可调大到 30
    3. 额外参数   config.ini -> [ci] extra_chrome_args，逗号分隔
                  容器里跑常需要 --no-sandbox 之类，已在无头模式下自动补上
==========================================================================
"""

import os
import re
import time

from selenium import webdriver
from selenium.common.exceptions import (
    NoSuchElementException,   # 元素找不到
    TimeoutException,         # 显式等待超时
    StaleElementReferenceException,  # 元素过期（DOM 刷新后旧引用失效，偶发失败主因）
    WebDriverException,       # 所有 webdriver 异常的父类，兜底用
)
from selenium.webdriver.common.by import By          # Selenium 4 的定位方式常量
from selenium.webdriver.common.keys import Keys      # 键盘按键，如 Keys.ENTER
from selenium.webdriver.support import expected_conditions as EC   # 等待条件
from selenium.webdriver.support.ui import WebDriverWait            # 显式等待

import getcwd                       # 取工程根目录
from Common.config import Config    # 读 config.ini
from Common import driverRegistry as driver_registry   # 浏览器实例登记（失败取证要用）
from Common.log import log1         # 统一日志

# ---------------------------------------------------------------------------
# autoit 是可选依赖：它用来操作 Windows 原生「打开」文件对话框。
# 未安装时不影响工程运行（默认上传方式不需要它），所以用 try 包起来。
# 如确实需要：pip install PyAutoIt
# ---------------------------------------------------------------------------
try:
    import autoit

    AUTOIT_AVAILABLE = True
except ImportError:  # pragma: no cover
    autoit = None
    AUTOIT_AVAILABLE = False

config = Config()

# 元素表里写的字符串定位方式 -> Selenium 4 的 By 常量。
# 有这张表，elementPage.py 就能继续用 'xpath'/'id' 这种可读的写法。
BY_MAP = {
    'id': By.ID,                          # 按 id 属性
    'name': By.NAME,                      # 按 name 属性
    'class': By.CLASS_NAME,               # 按 class 名
    'tag': By.TAG_NAME,                   # 按标签名，如 input
    'link': By.LINK_TEXT,                 # 按链接的完整文字
    'plink': By.PARTIAL_LINK_TEXT,        # 按链接的部分文字
    'css': By.CSS_SELECTOR,               # 按 CSS 选择器
    'xpath': By.XPATH,                    # 按 xpath
}

# 元素定位的默认超时秒数：等不到才判定"元素不存在"。
# 实际取值优先级：BasePage(timeout=...) > config.ini [ci] element_timeout > 本常量
DEFAULT_TIMEOUT = 15

# 无头模式自动附加的 Chrome 参数（容器/CI 环境必需，否则 Chrome 直接启动失败）
HEADLESS_ARGS = (
    '--headless=new',             # 新版无头模式，行为与有界面几乎一致
    '--no-sandbox',               # 容器内以 root 运行时必需
    '--disable-gpu',              # 无显卡环境避免 GPU 相关报错
    '--disable-dev-shm-usage',    # /dev/shm 太小时防止页面崩溃
    '--hide-scrollbars',          # 隐藏滚动条，截图更干净
    '--window-size=1920,1080',    # 固定窗口尺寸，避免元素被响应式布局折叠
)


class BasePage:
    """测试基类：浏览器 + 元素 + 交互的统一封装。

    典型用法（页面对象里）：
        class LoginPage(BasePage):
            def login(self, username, password):
                self.type(Element1.Username, username)   # 这里的 type 就来自本类
    """

    def __init__(self, driver=None, timeout=None):
        """
        :param driver:  webdriver 实例。BasePage 本身不开浏览器，
                        通常由 open_browser() 创建后再传给它、或直接由子类持有。
        :param timeout: 元素定位默认超时时间（秒）。不传则读
                        config.ini -> [ci] element_timeout，再退到 DEFAULT_TIMEOUT。
        """
        self.driver = driver
        self.timeout = timeout or config.get_int('ci', 'element_timeout', DEFAULT_TIMEOUT)

    # ====================================================================== #
    # 一、浏览器生命周期
    # ====================================================================== #
    def open_browser(self, url=None, browser=None, headless=None):
        """打开浏览器并访问被测地址，返回 webdriver 实例。【在用】

        浏览器类型和 url 都从 config.ini 的 [environment] 段读取，
        也可以由参数强制指定（命令行 --url / --browser 就是走这条）。

        :param url:      被测地址，为空则取 config.ini -> [environment] url
                         （会被环境变量 UI_ENVIRONMENT_URL 覆盖，CI 上就靠它切环境）
        :param browser:  chrome / firefox / edge，为空则取配置
        :param headless: 是否无头运行。不传则按
                         config.ini -> [ci] headless（可被 UI_CI_HEADLESS 覆盖）决定
        :return: webdriver 实例（同时保存在 self.driver）
        :raise ValueError: 未配置被测地址时抛出 —— 这是 CI 首跑最常见的错误，
                           明确报错比后面一堆元素定位失败好排查得多
        :raise WebDriverException: 浏览器打不开时向上抛，避免"静默失败"后
                                   后续所有用例都莫名其妙报错
        """
        # .lower() 容错：配置里写 Chrome / CHROME 都能识别
        browser = (browser or config.get('environment', 'browser', 'chrome')).lower()
        url = url or config.get('environment', 'url')
        if headless is None:
            headless = config.get_bool('ci', 'headless', False)

        if not url:
            # 没有地址就没法测，直接抛出并说清怎么修
            raise ValueError(
                '未配置被测地址：请在 config.ini -> [environment] url 填写，'
                '或设置环境变量 UI_ENVIRONMENT_URL，或使用命令行参数 --url'
            )

        log1.info('读取浏览器配置,值为%s，无头模式=%s' % (browser, headless))
        log1.info('读取url,值为%s' % url)
        # Selenium Grid 远程执行：配了 grid_url 就把驱动交给远程 Hub，
        # 由 Hub 决定在哪个节点、用哪个浏览器跑。对应 config.ini [ci] grid_url
        # 或环境变量 UI_CI_GRID_URL（命令行 --grid 会写到这里）。
        grid_url = config.get('ci', 'grid_url', '')
        try:
            if browser == 'chrome':
                options = webdriver.ChromeOptions()
                # 去掉"Chrome 正受到自动测试软件的控制"提示条
                # （Selenium 4 中旧的 'disable-infobars' 参数已失效，改用下面这种）
                options.add_experimental_option('excludeSwitches', ['enable-automation'])
                if headless:
                    # 无头模式：Jenkins 节点/容器里没有桌面，必须走这一支
                    for arg in HEADLESS_ARGS:
                        options.add_argument(arg)
                    options.add_argument('--lang=zh-CN')   # 保持页面中文文案，与有头模式一致
                else:
                    options.add_argument('--start-maximized')
                # 额外参数：容器或特殊环境用，config.ini -> [ci] extra_chrome_args
                for arg in self._extra_chrome_args():
                    options.add_argument(arg)
                # 指定 Chrome 可执行文件：容器里装的 chromium 不在默认路径时需要它。
                # 对应配置 [ci] chrome_binary，或环境变量 UI_CI_CHROME_BINARY
                # （例如 Docker 镜像里设为 /usr/bin/chromium）
                chrome_binary = config.get('ci', 'chrome_binary', '')
                if chrome_binary:
                    options.binary_location = chrome_binary
                    log1.info('指定 Chrome 可执行文件：%s' % chrome_binary)
                # 注意：Selenium 4 自带 Selenium Manager，会自动下载匹配的 chromedriver，
                # 不需要再手动放 driver 文件（旧工程根目录的 geckodriver.log 就是这么来的）
                if grid_url:
                    self.driver = webdriver.Remote(command_executor=grid_url,
                                                   options=options)
                    log1.info('通过 Selenium Grid 打开 chrome（无头=%s，Hub=%s）'
                              % (headless, grid_url))
                else:
                    self.driver = webdriver.Chrome(options=options)
                    log1.info('打开chrome浏览器（无头=%s）' % headless)
            elif browser == 'firefox':
                options = webdriver.FirefoxOptions()
                if headless:
                    options.add_argument('-headless')
                if grid_url:
                    self.driver = webdriver.Remote(command_executor=grid_url,
                                                   options=options)
                    log1.info('通过 Selenium Grid 打开 firefox（Hub=%s）' % grid_url)
                else:
                    self.driver = webdriver.Firefox(options=options)
                    log1.info('打开firefox浏览器')
            elif browser == 'edge':
                options = webdriver.EdgeOptions()
                if headless:
                    options.add_argument('--headless=new')
                if grid_url:
                    self.driver = webdriver.Remote(command_executor=grid_url,
                                                   options=options)
                    log1.info('通过 Selenium Grid 打开 edge（Hub=%s）' % grid_url)
                else:
                    self.driver = webdriver.Edge(options=options)
                    log1.info('打开edge浏览器')
            else:
                # 配置写错时立刻失败，比后面每个元素都定位不到好排查得多
                raise ValueError('浏览器配置有误，应为 chrome / firefox / edge')

            self.driver.get(url)
            log1.info('访问url')
            if headless:
                # 无头模式下 maximize_window() 在部分系统上无效甚至报错，
                # 改用固定分辨率（已在 HEADLESS_ARGS 里设过，这里兜底显式设置一次）
                self.driver.set_window_size(1920, 1080)
                log1.info('设置窗口尺寸 1920x1080')
            else:
                self.driver.maximize_window()
                log1.info('浏览器最大化')
            # 隐式等待：find_element 找不到元素时最多轮询 N 秒。
            # 它只对「查找元素」生效，不能等元素可点击 —— 那种场景用 get_element(timeout=...)
            implicit_wait = config.get_int('ci', 'implicit_wait', 5)
            self.driver.implicitly_wait(implicit_wait)
            log1.info('设置隐式等待%d秒' % implicit_wait)

            # 登记到全局表：用例失败时框架要靠它拿到浏览器做自动取证
            # （见 Common/driverRegistry.py 与 Common/failureCapture.py）
            driver_registry.register(self.driver)
            return self.driver
        except WebDriverException:
            log1.error('浏览器打开报错', exc_info=1)
            raise

    @staticmethod
    def _extra_chrome_args():
        """解析 config.ini -> [ci] extra_chrome_args 里的附加启动参数。

        :return: 参数列表，例如 ['--no-sandbox', '--disable-images']
        支持用逗号、分号或换行分隔；未配置时返回空列表。

        注意：想用换行分隔时，必须按 ini 的「续行」写法（后续行要缩进），例如
            extra_chrome_args = --disable-images,
                --allow-insecure-localhost
        ini 不支持 \\n 转义，若第二行顶格书写，configparser 会直接抛解析错误。
        """
        raw = config.get('ci', 'extra_chrome_args', '') or ''
        return [item.strip() for item in re.split(r'[,;\n]', raw) if item.strip()]

    def dr_quit(self, wait=0):
        """关闭浏览器并释放 driver。【在用】

        由用例的 tearDownClass 调用，保证不管用例成败都能关掉浏览器，
        否则会残留一堆 chrome 进程。

        :param wait: 关闭前先强制等待多少秒，默认 0（不等待）
        """
        if wait:
            self.my_sleep(wait)
        if self.driver is None:
            return
        try:
            self.driver.quit()
            log1.info('关闭浏览器')
        except WebDriverException:
            log1.error('关闭浏览器报错', exc_info=1)
        finally:
            # 注销登记：否则失败取证会去操作一个已关闭的浏览器，
            # 抛出的 InvalidSessionIdException 会把真正的失败原因盖掉
            driver_registry.unregister(self.driver)
            # 无论是否报错都把引用清空，避免后续误用到已失效的 driver
            self.driver = None

    # ====================================================================== #
    # 二、元素定位
    # ====================================================================== #
    @staticmethod
    def _parse_selector(selector):
        """把 ['xpath', '//div'] 翻译成 Selenium 4 需要的 (By.XPATH, '//div')。

        :param selector: 二元列表/元组，如 ['xpath', "//input[@type='text']"]
        :return: (By 常量, 定位值)；格式非法或定位方式不支持时返回 (None, None)
        """
        try:
            by, value = selector[0], selector[1]
        except (TypeError, IndexError):
            log1.error('元素定位参数格式错误，应形如 ["xpath", "//div/span"]：%s' % (selector,))
            return None, None
        by = BY_MAP.get(str(by).lower())
        if by is None:
            log1.error('元素定位方式错误，请使用 %s 之一' % '/'.join(BY_MAP))
            # 定位方式不认识时必须返回 (None, None)，与函数契约保持一致。
            # 早期只写日志就返回，会把 (None, '定位值') 这种半成品交给调用方，
            # 调用方一旦漏判 by 就会拿着 None 去 find_element 而报出难懂的错。
            return None, None
        return by, value

    def get_element(self, selector, timeout=None, visible=False):
        """定位单个元素，找不到返回 None（不抛异常）。【在用，最核心的方法】

        :param selector: 元素描述，如 ['xpath', '//input[@type="text"]']
        :param timeout:  等待秒数。
                         不传  -> 用 self.timeout（默认 15 秒，带显式等待）
                         传 0  -> 立即查找，不等待（元素一定已在页面上时用，更快）
        :param visible:  True 表示要求元素「可见」而不只是「存在于 DOM」。
                         有些元素存在但被隐藏，用 visible=True 更贴近真实用户视角。
        :return: WebElement，或 None

        新人注意：本方法返回 None 而不是抛异常，调用方必须自己判空，
        否则会得到 "AttributeError: 'NoneType' object has no attribute 'click'"。
        """
        by, value = self._parse_selector(selector)
        if by is None:
            return None
        try:
            if timeout == 0:
                # 快速通道：配合 implicitly_wait(5) 生效
                element = self.driver.find_element(by, value)
            else:
                # 显式等待：比 time.sleep 更聪明，元素一出现就继续，不等满超时
                wait = WebDriverWait(self.driver, timeout or self.timeout)
                condition = (
                    EC.visibility_of_element_located((by, value))
                    if visible
                    else EC.presence_of_element_located((by, value))
                )
                element = wait.until(condition)
            log1.info('元素定位成功。定位方式：%s，使用的值：%s' % (by, value))
            return element
        except (NoSuchElementException, TimeoutException):
            log1.error('没有定位到元素,定位方式：%s，使用的值：%s' % (by, value), exc_info=1)
            return None

    def get_elements(self, selector, timeout=None):
        """定位一组元素（如表格的每一行），未找到返回空列表。【预留】

        :return: WebElement 列表；没有匹配项时返回 []，调用方无需判空
        """
        by, value = self._parse_selector(selector)
        if by is None:
            return []
        if timeout != 0:
            try:
                # 先等到至少出现一个，再整体取；避免页面没渲染完就取到空列表
                WebDriverWait(self.driver, timeout or self.timeout).until(
                    EC.presence_of_element_located((by, value))
                )
            except TimeoutException:
                log1.error('没有定位到任何元素,定位方式：%s，使用的值：%s' % (by, value))
                return []
        return self.driver.find_elements(by, value)

    def wait_element(self, selector, timeout=None, visible=False):
        """显式等待元素出现，语义上比 get_element 更强调"等待"。【预留】

        :return: WebElement 或 None
        """
        return self.get_element(selector, timeout or self.timeout, visible=visible)

    def scroll_into_view(self, element):
        """把元素滚动到浏览器可视区域中间。【在用（click 内部调用）】

        为什么需要：元素在页面下方时，Selenium 直接 click 会报
        "element not interactable"，先滚动过去就能点。
        """
        try:
            self.driver.execute_script(
                'arguments[0].scrollIntoView({block: "center"});', element
            )
        except WebDriverException:
            log1.error('滚动到元素失败', exc_info=1)

    def js_click(self, element):
        """用 JS 强制点击元素。【在用（click 降级时调用）】

        适合被其他元素遮挡、或用原生 click 报错的场景。
        缺点：绕过了真实的用户点击行为，不会触发部分浏览器原生校验，
        所以只作为兜底，不要当默认手段。
        """
        try:
            self.driver.execute_script('arguments[0].click();', element)
            log1.info('JS点击成功')
        except WebDriverException:
            log1.error('JS点击失败', exc_info=1)
            raise

    @staticmethod
    def isdisplayed(element):
        """判断元素是否可见；element 为 None 时返回 False。【预留】

        可以简化成一句断言：self.assertTrue(page.isdisplayed(element))
        """
        if element is None:
            return False
        try:
            return element.is_displayed()
        except WebDriverException:
            return False

    # ====================================================================== #
    # 三、常用交互
    # ====================================================================== #
    def type(self, selector, value, timeout=None):
        """清空输入框并输入内容。【在用】

        :param selector: 输入框的元素描述
        :param value:    要输入的内容
        :raise NoSuchElementException: 输入框不存在时抛出（而不是静默跳过），
               这样失败会明确记在测试报告里
        """
        element = self.get_element(selector, timeout if timeout is not None else self.timeout)
        if element is None:
            raise NoSuchElementException('输入框不存在，无法输入：%s' % (selector,))
        try:
            element.clear()
        except WebDriverException:
            # 有些前端框架的输入框 clear() 不生效，退化成"全选 + 删除"
            element.send_keys(Keys.CONTROL, 'a')
            element.send_keys(Keys.DELETE)
        try:
            element.send_keys(value)
            log1.info('输入的内容：%s' % value)
        except WebDriverException:
            # 输入失败立刻截图，方便回溯当时页面是什么样
            log1.error('内容输入报错', exc_info=1)
            self.get_img()
            raise

    def click(self, selector, timeout=None):
        """点击元素，失败自动降级为 JS 点击。【在用】

        内部流程：定位（带等待）-> 滚动到可视区 -> 原生点击
                  -> 报错则改用 JS 点击
        """
        element = self.get_element(selector, timeout if timeout is not None else self.timeout)
        if element is None:
            raise NoSuchElementException('元素不存在，无法点击：%s' % (selector,))
        self.scroll_into_view(element)
        try:
            element.click()
            log1.info('点击元素成功')
        except WebDriverException:
            log1.error('常规点击失败，降级为JS点击', exc_info=1)
            self.js_click(element)

    # ====================================================================== #
    # 稳定性增强：自动重试 + 防元素过期（降低 CI 上的偶发失败 flaky）
    #   Web 自动化最常见的偶发失败：元素还没渲染完、DOM 刚刷新导致引用过期、
    #   点击被临时遮罩挡住。对这些"重试一次大概率就好"的瞬时错误，
    #   框架层统一兜底重试，避免用例本身到处写 try/except。
    # ====================================================================== #
    # 默认对「瞬时错误」重试 2 次（共尝试 3 次）；可被配置 [ci] retry_times 覆盖
    DEFAULT_RETRY = 2

    def _retry_times(self):
        """读取重试次数配置，缺省用 DEFAULT_RETRY。"""
        return config.get_int('ci', 'retry_times', self.DEFAULT_RETRY)

    def retry(self, func, *args, **kwargs):
        """对瞬时错误自动重试执行 func，成功即返回，全部失败才抛出。

        会被重试的异常：StaleElementReference（元素过期）、Timeout（等太久）、
        以及其它 WebDriverException（点击被挡、元素未就绪等）。
        AssertionError / ValueError 这类「业务断言或参数错误」不重试 ——
        重试它们只会浪费时间，不会改变结果。

        :param func: 要执行的函数（通常是 lambda: self.click(sel)）
        :return: func 的返回值
        """
        times = self._retry_times()
        last_exc = None
        for attempt in range(times + 1):
            try:
                return func(*args, **kwargs)
            except (StaleElementReferenceException, TimeoutException, WebDriverException) as e:
                last_exc = e
                if attempt < times:
                    log1.warning('操作失败，第 %d/%d 次重试：%s' % (attempt + 1, times, e))
                    self.my_sleep(1)   # 给页面一点喘息时间再重试
                else:
                    log1.error('重试 %d 次后仍失败：%s' % (times, e), exc_info=1)
        raise last_exc

    def safe_click(self, selector, timeout=None):
        """带重试的点击：元素过期/被遮挡等瞬时错误会自动重试。【推荐用于易 flaky 的步骤】"""
        return self.retry(lambda: self.click(selector, timeout))

    def safe_type(self, selector, value, timeout=None):
        """带重试的输入。"""
        return self.retry(lambda: self.type(selector, value, timeout))

    def input_enter(self, txt, value, name='xpath', selector=None):
        """在输入框里输入内容后按回车（常用于搜索框）。【预留】

        :param txt:      要输入的内容
        :param value:    定位值，如 "//input[@id='q']"
        :param name:     定位方式字符串，默认 xpath
        :param selector: 也可直接传完整元素描述，传了它则忽略 name/value
        """
        if selector is not None:
            element = self.get_element(selector)
        else:
            element = self.get_element([str(name).lower(), value])
        if element is None:
            raise NoSuchElementException('输入框不存在，无法输入：%s=%s' % (name, value))
        element.clear()
        element.send_keys(txt)
        self.my_sleep(0.5)          # 给前端一点时间响应，再敲回车
        element.send_keys(Keys.ENTER)

    @staticmethod
    def my_sleep(seconds):
        """强制等待固定秒数。【在用】

        只在前端有动画、异步渲染等"无法用条件判断"的场景使用。
        能判断出条件时优先用 get_element(timeout=...)，它会提前返回、更快也更稳。
        """
        time.sleep(seconds)
        log1.info('强制等待%s秒' % seconds)

    def get_title(self):
        """获取当前窗口的页面标题（浏览器标签上那行字）。【在用】

        本工程的用例主要靠它做断言 —— 每次跳转后校验 title 是否符合预期。
        """
        title = self.driver.title
        log1.info('当前打开的title是：%s' % title)
        return title

    def get_text(self, selector, timeout=None):
        """获取元素的文本内容（页面上看得见的字）。【预留】

        常用于断言按钮文案、表格单元格内容等。
        """
        element = self.get_element(selector, timeout if timeout is not None else self.timeout)
        if element is None:
            raise NoSuchElementException('元素不存在，无法获取文本：%s' % (selector,))
        text = element.text
        log1.info('获取的text：%s' % text)
        return text

    def get_value(self, selector, timeout=None):
        """获取表单控件当前的 value（输入框里用户看到的那串字）。【通用】

        与 get_text() 的区别（新手最容易搞混的一对）：
            get_text()  读元素中间**显示的文字** —— 用在按钮、标题、表格单元格
            get_value() 读控件的 **value 属性** —— 用在 input / textarea / select

        为什么需要它：只"输入成功没报错"不等于"值真的填进去了"，
        校验"输入是否生效""重置后是否真的清空"必须读到值才算验证过。

        :return: value 字符串；元素没有 value 属性时返回 None
        """
        element = self.get_element(selector, timeout if timeout is not None else self.timeout)
        if element is None:
            raise NoSuchElementException('元素不存在，无法获取它的值：%s' % (selector,))
        value = element.get_attribute('value')
        log1.info('获取的value：%s' % value)
        return value

    def use_js(self, js):
        """执行任意 JS 脚本。【预留】

        用途举例：直接改元素属性、去掉只读限制、滚动整页等。
        """
        try:
            self.driver.execute_script(js)
            log1.info('js执行成功，js内容为：%s' % js)
        except WebDriverException:
            log1.error('js执行报错', exc_info=1)
            raise

    # ====================================================================== #
    # 四、窗口 / frame 切换（多标签页、内嵌 iframe 的必用技能）
    # ====================================================================== #
    def switch_menue(self, parentelement, secelement, targetelement):
        """依次点击一级、二级、三级菜单完成页面切换。【预留】

        :param parentelement: 一级菜单元素
        :param secelement:    二级菜单元素
        :param targetelement: 三级菜单元素
        """
        self.my_sleep(3)
        try:
            # 先回到最外层文档，避免上一次操作还停留在 iframe 里导致定位失败
            self.driver.switch_to.default_content()
            self.click(parentelement)
            log1.info('成功点击一级菜单：%s' % parentelement)
            self.click(secelement)
            log1.info('成功点击二级菜单：%s' % secelement)
            self.click(targetelement)
            log1.info('成功点击三级菜单：%s' % targetelement)
        except BaseException:
            log1.error('切换菜单报错', exc_info=1)

    def switch_iframe(self, selector):
        """切换到指定的 iframe 内部（切换后定位范围只剩这个框架）。【预留】

        切进去之后想操作主页面，必须先 switch_default_content() 回来。
        """
        element = self.get_element(selector)
        if element is None:
            raise NoSuchElementException('frame 不存在，无法切换：%s' % (selector,))
        self.driver.switch_to.frame(element)
        log1.info('切换frame成功')

    # 兼容旧命名：原工程把 iframe 拼成了 ifarme，老代码可能还在用这个别名
    switch_ifarme = switch_iframe

    def switch_default_content(self):
        """从 iframe 回到最外层文档。【预留】

        对应 Selenium 3 的 switch_to_default_content()，
        该方法在 Selenium 4 已被移除，必须写成 switch_to.default_content()。
        """
        self.driver.switch_to.default_content()
        log1.info('回到最外层文档')

    def get_handle(self):
        """获取当前窗口的唯一标识 handle。【预留】

        每个标签页都有自己的 handle，用于切换和返回。
        """
        return self.driver.current_window_handle

    def chage_handle(self, handle):
        """切换到非当前的其他窗口（旧命名，现保留兼容）。【预留】

        拼写 typo 已修正为 switch_other_window，新代码请用后者。
        """
        return self.switch_other_window(handle)

    def switch_other_window(self, handle=None):
        """切换到另一个标签页并返回新窗口的 handle。【在用】

        典型场景：从门户点进业务系统，页面在新标签页打开，
        必须切过去才能继续操作（本工程 test_2select_scxt 就是这么做的）。

        :param handle: 当前窗口 handle；不传则自动取当前窗口
        :return: 新窗口 handle；没有其他窗口时返回 None
        """
        current = handle or self.driver.current_window_handle
        for item in self.driver.window_handles:
            if item != current:
                self.driver.switch_to.window(item)
                log1.info('切换到窗口：%s' % item)
                return item
        log1.error('没有找到其他可切换的窗口')
        return None

    # ====================================================================== #
    # 五、文件上传（本工程业务重点：上传视频到素材库）
    # ====================================================================== #
    def files_upload(self, selector, file_path=None):
        """通过给 input[type=file] 赋值来选择文件。【在用，推荐方案】

        为什么这么做：点击"上传"按钮会弹出 Windows 原生对话框，
        那是操作系统窗口，Selenium 管不了，只能借助 autoit 这类工具模拟键盘。
        而给隐藏的 file 控件直接 send_keys(路径) 可以绕过整个弹窗流程，
        更快、更稳，也不依赖 Windows。

        :param selector:  file 控件的元素描述，通常是 Element1.FileInput
        :param file_path: 文件绝对路径；不传则读 config.ini -> [testcase] upload_file
        :raise FileNotFoundError: 文件不存在时抛出，避免用例"假成功"
        """
        file_path = file_path or config.get('testcase', 'upload_file')
        if not file_path:
            raise ValueError('未配置上传文件路径（config.ini -> [testcase] upload_file）')
        # expanduser 支持 ~/ 开头；abspath 保证 Selenium 拿到的是绝对路径
        file_path = os.path.abspath(os.path.expanduser(file_path))
        if not os.path.exists(file_path):
            raise FileNotFoundError('上传文件不存在：%s' % file_path)
        element = self.get_element(selector)
        if element is None:
            raise NoSuchElementException('未找到文件上传控件：%s' % (selector,))
        element.send_keys(file_path)
        log1.info('上传文件：%s' % file_path)
        self.my_sleep(1)   # 等上传组件响应文件选择

    def upload_by_autoit(self, file_path=None, window_title='打开'):
        """备选方案：用 autoit 操作 Windows「打开」对话框。【在用（降级分支）】

        仅在 files_upload 失败时作为兜底，需要 pip install PyAutoIt。
        :param window_title: 对话框标题，中文系统下是「打开」，英文系统需改成 Open
        """
        if not AUTOIT_AVAILABLE:
            raise RuntimeError('未安装 PyAutoIt，无法使用 autoit 上传；请改用 files_upload()')
        file_path = file_path or config.get('testcase', 'upload_file')
        autoit.win_wait_active(window_title, 3)                      # 等对话框出现（最多3秒）
        autoit.win_activate(window_title)                            # 激活到前台
        autoit.control_focus(window_title, '[class:Edit; instance:1]')  # 聚焦文件名输入框
        time.sleep(1)
        autoit.control_send(window_title, '[class:Edit; instance:1]', file_path)  # 输入路径
        time.sleep(2)
        autoit.control_click(window_title, '[class:Button; instance:1]')         # 点「打开」
        log1.info('autoit 上传文件：%s' % file_path)

    # ====================================================================== #
    # 六、截图与弹窗
    # ====================================================================== #
    def get_img(self):
        """截取当前页面并保存到 img/日期/ 下，返回图片路径。【在用】

        命名规则：img/2026-09-25/2026-09-25 120718.png（秒级时间戳，天然不重名）
        用例断言失败时会自动调用它，是最常用的排错线索。
        """
        img_path = os.path.join(getcwd.get_cwd(), 'img')
        local_date = time.strftime('%Y-%m-%d', time.localtime(time.time()))
        date_file_path = os.path.join(img_path, local_date)
        if not os.path.exists(date_file_path):
            os.makedirs(date_file_path)
        local_time = time.strftime('%Y-%m-%d %H%M%S', time.localtime(time.time()))
        jt_path = os.path.join(date_file_path, local_time + '.png')
        try:
            self.driver.get_screenshot_as_file(jt_path)
            log1.info('截图保存成功：%s' % jt_path)
            return jt_path
        except BaseException:
            # 截图本身失败不应该中断用例，只记日志
            log1.error('截图失败', exc_info=1)
            return None

    def popout(self):
        """接受（点击"确定"）浏览器原生 alert 弹窗。【预留】

        注意：alert 属于浏览器原生弹窗，不是页面 DOM 元素，
        必须先 switch_to.alert 再调用 accept()，直接 find_element 是找不到的。
        """
        alert = self.driver.switch_to.alert
        alert.accept()
        log1.info('已接受 alert 弹窗')

    # ====================================================================== #
    # 七、跨系统通用能力（让本框架能适配任意主流 Web 系统）
    #   设计目标：党政 / 财务 / ERP / 商城 / 数据中台等系统虽然业务不同，
    #   但底层 UI 模式高度相似 —— 都有"按文字点按钮/菜单、按占位符填输入框、
    #   选下拉、等加载遮罩消失、按单元格定位表格行"。把这些通用模式沉淀在这里，
    #   接入一个新系统时，页面对象直接调用即可，无需为每个系统重复造轮子。
    #   全部方法与现有方法一样：找不到元素返回 None / 记日志，不随意抛异常。
    # ====================================================================== #
    def _xpath_norm(self, text):
        """把文本里的单引号转义成 XPath 兼容写法（concat 拼接），避免引号破坏 xpath。"""
        if "'" not in text:
            return "'%s'" % text
        # 含单引号时，用 concat 把每段包成双引号字符串再拼起来
        parts = text.split("'")
        return "concat(%s)" % ", \"'\", ".join("'%s'" % p for p in parts)

    def get_element_by_text(self, text, tag='*', timeout=None, contains=False):
        """按「可见文本」定位元素（最通用、最不依赖具体 DOM 结构的定位方式）。【通用】

        几乎所有系统都能用它点按钮、菜单、tab、链接。优先于脆弱的绝对 xpath。
        :param text:     要匹配的可见文本
        :param tag:      限定标签，如 'button'/'a'/'span'，默认 '*' 不限
        :param timeout:  等待秒数，默认取类属性 timeout
        :param contains: True=文本包含即可（模糊），False=精确等于文本
        :return: WebElement 或 None
        """
        timeout = timeout if timeout is not None else self.timeout
        if contains:
            xp = "//%s[contains(normalize-space(.), %s)]" % (tag, self._xpath_norm(text))
        else:
            xp = "//%s[normalize-space(.)=%s]" % (tag, self._xpath_norm(text))
        try:
            el = WebDriverWait(self.driver, timeout).until(
                EC.presence_of_element_located((By.XPATH, xp)))
            log1.info('按文本定位成功：text=%s tag=%s' % (text, tag))
            return el
        except TimeoutException:
            log1.error('按文本未找到元素：text=%s tag=%s' % (text, tag))
            return None

    def click_by_text(self, text, tag='*', timeout=None, contains=False):
        """按可见文本点击元素（按钮/菜单/链接/tab）。【通用，推荐】

        内部先尝试 WebElement.click()，失败自动降级为 JS 点击（与 click() 一致）。
        """
        el = self.get_element_by_text(text, tag=tag, timeout=timeout, contains=contains)
        if el is None:
            return False
        try:
            el.click()
            log1.info('按文本点击成功：%s' % text)
            return True
        except WebDriverException:
            try:
                self.driver.execute_script('arguments[0].click();', el)
                log1.info('按文本点击（JS 降级）成功：%s' % text)
                return True
            except WebDriverException:
                log1.error('按文本点击失败：%s' % text, exc_info=1)
                return False

    def get_element_by_attr(self, attr, value, tag='*', timeout=None):
        """按「属性=值」定位元素，最常用于按 placeholder 找输入框。【通用】

        例如 get_element_by_attr('placeholder', '请输入用户名') 可跨系统复用，
        因为 placeholder 文案通常稳定，比绝对 xpath 抗改版。
        """
        timeout = timeout if timeout is not None else self.timeout
        xp = "//%s[@%s=%s]" % (tag, attr, self._xpath_norm(value))
        try:
            el = WebDriverWait(self.driver, timeout).until(
                EC.presence_of_element_located((By.XPATH, xp)))
            log1.info('按属性定位成功：@%s=%s' % (attr, value))
            return el
        except TimeoutException:
            log1.error('按属性未找到元素：@%s=%s' % (attr, value))
            return None

    def type_by_placeholder(self, placeholder, value, clear=True, tag='input'):
        """按 placeholder 定位输入框并输入（适用于绝大多数表单页）。【通用】

        :param placeholder: 输入框占位提示文案
        :param value:       要输入的文本
        :param clear:       输入前是否清空（默认清空）
        """
        el = self.get_element_by_attr('placeholder', placeholder, tag=tag)
        if el is None:
            raise NoSuchElementException('未找到 placeholder=%s 的输入框' % placeholder)
        if clear:
            el.clear()
        el.send_keys(value)
        log1.info('按 placeholder 输入：%s -> %s' % (placeholder, value))

    def select_option(self, selector, text=None, value=None, index=None):
        """操作原生 <select> 下拉框，按可见文本/值/序号三选一。【通用】

        注意：只适用于原生 select；若系统用 div 模拟下拉（很多后台如此），
        请改用 click_by_text 先展开再点选项。
        """
        from selenium.webdriver.support.ui import Select
        el = self.get_element(selector)
        if el is None:
            raise NoSuchElementException('未找到下拉框：%s' % (selector,))
        sel = Select(el)
        if text is not None:
            sel.select_by_visible_text(text)
            log1.info('下拉选择(文本)：%s' % text)
        elif value is not None:
            sel.select_by_value(value)
            log1.info('下拉选择(值)：%s' % value)
        elif index is not None:
            sel.select_by_index(index)
            log1.info('下拉选择(序号)：%s' % index)
        else:
            raise ValueError('select_option 必须传 text / value / index 之一')

    def wait_loading_gone(self, selector=None, timeout=15, poll_frequency=0.3):
        """等待「加载遮罩/转圈」消失后再继续。【通用】

        几乎所有后台系统点查询/保存后都会出现 loading 遮罩，
        不等待就去操作下一个元素极易偶发失败。
        :param selector: 遮罩元素的定位描述；不传则用默认 xpath（含常见 loading 文案）
        """
        if selector is None:
            # 常见 loading 特征：class 含 loading / 文本含"加载中"
            selector = ['xpath', '//*[contains(@class,"loading") or contains(normalize-space(.),"加载中")]']
        end_time = time.time() + timeout
        while time.time() < end_time:
            els = self.driver.find_elements(*selector) if isinstance(selector, (list, tuple)) \
                else self.driver.find_elements(By.XPATH, selector if isinstance(selector, str) else selector[1])
            if not els or not els[0].is_displayed():
                log1.info('加载遮罩已消失')
                return True
            time.sleep(poll_frequency)
        # 超时不抛异常（避免用例因网络慢整体崩），仅记日志，交给后续断言去判定
        log1.error('等待加载遮罩消失超时(%ss)，继续执行后续步骤' % timeout)
        return False

    def get_table_rows(self, table_selector=None):
        """获取页面上所有 <tr> 行元素（表格数据断言/按行操作的基础）。【通用】

        :param table_selector: 限定某个表格的定位描述；不传则取全页所有 tr
        """
        if table_selector is None:
            return self.driver.find_elements(By.XPATH, '//tr')
        tbl = self.get_element(table_selector)
        if tbl is None:
            return []
        return tbl.find_elements(By.XPATH, './/tr')

    def find_row_by_cell_text(self, text, table_selector=None):
        """在表格中查找「某个单元格包含指定文本」的那一行，返回 tr 元素。【通用】

        数据中台/ERP/商城的列表页都靠它定位要操作的记录（点编辑/删除前先找到行）。
        """
        for tr in self.get_table_rows(table_selector):
            if text in (tr.text or ''):
                return tr
        log1.error('表格中未找到含文本 %s 的行' % text)
        return None

    def hover(self, selector):
        """鼠标悬停到元素上（触发下拉菜单、二级导航展开）。【通用】"""
        from selenium.webdriver.common.action_chains import ActionChains
        el = self.get_element(selector)
        if el is None:
            raise NoSuchElementException('未找到要悬停的元素：%s' % (selector,))
        ActionChains(self.driver).move_to_element(el).perform()
        log1.info('已悬停到元素：%s' % (selector,))

    def scroll_to(self, selector):
        """滚动到元素可见（列表很长时，目标元素在视口外点不到）。【通用】"""
        el = self.get_element(selector)
        if el is None:
            raise NoSuchElementException('未找到要滚动到的元素：%s' % (selector,))
        self.driver.execute_script('arguments[0].scrollIntoView({block:"center"});', el)
        log1.info('已滚动到元素：%s' % (selector,))
