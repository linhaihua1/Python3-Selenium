# -*- coding: utf-8 -*-
"""单元测试：测试数据治理与用例隔离（Common/dataGovernance.py）"""

import unittest

from tests.helpers import patch_config
from Common import dataGovernance
from Common.dataGovernance import TestDataGovernor, IsolatedTestCase


class TestTag(unittest.TestCase):
    def test_tag唯一且格式正确(self):
        tags = {dataGovernance._new_tag() for _ in range(50)}
        self.assertEqual(len(tags), 50)          # 50 个不重复
        for t in tags:
            self.assertTrue(t.replace('_', '').isalnum())


class TestGovernor(unittest.TestCase):
    def test_record要求可调用(self):
        g = TestDataGovernor()
        with self.assertRaises(TypeError):
            g.record('x', 'not callable')

    def test_cleanup_all按倒序执行且永不抛(self):
        g = TestDataGovernor()
        order = []
        g.record('a', lambda: order.append('a'))
        g.record('b', lambda: (_ for _ in ()).throw(RuntimeError('boom')))
        g.record('c', lambda: order.append('c'))
        results = g.cleanup_all()
        # 倒序：c 先，b 中（抛异常被兜住），a 最后
        self.assertEqual(order, ['c', 'a'])
        labels = [(r[0], r[1]) for r in results]
        self.assertEqual(labels, [('c', True), ('b', False), ('a', True)])
        self.assertIn('boom', results[1][2])
        self.assertEqual(g.pending, 0)

    def test_cleanup_only_once(self):
        g = TestDataGovernor()
        n = [0]
        g.record('a', lambda: n.__setitem__(0, n[0] + 1))
        g.cleanup_all()
        g.cleanup_all()                      # 二次调用不应重复执行
        self.assertEqual(n[0], 1)

    def test_tag可自定义(self):
        g = TestDataGovernor(tag='fixed')
        self.assertEqual(g.tag, 'fixed')


class TestIsolatedTestCase(unittest.TestCase):
    def setUp(self):
        self._cfg = patch_config()
        self._cfg.__enter__()

    def tearDown(self):
        self._cfg.__exit__(None, None, None)

    def test_清理在用例失败后仍执行(self):
        cleaned = []

        class Demo(IsolatedTestCase):
            def runTest(self):
                self.data.record('x', lambda: cleaned.append('x'))
                raise AssertionError('故意失败')

        case = Demo('runTest')
        result = unittest.TestResult()
        case.run(result)                       # 用例失败，但 tearDown 仍应清理
        self.assertEqual(cleaned, ['x'])
        self.assertEqual(len(result.failures), 1)   # 失败结果未被掩盖

    def test_reset_state异常不影响用例(self):
        class Demo(IsolatedTestCase):
            def reset_state(self):
                raise RuntimeError('复位失败')

            def runTest(self):
                self.assertTrue(True)

        result = unittest.TestResult()
        Demo('runTest').run(result)
        self.assertTrue(result.wasSuccessful())   # 用例本身通过

    def test_关闭自动清理时不执行(self):
        cleaned = []

        class Demo(IsolatedTestCase):
            def runTest(self):
                self.data.record('x', lambda: cleaned.append('x'))

        with patch_config(ini_text='[testcase]\nauto_cleanup = false\n'):
            Demo('runTest').run(unittest.TestResult())
        self.assertEqual(cleaned, [])


if __name__ == '__main__':
    unittest.main()
