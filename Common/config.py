# -*- coding: utf-8 -*-
"""
==========================================================================
 config.ini 读写封装（新人阅读顺序：第 9 个）
==========================================================================

【一句话说明】
    工程读取 config.ini 的唯一入口。所有环境地址、账号、报告配置都从这里取。

【在框架中的位置】
    config.ini  <- 磁盘上的真实配置文件
        └─> Common/config.py         <- 本文件
              ├─> Common/basePage.py  读 [environment]、[testcase]
              ├─> Common/runner.py    读 [report]
              └─> Common/sentMail.py  读 [sender]、[addressed]
    Common/configOverWriter.py 是本类的底座（定制版 ConfigParser）。

【config.ini 的段位说明（共 11 类）】
    [environment]  被测环境：url、browser
    [testcase]     用例参数：登录账号、上传文件、上传方式、写入范围 mode
    [assert]       断言期望值：各页面标题（换系统只改这里）
    [system]       跨系统适配：登录页的文案特征（placeholder / 按钮文字）
    [safety]       ★安全守卫：防止误连生产环境（见 Common/env_guard.py）
    [env_xxx]      ★多环境：一套代码在 dev/test/prod 间切换（run.py --env）
    [report]       报告元信息：标题、文件名、执行人、描述
    [ci]           流水线适配：无头、超时、冒烟集、JUnit 路径、失败取证
    [notify]       群机器人通知：钉钉 / 企业微信 webhook
    [sender]       发件人：邮箱、SMTP 授权码、显示名
    [addressed]    收件人：键是姓名、值是邮箱（发送时遍历取值）

【新人必读：两种读取风格】
    推荐：Config.get('段', '键', '默认值')   —— 取不到就返回默认值，不抛异常
    旧式：Config.config_read('段', '键')     —— 等价于 get，保留给老代码
    多值：Config.get_list('段', '键')        —— 返回列表，支持逗号/换行/分号分隔
    ★ 必填：Config.get_required('段', '键')  —— 取不到立即报错并说明怎么改
            ★★凡是「业务数据」（期望标题、查询关键字、表单字段等）都用它★★
            框架层通用开关（超时、路径、是否无头）才用 get + 默认值。
            原因见get_required 的文档字符串：拿错的默认值去比对会产生
            "标题不符"这种掩盖真实原因的失败。

【★ 测试数据配置化约定（本工程的一条硬规则）】
    框架代码里**不允许**出现任何具体被测系统的业务数据 —— 页面标题、
    查询关键字、上报单位、手机号、报告名称等，一律只能来自 config.ini。
    换系统 / 换环境时只改配置，不改任何 .py 文件。
    违反这条会怎样，tests/test_config.py 与 tests/test_test_login_suite.py
    里有专门的检查把住（源码里出现业务字面量就让单测变红）。

【新人必读：环境变量覆盖（CI/CD 的关键机制）】
    读取任意配置项前，会先查同名环境变量，规则：
        UI_ + 段名 + _ + 键名 ，全部大写，非字母数字转成下划线
    例如：
        [environment] url             ->  UI_ENVIRONMENT_URL
        [testcase]    login_password  ->  UI_TESTCASE_LOGIN_PASSWORD
        [ci]          headless        ->  UI_CI_HEADLESS
    环境变量**优先于** config.ini。

    为什么要这么做：Jenkins 上不能把生产账号密码写进仓库，
    而是配成 Jenkins 凭据，构建时注入成环境变量。
    这样同一份代码在本机、测试环境、流水线上无需改任何文件即可运行。
    想整体关掉该机制，设置 UI_ENV_OVERRIDE=false。

【新人注意】
    1. 敏感信息目前是明文写在 config.ini 里的（账号密码、邮箱授权码），
       提交代码前请确认该文件不要入库（仓库根目录的 .gitignore 已忽略它），
       真实值建议通过环境变量或 Jenkins 凭据注入。
    2. 写入方法（set_value / config_delete）会直接改磁盘文件，
       只建议给一次性维护脚本使用，不要在用例里随机写配置。
==========================================================================
"""

import configparser
import os
import re

import getcwd
from Common.configOverWriter import ConfigOverWrite
from Common.log import log1

# ---------------------------------------------------------------------------
# 环境变量覆盖机制的前缀。所有可覆盖的变量都以它开头，避免与系统变量撞名。
# ---------------------------------------------------------------------------
ENV_PREFIX = 'UI_'

# 用来判断真/假的文本（配置项和布尔型环境变量共用）
TRUE_VALUES = ('1', 'true', 'yes', 'on', 'y', 't')
FALSE_VALUES = ('0', 'false', 'no', 'off', 'n', 'f', '')

