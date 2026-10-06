# -*- coding: utf-8 -*-
"""
单元测试：Common/config.py（配置读取封装）

重点覆盖三类容易出错的地方：
    1. 取不到配置时是否"返回默认值"而不是抛异常
    2. 环境变量覆盖机制（CI 上账号密码、无头开关全靠它）
    3. 布尔/整数转换（配置里是字符串 'false'，直接 bool() 会得到 True）
"""

import os
import unittest

from tests.helpers import patch_config
from Common.config import Config, ENV_PREFIX


class _EnvGuard(unittest.TestCase):
    """基类：隔离 UI_ 开头的环境变量，避免测试之间相互污染。"""

    def setUp(self):
        self._saved = {k: v for k, v in os.environ.items() if k.startswith(ENV_PREFIX)}
        for key in list(self._saved):
            os.environ.pop(key, None)

    def tearDown(self):
        for key in list(os.environ):
            if key.startswith(ENV_PREFIX):
                os.environ.pop(key, None)
        os.environ.update(self._saved)


class TestEnvName(_EnvGuard):
    """环境变量名换算规则。"""

    def test_常规段键换算为全大写下划线(self):
        self.assertEqual(Config._env_name('environment', 'url'), 'UI_ENVIRONMENT_URL')
        self.assertEqual(Config._env_name('ci', 'headless'), 'UI_CI_HEADLESS')
        self.assertEqual(
            Config._env_name('testcase', 'login_password'), 'UI_TESTCASE_LOGIN_PASSWORD'
        )

    def test_非字母数字字符统一换成下划线(self):
        self.assertEqual(Config._env_name('testcase', 'upload-file'), 'UI_TESTCASE_UPLOAD_FILE')
        self.assertEqual(Config._env_name('my.section', 'a b'), 'UI_MY_SECTION_A_B')


class TestGet(_EnvGuard):
    """Config.get 的取值优先级与容错。"""

    def test_读取存在的配置项(self):
        with patch_config():
            self.assertEqual(Config.get('environment', 'browser'), 'chrome')
            self.assertEqual(Config.get('testcase', 'login_username'), 'unit_user')

    def test_段不存在时返回默认值不抛异常(self):
        with patch_config():
            self.assertIsNone(Config.get('不存在的段', 'key'))
            self.assertEqual(Config.get('不存在的段', 'key', '兜底'), '兜底')

    def test_键不存在时返回默认值不抛异常(self):
        with patch_config():
            self.assertEqual(Config.get('environment', '不存在的键', '兜底'), '兜底')

    def test_含百分号的值能原样读出(self):
        """config.ini 里的密码含 %，一旦插值没关掉这里就会抛异常。"""
        with patch_config():
            self.assertEqual(Config.get('testcase', 'login_password'), 'p%ss%word')

    def test_环境变量优先于配置文件(self):
        with patch_config():
            os.environ['UI_ENVIRONMENT_BROWSER'] = 'firefox'
            self.assertEqual(Config.get('environment', 'browser'), 'firefox')

    def test_环境变量为空字符串时不覆盖(self):
        """Jenkins 传空参数不应把配置清空 —— 这是刻意的设计。"""
        with patch_config():
            os.environ['UI_ENVIRONMENT_BROWSER'] = ''
            self.assertEqual(Config.get('environment', 'browser'), 'chrome')

    def test_环境变量全为空白也不覆盖(self):
        with patch_config():
            os.environ['UI_ENVIRONMENT_BROWSER'] = '   '
            self.assertEqual(Config.get('environment', 'browser'), 'chrome')

    def test_可以整体关闭环境变量覆盖(self):
        with patch_config():
            os.environ['UI_ENVIRONMENT_BROWSER'] = 'firefox'
            os.environ['UI_ENV_OVERRIDE'] = 'false'
            self.assertEqual(Config.get('environment', 'browser'), 'chrome')

    def test_环境变量覆盖值为false字符串时仍生效(self):
        """只有 UI_ENV_OVERRIDE 这个总开关参与真假判断，普通配置项原样返回。"""
        with patch_config():
            os.environ['UI_CI_HEADLESS'] = 'false'
            self.assertEqual(Config.get('ci', 'headless'), 'false')

    def test_兼容旧调用名config_read(self):
        with patch_config():
            self.assertEqual(Config.config_read('environment', 'browser'), 'chrome')


