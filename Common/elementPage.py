# -*- coding: utf-8 -*-
"""
==========================================================================
 页面元素表（新人阅读顺序：第 4 个）
==========================================================================

【一句话说明】
    整个工程**所有**元素的定位信息都集中在这里，其他地方不许出现 xpath。
    前端页面一改版，优先改 config.ini 的 [elements] 段（一行代码都不用动）。

【★ 定位值的真正来源：config.ini 的 [elements] 段】
    本文件里的定位值是**默认示例**（对应仓库自带的示例业务），
    会被 config.ini 逐条覆盖。取值优先级：

        config.ini [elements]  >  本文件的默认值

    接新系统的标准做法（零代码改动）：
        1. 在 config.ini 加一段
               [elements]
               Username    = xpath://input[@name='userName']
               Sign_button = id:login-btn
        2. 跑 python run.py --cases test_1login 验证
    没在 [elements] 里出现的元素，继续用本文件的默认值 ——
    所以不需要把整张表抄一遍，只写自己关心的几条。

    值的写法：`id:xxx` / `name:xxx` / `css:xxx` / `xpath://xxx`；
    省略前缀时按 xpath 解析。对应环境变量：`UI_ELEMENTS_<键名>`。

【在框架中的位置】
    Common/basePage.py 负责"怎么定位"，本文件只提供"定位什么"：
        Element1.Username  等价于  ['xpath', "//input[@type='text']"]
    使用方式（在 PageObject 里）：
        self.type(Element1.Username, 'zhangsan')

【描述格式】
    [定位方式, 定位值]，定位方式取值见 basePage.BY_MAP：
    id / name / class / tag / link / plink / css / xpath
    例：['id', 'global-uploader-btn']  ['css', '#app .upload-btn']

【★ 本文件是「示例业务」，不是框架的一部分】
    下面每一个定位值都绑定在**某一个具体被测系统**的页面上，它们对这个系统
    有效仅仅因为它就是这个系统的页面。接入新系统时，本文件与
    PageObject/loginPage.py 一起整体替换，框架层一行都不用改。

    ★★绝对不要把这里的定位值搬去当别的系统的定位★★
        照抄到别的系统上只会失败 —— 定位值描述的是具体 DOM，不是通用规律。
        新系统请优先用基类的通用定位能力（按可见文字 / placeholder / 属性），
        那些不依赖 DOM 层级、抗改版，见 Common/basePage.py 第七节。

    ★★ 定位值与「业务数据」是两回事 ★★
        本文件的定位值（xpath）属于示例业务，会随换系统整体替换；
        而**业务数据**（期望标题、查询关键字、表单字段值）连示例都不该留，
        必须全部来自 config.ini，见 Common/config.py 的 get_required。

【示例业务的页面顺序（仅用于说明各条定位分别在哪个页面）】
    第 1 站 门户登录页
        单点登录页，输入账号密码登录。
    第 2 站 业务系统入口
        门户里有系统入口，点进去会**新开一个标签页**，对应下面的「工作台」相关定位。
    第 3 站 素材库
        左侧菜单进入素材库，是上传/查询/报送三类操作的操作现场。
    业务动作
        上传：上传本地文件，并填写若干表单字段（字段值来自 config.ini [testcase]）。
        查询：按关键字搜索，另有"重置"按钮清空查询条件。
        报送：提交进入审核流程，需要选择审核人后保存。

【新人注意 —— 本文件最大的坑】
    下面很多 xpath 是**绝对路径或长链路**，形如 /html/body/div[4]/div/div[2]/... 或
    //*[@id='app']/div/div[2]/section/section/main/...
    这种写法对 DOM 层级极度敏感，页面上多套一层 div 就会失效。

    【先跑一次体检，看清现状】
        python -m Common.locator_policy            # 完整报告
        python -m Common.locator_policy --issues   # 只看需要改进的条目
    它会按 GOOD / INDEXED / DEEP_INDEX / ABSOLUTE 四级给每条定位评级，
    **只读源码、不启动浏览器**，随时可跑。

    【已完成的定位治理（2026-10-11）】
        全工程最脆弱的三条已经改掉，不再依赖绝对路径与写死的序号：
            submission           长链路+td[8]+button[3]  ->  按可见文字「报 送」锚定
            first_trial          /html/body/div[4]/...  ->  按「初审」文字向上找表单项
            person_of_first_instance  下拉第 8 项（会静默选错人）->  按人名字定位
        其中审核人姓名来自 config.ini -> [testcase] first_trial_person，
        换人只改配置、不改代码。

    【当前的脆弱条目（仍有，改版时优先检查）】
        下面这些是「带少量下标的相对 xpath」（INDEXED 级），
        它们锚在结构上而非文字上，前端调整层级时可能失效：
            Sign_button / content / material / videoauthor / phone / reporting
        改法同上：优先按可见文字、placeholder 或属性定位。
        体检命令：python -m Common.locator_policy --issues

    【新增定位时的优先级（按稳健程度从高到低）】
        id > name > 可见文字 > 占位提示 > 元素属性 > css > 相对 xpath
        绝对路径 xpath（以 /html 开头）**一律不要写**
    框架已提供这些语义化定位能力，优先用它们（见 Common/basePage.py）：
        get_element_by_text / click_by_text    —— 按页面上看得见的文字找
        get_element_by_attr                    —— 按属性找
        type_by_placeholder                    —— 按输入框的灰色提示文字找

    【改定位时的验证方法】
        python -m Common.locator_policy --issues          # 先确认改完评级变好
        python tests/run_unit_tests.py                    # 再确认框架没坏
        python run.py --cases <用例名>                     # 最后到真实环境验证
        失败时看 Logs/日期/Error_Logs/ 的"没有定位到元素"一行，
        以及 Report/artifacts/日期/ 里框架自动保存的截图与页面源码。
==========================================================================
"""


