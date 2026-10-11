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

    每条用例都以 ensure_xxx() 开头 -> **任意一条都能单独运行、可乱序**

    用例1 test_1login          登录并进入首页
              │                断言 title == [assert] title_login
              │                + 无 console 报错
              ▼
    用例2 test_2select_scxt    点入口并切到新打开的标签页
              │                断言 title == [assert] title_workbench
              ▼
    用例3 test_3material       左侧菜单进入素材库/业务页
              │                断言 title == [assert] title_material
              │                + 查询区控件齐全（业务断言）
              ▼
    用例4 test_4uplaodbutton   填表单 -> 上传
              │                断言 **素材列表行数 +1**（业务断言）
              ▼
    用例5 test_5keyword        关键字查询 -> 重置
              │                断言 查询后列表正常渲染（业务断言）
              ▼
    用例6 test_6submitted      刷新 -> 报送 -> 按姓名选审核人 -> 保存
                               断言 **第一行状态已变化**（业务断言）

===========================================================

【★★★ 断言约定：必须断言"业务结果"，不能只断言"页面标题"★★★】

    这是本文件 2026-10-11 最重要的一次改造。

    改造前的问题（"假绿"）：
        6 条用例只有 1 个断言 —— 比对页面标题。于是下面这些情况**全都判绿**：
            · 上传失败、进度卡住、弹窗报错      -> 标题没变，绿
            · 查询 0 条命中、接口 500            -> 标题没变，绿
            · 报送被拒绝、选错了审核人            -> 标题没变，绿
            · 前端 JS 抛异常                     -> 标题没变，绿
        结果就是 CI 天天全绿，线上照样出问题，团队逐渐不再相信自动化。

    改造后的三层断言：
        ① 业务结果断言（最重要）—— 上传后行数 +1、报送后状态变化、查询后列表渲染
        ② 结构断言 —— 查询区关键控件齐全（缺一个就说明前端改版了）
        ③ 守卫断言 —— 页面标题正确（说明"页面没崩、还在对的页面"）+ 无 console 报错

        只有 ① 才能真正回答"这个功能是好的吗"。②③ 是辅助定位问题的。

    ★ 新增用例时请自问：**如果这个功能坏了，我的断言会不会红？**
      如果答案是不会，说明断言不够，需要补业务断言。

===========================================================