class TestGetBool(_EnvGuard):
    """布尔型读取。"""

    def test_真值写法(self):
        with patch_config():
            for raw in ('true', 'TRUE', 'True', '1', 'yes', 'on', 'y', 't'):
                os.environ['UI_CI_HEADLESS'] = raw
                self.assertTrue(Config.get_bool('ci', 'headless'), '应为真值：%s' % raw)

    def test_假值写法(self):
        with patch_config():
            for raw in ('false', 'FALSE', '0', 'no', 'off', 'n', 'f'):
                os.environ['UI_CI_HEADLESS'] = raw
                self.assertFalse(Config.get_bool('ci', 'headless'), '应为假值：%s' % raw)

    def test_配置文件的false不会被当成True(self):
        """经典的 bool('false') == True 陷阱，本方法必须避开。"""
        with patch_config():
            self.assertFalse(Config.get_bool('ci', 'headless'))

    def test_非法值回退到默认值(self):
        with patch_config():
            os.environ['UI_CI_HEADLESS'] = 'maybe'
            self.assertTrue(Config.get_bool('ci', 'headless', True))
            self.assertFalse(Config.get_bool('ci', 'headless', False))

    def test_缺配置时使用默认值(self):
        with patch_config():
            self.assertTrue(Config.get_bool('没有的段', '没有的键', True))

    def test_传入布尔默认值时直接返回(self):
        with patch_config():
            self.assertIs(Config.get_bool('没有的段', '没有的键', True), True)


class TestGetInt(_EnvGuard):
    """整数型读取。"""

    def test_正常整数(self):
        with patch_config():
            self.assertEqual(Config.get_int('ci', 'element_timeout'), 7)
            self.assertEqual(Config.get_int('ci', 'implicit_wait'), 2)

    def test_非法值回退默认(self):
        with patch_config():
            os.environ['UI_CI_ELEMENT_TIMEOUT'] = '十五秒'
            self.assertEqual(Config.get_int('ci', 'element_timeout', 15), 15)

    def test_缺配置回退默认(self):
        with patch_config():
            self.assertEqual(Config.get_int('没有的段', '没有的键', 30), 30)


class TestOptionsAndSections(_EnvGuard):
    """段与键的枚举。"""

    def test_列出段下的所有键(self):
        with patch_config():
            options = Config.options('testcase')
            self.assertIn('login_username', options)
            self.assertIn('upload_file', options)

    def test_段不存在时返回空列表(self):
        with patch_config():
            self.assertEqual(Config.options('不存在的段'), [])

    def test_中文键名保持原样(self):
        """[addressed] 的键是中文，选项名不应被改写。"""
        with patch_config():
            self.assertIn('张三', Config.options('addressed'))

    def test_has_section(self):
        with patch_config():
            self.assertTrue(Config.has_section('environment'))
            self.assertFalse(Config.has_section('不存在的段'))

    def test_config_options与options等价(self):
        with patch_config():
            self.assertEqual(
                sorted(Config.config_options('testcase')),
                sorted(Config.options('testcase')),
            )