class Element1:
    """示例业务的元素表。

    命名约定：变量名首字母大写的是"页面主控件"，小写的是表单字段/按钮。

    ★ 换被测系统时本类整体替换，框架层不用动。理由见模块头说明。
    """

    # ==================== 第 1 站：门户登录页 ====================
    Username = ['xpath', "//input[@type='text']"]      # 用户名输入框（按 type=text 定位，跨系统较通用）
    Password = ['xpath', "//input[@type='password']"]  # 密码输入框（用 type=password 精确区分）
    Sign_button = ['xpath', "//div[@id='app']/div/div[2]/div/div/div/form/div[4]/div/div"]  # 登录按钮

    # ==================== 第 2 站：从门户进生产系统 ====================
    # 通过"发布系统"这段文字定位到它后面的可点击区域
    button = ['xpath', "(.//*[normalize-space(text()) and normalize-space(.)='发布系统'])[1]/following::div[4]"]

    # ==================== 第 3 站：素材库导航 ====================
    content = ['xpath', "//*[@id='app']/div[1]/div[1]/div/div[1]/div/ul/div[3]/li/div/span"]  # 左侧菜单「内容管理」
    material = ['xpath', "//div[@id='app']/div/div/div/div/div/ul/div[3]/li/ul/div/a/li/span"]  # 子菜单「素材库」

    # ==================== 业务动作一：上传视频 ====================
    # 页面上可见的"上传文件"按钮（是个 label，点它会弹出 Windows 系统对话框）
    uplaodbutton = ['xpath', "//label[@id='global-uploader-btn']/i"]   # 注：拼写保留原样，别单独改，loginPage 在引用
    # 隐藏在组件内部的文件控件。给它的 send_keys(文件路径) 就能完成选择，
    # 从而绕开系统对话框 —— 这是工程默认的上传方式，见 basePage.files_upload()
    FileInput = ['xpath', "//input[@type='file']"]
    videoauthor = ['xpath', "//main/form/div[2]/div/div/input"]   # 上传表单：视频作者
    phone = ['xpath', "//div[3]/div/div/input"]                   # 上传表单：手机号
    reporting = ['xpath', "//div[5]/div/div/input"]               # 上传表单：上报单位
    # 「上 传」提交按钮：靠左边的「取 消」按钮文字做相对定位（按钮文字里带空格，别删）
    upload = ['xpath', "(.//*[normalize-space(text()) and normalize-space(.)='取 消'])[1]/following::span[1]"]
    showbuttons = ['xpath', "//div[@id='global-uploader']/div/div[3]/div/div/div/button/span/i"]  # 文件列表的展开/收起按钮
    confirm = ['xpath', "(.//*[normalize-space(text()) and normalize-space(.)='取消'])[1]/following::span[1]"]  # 「确定」

    # ==================== 业务动作二：关键字查询 ====================
    keyword = ['xpath', "//*[@id='app']/div/div[2]/section/section/main/div[1]/form/div[2]/div/div/input"]  # 关键字输入框
    # 「查 询」按钮（发请求，非只读）
    querybutton = ['xpath', "//*[@id='app']/div/div[2]/section/section/main/div[1]/form/div[6]/div/button/span"]
    # 「重 置」按钮（清空查询条件，把列表还回初始状态）
    replacement = ['xpath', "//*[@id='app']/div/div[2]/section/section/main/div[1]/form/div[7]/div/button"]

    # ==================== 素材列表：用于业务结果断言 ====================
    # ★ 这些是「断言用的观察点」，不是操作目标。
    #   有了它们，用例才能验证"上传真的成功了""查询真的命中了"，
    #   而不是只断言"页面标题没变"（那种断言在业务失败时照样绿）。
    #   相对 xpath + 语义锚定，不写死行号列号。
    material_rows = ['xpath', "//table//tbody/tr"]                      # 列表数据行（数行数）
    total_count = ['xpath', "//*[contains(text(),'共') and contains(text(),'条')]"]  # "共 N 条"
    # 第一行最后一列（状态位）。用 last() 而不是写死列号 ——
    # 前端增删列时不会失效（状态列通常固定在最后）。
    # 取第一个匹配元素即第一行的状态。
    first_row_status = ['xpath', "//table//tbody/tr/td[last()]"]

    # ==================== 业务动作三：报送 ====================
    # 素材列表第一行的「报 送」按钮。
    # ★ 已从「长链路 + td[8] + button[3]」改为**按可见文字锚定**：
    #    旧写法把"第 8 列第 3 个按钮"写死，前端一调列顺序或加个图标就失效。
    #    新写法只认"这一行里有『报 送』字样的按钮"，与列顺序无关。
    submission = ['xpath',
                  "//table//tr[1]//button[.//span[contains(normalize-space(text()), '报') "
                  "and contains(normalize-space(text()), '送')]]/span"]
    # 「初审」下拉框。
    # ★ 已从「/html/body/div[4]/... 绝对路径」改为**按标签文字向上找所属表单项**：
    #    旧写法从根节点逐层写死，页面上多套一层 div 就挂。
    #    新写法从「初审」这两个字出发，找到它所在的表单项，再取里面的下拉箭头。
    first_trial = ['xpath',
                   "//*[normalize-space(text())='初审']"
                   "/ancestor::div[contains(@class,'form-item') or contains(@class,'el-form-item')]"
                   "//i"]
    save = ['xpath', "(.//*[normalize-space(text()) and normalize-space(.)='返 回'])[1]/following::span[1]"]  # 「保 存」

    # ----------------------------------------------------------------------
    # 下面这条不是固定定位值，而是**按人名字动态构造**的定位。
    #
    # 旧写法 person_of_first_instance = /html/body/div[5]/div[1]/div[1]/ul/li[8]
    # 有两个致命问题：① 绝对路径，DOM 一变就挂；
    #                ② 写死"下拉列表第 8 项"这个业务序号 —— 只要审核人列表
    #                   顺序一变（有人入职/离职/改名），就会**静默选错人**。
    #                   选错人不会报错，用例照样绿 —— 这是最危险的一类缺陷。
    #
    # 新写法按"人名字"定位，姓名从 config.ini [testcase] first_trial_person 读。
    # 换人只改配置，不用改代码。
    # ----------------------------------------------------------------------
    @staticmethod
    def first_trial_person(name):
        """按审核人姓名构造下拉选项定位。

        :param name: 审核人姓名（来自 config.ini -> [testcase] first_trial_person）
        :return: 元素描述，形如 ['xpath', "//li[...][normalize-space(text())='张三']"]

        ★ 单引号会被转义，避免姓名里的引号破坏 xpath 语法。
        """
        safe = str(name).replace("'", "&apos;")
        return ['xpath',
                "//li[contains(@class,'el-select-dropdown__item') "
                "or contains(@class,'option')]"
                "[normalize-space(text())='%s']" % safe]