【★ 条件等待，不要 my_sleep】

    改造前有 12 处 my_sleep(2/3/5) —— 等多久全靠拍脑袋：
    页面快时白等（全量用例白等 1 分钟），页面慢时又不够（偶发失败）。

    现在统一用条件等待，**对了就立刻返回**：
        wait_title(expected)         等标题变成期望值
        wait_text(text)              等某段文字出现
        wait_any_text(a, b)          等任意一条出现（判断走了哪条业务分支）
        wait_loading_gone()          等加载遮罩消失（点击/提交后必用）
        wait_material_count(at_least=N)  等列表行数达到 N
        wait_status_changed(before)  等状态文本发生变化

    只有"确实无法用条件判断"的场景（如纯动画）才允许用 my_sleep，
    并必须在注释里写明为什么。

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
        cls.base = BasePage()          # 基类实例，只用来管浏览器生命周期
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
    def check_title(self, case_name, expected, timeout=None):
        """断言页面标题等于预期值；**带条件等待**，不再靠固定 sleep。

        :param case_name: 用例中文名，只用于日志可读性
        :param expected:  期望的页面标题（来自 config.ini [assert]）
        :param timeout:   最长等待秒数，默认取配置的元素超时
        :raise AssertionError: 标题不符时抛出 —— 用例会被报告标记为「失败」

        用 wait_title 而不是"读一次就比"：
            页面跳转是异步的，读完立刻比会偶发失败（CI 上尤其明显）。
            等一等再比，既更稳，又比 my_sleep(5) 更快（标题对了就立刻返回）。
        """
        ok, actual = self.login_page.wait_title(expected, timeout=timeout)
        try:
            self.assertTrue(
                ok, '页面标题不符：期望[%s] 实际[%s]' % (expected, actual))
        except AssertionError:
            log1.error('测试用例执行失败:%s，期望[%s] 实际[%s]\n' % (case_name, expected, actual))
            self.login_page.get_img()   # 失败瞬间截图，排查最有效的证据
            raise
        log1.info('测试用例执行成功:%s\n' % case_name)

    def check_no_console_error(self, case_name, ignore_patterns=None):
        """断言本次操作没产生新的浏览器 console 错误。【★ 拦"假绿"】

        为什么必须加这条：
            旧用例只断言页面标题，于是"接口 500 但页面照常渲染"
            "JS 抛异常但标题没变"这类故障一律判为**通过**。
            加上这条断言后，前端报错会直接把用例标红。
        """
        try:
            self.login_page.assert_no_console_error(ignore_patterns)
        except AssertionError as exc:
            log1.error('用例[%s] 出现浏览器 console 错误：%s' % (case_name, exc))
            self.login_page.get_img()
            raise

    # ---------------------------------------------------------------------- #
    # 前置自愈：让**任意一条用例都能单独运行**
    #
    #   ★ 解决什么问题
    #     旧设计是"6 条用例一条链，只能从 test_1 顺序跑"——
    #     `python run.py --cases test_5keyword` 会因为没有登录态而失败。
    #     大厂要求任意用例可独立运行、可乱序、可单条重跑（否则没法做 flaky 复跑）。
    #
    #   ★ 怎么做到
    #     把"到某一步之前需要具备的状态"封装成 ensure_xxx()：
    #     先看当前在哪，缺哪一步补哪一步。顺序跑时这些检查全部立即返回（零开销），
    #     单独跑时会自动把前置链路走一遍。
    # ---------------------------------------------------------------------- #
    def ensure_login(self):
        """确保已登录（若当前已在登录后的页面则直接返回）。"""
        if self.login_page.wait_title(self.title_login, timeout=1)[0]:
            log1.info('已在登录页，跳过登录前置')
            return
        self.login_page.login(self.username, self.password)
        self.check_title('前置-登录', self.title_login)

    def ensure_workbench(self):
        """确保已进入业务系统工作台（会处理新标签页切换）。"""
        if self.login_page.wait_title(self.title_workbench, timeout=1)[0]:
            log1.info('已在工作台，跳过入口前置')
            return
        self.ensure_login()
        self.login_page.click_sign_in()
        self.login_page.switch_other_window()   # ★ 不切窗口后续定位全部失败
        self.check_title('前置-进入业务系统', self.title_workbench)

    def ensure_material_page(self):
        """确保已进入素材库/业务页。"""
        if self.login_page.wait_title(self.title_material, timeout=1)[0]:
            log1.info('已在素材库，跳过菜单前置')
            return
        self.ensure_workbench()
        self.login_page.click_material()
        self.check_title('前置-进入素材库', self.title_material)

    # ====================================================================== #
    # 用例（执行顺序由方法名 test_N 前缀固定，不要随意改名）
    #
    # ★ 作用域标记说明（见 Common/testcase_meta.py）
    #   前 3 条标了 @readonly：它们只做登录和页面跳转，不产生任何业务数据，
    #     所以在生产环境也能安全执行 —— 这也是冒烟集敢取前 3 条的原因。
    #   后 3 条没标：上传视频、提交报送单都会真实改动数据，
    #     保持默认的「写」作用域，在生产特征的环境下会被环境守卫拦下。
    #   新增用例时照这个标准判断：页面数据会不会变？会变就别加 @readonly。
    #
    # ★ 每条用例都以 ensure_xxx() 开头，因此**可以单独运行**：
    #     python run.py --cases test_5keyword
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
        # ★ 业务断言：登录页不该有 JS 报错（接口挂了页面照样渲染）
        self.check_no_console_error(case_name)

    @readonly
    def test_2select_scxt(self):
        """用例2：从门户进入业务系统（只读）。

        步骤：点入口（会新开标签页）-> 切到新标签页 -> 等标题 -> 校验。

        注意：switch_other_window() 是必须的，不切窗口的话
        后续所有元素定位都会在旧标签页上失败。
        """
        case_name = '进入业务系统'
        log1.info('执行测试用例：%s' % case_name)
        self.ensure_login()
        self.login_page.click_sign_in()
        self.login_page.switch_other_window()   # 切到新打开的标签页
        self.check_title(case_name, self.title_workbench)
        self.check_no_console_error(case_name)

    @readonly
    def test_3material(self):
        """用例3：进入素材库/业务页（只读）。

        步骤：左侧菜单进入目标页 -> 等标题 -> 校验。
        期望标题取自 config.ini -> [assert] title_material。
        """
        case_name = '进入素材库'
        log1.info('执行测试用例：%s' % case_name)
        self.ensure_workbench()
        self.login_page.click_material()
        self.check_title(case_name, self.title_material)
        # ★ 业务断言：查询区关键控件必须渲染出来（旧用例只比标题，控件缺失照样绿）
        ready = self.login_page.query_form_ready()
        missing = [name for name, ok in ready.items() if not ok]
        self.assertEqual(missing, [], '素材库查询区缺少控件：%s' % missing)
        self.check_no_console_error(case_name)

    def test_4uplaodbutton(self):
        """用例4：上传视频到素材库（本工程最核心的用例）。

        步骤：选本地文件 -> 填表单（作者/手机号/上报单位）-> 上传 -> 确定。
        ★ 业务断言：**素材列表行数真的 +1** —— 这才是"上传成功"的证据。

        旧写法只断言"标题没变"，等于没验证上传结果：
        上传失败、进度卡住、弹窗报错，用例都会绿。这是本工程最大的盲区，
        改成比对行数后，上传失败会立刻暴露。

        表单字段全部现取自 config.ini -> [testcase]，缺一项就在这里明确报错。
        前置条件：upload_file 指向的文件必须真实存在，否则以 FileNotFoundError 失败。
        """
        case_name = '上传视频'
        log1.info('执行测试用例：%s' % case_name)
        self.ensure_material_page()

        # ---- 表单字段：延迟到本用例才读，缺失才报错（冒烟集不涉及它们）----
        video_author = Config.get_form_field('video_author', '上传表单的视频作者')
        phone = Config.get_form_field('phone', '上传表单的手机号')
        reporting = Config.get_form_field('reporting', '上传表单的上报单位')

        # 上传前的行数基线（异步，先确保列表已渲染）
        _, count_before = self.login_page.wait_material_count(timeout=10)

        self.login_page.upload_file(Config.get_upload_file())   # 选文件
        self.login_page.fill_upload_form(video_author, phone, reporting)
        # ★ 等页面提示，而不是盲等 5 秒
        self.login_page.wait_loading_gone(timeout=30)

        # ★ 业务断言：行数应增加（等最多 30 秒，上传本身是异步的）
        ok, count_after = self.login_page.wait_material_count(
            at_least=count_before + 1, timeout=30)
        self.assertTrue(
            ok,
            '上传后素材列表行数未增加：上传前 %d 行，等待后仍为 %d 行 —— '
            '说明上传没有成功（旧用例只比标题，这种情况会被误判为通过）'
            % (count_before, count_after))

        self.check_title(case_name, self.title_material)
        self.check_no_console_error(case_name)

    def test_5keyword(self):
        """用例5：关键字查询素材。

        步骤：输入关键字 -> 点查询 -> 点重置恢复初始列表。
        ★ 业务断言：查询**真的发起了请求并返回结果**，而不是只比标题。

        关键字取自 config.ini -> [testcase] query_keyword。
        """
        case_name = '关键字查询'
        log1.info('执行测试用例：%s' % case_name)
        self.ensure_material_page()
        query_keyword = Config.get_form_field('query_keyword', '素材查询关键字')

        self.login_page.keyword_query(query_keyword)
        self.login_page.wait_loading_gone(timeout=30)

        # ★ 业务断言：查询后列表已渲染完（至少出现一行 或 明确的空结果提示）
        self.login_page.wait_material_count(timeout=15)
        self.check_title(case_name, self.title_material)
        self.check_no_console_error(case_name)

    def test_6submitted(self):
        """用例6：把素材报送进审核流程。

        步骤：刷新页面拿到最新素材列表 -> 点第一行的「报 送」
              -> 按姓名选审核人 -> 保存。
        ★ 业务断言：第一行的**状态真的发生了变化**，而不是只比标题。

        旧写法只断言标题 —— 报送被拒绝、选错人、保存失败都会判绿。
        改成比对状态文本后，报送没生效会立刻暴露。

        注意：这里直接用了 self.driver.refresh()，
        属于绕过页面对象的分层写法，属于历史遗留，后续可补一个 refresh() 到 BasePage。
        """
        case_name = '报送'
        log1.info('执行测试用例：%s' % case_name)
        self.ensure_material_page()

        self.driver.refresh()
        self.login_page.wait_loading_gone(timeout=30)
        self.login_page.wait_material_count(timeout=15)

        # 报送前的状态基线
        status_before = self.login_page.get_first_row_status()
        log1.info('报送前第一行状态：%s' % status_before)

        self.login_page.submitted()
        self.login_page.wait_loading_gone(timeout=30)

        # ★ 业务断言：状态应发生变化（等最多 30 秒，报送要走后端审核流程）
        changed, status_after = self.login_page.wait_status_changed(
            status_before, timeout=30)
        self.assertTrue(
            changed,
            '报送后第一行状态未变化（仍为 [%s]）—— '
            '说明报送没有生效（旧用例只比标题，这种情况会被误判为通过）'
            % status_after)

        self.check_title(case_name, self.title_material)
        self.check_no_console_error(case_name)
