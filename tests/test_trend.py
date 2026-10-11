# -*- coding: utf-8 -*-
"""
单元测试：Common/trend.py（通过率趋势）

★ 核心原则：**趋势是辅助功能，绝不能影响测试结论**。
  所以这里重点验证"各种坏情况下都不抛异常、不拖垮主流程"。
"""

import json
import os
import unittest
from unittest import mock

from tests.helpers import patch_dirs
from Common import trend


class _TrendCase(unittest.TestCase):
    """基类：把 Report 目录重定向到临时目录，避免污染工程。"""

    def setUp(self):
        self._dirs = patch_dirs()
        self.root = self._dirs.__enter__()

    def tearDown(self):
        self._dirs.__exit__(None, None, None)

    @staticmethod
    def _summary(tests=10, failures=0, errors=0, skipped=0):
        return {'tests_run': tests, 'failures': failures, 'errors': errors,
                'skipped': skipped, 'duration': 1.0, 'exit_code': 0}


class TestPassRate(unittest.TestCase):

    def test_全通过为100(self):
        self.assertEqual(trend.pass_rate({'tests_run': 6, 'failures': 0, 'errors': 0}), 100.0)

    def test_部分失败(self):
        self.assertEqual(trend.pass_rate({'tests_run': 10, 'failures': 2, 'errors': 1}),
                         70.0)

    def test_零用例不除零(self):
        self.assertEqual(trend.pass_rate({'tests_run': 0}), 0.0)
        self.assertEqual(trend.pass_rate({}), 0.0)


class TestAppendRun(_TrendCase):

    def test_追加成功并返回记录(self):
        record = trend.append_run(self._summary())
        self.assertIsNotNone(record)
        self.assertEqual(record['pass_rate'], 100.0)
        self.assertIs(os.path.isfile(trend.history_path()), True)

    def test_多次追加累积(self):
        for _ in range(3):
            trend.append_run(self._summary())
        self.assertEqual(len(trend.load_history()), 3)

    def test_额外字段被合并(self):
        trend.append_run(self._summary(), extra={'app_build': '20261011.1'})
        record = trend.load_history()[-1]
        self.assertEqual(record['app_build'], '20261011.1')

    def test_写入失败不抛异常(self):
        """★ 趋势记录不了不该让一次成功的测试变成失败。"""
        with mock.patch('Common.trend.open', side_effect=OSError('磁盘满'), create=True):
            self.assertIsNone(trend.append_run(self._summary()))

    def test_超过上限会裁剪(self):
        with mock.patch.object(trend, 'MAX_KEEP', 5):
            for _ in range(8):
                trend.append_run(self._summary())
        self.assertEqual(len(trend.load_history()), 5)


class TestLoadHistory(_TrendCase):

    def test_文件不存在返回空列表(self):
        self.assertEqual(trend.load_history(), [])

    def test_坏行被跳过而不是整个文件失效(self):
        """★ 写入被中断时最多损失一行，不该让整个趋势不可读。"""
        trend.append_run(self._summary(tests=10))
        with open(trend.history_path(), 'a', encoding='utf-8') as fp:
            fp.write('{这不是合法json\n')
        trend.append_run(self._summary(tests=20))
        records = trend.load_history()
        self.assertEqual(len(records), 2, '坏行应被跳过，其它行照常读出')

    def test_limit只取最近N条(self):
        for i in range(5):
            trend.append_run(self._summary(tests=i + 1))
        records = trend.load_history(limit=2)
        self.assertEqual(len(records), 2)
        self.assertEqual(records[-1]['tests_run'], 5)


class TestTrend(_TrendCase):

    def test_无历史时给出说明(self):
        info = trend.trend()
        self.assertEqual(info['samples'], 0)
        self.assertIn('第一次', info['message'])
        self.assertFalse(info['alert'])

    def test_计算出最新与环比(self):
        trend.append_run(self._summary(tests=10, failures=2))   # 80%
        trend.append_run(self._summary(tests=10, failures=0))   # 100%
        info = trend.trend()
        self.assertEqual(info['latest'], 100.0)
        self.assertEqual(info['previous'], 80.0)
        self.assertEqual(info['delta'], 20.0)
        self.assertEqual(info['direction'], 'up')

    def test_通过率下降方向为down(self):
        trend.append_run(self._summary(tests=10, failures=0))
        trend.append_run(self._summary(tests=10, failures=3))
        self.assertEqual(trend.trend()['direction'], 'down')

    def test_连续下滑触发告警(self):
        """★ 这条是趋势功能的核心价值：在"还绿着"的时候就发现劣化。"""
        for failures in (0, 1, 2, 3):
            trend.append_run(self._summary(tests=10, failures=failures))
        info = trend.trend()
        self.assertTrue(info['alert'])
        self.assertIn('连续', info['message'])

    def test_低于90触发告警(self):
        trend.append_run(self._summary(tests=10, failures=3))   # 70%
        info = trend.trend()
        self.assertTrue(info['alert'])
        self.assertIn('90', info['message'])

    def test_平稳时不告警(self):
        for _ in range(3):
            trend.append_run(self._summary(tests=10, failures=0))
        self.assertFalse(trend.trend()['alert'])

    def test_平均值正确(self):
        trend.append_run(self._summary(tests=10, failures=0))   # 100
        trend.append_run(self._summary(tests=10, failures=5))   # 50
        self.assertEqual(trend.trend()['average'], 75.0)


class TestFormatTrend(_TrendCase):

    def test_无历史返回空串(self):
        self.assertEqual(trend.format_trend(), '')

    def test_有历史时包含关键信息(self):
        trend.append_run(self._summary(tests=10, failures=1))
        text = trend.format_trend()
        self.assertIn('通过率趋势', text)
        self.assertIn('90.0%', text)
        self.assertIn('结论', text)

    def test_环比箭头(self):
        trend.append_run(self._summary(tests=10, failures=5))
        trend.append_run(self._summary(tests=10, failures=0))
        self.assertIn('↑', trend.format_trend())


class TestHistoryIsJsonl(_TrendCase):
    """历史文件是 JSON Lines —— 可 grep、可 git diff。"""

    def test_每行一个独立json对象(self):
        for _ in range(3):
            trend.append_run(self._summary())
        with open(trend.history_path(), encoding='utf-8') as fp:
            lines = [ln for ln in fp.read().splitlines() if ln.strip()]
        self.assertEqual(len(lines), 3)
        for line in lines:
            self.assertIsInstance(json.loads(line), dict)

    def test_中文不被转义成unicode转义序列(self):
        """ensure_ascii=False：人得能直接看懂文件内容。"""
        trend.append_run(self._summary(tests=10, failures=1),
                         extra={'note': '中文说明'})
        with open(trend.history_path(), encoding='utf-8') as fp:
            self.assertIn('中文说明', fp.read())


if __name__ == '__main__':
    unittest.main(verbosity=2)
