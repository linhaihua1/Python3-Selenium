# -*- coding: utf-8 -*-
"""
单元测试：Common/elementPage.py（元素表）

元素表是"前端改版时唯一需要改的文件"，一旦格式写错，
表现是所有用例都定位失败，很难排查。所以这里用测试把格式约束钉死：
    - 每个元素必须是 [定位方式, 定位值] 的二元结构
    - 定位方式必须是 basePage.BY_MAP 支持的那几种（否则直接失效）
"""

import os
import unittest

from Common.basePage import BY_MAP
from Common.elementPage import Element1, Elemen1


def _public_elements():
    """取出元素表里所有公开元素（排除私有属性与方法）。"""
    items = []
    for name in dir(Element1):
        if name.startswith('_'):
            continue
        value = getattr(Element1, name)
        if callable(value):
            continue
        items.append((name, value))
    return items


class TestElementFormat(unittest.TestCase):
    """元素描述的结构约束。"""

    def test_元素表非空(self):
        self.assertGreaterEqual(len(_public_elements()), 15)

    def test_每个元素都是二元结构(self):
        for name, value in _public_elements():
            self.assertIsInstance(value, (list, tuple), '元素 %s 应为列表/元组' % name)
            self.assertEqual(len(value), 2, '元素 %s 应为 [定位方式, 定位值] 两个元素' % name)

    def test_每个元素都是字符串(self):
        for name, value in _public_elements():
            self.assertIsInstance(value[0], str, '元素 %s 的定位方式应为字符串' % name)
            self.assertIsInstance(value[1], str, '元素 %s 的定位值应为字符串' % name)

    def test_定位方式都被BYMAP支持(self):
        for name, value in _public_elements():
            self.assertIn(
                value[0].lower(), BY_MAP,
                '元素 %s 的定位方式 %r 不在 BY_MAP 中，定位必然失败' % (name, value[0]),
            )

    def test_定位值非空(self):
        for name, value in _public_elements():
            self.assertTrue(value[1].strip(), '元素 %s 的定位值为空' % name)


class TestElementCoverage(unittest.TestCase):
    """业务链上必须存在的关键元素。"""

    REQUIRED = (
        'Username', 'Password', 'Sign_button',                    # 登录
        'button',                                                  # 进生产系统
        'content', 'material',                                     # 素材库导航
        'FileInput', 'videoauthor', 'phone', 'reporting', 'upload',  # 上传
        'keyword', 'querybutton', 'replacement',                   # 查询
        'submission', 'first_trial', 'save',                        # 报送
    )

    #: ★ 已删除的定位，删了就别再加回来（理由见下）
    RETIRED = {
        # 旧写法是"下拉列表第 8 项"，把审核人的**位置序号**写死 ——
        # 人员列表顺序一变就会静默选错人：不报错、用例还是绿的，最难发现。
        # 现改用 Element1.first_trial_person(姓名) 按姓名定位（姓名来自配置）。
        'person_of_first_instance',
    }

    def test_关键元素齐全(self):
        for name in self.REQUIRED:
            self.assertTrue(hasattr(Element1, name), '缺少关键元素：%s' % name)

    def test_已退役的脆弱定位不得回归(self):
        """★ 防止有人把写死序号的定位又加回来。"""
        for name in self.RETIRED:
            self.assertFalse(
                hasattr(Element1, name),
                '[%s] 是已退役的脆弱定位（写死下拉序号，会静默选错人）。\n'
                '    需要选审核人请用 Element1.first_trial_person(姓名)。' % name)

    def test_审核人按姓名动态构造定位(self):
        """审核人定位不再是固定条目，而是按姓名生成。"""
        self.assertTrue(callable(getattr(Element1, 'first_trial_person', None)),
                        '应提供 first_trial_person(name) 按姓名构造下拉项定位')
        selector = Element1.first_trial_person('张三')
        self.assertEqual(selector[0], 'xpath')
        self.assertIn('张三', selector[1])

    def test_文件上传控件使用input_file(self):
        """上传走 send_keys 方案的前提：定位到 input[type=file]。"""
        self.assertIn('file', Element1.FileInput[1].lower())


