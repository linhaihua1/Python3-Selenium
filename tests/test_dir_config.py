# -*- coding: utf-8 -*-
"""
单元测试：Common/dir_config.py（路径单一来源）

价值：路径推导一旦出错，会表现为"报告生成到别的目录""用例一条都收不到"，
属于很难一眼看出的故障，所以用测试把它钉死。
"""

import os
import shutil
import tempfile
import unittest

from tests.helpers import BASE_DIR
from Common import dir_config


class TestDirConfig(unittest.TestCase):
    """路径常量与 ensure_dir。"""

    def test_base_dir指向工程根目录(self):
        self.assertEqual(
            os.path.normpath(dir_config.base_dir), os.path.normpath(BASE_DIR)
        )

    def test_工程根目录下确实存在标志性文件(self):
        for name in ('run.py', 'entrance.py', 'getcwd.py', 'config.ini', 'Common'):
            self.assertTrue(
                os.path.exists(os.path.join(dir_config.base_dir, name)),
                '工程根目录应包含：%s' % name,
            )

    def test_用例目录与报告目录拼接正确(self):
        self.assertEqual(
            dir_config.testcases_dir, os.path.join(dir_config.base_dir, 'TestSuites')
        )
        self.assertEqual(
            dir_config.htmlreport_dir, os.path.join(dir_config.base_dir, 'Report')
        )

    def test_junit结果文件位于报告目录内(self):
        self.assertEqual(
            os.path.dirname(dir_config.junitreport_file), dir_config.htmlreport_dir
        )
        self.assertTrue(dir_config.junitreport_file.endswith('.xml'))

    def test_所有路径都是绝对路径(self):
        for value in (dir_config.base_dir, dir_config.testcases_dir,
                      dir_config.htmlreport_dir, dir_config.junitreport_file):
            self.assertTrue(os.path.isabs(value), '应为绝对路径：%s' % value)


class TestEnsureDir(unittest.TestCase):
    """ensure_dir 的创建与幂等性。"""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix='ut_dir_')

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_目录不存在时创建并返回(self):
        target = os.path.join(self.tmpdir, 'a', 'b', 'c')
        self.assertFalse(os.path.exists(target))
        returned = dir_config.ensure_dir(target)
        self.assertTrue(os.path.isdir(target))
        self.assertEqual(returned, target)

    def test_目录已存在时不报错(self):
        target = os.path.join(self.tmpdir, 'exists')
        os.makedirs(target)
        self.assertEqual(dir_config.ensure_dir(target), target)

    def test_可链式拼接文件路径(self):
        target = os.path.join(self.tmpdir, 'report')
        path = os.path.join(dir_config.ensure_dir(target), 'x.html')
        self.assertTrue(os.path.isdir(os.path.dirname(path)))


if __name__ == '__main__':
    unittest.main(verbosity=2)
