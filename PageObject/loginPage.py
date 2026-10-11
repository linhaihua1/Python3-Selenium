# -*- coding: utf-8 -*-
"""
==========================================================================
 页面对象 LoginPage（新人阅读顺序：第 3 个）
==========================================================================

【一句话说明】
    把"门户登录"和"素材库"这两个页面的操作，写成人话级别的方法。
    用例层只需要调 login()/click_material()/submitted()，不用关心 xpath 长什么样。

【★ 这是一个「示例业务」，不是框架的一部分】
    本文件的方法名与元素表 Element1 的定位值一样，都绑定在**某一个具体被测系统**上。
    接入新系统时，本文件与 Common/elementPage.py 一起整体替换即可，
    框架层（Common/basePage.py 与 PageObject/genericPage.py）一行都不用改。

    ★ 但**不要**把这里的定位值搬去当别的系统的定位 —— 它们对这个系统有效，
      是因为它就是这个系统的页面。新系统请优先用基类的通用定位能力
      （按可见文字 / placeholder / 属性），那些不依赖 DOM 层级、抗改版，
      见 Common/basePage.py 第七节。

【在框架中的位置】
    TestSuites/testLogin.py       用例层：调本类的方法 + 写断言
        └─> PageObject/loginPage.py  <- 本文件：一个方法 = 一个业务动作
              └─> Common/basePage.py   真正操作浏览器
                    └─> Common/elementPage.py  提供元素定位值

【设计原则（接手时务必遵守）】
    ✅ 本文件只写"做什么"：点哪个按钮、填哪个框、按什么顺序
    ❌ 本文件不写断言（assertEqual 之类）—— 断言是用例层的职责
    ❌ 本文件不出现 xpath 字符串 —— 元素一律从 Element1 取
    ❌ 本文件不写死任何业务数据（期望标题、查询关键字、表单值）
       —— 那些只能来自 config.ini，见 Common/config.py 的 get_required

【为什么本文件同时包含登录与素材库两个页面的操作】
    因为这两个页面属于同一条业务链（登录门户 -> 进系统 -> 素材库），
    元素和跳转关系紧密，放在一起比拆成三个文件更好维护。
    文件名叫 loginPage 是沿用历史命名。
==========================================================================
"""

import time

from selenium.common.exceptions import NoSuchElementException

from Common.basePage import BasePage
from Common.config import Config
from Common.elementPage import Element1
from Common.log import log1