class TestWriteOperations(_EnvGuard):
    """写操作：只允许写到临时 ini，绝不碰工程里的 config.ini。"""

    def test_写入后可以读回(self):
        with patch_config() as ini_path:
            Config.set_value('newsection', 'newkey', '新值')
            self.assertEqual(Config.get('newsection', 'newkey'), '新值')
            with open(ini_path, encoding='utf-8') as fp:
                self.assertIn('newkey', fp.read())

    def test_写入时保留键名大小写(self):
        with patch_config() as ini_path:
            Config.set_value('env2', 'CamelKey', 'v')
            with open(ini_path, encoding='utf-8') as fp:
                content = fp.read()
            self.assertIn('CamelKey', content)
            self.assertNotIn('camelkey', content)

    def test_覆盖已有键(self):
        with patch_config():
            Config.set_value('environment', 'browser', 'edge')
            self.assertEqual(Config.get('environment', 'browser'), 'edge')

    def test_config_write兼容旧签名_写入键值(self):
        with patch_config():
            Config.config_write('sec', 'k', 'v')
            self.assertEqual(Config.get('sec', 'k'), 'v')

    def test_config_write兼容旧签名_只建段(self):
        with patch_config():
            Config.config_write('emptysec')
            self.assertTrue(Config.has_section('emptysec'))
            self.assertEqual(Config.options('emptysec'), [])

    def test_删除单个键(self):
        with patch_config():
            self.assertEqual(Config.get('environment', 'browser'), 'chrome')
            Config.config_delete('environment', 'browser')
            self.assertIsNone(Config.get('environment', 'browser'))

    def test_删除整段(self):
        with patch_config():
            Config.config_delete('report')
            self.assertFalse(Config.has_section('report'))

    def test_删除不存在的键或段不报错(self):
        with patch_config():
            Config.config_delete('不存在的段', '不存在的键')
            Config.config_delete('不存在的段')


class TestBusinessHelpers(_EnvGuard):
    """业务便捷方法。"""

    def test_取登录账号返回元组(self):
        with patch_config():
            self.assertEqual(Config.get_account(), ('unit_user', 'p%ss%word'))

    def test_取上传文件返回绝对路径并展开用户目录(self):
        with patch_config():
            path = Config.get_upload_file()
            self.assertTrue(os.path.isabs(path), '必须返回绝对路径：%s' % path)
            self.assertTrue(path.endswith(os.path.join('video', 'demo.mp4')))
            self.assertNotIn('~', path)

    def test_未配置上传文件时返回None(self):
        ini = '[testcase]\nupload_file =\n'
        with patch_config(ini_text=ini):
            self.assertIsNone(Config.get_upload_file())

    def test_get_addkey把收件人键翻译成邮箱(self):
        with patch_config():
            emails = Config().get_addkey(['张三', '李四'])
            self.assertEqual(emails, ['zhangsan@example.com', 'lisi@example.com'])


class TestSectionHeaderFootgun(_EnvGuard):
    """★ 段头与键写在同一行会被**静默丢弃** —— 实测踩过的配置陷阱。

    ConfigParser 的段匹配正则 r"\\[(?P<header>.+)\\]" **没有整行锚定**，
    所以 `[ci]preflight = false` 这一整行会被当成"段头 [ci]"，后半句直接消失。
    既不报错、也不生效，排查时非常费劲（曾因此让一个单测莫名去检查跑测机器的驱动版本）。

    这组测试的作用是把"坑"固定下来：一旦将来有人把它改成"整行严格匹配"，
    这里会立刻变红，提醒同步修改 config.ini.example 里的格式说明。
    """

    def test_段头后面的内容被静默丢弃(self):
        ini = '[environment]\nurl = http://a.local/x\n\n[ci]preflight = false\nsmoke_cases = a,b\n'
        with patch_config(ini_text=ini):
            # 段头被识别成 [ci]，但键没有生效 —— 回落到传入的默认值
            self.assertTrue(Config.get_bool('ci', 'preflight', True),
                            'preflight 并未被设置，应当回落到默认值 True')
            self.assertEqual(Config.get('ci', 'smoke_cases', ''), 'a,b',
                             '紧跟在后面的键仍然在 [ci] 段内，正常生效')

    def test_分行写才生效(self):
        ini = '[environment]\nurl = http://a.local/x\n\n[ci]\npreflight = false\nsmoke_cases = a,b\n'
        with patch_config(ini_text=ini):
            self.assertFalse(Config.get_bool('ci', 'preflight', True),
                             '分行写时 preflight 才会被真正读到')

    def test_环境段同样会踩这个坑(self):
        """[environment]url = xxx 是同一个坑的另一种写法，地址会变成没配。"""
        ini = '[environment]url = http://a.local/x\n\n[ci]\nheadless = false\n'
        with patch_config(ini_text=ini):
            self.assertEqual(Config.get('environment', 'url', ''), '')


if __name__ == '__main__':
    unittest.main(verbosity=2)
