# -*- coding: utf-8 -*-
"""单元测试：并行执行能力（Common/parallelRunner + runner._load_modules/build_suite modules 参数）"""

import os
import tempfile
import unittest

from tests.helpers import patch_config, patch_dirs
from Common import parallelRunner, runner


class TestShard(unittest.TestCase):
    def test_轮询分片均衡(self):
        self.assertEqual(parallelRunner.shard(['a', 'b', 'c', 'd', 'e'], 2),
                         [['a', 'c', 'e'], ['b', 'd']])

    def test_分片数不超过元素数(self):
        self.assertEqual(parallelRunner.shard(['a', 'b'], 5), [['a'], ['b']])

    def test_空列表(self):
        self.assertEqual(parallelRunner.shard([], 3), [])

    def test_workers_非法值兜底(self):
        # n<=0 被规范成 1：所有元素进一个分片
        self.assertEqual(parallelRunner.shard(['a', 'b'], 0), [['a', 'b']])
        self.assertEqual(parallelRunner.shard(['a', 'b'], -1), [['a', 'b']])


class TestAggregate(unittest.TestCase):
    def test_统计相加_cases拼接(self):
        s1 = runner._summary(tests_run=3, failures=1, exit_code=1,
                             cases=[{'status': 'failure'}], duration=5.0)
        s2 = runner._summary(tests_run=2, errors=1, exit_code=2,
                             cases=[{'status': 'error'}], duration=2.0, reason='x')
        m = parallelRunner.aggregate([s1, s2])
        self.assertEqual(m['tests_run'], 5)
        self.assertEqual(m['failures'], 1)
        self.assertEqual(m['errors'], 1)
        self.assertEqual(m['exit_code'], 2)   # 取最大
        self.assertEqual(m['duration'], 5.0)  # 取最大（墙钟）
        self.assertEqual(len(m['cases']), 2)
        self.assertEqual(m['reason'], 'x')
        self.assertFalse(m['success'])

    def test_空输入返回默认结构(self):
        m = parallelRunner.aggregate([])
        self.assertEqual(m['exit_code'], 0)
        self.assertEqual(m['cases'], [])
        self.assertTrue(m['success'])

    def test_全部通过时success为真(self):
        s = runner._summary(tests_run=2, exit_code=0, duration=1.0)
        m = parallelRunner.aggregate([s])
        self.assertTrue(m['success'])


class TestListAndLoadModules(unittest.TestCase):
    def setUp(self):
        self._cfg = patch_config()
        self._cfg.__enter__()
        self._dirs = patch_dirs()
        self._dirs.__enter__()

    def tearDown(self):
        self._dirs.__exit__(None, None, None)
        self._cfg.__exit__(None, None, None)

    def test_build_suite按modules加载(self):
        # 用一个真实存在的测试文件验证路径->模块名->用例加载链路
        real_file = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'TestSuites', 'testLogin.py')
        if not os.path.isfile(real_file):
            self.skipTest('TestSuites/testLogin.py 不存在')
        suite = runner.build_suite(modules=[real_file])
        self.assertGreater(suite.countTestCases(), 0)

    def test_list_test_files(self):
        files = parallelRunner.list_test_files()
        # 至少应包含工程里的用例文件
        self.assertTrue(any(f.endswith('.py') for f in files))


if __name__ == '__main__':
    unittest.main()