# ---------------------------------------------------------------------------
# ★★ 配置覆盖层：本模块真正的"数据来源"★★
#
# 【为什么需要这一层】
#   改造前，换被测系统必须改 Common/elementPage.py 这个 .py 文件。
#   这与工程的头号原则「换系统只改配置、一个 .py 都不用动」直接冲突 ——
#   定位值本质上也是"被测系统的业务数据"，同样不该写死在代码里。
#
#   所以改成：**代码里的值只是默认值，config.ini 的 [elements] 段可以逐条覆盖**。
#   接新系统时在 config.ini 里写自己的定位，一个字都不用碰 Python：
#
#       [elements]
#       Username   = xpath://input[@name='userName']
#       Sign_button= id:login-btn
#       ...
#
#   值的格式（与 basePage.BY_MAP 的键一致）：
#       id:xxx              -> ['id', 'xxx']
#       css:#app .btn       -> ['css', '#app .btn']
#       xpath://div[@id=1]  -> ['xpath', '//div[@id=1]']
#   省略前缀时默认按 xpath 解析。
#
# 【为什么默认值仍要保留在代码里】
#   1. 元素表要能被 Common/locator_policy.py 静态扫描（门禁靠读源码做定位评级）；
#   2. tests/ 的元素表单测需要一个确定的基线；
#   3. 新人 clone 下来不配任何东西也能看懂"这个工程大概在测什么"。
#   但真正的取值优先级是「config.ini > 代码默认值」，
#   所以一旦配了 [elements]，代码里的示例值就完全不参与运行。
# ---------------------------------------------------------------------------
def parse_locator_spec(spec):
    """把配置里的一条定位写法解析成 [定位方式, 定位值]。

    :param spec: 形如 'id:login-btn' / 'css:#app .btn' / 'xpath://div' / '//div'
    :return: ['id', 'login-btn'] 这样的二元列表
    :raise ValueError: 写法为空或无法识别时抛出，消息里带原文便于定位

    为什么不在这里校验定位方式是否受支持：
        BY_MAP 在 Common/basePage.py，import 它会把 selenium 依赖拉进来，
        而元素表需要能被"不开浏览器、不装 selenium"地静态扫描。
        合法性的校验交给 basePage._parse_selector（真正使用定位时才校验）。
    """
    text = str(spec or '').strip()
    if not text:
        raise ValueError('元素定位配置为空（写法应为 id:xxx / css:xxx / xpath:xxx）')
    # 只在第一个冒号处切分：xpath 值里含有大量冒号（如 //a[@href='a:b']）
    if ':' in text:
        prefix, _, value = text.partition(':')
        prefix, value = prefix.strip().lower(), value.strip()
    else:
        prefix, value = 'xpath', text
    if not value:
        raise ValueError('元素定位配置缺少定位值：%r' % spec)
    return [prefix or 'xpath', value]


