# -*- coding: utf-8 -*-
"""
==========================================================================
 用例层：主业务流（新人阅读顺序：第 1 个，先看这里）
==========================================================================

【一句话说明】
    本工程最主要的测试文件，用 6 条用例走完
    「登录 -> 进系统 -> 进业务页 -> 上传素材 -> 查询 -> 报送」整条业务链。
    想了解这个工程在测什么，读这个文件就够了。

    ★ 它是「示例业务」，不是「框架的一部分」：
      换被测系统时，通常整个替换掉本文件（连同 PageObject/ 与元素表），
      框架层 Common/ 一行都不用改。

============== 业务流程（6 条用例的执行顺序） ==============

    用例1 test_1login          登录并进入首页
              │                断言 title == [assert] title_login
              ▼
    用例2 test_2select_scxt    点入口并切到新打开的标签页
              │                断言 title == [assert] title_workbench
              ▼
    用例3 test_3material       左侧菜单进入素材库/业务页
              │                断言 title == [assert] title_material
              ▼
    用例4 test_4uplaodbutton   选本地视频 → 填作者/手机号/上报单位
              │                → 上传 → 确定
              │                断言 title == [assert] title_material
              ▼
    用例5 test_5keyword        关键字查询 → 重置
              │                断言 title == [assert] title_material
              ▼
    用例6 test_6submitted      刷新 → 报送 → 选初审人 → 保存
                               断言 title == [assert] title_material

===========================================================

【★★★ 本工程的一条硬规则：代码里不许有业务数据 ★★★】

    整个框架代码（Common/ / PageObject/ / TestSuites/）**不允许**出现
    任何具体被测系统的业务数据：页面标题、查询关键字、上报单位、手机号、
    报告名称…… 一律只能来自 config.ini。换系统 / 换环境时只改配置，
    一个 .py 文件都不用动。

    为什么这么严格（这是踩过的坑）：
        如果代码里留着"兜底默认值"，换系统后忘了改配置，框架就会拿着
        上一个系统的标题去比对，报出

            期望[旧系统首页] 实际[新系统首页]

        这种完全看不出原因的失败 —— 真实原因（配置没跟着换）被彻底���盖，
        排查的人会误以为是页面改版或元素定位失效，往错的方向查很久。

    所以本文件一律用 Config.get_required() / get_assert_value()：
        配置齐全 -> 正常运行
        配置缺失 -> 立刻抛出可读错误，明确告诉你去 config.ini 哪一段补哪个键

    报错消息长这样：
        缺少必填配置 [assert] title_login（登录后首页标题）。
          1. 在 config.ini 的 [assert] 段补上  title_login = 实际值
          2. 设置环境变量（CI 推荐，不落仓库）：  set UI_ASSERT_TITLE_LOGIN=实际值
          3. 若该项目有环境档位，可用命令行指定：  python run.py --env 档位名

    ★ 这条规则由单元测试把守：tests/test_test_login_suite.py 会扫描本文件源码，
      发现业务字面量就让测试变红。

===========================================================

【配置项清单：本文件用到的全部配置（缺一即中止）】

    [testcase] login_username   登录账号
    [testcase] login_password   登录密码
    [testcase] upload_file       待上传文件的绝对路径（仅 test_4 需要）
    [testcase] video_author      上传表单-作者（仅 test_4 需要）
    [testcase] phone             上传表单-手机号（仅 test_4 需要）
    [testcase] reporting         上传表单-上报单位（仅 test_4 需要）
    [testcase] query_keyword     查询关键字（仅 test_5 需要）
    [assert]   title_login       登录后断言的标题
    [assert]   title_workbench   进入工作台后断言的标题
    [assert]   title_material    进入业务页后断言的标题

    全部支持环境变量覆盖：UI_TESTCASE_XXX / UI_ASSERT_XXX

    【为什么分两批读取】
        账号与三个标题期望值在 setUpClass 里一次性读（每条用例都要用）。
        表单字段与查询关键字**延迟到用例里现取**——因为只跑冒烟集（前 3 条）
        时根本不需要它们，放前���统一读会导致"没配手机号连冒烟都跑不了"。

===========================================================

【新人必读：四条设计约定】

1）为什么 6 条用例共用同一个浏览器？
    因为它们是**一条串行业务流**，第 4 步上传必须有第 3 步的登录态，
    拆开各自 setUp/tearDown 反而要多登 6 次、跑得更慢也更稳。
    做法：setUpClass 只开一次浏览器，tearDownClass 统一关闭。

2）为什么方法名是 test_1login、test_2select_scxt 这种带数字的？
    unittest 默认按方法名字母序执行，加数字前缀就是**为了固定执行顺序**。
    改动方法名会改变执行顺序，进而让用例失败 —— 名字不要随便动。
    另外这也意味着：**不能单独跑某一条中间用例**（比如只跑 test_5keyword），
    因为它依赖前面已经登录并进入素材库。

3）为什么断言都在 check_title() 里？
    6 条用例的断言方式完全一样（校验页面标题），统一抽成一个方法后，
    只在一个地方加"失败自动截图"，改动成本最低。
    新增用例时直接调 self.check_title('用例名', 期望标题) 即可。

4）为什么前 3 条有 @readonly 而后 3 条没有？
    这是**作用域标记**，用来区分"这条用例会不会改动真实数据"：
        test_1/2/3  只是登录、跳页 -> 标 @readonly，生产环境也敢跑
        test_4      真实上传视频    -> 写
        test_5      查询本身只读，但它依赖 test_4 刚上传的素材才能验证，
                    单独放到生产环境跑没有意义，所以也留在「写」这一组
        test_6      真实提交报送单  -> 写
    框架据此做两件事：
        ① config.ini [testcase] mode = readonly 时，自动跳过写用例；
        ② 环境守卫发现"疑似生产 + 含写用例"时直接中止（退出码 2）。
    详见 Common/testcase_meta.py 与 Common/env_guard.py。
    ★ 新增用例时先问自己两句：页面数据会不会变？会不会依赖前面用例的产物？
      两个都否，才加 @readonly。

【新人注意】
    1. 参数全部来自 config.ini，绝不在用例里硬编码账号、路径或期望标题。
    2. 被测地址若是生产环境，跑全量会真实上传/报送；只读跑法：
       python run.py --env test        # 用 [env_test] 档，自带 mode = readonly
    3. 用例之间没有数据隔离，任何一步失败，后面的用例会连着失败 ——
       排错时优先修最早失败的那一条。
    4. 排查失败：先看控制台输出的「失败摘要」，再看 Logs/日期/Error_Logs/，
       最后看 Report/artifacts/日期/（框架自动保存的失败截图 + 页面源码）。
==========================================================================
"""