# ---------------------------------------------------------------------------
# 模块级初始化：确定配置文件位置，建好可复用的解析器实例
# ---------------------------------------------------------------------------
path = getcwd.get_cwd()                                            # 工程根目录
config_path = os.path.join(path, 'config.ini')                     # 配置文件绝对路径
# 用自定义的子类：保留键的大小写 + 关闭 % 插值（密码里可能有 %）
config = ConfigOverWrite()
config.read(config_path, encoding='utf-8-sig')                     # utf-8-sig 兼容带 BOM 的文件


class Config:
    """配置文件操作类。所有方法都是静态方法，直接 Config.get(...) 调用即可。

    注意：本类与模块级变量 `config` 是两个东西 ——
    前者是"工具类"，后者是"底层的 ConfigParser 实例"，不要混淆。
    """

    # ====================================================================== #
    # 环境变量覆盖（CI/CD 用；本机运行时通常不会命中）
    # ====================================================================== #
    @staticmethod
    def _env_name(section, key):
        """把 [段]键 换算成环境变量名。

        :return: 例 _env_name('environment', 'url') -> 'UI_ENVIRONMENT_URL'

        规则：前缀 UI_ + 段 + 键，转大写，非字母数字一律换成下划线。
        所以 [testcase] 里的 upload-file / upload_file 都会变成 UI_TESTCASE_UPLOAD_FILE。
        """
        raw = '%s%s_%s' % (ENV_PREFIX, section, key)
        return re.sub(r'[^0-9A-Za-z]+', '_', raw).upper()

    @staticmethod
    def _env_override(section, key):
        """查找是否有环境变量覆盖了该配置项。

        :return: 环境变量值（字符串）；没有覆盖时返回 None

        注意与"环境变量为空字符串"的区别：空字符串视为未设置，
        否则 Jenkins 里传一个空参数就会把配置意外清空。
        """
        # 允许整体关闭该机制：UI_ENV_OVERRIDE=false
        switch = os.environ.get('%sENV_OVERRIDE' % ENV_PREFIX)
        if switch is not None and switch.strip().lower() in FALSE_VALUES:
            return None

        name = Config._env_name(section, key)
        value = os.environ.get(name)
        if value is None or value.strip() == '':
            return None
        log1.info('配置 [%s] %s 被环境变量 %s 覆盖' % (section, key, name))
        return value

    @staticmethod
    def _reload():
        """操作前重新读盘，保证拿到的是最新内容。

        为什么需要：配置文件在运行期间可能被手工改了，
        缓存住旧值会让改动"不生效"，这是很难排查的坑。
        """
        config.read(config_path, encoding='utf-8-sig')

    # ====================================================================== #
    # 读操作
    # ====================================================================== #
    @staticmethod
    def get(section, key, fallback=None):
        """读取配置项，取不到就返回 fallback，不抛异常。【推荐用法】

        :param section:  段名，如 'environment'
        :param key:      键名，如 'url'
        :param fallback: 取不到时的默认值
        :return: 字符串值，或 fallback

        取值优先级：环境变量 UI_段_键  >  config.ini  >  fallback

        设计说明：旧版直接 config.get() 会在缺配置时抛异常，
        导致"少配一项就整个跑不起来"。改成有默认值后更容易定位真正的问题。
        """
        # 1. 先看是否被环境变量覆盖（CI 上账号密码就是从这里进来的）
        override = Config._env_override(section, key)
        if override is not None:
            return override

        # 2. 再读配置文件
        Config._reload()
        try:
            value = config.get(section, key)
            log1.info('%s下读取%s的值：%s' % (section, key, value))
            return value
        except (configparser.NoSectionError, configparser.NoOptionError):
            log1.info('%s下不存在%s，使用默认值：%s' % (section, key, fallback))
            return fallback

    # 兼容旧调用名：历史代码里写的是 config_read，效果与 get 完全一致
    config_read = get

    @staticmethod
    def get_required(section, key, purpose='', env_name=None):
        """读取**必须配置**的项，取不到立即抛错。【所有业务数据的推荐读法】

        :param section:  段名，如 'assert'
        :param key:      键名，如 'title_login'
        :param purpose:  这项配置是干什么的（中文），会拼进报错信息，让人一眼知道该改哪里
        :param env_name: 环境变量名；不传按 UI_<段>_<键> 规则自动推导
        :return: 配置值（已strip）

        :raise ValueError: 配置缺失或为空时抛出，消息里给出三种修复方式

        ★ 为什么需要它（与 get 的区别）
            get(section, key, fallback) 取不到就返回一个默认值。对通用框架来说，
            那个默认值往往是上一个被测系统留下的业务字面量 —— 一旦忘了改配置，
            就会拿着一个错的期望值去比对，报出"标题不符"这种看不懂的失败，
            真实原因（配置没填）被完全掩盖。

            所以凡是「业务相关的数据」（期望标题、查询关键字、表单字段…）
            一律用本方法：配置缺失就让用例**明确失败并说清怎么改**，
            而不是用一个错的期望值跑出一个误导性的断言失败。

        报错消息里同时给出三种修复方式，覆盖三种使用场景：
            ① 改 config.ini        —— 本机开发
            ② 设环境变量            —— CI 上用凭据注入，不落仓库
            ③ 命令行 --env 指定档位  —— 多环境切换
        """
        env_name = env_name or Config._env_name(section, key)
        value = Config.get(section, key, None)
        # get() 已经处理过环境变量覆盖；这里再确认一次没有把空串当成有效值
        if value is not None and not str(value).strip():
            value = None
        if value is not None:
            return str(value).strip()

        what = '（%s）' % purpose if purpose else ''
        raise ValueError(
            '缺少必填配置 [%s] %s%s。\n'
            '        三种修复方式，任选其一：\n'
            '          1. 在 config.ini 的 [%s] 段补上  %s = 实际值\n'
            '          2. 设置环境变量（CI 推荐，不落仓库）：  set %s=实际值\n'
            '          3. 若该项目有环境档位，可用命令行指定：  python run.py --env 档位名'
            % (section, key, what, section, key, env_name)
        )

    @staticmethod
    def get_required_list(section, key, purpose='', env_name=None):
        """必填版的列表读取：取不到或为空列表都报错。

        用于"必须填的多个值"型配置（如冒烟用例关键字、生产特征黑名单）。
        分隔规则与 get_list 完全一致（换行 / 逗号 / 分号）。
        """
        items = Config.get_list(section, key, None)
        if items:
            return items
        env_name = env_name or Config._env_name(section, key)
        what = '（%s）' % purpose if purpose else ''
        raise ValueError(
            '缺少必填配置 [%s] %s%s（值为空）。\n'
            '        请在 config.ini 的 [%s] 段填写实际值，'
            '或设置环境变量 %s=实际值（多个值用逗号或换行分隔）。'
            % (section, key, what, section, env_name)
        )

    @staticmethod
    def get_bool(section, key, fallback=False):
        """读取开关型配置（true/false、1/0、yes/no 都认）。【在用】

        :return: True / False

        用在哪：config.ini -> [ci] headless 就是这种开关。
        之所以单独写一个方法，是因为配置里写的是字符串 'true'，
        直接 bool('false') 得到的是 True —— 这是个很经典的坑。
        """
        value = Config.get(section, key, fallback)
        if isinstance(value, bool):
            return value
        text = str(value).strip().lower()
        if text in TRUE_VALUES:
            return True
        if text in FALSE_VALUES:
            return False
        log1.error('%s下%s的值不是合法布尔值：%s，使用默认值 %s' % (section, key, value, fallback))
        return bool(fallback)

    @staticmethod
    def get_int(section, key, fallback=0):
        """读取整数配置（如超时秒数），非法值回退到 fallback。【预留】"""
        value = Config.get(section, key, fallback)
        try:
            return int(value)
        except (TypeError, ValueError):
            log1.error('%s下%s的值无法转为整数：%s' % (section, key, value))
            return fallback

    @staticmethod
    def get_list(section, key, fallback=None, sep='\n,;'):
        """读取"多个值"型配置，返回去掉空白与空项的字符串列表。【在用】

        :param sep: 分隔符集合，默认支持 换行 / 逗号 / 分号 三种写法
        :return: 列表；配置不存在时返回 fallback（或空列表）

        用在哪：环境守卫的生产特征关键字（[safety] url_blocklist）、
        冒烟用例列表（[ci] smoke_cases）都是这种"可填多个值"的配置。
        相比在调用处各自 split，这里统一处理了三件事：
            ① 三种分隔符都认（写逗号还是换行都行，不容易配错）
            ② 空项自动丢弃（'a,,b' 不会产生一个空字符串）
            ③ 每项 strip（配置里手写的空格不会变成匹配失败的原因）
        """
        value = Config.get(section, key, None)
        if value is None:
            return list(fallback) if fallback else []
        if isinstance(value, (list, tuple)):
            raw_items = list(value)
        else:
            text = str(value)
            for ch in sep:
                text = text.replace(ch, '\n')
            raw_items = text.split('\n')
        return [item.strip() for item in raw_items if str(item).strip()]

    @staticmethod
    def has_section(section):
        """判断某个段是否存在，返回 True/False。【预留】"""
        Config._reload()
        return config.has_section(section)

    @staticmethod
    def options(section):
        """列出某个段下的所有键名；段不存在返回空列表。

        【在用】sentMail 用它遍历 [addressed] 段，因为收件人是"想加几个加几个"的，
        没法预先知道键名。
        """
        Config._reload()
        if not config.has_section(section):
            log1.info('配置文件中不存在 section：%s' % section)
            return []
        return config.options(section)

    # ====================================================================== #
    # 写操作（会真实修改 config.ini 文件）
    # ====================================================================== #
    @staticmethod
    def set_value(section, key, value):
        """写入一个配置项，段不存在时自动创建。【慎用：会改磁盘文件】"""
        Config._reload()
        if not config.has_section(section):
            config.add_section(section)
            log1.info('新增%s' % section)
        config.set(section, key, value)
        log1.info('%s下新增%s=%s' % (section, key, value))
        with open(config_path, 'w', encoding='utf-8') as f:
            config.write(f)

    @staticmethod
    def config_write(section, key=None, value=None):
        """兼容旧签名的写法。【慎用：会改磁盘文件】

        - 只传 section            -> 新增一个空段
        - 传 section + key + value -> 等价于 set_value()
        """
        Config._reload()
        if key is not None and value is not None:
            Config.set_value(section, key, value)
        else:
            if not config.has_section(section):
                config.add_section(section)
                log1.info('新增%s' % section)
                with open(config_path, 'w', encoding='utf-8') as f:
                    config.write(f)

    @staticmethod
    def config_delete(section, key=None):
        """删除配置。【慎用：删了就没了，没有撤销】

        - 传 section + key -> 只删这个键
        - 只传 section     -> 删掉整个段
        """
        Config._reload()
        if key is not None:
            if config.has_option(section, key):
                config.remove_option(section, key)
                log1.info('删除%s下%s和他的值' % (section, key))
        else:
            if config.has_section(section):
                config.remove_section(section)
                log1.info('删除%s' % section)
        with open(config_path, 'w', encoding='utf-8') as f:
            config.write(f)

    # ====================================================================== #
    # 业务便捷方法：把"用例真正关心的配置"包成一句调用
    # ====================================================================== #
    @staticmethod
    def config_options(section):
        """读取某段下所有键（保留旧接口名），等价于 options()。【预留】"""
        return Config.options(section)

    def get_addkey(self, keys):
        """把收件人键名列表翻译成邮箱列表（保留旧接口）。【预留】

        sentMail.py 现在直接用 Config.options + Config.get，
        这个方法留给外部或老代码调用。
        """
        return [Config.get('addressed', key) for key in keys]

    @staticmethod
    def get_account():
        """取出登录账号，返回元组 (用户名, 密码)。【在用】

        ★ 两个字段都是必填的：账号密码是所有 UI 用例的前置条件，
        缺任何一个都意味着这次执行注定失败。与其跑到一半报
        "元素不存在"，不如在第一步就说清"没配账号，去哪里配"。

        用例里这样用：
            username, password = Config.get_account()
        这样账号只存在于 config.ini，代码里不再硬编码。
        """
        return (
            Config.get_required('testcase', 'login_username', '登录账号'),
            Config.get_required('testcase', 'login_password', '登录密码'),
        )

    @staticmethod
    def get_upload_file():
        """取出待上传文件的绝对路径。【在用】

        ⚠️ 与账号不同，这里**允许返回 None** —— 上传不是每条用例都要做，
        只读冒烟用例完全用不到它。真正要上传的用例（files_upload / autoit）
        会在使用时显式校验"路径为空或文件不存在"并抛出可读的 FileNotFoundError，
        不会静默跳过。

        支持配置里写 ~/video/demo.mp4 这种带用户目录的写法。
        """
        value = Config.get('testcase', 'upload_file')
        if not value:
            return None
        return os.path.abspath(os.path.expanduser(value))

    @staticmethod
    def get_form_field(key, purpose=''):
        """取上传/查询表单里的一个字段值。【推荐】

        表单字段（作者、手机号、上报单位…）在不同系统里名称与是否必填都不同，
        所以框架不预设字段清单，改为按需读取：

            author = Config.get_form_field('video_author', '上传表单的视频作者')
            phone= Config.get_form_field('phone', '上传表单的手机号')

        :param purpose: 中文说明，会拼进报错信息
        :return: 配置值（已strip）
        :raise ValueError: 未配置时抛出，提示去 config.ini [testcase] 补
        """
        return Config.get_required('testcase', key, purpose or ('表单字段 %s' % key))

    @staticmethod
    def get_assert_value(key, purpose=''):
        """取一条断言的期望值（页面标题等）。【推荐】

        用例里的断言期望值必须来自配置，且**不设代码兜底**：
        兜底里放的是一个具体系统的标题，换系统后忘了改就会拿它去比对，
        报出"期望[旧系统标题] 实际[新系统标题]"这种毫无信息量的失败。

        用法：
            expected = Config.get_assert_value('title_login', '登录后首页标题')

        :raise ValueError: 未配置时抛出，提示去 config.ini [assert] 补
        """
        return Config.get_required('assert', key, purpose or ('断言期望值 %s' % key))
