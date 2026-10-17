# -*- coding: utf-8 -*-
"""
单元测试：Common/config.py 新增的「必填配置」读取能力

★ 本文件锁住一条工程硬规则：**业务数据不许出现在代码里**
    页面标题、查询关键字、表单字段值、报告名称等一律只能来自 config.ini。
    历史上代码里留过"兜底默认值"，换系统后忘了改配置，框架拿着上一个系统的
    标题去比对，报出「期望[旧标题] 实际[新标题]」这种完全看不出原因的失败 ——
    真实原因（配置没跟着换）被彻底掩盖。

    所以这里验证两件事：
      1. get_required 缺失时确实报错，且错误信息足够可操作（说要改哪一段哪个键）
      2. 用例层与框架层的源码里确实没有业务字面量（防劣化门禁）
"""

import inspect
import os
import unittest

from tests.helpers import BASE_DIR, patch_config
from Common.config import Config
from TestSuites import testLogin as login_suite
from TestSuites import testMaterialCheck as check_suite


# ---------------------------------------------------------------------------
# ★ 防劣化基线
#
# 【为什么这里不再是"枚举式黑名单"】
#   本文件曾经这样写：
#       BANNED_LITERALS = ('统一门户', '云媒资', '党建云', '融媒体生产系统', ...)
#   它只能拦住这 6 个词 —— 换一套业务名（比如「教务管理系统」「财务核算平台」），
#   硬编码照样能混进来，门禁形同虚设。这是最危险的一种失效：
#   它看起来在管，实际不管，还给人虚假的安全感。
#
#   现在主门禁已升级为**规则级 AST 扫描**（见 tests/test_no_hardcoded_data.py）：
#   不依赖任何具体业务词，对任意业务名都生效。
#
#   下面这组仍然保留，作为**第二道防线**：它的价值不在于"拦住新业务名"，
#   而在于锁定"这些具体的历史值一旦出现在配置模板里就是错的"。
# ---------------------------------------------------------------------------
BANNED_LITERALS = (
    '统一门户',
    '云媒资',
    '党建云',
    '融媒体生产系统',
    '工作台 - ',
    '素材库 - ',
)

#: 允许出现业务名的地方：示例业务的定位表本身绑定具体系统，无法避免
#  （但也不该在这里 —— 定位值不叫"测试数据"，换系统时整体替换即可）
ALLOW_BIZ_IN_FILES = ('elementPage.py',)


def _sources():
    """待扫描的源码：所有用例层文件（业务数据的重灾区）。"""
    targets = [
        os.path.join(BASE_DIR, 'TestSuites', name)
        for name in sorted(os.listdir(os.path.join(BASE_DIR, 'TestSuites')))
        if name.endswith('.py') and not name.startswith('__')
    ]
    targets.append(os.path.join(BASE_DIR, 'PageObject', 'loginPage.py'))
    out = {}
    for path in targets:
        if os.path.basename(path) in ALLOW_BIZ_IN_FILES:
            continue
        with open(path, encoding='utf-8') as fp:
            out[path] = fp.read()
    return out