class LoginPage(BasePage):
    """示例业务页面对象：门户登录 + 素材库操作。

    继承 BasePage 后，self.type / self.click / self.get_img 等方法可直接使用。
    实例化时要把 driver 传进来：
        login_page = LoginPage(driver)

    ★ 换被测系统时本类整体替换，框架层不用动。理由见模块头说明。
    """

    # ====================================================================== #
    # 一、门户：登录与跳转
    # ====================================================================== #
    def login(self, username, password):
        """在门户输入账号密码并点登录。

        :param username: 登录账号（来自 config.ini -> [testcase] login_username）
        :param password: 登录密码（来自 config.ini -> [testcase] login_password）

        执行后页面 title 的期望值取自 config.ini -> [assert] title_login，
        由用例 test_1login 校验。页面对象层不写断言，也不持有期望值。
        """
        self.type(Element1.Username, username)   # 填用户名
        self.type(Element1.Password, password)   # 填密码
        self.click(Element1.Sign_button)         # 点登录
        self.get_img()                           # 留一张登录后的截图，便于回溯

    def click_sign_in(self):
        """点门户里的业务系统入口。

        注意：这一步会**新开一个浏览器标签页**，
        调用方之后必须 switch_other_window() 切换过去，否则后续操作还在旧标签页上。
        """
        self.click(Element1.button)

    # ====================================================================== #
    # 二、素材库导航
    # ====================================================================== #
    def click_material(self):
        """在左侧菜单依次点「内容管理」->「素材库」。

        说明：素材库是二级菜单，需要先展开一级菜单才会出现。
        """
        self.click(Element1.content)    # 一级：内容管理
        self.click(Element1.material)   # 二级：素材库

    # ====================================================================== #
    # 三、上传视频（本工程最主要的业务动作）
    # ====================================================================== #
    def upload_file(self, file_path=None):
        """选择本地待上传的视频文件。

        :param file_path: 文件绝对路径；不传则用 config.ini -> [testcase] upload_file

        两种实现方式，由 config.ini -> [testcase] upload_mode 决定：
          send_keys（默认）直接给 input[type=file] 赋值，不弹系统对话框
          autoit              点上传按钮弹出 Windows「打开」对话框，用 autoit 模拟输入
        默认方案失败时会自动回退到 autoit，所以通常不用手动改配置。

        ⚠️ 例外：**配置缺失 / 文件不存在**属于前置条件不满足，回退到 autoit 也解决不了，
        所以这类错误会直接抛出原始原因，不做降级 ——
        否则真实原因会被 autoit 的报错盖掉，排查时完全摸不着头脑。
        """
        mode = (Config.get('testcase', 'upload_mode', 'send_keys') or 'send_keys').lower()

        if mode == 'autoit':
            # 明确指定了用对话框方案
            self.click(Element1.uplaodbutton)
            self.upload_by_autoit(file_path)
            return

        try:
            # 推荐方案：不触发任何原生弹窗，速度快、可在无桌面环境跑
            self.files_upload(Element1.FileInput, file_path)
        except (ValueError, FileNotFoundError):
            # 配置缺失 / 文件不存在属于「前置条件不满足」，回退到 autoit 也解决不了，
            # 只会把真实原因盖成一个更难懂的 autoit 报错。所以直接抛出。
            log1.error('上传前置条件不满足，不进行 autoit 回退', exc_info=1)
            raise
        except Exception:
            # 兜底：某些前端结构下 file 控件拿不到，就退回对话框方案
            # 需要 pip install PyAutoIt，且中文 Windows 系统
            log1.error('send_keys 上传失败，回退到 autoit 方案', exc_info=1)
            self.click(Element1.uplaodbutton)
            self.upload_by_autoit(file_path)

    def fill_upload_form(self, video_author, phone, reporting):
        """填写上传表单并提交。

        :param video_author: 视频作者
        :param phone:        手机号
        :param reporting:    上报单位

        顺序不能乱：必须先把表单字段填完，才能点「上 传」；
        上传成功后还要收起文件列表、点「确定」关闭上传弹窗。
        """
        self.type(Element1.videoauthor, video_author)   # 视频作者
        self.type(Element1.phone, phone)                # 手机号
        self.type(Element1.reporting, reporting)        # 上报单位
        self.click(Element1.upload)                     # 「上 传」提交
        self.click(Element1.showbuttons)                # 收起已上传文件列表
        self.click(Element1.confirm)                    # 「确定」关闭弹窗

    # ====================================================================== #
    # 四、关键字查询（关键字取自 config.ini -> [testcase] query_keyword）
    # ====================================================================== #
    def query_form_ready(self):
        """自检：素材库查询区的关键控件是否都已渲染出来，返回检查结果。

        :return: dict，形如 {'关键字输入框': True, '查询按钮': True, '重置按钮': False}

        为什么要有这个方法：素材库是异步渲染的单页应用，刚进页面时表单可能还没出来，
        直接操作会偶发失败。先做一次"控件是否齐全"的自检，
        失败时能直接指出**少了哪一个**，而不是只报一句 xpath 定位失败。

        本方法**只读**：不点任何按钮、不发请求，因此可以安全地在生产环境执行。
        """
        checks = {
            '关键字输入框': Element1.keyword,
            '查询按钮': Element1.querybutton,
            '重置按钮': Element1.replacement,
        }
        result = {}
        for name, selector in checks.items():
            # timeout=0 表示立即判定，不等待：此时页面已经加载完，等下去没意义
            result[name] = self.get_element(selector, timeout=0) is not None
            log1.info('查询区控件[%s] 存在=%s' % (name, result[name]))
        return result

    def fill_keyword(self, keyword):
        """只往关键字输入框里填内容，**不点查询**（只读操作，不产生数据影响）。

        :param keyword: 要填入的关键词

        与 keyword_query() 的区别：那个会点「查 询」真正发起搜索、
        再点「重 置」恢复；本方法只负责填值，用于校验"输入是否生效"。
        """
        self.type(Element1.keyword, keyword)

    def read_keyword(self):
        """读取关键字输入框当前的值（校验输入是否生效、重置是否清空）。"""
        return self.get_value(Element1.keyword)

    def reset_query(self):
        """点「重 置」清空查询条件，把列表恢复到初始状态。

        单独抽出来的原因：重置是"把页面还回去"的动作，
        用例做只读校验后必须调用它，避免影响后续用例。
        """
        self.click(Element1.replacement)

    def keyword_query(self, keyword):
        """按关键字搜索素材，搜索后点「重 置」清空查询条件。

        :param keyword: 搜索关键词

        注意：本方法不返回搜索结果，用例层只校验页面 title 未跳走 ——
        如果将来要校验搜索命中数量，需要在这里 return 结果列表。
        """
        self.type(Element1.keyword, keyword)     # 输入关键字
        self.click(Element1.querybutton)         # 点「查 询」
        self.click(Element1.replacement)         # 点「重 置」，为后续用例恢复初始状态

    # ====================================================================== #
    # 六、业务结果的「观察点」（只返回数据，断言由用例层做）
    #
    #   ★ 为什么需要这一节：
    #     旧用例只断言页面标题，于是"上传失败但弹窗没关""查询 0 条命中"
    #     "报送被拒绝"这类业务失败**照样判绿**（假绿）。
    #     下面这些方法把"业务结果"变成可读的数据，让用例层能真正断言。
    #     本层只负责"读"，不下结论 —— 断言是用例层的职责，别放错层。
    # ====================================================================== #
    def get_material_count(self):
        """读素材列表当前显示的数据行数。【在用：业务断言的核心观察点】

        :return: 行数（int）；读不到返回 0

        上传成功后行数应 +1，查询后可用来判断"命中了几条"。
        """
        rows = self.get_elements(Element1.material_rows, timeout=0)
        count = len(rows)
        log1.info('素材列表当前行数：%d' % count)
        return count

    def get_total_count_text(self):
        """读列表的「共 N 条」文案（没有则返回空串）。"""
        try:
            return self.get_text(Element1.total_count, timeout=0) or ''
        except (NoSuchElementException, ValueError):
            return ''

    def get_first_row_status(self):
        """读列表第一行最后一列的文本（通常是状态位：待初审/已报送/已发布…）。

        :return: 状态文本；读不到返回空串
        报送用例用它验证"状态真的变了"，而不是"标题没变"。
        """
        try:
            return (self.get_text(Element1.first_row_status, timeout=0) or '').strip()
        except (NoSuchElementException, ValueError):
            return ''

    def wait_material_count(self, at_least=None, timeout=None):
        """等待素材列表行数达到某个下限（上传是异步的，需要等）。

        :param at_least: 期望的**最少**行数；不传则只等"列表出现"
        :return: (是否满足, 最终行数)
        """
        timeout = timeout if timeout is not None else self.timeout
        end_time = time.time() + timeout
        count = 0
        while True:
            count = self.get_material_count()
            if at_least is None:
                if count > 0:
                    return True, count
            elif count >= at_least:
                return True, count
            if time.time() >= end_time:
                log1.error('等待素材列表行数超时(%ss)：期望 >= %s，实际 %s'
                           % (timeout, at_least, count))
                return False, count
            time.sleep(0.5)

    def wait_status_changed(self, before, timeout=None):
        """等待第一行的状态文本**不再是** before（用于报送后的状态流转）。

        :param before: 操作前读到的状态文本
        :return: (是否已变化, 最终状态文本)
        """
        timeout = timeout if timeout is not None else self.timeout
        end_time = time.time() + timeout
        current = before
        while True:
            current = self.get_first_row_status()
            if current and current != before:
                log1.info('状态已变化：%s -> %s' % (before, current))
                return True, current
            if time.time() >= end_time:
                log1.error('等待状态变化超时(%ss)：仍为 [%s]' % (timeout, current))
                return False, current
            time.sleep(0.5)

    # ====================================================================== #
    # 七、报送（把素材提交进审核流程）
    # ====================================================================== #
    def submitted(self, person=None):
        """对列表第一条素材执行报送：开审核人下拉 -> 选审核人 -> 保存。

        :param person: 审核人姓名；不传则读 config.ini -> [testcase] first_trial_person

        业务说明：报送 = 把素材提交给第一级审核人（初审人）审核，
        运营流程上是「编辑提交 -> 初审 -> 终审 -> 发布」，本用例只覆盖第一步。

        ★ 已从"下拉列表第 8 项"改为**按人名字定位**：
          旧写法把审核人的**位置序号**写死，只要人员列表顺序一变就会
          **静默选错人** —— 选错人不报错、用例照样绿，是最危险的一类缺陷。
          现在姓名来自配置，换人只改 config.ini。
        """
        person = person or Config.get_form_field('first_trial_person', '报送的审核人姓名')
        self._open_first_trial_dropdown()
        self.click(Element1.first_trial_person(person))   # 按姓名选中
        self.click(Element1.save)                         # 点「保 存」

    def _open_first_trial_dropdown(self):
        """点开素材列表的「报 送」-> 「初审」下拉框。

        单独抽出来是为了让 submitted() 读起来仍是"三步业务动作"：
        报送 -> 选人 -> 保存。
        """
        self.click(Element1.submission)   # 点第一行的「报 送」
        self.click(Element1.first_trial)  # 点开「初审」下拉框