class TestCompatAlias(unittest.TestCase):
    """历史兼容别名。"""

    def test_旧类名Elemen1指向同一个类(self):
        self.assertIs(Elemen1, Element1)

    def test_别名获取到的元素与正式类一致(self):
        self.assertEqual(Elemen1.Username, Element1.Username)


class TestElementEnvOverride(unittest.TestCase):
    """元素定位的**环境变量**覆盖（UI_ELEMENTS_<键名大写>）。

    为什么单独测：文档（config.ini 注释、接入新系统指南）都承诺了环境变量能覆盖，
    但实现早期只遍历 config.ini 的 [elements] 段 —— 配置段里没写的键在
    Config.options() 里根本看不到，于是"UI_ELEMENTS_XXX 设了没反应"。
    这类失效最危险：不报错、不告警，只是定位悄悄用了旧值。
    """

    def setUp(self):
        from Common import elementPage
        self.mod = elementPage
        self._original = elementPage.Element1.Username
        self._saved_env = {k: v for k, v in os.environ.items()
                           if k.startswith(elementPage.ENV_ELEMENTS_PREFIX)}

    def tearDown(self):
        self.mod.Element1.Username = self._original
        for key in [k for k in os.environ
                    if k.startswith(self.mod.ENV_ELEMENTS_PREFIX)]:
            del os.environ[key]
        os.environ.update(self._saved_env)

    def test_环境变量可覆盖元素定位(self):
        """配置段里没有这一行，也要能被环境变量覆盖（CI 注入定位的核心用法）。"""
        from tests.helpers import patch_config

        with patch_config(ini_text='[elements]\n'):
            os.environ['UI_ELEMENTS_USERNAME'] = 'css:#u'
            applied = self.mod.apply_config_overrides()
        self.assertIn('Username', applied, '环境变量给了定位却没被应用')
        self.assertEqual(self.mod.Element1.Username, ['css', '#u'])

    def test_环境变量优先于配置文件(self):
        """同一条既配了文件又给了环境变量时，环境变量赢（与全工程优先级一致）。"""
        from tests.helpers import patch_config

        with patch_config(ini_text='[elements]\nUsername = id:from_ini\n'):
            os.environ['UI_ELEMENTS_USERNAME'] = 'css:#from_env'
            self.mod.apply_config_overrides()
        self.assertEqual(self.mod.Element1.Username, ['css', '#from_env'])

    def test_环境变量里拼错的键名不生效(self):
        """拼错不能静默改到别的元素上，也不能崩。"""
        from tests.helpers import patch_config

        with patch_config(ini_text='[elements]\n'):
            os.environ['UI_ELEMENTS_USERNAMEX'] = 'css:#u'
            applied = self.mod.apply_config_overrides()
        self.assertEqual(applied, [])
        self.assertEqual(self.mod.Element1.Username, self._original)

    def test_环境变量写法非法时报错并指出键名(self):
        from tests.helpers import patch_config

        with patch_config(ini_text='[elements]\n'):
            os.environ['UI_ELEMENTS_USERNAME'] = 'id:'
            with self.assertRaises(ValueError) as ctx:
                self.mod.apply_config_overrides()
        self.assertIn('Username', str(ctx.exception))

    def test_关闭环境变量覆盖时环境变量不生效(self):
        """UI_ENV_OVERRIDE=false 是全局开关，元素覆盖也要遵守。"""
        from tests.helpers import patch_config

        with patch_config(ini_text='[elements]\n'):
            os.environ['UI_ENV_OVERRIDE'] = 'false'
            os.environ['UI_ELEMENTS_USERNAME'] = 'css:#u'
            try:
                applied = self.mod.apply_config_overrides()
            finally:
                del os.environ['UI_ENV_OVERRIDE']
        self.assertEqual(applied, [])
        self.assertEqual(self.mod.Element1.Username, self._original)


if __name__ == '__main__':
    unittest.main(verbosity=2)