class TestGetRequired(unittest.TestCase):
    """Config.get_required：缺失即报错，且错误信息可操作。"""

    def setUp(self):
        self._cfg = patch_config()
        self._cfg.__enter__()

    def tearDown(self):
        self._cfg.__exit__(None, None, None)

    def test_有配置时正常返回(self):
        self.assertEqual(Config.get_required('testcase', 'login_username'), 'unit_user')

    def test_返回值已strip(self):
        with patch_config(ini_text='[x]\nk =  值带空格  \n'):
            self.assertEqual(Config.get_required('x', 'k'), '值带空格')

    def test_缺失时抛ValueError(self):
        with self.assertRaises(ValueError):
            Config.get_required('assert', 'title_login')   # DEFAULT_INI 无 [assert]

    def test_空值等同于缺失(self):
        """配置写了但值为空 —— 同样必须报错，否则会拿空串去比对标题。"""
        with patch_config(ini_text='[assert]\ntitle_login =\n'):
            with self.assertRaises(ValueError):
                Config.get_required('assert', 'title_login')

    def test_报错信息包含段名与键名(self):
        try:
            Config.get_required('assert', 'title_login')
        except ValueError as exc:
            message = str(exc)
        else:                                    # pragma: no cover - 上面必然抛
            self.fail('应当抛出 ValueError')
        self.assertIn('[assert]', message)
        self.assertIn('title_login', message)

    def test_报错信息给出三种修复方式(self):
        """必须告诉人到底怎么改：改配置 / 设环境变量 / 用环境档位。"""
        try:
            Config.get_required('assert', 'title_login')
        except ValueError as exc:
            message = str(exc)
        else:                                    # pragma: no cover
            self.fail('应当抛出 ValueError')
        self.assertIn('config.ini', message, '要说明改哪个文件')
        self.assertIn('UI_ASSERT_TITLE_LOGIN', message, '要给出环境变量名（便于 CI 注入）')
        self.assertIn('--env', message, '要提示多环境档位的用法')

    def test_报错信息带用途说明(self):
        try:
            Config.get_required('assert', 'title_login', '登录后首页标题')
        except ValueError as exc:
            message = str(exc)
        else:                                    # pragma: no cover
            self.fail('应当抛出 ValueError')
        self.assertIn('登录后首页标题', message)

    def test_支持自定义环境变量名(self):
        with self.assertRaises(ValueError) as ctx:
            Config.get_required('assert', 'title_login', env_name='MY_CUSTOM_VAR')
        self.assertIn('MY_CUSTOM_VAR', str(ctx.exception))


class TestGetRequiredList(unittest.TestCase):
    """Config.get_required_list：多值型必填配置。"""

    def test_有值时返回列表(self):
        with patch_config(ini_text='[ci]\nsmoke_cases = a,b,c\n'):
            self.assertEqual(Config.get_required_list('ci', 'smoke_cases'),
                             ['a', 'b', 'c'])

    def test_缺失时报错(self):
        with self.assertRaises(ValueError):
            Config.get_required_list('ci', 'nothing_here')

    def test_值为空时报错(self):
        """写了键但内容为空 —— 同样视为缺失，避免"以为配了其实没配"。"""
        with patch_config(ini_text='[ci]\nsmoke_cases =\n'):
            with self.assertRaises(ValueError):
                Config.get_required_list('ci', 'smoke_cases')


class TestBusinessHelpers(unittest.TestCase):
    """get_account / get_upload_file / get_form_field / get_assert_value 四个便捷方法。"""

    def setUp(self):
        # 必须用 patch_config 把配置来源换成临时 ini：
        # 工程里真实的 config.ini 含占位值与明文，不能被这些测试读到。
        self._cfg = patch_config()
        self._cfg.__enter__()

    def tearDown(self):
        self._cfg.__exit__(None, None, None)

    def test_get_account返回元组(self):
        self.assertEqual(Config.get_account(), ('unit_user', 'p%ss%word'))

    def test_get_account缺账号时报错(self):
        with patch_config(ini_text='[testcase]\nlogin_password = x\n'):
            with self.assertRaises(ValueError):
                Config.get_account()

    def test_get_upload_file缺失时返回None而非报错(self):
        """上传不是每条用例都要做，只读冒烟用不到 —— 允许为 None，
        真正上传时 files_upload() 会显式校验并抛出可读的 FileNotFoundError。"""
        with patch_config(ini_text='[testcase]\nlogin_username = u\n'):
            self.assertIsNone(Config.get_upload_file())

    def test_get_form_field读testcase段(self):
        with patch_config(ini_text='[testcase]\nphone = 13800000000\n'):
            self.assertEqual(Config.get_form_field('phone'), '13800000000')

    def test_get_form_field缺失时报错(self):
        with patch_config(ini_text='[testcase]\nlogin_username = u\n'):
            with self.assertRaises(ValueError):
                Config.get_form_field('reporting', '上报单位')

    def test_get_assert_value读assert段(self):
        with patch_config(ini_text='[assert]\ntitle_login = 某某首页\n'):
            self.assertEqual(Config.get_assert_value('title_login'), '某某首页')

    def test_get_assert_value缺失时报错(self):
        with patch_config(ini_text='[testcase]\nlogin_username = u\n'):
            with self.assertRaises(ValueError):
                Config.get_assert_value('title_login')


