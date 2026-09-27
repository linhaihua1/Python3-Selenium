# -*- coding: utf-8 -*-
"""
单元测试：Common/configOverWriter.py（定制版 ConfigParser）

覆盖两个被真实故障逼出来的改造点：
    1. 键名大小写保留（父类会强制转小写）
    2. 关闭 % 插值（父类把 % 当插值符，路徑/密码里有 % 就抛异常）
"""

import configparser
import os
import tempfile
import unittest

from tests.helpers import ConfigOverWrite


class TestConfigOverWrite(unittest.TestCase):
    """ConfigOverWrite 的读取行为。"""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix='ut_cow_')
        self.ini_path = os.path.join(self.tmpdir, 'cfg.ini')
        with open(self.ini_path, 'w', encoding='utf-8') as fp:
            fp.write(
                '[Mixed]\n'
                'MixedKey = 混大小写\n'
                'UPPER = 全大写\n'
                'lower = 全小写\n'
                '\n'
                '[Pct]\n'
                'percent = 100%素材\n'
                'password = ab%cd123\n'
            )

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _parse(self, cls):
        parser = cls()
        parser.read(self.ini_path, encoding='utf-8')
        return parser

    def test_键名大小写被原样保留(self):
        parser = self._parse(ConfigOverWrite)
        self.assertEqual(
            sorted(parser.options('Mixed')),
            ['MixedKey', 'UPPER', 'lower'],
            'ConfigOverWrite 应保留键名原始大小写',
        )
        self.assertEqual(parser.get('Mixed', 'MixedKey'), '混大小写')
        self.assertEqual(parser.get('Mixed', 'UPPER'), '全大写')

    def test_标准解析器会丢大小写_用作对照(self):
        """对照组：说明这个子类确实修掉了父类的行为差异。"""
        parser = self._parse(configparser.ConfigParser)
        self.assertEqual(sorted(parser.options('Mixed')), ['lower', 'mixedkey', 'upper'])

    def test_百分比不被当作插值符(self):
        parser = self._parse(ConfigOverWrite)
        self.assertEqual(parser.get('Pct', 'percent'), '100%素材')
        self.assertEqual(parser.get('Pct', 'password'), 'ab%cd123')

    def test_标准解析器会因百分比抛插值异常_用作对照(self):
        """对照组：证明关闭插值不是多余动作。"""
        parser = self._parse(configparser.ConfigParser)
        with self.assertRaises(configparser.InterpolationSyntaxError):
            parser.get('Pct', 'percent')

    def test_支持传入默认值字典(self):
        parser = ConfigOverWrite(defaults={'base': '默认值'})
        self.assertEqual(parser.get('DEFAULT', 'base'), '默认值')


if __name__ == '__main__':
    unittest.main(verbosity=2)