import unittest

from Common.basePage import BasePage
from Common.config import Config
from Common.log import log1
from Common.testcase_meta import readonly
from PageObject.loginPage import LoginPage


class TestLogin(unittest.TestCase):
    """主业务流测试用例集：登录 -> 进系统 -> 进业务页 -> 上传 -> 查询 -> 报送。

    一个 TestCase 类 = 一组有共同前置条件的用例；
    这里的共同前置条件就是"浏览器已打开、且处于登录后的状态"。

    ★ 本类不含任何业务数据字面量 —— 全部来自 config.ini，
      详见模块头「本工程的一条硬规则：代码里不许有业务数据」。
    """

    # 类属性：保存打开的浏览器实例，供各用例共享
    # （在 setUpClass 里赋值，在 tearDownClass 里关闭）
    driver = None

    # ---------------------------------------------------------------------- #
    # 前置 / 后置：整个类只执行一次（区别于每条用例都跑的 setUp / tearDown）
    # ---------------------------------------------------------------------- #
    @classmethod
    def setUpClass(cls):
        """类级前置：读必填参数 -> 开浏览器 -> 建页面对象。只执行一次。

        这里只读**每条用例都要用**的参数（账号 + 三个断言期望标题）。
        表单字段与查询关键字在各自用例里现取，避免"没配手机号连冒烟都跑不了"。

        :raise ValueError: 必填配置缺失时抛出，消息里写明该改 config.ini 哪一段。
                          此时浏览器还没打开，不会产生任何副作用。
        """
        # ---- 1. 必填参数：账号与断言期望值（缺失立即中止）----
        cls.username, cls.password = Config.get_account()
        cls.title_login = Config.get_assert_value('title_login', '登录后首页标题')
        cls.title_workbench = Config.get_assert_value('title_workbench', '进入工作台后的标题')
        cls.title_material = Config.get_assert_value('title_material', '进入素材库/业务页后的标题')

        # ---- 2. 打开浏览器并访问被测地址 ----
        cls.base = BasePage()# 基类实例，只用来管浏览器生命周期
        cls.driver = cls.base.open_browser()        # 返回 driver，并保存在 cls.base.driver

        # ---- 3. 创建页面对象，后续所有用例共用它 ----
        cls.login_page = LoginPage(cls.driver)

    @classmethod
    def tearDownClass(cls):
        """类级后置：关闭浏览器，避免残留 chrome 进程。"""
        cls.base.dr_quit()

    # ---------------------------------------------------------------------- #
    # 自定义断言：把"校验标题"这件事收敛到一个地方
    # ---------------------------------------------------------------------- #
    def check_title(self, case_name, expected):
        """断言当前页面标题等于预期值，并统一记录用例结果。

        :param case_name: 用例中文名，只用于日志可读性
        :param expected:  期望的页面标题（来自 config.ini [assert]）
        :raise AssertionError: 标题不符时抛出 —— 用例会被报告标记为「失败」

        成功：写一条 INFO 日志
        失败：写 ERROR 日志（含 期望/实际 对比）+ 自动截图，再抛出异常
        """
        actual = self.login_page.get_title()
        try:
            self.assertEqual(actual, expected)
        except AssertionError:
            log1.error('测试用例执行失败:%s，期望[%s] 实际[%s]\n' % (case_name, expected, actual))
            # 关键：失败瞬间截图。这是排查问题最有效的证据
            self.login_page.get_img()
            raise
        log1.info('测试用例执行成功:%s\n' % case_name)

    # ====================================================================== #
    # 用例（执行顺序由方法名 test_N 前缀固定，不要随意改名）
    #
    # ★ 作用域标记说明（见 Common/testcase_meta.py）
    #   前 3 条标了 @readonly：它们只做登录和页面跳转，不产生任何业务数据，
    #     所以在生产环境也能安全执行 —— 这也是冒烟集敢取前 3 条的原因。
    #   后 3 条没标：上传视频、提交报送单都会真实改动数据，
    #     保持默认的「写」作用域，在生产特征的环境下会被环境守卫拦下。
    #   新增用例时照这个标准判断：页面数据会不会变？会变就别加 @readonly。
    # ====================================================================== #
    @readonly
    def test_1login(self):
        """用例1：登录成功（只读）。

        步骤：输入账号密码 -> 点登录 -> 校验跳转到首页。
        期望标题取自 config.ini -> [assert] title_login。
        """
        case_name = '登录成功'
        log1.info('执行测试用例：%s' % case_name)
        self.login_page.login(self.username, self.password)
        self.check_title(case_name, self.title_login)

    @readonly
    def test_2select_scxt(self):
        """用例2：从门户进入业务系统（只读）。

        步骤：点入口（会新开标签页）-> 切到新标签页 -> 等页面加载 -> 校验标题。

        注意：switch_other_window() 是必须的，不切窗口的话
        后续所有元素定位都会在旧标签页上失败。
        期望标题取自 config.ini -> [assert] title_workbench。
        """
        case_name = '进入业务系统'
        log1.info('执行测试用例：%s' % case_name)
        self.login_page.click_sign_in()
        self.login_page.switch_other_window()   # 切到新打开的标签页
        self.login_page.my_sleep(2)             # 等新页面首屏渲染
        self.check_title(case_name, self.title_workbench)

    @readonly
    def test_3material(self):
        """用例3：进入素材库/业务页（只读）。

        步骤：左侧菜单进入目标页 -> 校验标题。
        期望标题取自 config.ini -> [assert] title_material。
        """
        case_name = '进入素材库'
        log1.info('执行测试用例：%s' % case_name)
        self.login_page.my_sleep(3)             # 等工作台的菜单加载完
        self.login_page.click_material()
        self.login_page.my_sleep(2)
        self.check_title(case_name, self.title_material)

    def test_4uplaodbutton(self):
        """用例4：上传视频到素材库（本工程最核心的用例）。

        步骤：选本地文件 -> 等上传组件就绪 -> 填表单（作者/手机号/上报单位）
              -> 上传 -> 收起文件列表 -> 确定。
        校验：上传是弹窗操作，页面不会跳转，因此仍校验标题未变。

        表单字段全部现取自 config.ini -> [testcase]，缺一项就在这里明确报错，
        而不是留个代码默认值硬填。
        前置条件：upload_file 指向的文件必须真实存在，否则以FileNotFoundError 失败。
        """
        case_name = '上传视频'
        log1.info('执行测试用例：%s' % case_name)
        # ---- 表单字段：延迟到本用例才读，缺失才报错（冒烟集不涉及它们）----
        video_author = Config.get_form_field('video_author', '上传表单的视频作者')
        phone = Config.get_form_field('phone', '上传表单的手机号')
        reporting = Config.get_form_field('reporting', '上传表单的上报单位')

        self.login_page.upload_file(Config.get_upload_file())   # 选择文件（send_keys 或 autoit）
        self.login_page.my_sleep(3)                       # 等上传组件识别到文件
        self.login_page.fill_upload_form(video_author, phone, reporting)
        self.login_page.my_sleep(5)                       # 等上传进度走完
        self.check_title(case_name, self.title_material)

    def test_5keyword(self):
        """用例5：关键字查询素材。

        步骤：输入关键字 -> 点查询 -> 点重置恢复初始列表。
        校验：查询是页内操作，标题不变。

        关键字取自 config.ini -> [testcase] query_keyword。
        """
        case_name = '关键字查询'
        log1.info('执行测试用例：%s' % case_name)
        query_keyword = Config.get_form_field('query_keyword', '素材查询关键字')
        self.login_page.keyword_query(query_keyword)
        self.login_page.my_sleep(3)                       # 等查询结果返回
        self.check_title(case_name, self.title_material)

    def test_6submitted(self):
        """用例6：把素材报送进审核流程。

        步骤：刷新页面拿到最新素材列表 -> 点第一行的「报 送」-> 选初审人 -> 保存。
        校验：报送是弹窗流程，标题不变。

        注意：这里直接用了 self.driver.refresh()，
        属于绕过页面对象的分层写法，属于历史遗留，后续可补一个 refresh() 到 BasePage。
        """
        case_name = '报送'
        log1.info('执行测试用例：%s' % case_name)
        self.driver.refresh()                             # 刷新，确保能看到刚上传的素材
        self.login_page.my_sleep(5)
        self.login_page.submitted()
        self.login_page.my_sleep(2)
        self.check_title(case_name, self.title_material)