# -*- coding: utf-8 -*-
"""
==========================================================================
 页面对象 LoginPage（新人阅读顺序：第 3 个）
==========================================================================

【一句话说明】
    把"统一门户登录"和"融媒体素材库"这两个页面的操作，写成人话级别的方法。
    用例层只需要调 login()/click_material()/submitted()，不用关心 xpath 长什么样。

【在框架中的位置】
    TestSuites/testLogin.py       用例层：调本类的方法 + 写断言
        └─> PageObject/loginPage.py  <- 本文件：一个方法 = 一个业务动作
              └─> Common/basePage.py   真正操作浏览器
                    └─> Common/elementPage.py  提供元素定位值

【设计原则（接手时务必遵守）】
    ✅ 本文件只写"做什么"：点哪个按钮、填哪个框、按什么顺序
    ❌ 本文件不写断言（assertEqual 之类）—— 断言是用例层的职责
    ❌ 本文件不出现 xpath 字符串 —— 元素一律从 Element1 取

【为什么叫 LoginPage 却包含素材库操作】
    因为这两个页面属于同一条业务链（登录门户 -> 进生产系统 -> 素材库），
    元素和跳转关系紧密，放在一起比拆成三个文件更好维护。
    文件名叫 loginPage 是沿用历史命名。
==========================================================================
"""

from Common.basePage import BasePage
from Common.config import Config
from Common.elementPage import Element1
from Common.log import log1


class LoginPage(BasePage):
    """统一门户登录与融媒体素材库操作。

    继承 BasePage 后，self.type / self.click / self.get_img 等方法可直接使用。
    实例化时要把 driver 传进来：
        login_page = LoginPage(driver)
    """

    # ====================================================================== #
    # 一、统一门户：登录与跳转
    # ====================================================================== #
    def login(self, username, password):
        """在统一门户输入账号密码并点登录。

        :param username: 登录账号（来自 config.ini -> [testcase] login_username）
        :param password: 登录密码（来自 config.ini -> [testcase] login_password）

        执行后页面 title 应为 '统一门户'，用例 test_1login 会校验这一点。
        """
        self.type(Element1.Username, username)   # 填用户名
        self.type(Element1.Password, password)   # 填密码
        self.click(Element1.Sign_button)         # 点登录
        self.get_img()                           # 留一张登录后的截图，便于回溯

    def click_sign_in(self):
        """点门户里的「发布系统」进入生产系统。

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
    # 四、关键字查询
    # ====================================================================== #
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
    # 五、报送（把素材提交进审核流程）
    # ====================================================================== #
    def submitted(self):
        """对列表第一条素材执行报送：开初审下拉 -> 选初审人 -> 保存。

        业务说明：报送 = 把素材提交给第一级审核人（初审人）审核，
        运营流程上是「编辑提交 -> 初审 -> 终审 -> 发布」，本用例只覆盖第一步。

        已知脆弱点：first_trial 和 person_of_first_instance 用的是绝对 xpath，
        页面上多一层 div 就会失效，改版后优先检查这两个。
        """
        self.click(Element1.submission)                  # 点第一行的「报 送」
        self.click(Element1.first_trial)                 # 点开「初审」下拉框
        self.click(Element1.person_of_first_instance)    # 选中初审人
        self.click(Element1.save)                        # 点「保 存」