def apply_config_overrides(target=None):
    """用 config.ini 的 [elements] 段覆盖元素表里的定位值。

    :param target: 要覆盖的元素表类；默认 Element1（传入其他类可复用于扩展元素表）
    :return: 被覆盖的条目名列表（没配任何项时返回空列表）

    ★ 未在配置里出现的元素**保持代码默认值不变** ——
      这样接入新系统时只需要写自己关心的几条，不用把整张表抄一遍。
    """
    target = target or Element1
    try:
        # 延迟导入：元素表要能被静态工具读取，不能强制依赖配置模块的初始化时序
        from Common.config import Config
        if not Config.has_section('elements'):
            return []
        overridden = []
        for key in Config.options('elements'):
            raw = Config.get('elements', key)
            if not raw or not str(raw).strip():
                continue
            if not hasattr(target, key):
                log_missing(key)
                continue
            try:
                setattr(target, key, parse_locator_spec(raw))
            except ValueError as exc:
                raise ValueError(
                    'config.ini [elements] %s 的写法不合法：%s\n'
                    '        正确写法示例：\n'
                    '          Sign_button = id:login-btn\n'
                    '          keyword     = css:#app .search input\n'
                    '          save        = xpath://button[text()="保存"]\n'
                    '          material    = //div[@id="app"]//span[text()="素材库"]'
                    % (key, exc)) from exc
            overridden.append(key)
        if overridden:
            from Common.log import log1
            log1.info('元素表已由 config.ini [elements] 覆盖 %d 条：%s'
                      % (len(overridden), '、'.join(overridden)))
        return overridden
    except ImportError:
        # 配置模块不可用（例如只做静态扫描的工具在跑），保持默认值即可
        return []


def log_missing(key):
    """配置里出现元素表中不存在的键时告警（不中断执行）。

    多半是把段名或键名拼错了。与其在这里抛异常让整轮测试挂掉，
    不如让它继续跑 —— 没被覆盖的元素用代码默认值，随后由门禁暴露出来。
    """
    try:
        from Common.log import log1
        log1.error('config.ini [elements] 里的键「%s」在元素表中不存在，已忽略。\n'
                   '        请检查拼写；键名应与 Common/elementPage.py 的属性名完全一致。' % key)
    except ImportError:
        pass


# 导入本模块时立即应用配置覆盖（保持"import 即生效"的直觉）
apply_config_overrides()


# ---------------------------------------------------------------------------
# 兼容旧命名：类名早期少写了一个 t（Elemen1），老代码或老笔记可能还用这个名字。
# 新代码请统一写 Element1。
# ---------------------------------------------------------------------------
Elemen1 = Element1