class TestNoBusinessDataInCode(unittest.TestCase):
    """★ 防劣化门禁：代码里不许出现业务数据字面量。"""

    def test_用例层与页面对象层无业务字面量(self):
        offenders = []
        for path, source in _sources().items():
            for literal in BANNED_LITERALS:
                if literal in source:
                    offenders.append('%s -> %s'
                                     % (os.path.basename(path), literal))
        self.assertEqual(
            offenders, [],
            '代码里出现了业务数据字面量：%s\n'
            '    这些值必须搬到 config.ini（[assert] / [testcase]），代码里不要留默认值。\n'
            '    原因：换系统后忘了改配置，会拿着旧值去比对，'
            '报出看不出原因的断言失败。\n'
            '    正确写法：Config.get_assert_value("title_login") / '
            'Config.get_form_field("phone")' % offenders)

    def test_用例层不使用带默认值的Config_get(self):
        """断言/表单字段一律走 get_assert_value / get_form_field（必填版）。

        带默认值的 Config.get(section, key, fallback) 用在业务数据上，
        就是把兜底默认值又请回来了 —— 与本工程的规则直接冲突。
        允许的例外：框架自身的通用开关（超时、路径、是否无头），
        它们在别处出现即可，本用例只锁用例层的三个数据段。
        """
        for module in (login_suite, check_suite):
            source = inspect.getsource(module)
            for key in ('title_login', 'title_workbench', 'title_material',
                        'video_author', 'reporting', 'query_keyword'):
                for reader in ('Config.get(', 'Config.config_read('):
                    needle = "%s'%s'" % (reader, key)
                    if needle in source:
                        self.fail(
                            '%s 里用了带默认值的 %s%s —— '
                            '业务数据必须用 get_assert_value / get_form_field（缺失即报错），'
                            '不能用默认值兜底'
                            % (module.__name__, reader, key))

    def test_断言期望值不再有类属性兜底(self):
        """类定义里不应再有 title_xxx = '某标题' 这种兜底默认值。"""
        for cls in (login_suite.TestLogin, check_suite.TestMaterialCheck):
            for attr in ('title_login', 'title_workbench', 'title_material'):
                self.assertFalse(
                    isinstance(getattr(cls, attr, None), str) and attr in cls.__dict__,
                    '%s.%s 仍是代码里的兜底默认值 —— '
                    '应改为类级前置里用 Config.get_assert_value() 读取'
                    % (cls.__name__, attr))


class TestConfigExampleHasNoRealBusinessData(unittest.TestCase):
    """config.ini.example 是入库模板，不能带任何具体系统的业务数据。"""

    def test_模板里的assert段是占位符(self):
        path = os.path.join(BASE_DIR, 'config.ini.example')
        with open(path, encoding='utf-8') as fp:
            text = fp.read()
        for literal in BANNED_LITERALS:
            self.assertNotIn(literal, text,
                             'config.ini.example 不应含业务数据「%s」—— '
                             '模板只给占位值，真实值由使用者填' % literal)

    def test_模板说明了必填与报错行为(self):
        """模板必须讲清"缺失会报错、去哪补"，否则新人不知道怎么办。"""
        path = os.path.join(BASE_DIR, 'config.ini.example')
        with open(path, encoding='utf-8') as fp:
            text = fp.read()
        self.assertIn('get_required', text, '模板应说明必填配置的读取方式')
        self.assertIn('UI_ASSERT_TITLE_LOGIN', text, '模板应给出环境变量覆盖示例')


if __name__ == '__main__':
    unittest.main(verbosity=2)
