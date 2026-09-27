# -*- coding: utf-8 -*-
"""
单元测试：Common/HTMLTestReportCN.py 的健壮性（第三方报告模板的定制部分）

只测工程改过/依赖的部分，不做模板渲染的像素级比对：
    1. 结果缓冲区在 __init__ 就建好 —— 这是修过的真实缺陷：
       setUpClass 抛异常（最常见的是浏览器起不来）时 unittest 会直接回调
       addError()，若缓冲区还没创建，就会抛 AttributeError 把真实原因盖掉，
       并产出一个 0 字节的空报告。
    2. HTMLTestRunner.run() 的 try/finally —— 无论发生什么都必须写出报告。
    3. resultclass 注入 —— 一次执行同时产出 HTML 与 JUnit XML 的关键。

说明：模拟各类结果的用例类放在 tests/samples.py，本文件不定义 TestCase 子类，
避免它们被 discover 当成真实用例执行。
"""

import io
import unittest

from Common.HTMLTestReportCN import HTMLTestRunner, _TestResult
from Common.junitReport import JUnitResult

# ★ 必须以「模块」方式引用样例用例，不能用 from tests.samples import Xxx，
#   否则这些 TestCase 子类会被 unittest 当成真实用例收集执行。
from tests import samples


def _run(suite, resultclass=None):
    """用 BytesIO 当输出流跑一次，返回 (runner, result, html字节)。"""
    stream = io.BytesIO()
    runner = HTMLTestRunner(stream=stream, title='单测报告', description='描述',
                            tester='unittest', resultclass=resultclass)
    result = runner.run(suite)
    return runner, result, stream.getvalue()


class TestResultBuffer(unittest.TestCase):
    """结果缓冲区的前提条件。"""

    def test_初始化时缓冲区已存在(self):
        result = _TestResult(verbosity=0)
        self.assertIsNotNone(getattr(result, 'outputBuffer', None))

    def test_未开始用例也能安全读取输出(self):
        """对应修复点：addError 在 startTest 之前被调用时不能崩。"""
        result = _TestResult(verbosity=0)
        self.assertEqual(result.complete_output(), '')

    def test_重复调用complete_output不报错(self):
        result = _TestResult(verbosity=0)
        result.complete_output()
        result.complete_output()

    def test_默认结果类就是内置实现(self):
        runner = HTMLTestRunner(stream=io.BytesIO())
        self.assertIs(runner.resultclass, _TestResult)

    def test_默认标题与执行人非空(self):
        runner = HTMLTestRunner(stream=io.BytesIO())
        self.assertTrue(runner.title)
        self.assertTrue(runner.tester)


class TestRunnerBehaviors(unittest.TestCase):
    """HTMLTestRunner 的执行与产出。"""

    def test_用例通过时报告非空且计数正确(self):
        _, result, html = _run(unittest.TestSuite([samples.PassCase('test_pass')]))
        self.assertGreater(len(html), 0, '报告不能是空文件')
        self.assertEqual(result.success_count, 1)

    def test_用例失败时报告包含失败信息且计数正确(self):
        _, result, html = _run(unittest.TestSuite([samples.FailCase('test_fail')]))
        self.assertEqual(result.failure_count, 1)
        text = html.decode('utf-8', errors='replace')
        self.assertIn('故意失败', text)

    def test_报告里包含用例名与标题(self):
        _, _, html = _run(unittest.TestSuite([samples.PassCase('test_pass')]))
        text = html.decode('utf-8', errors='replace')
        self.assertIn('test_pass', text)
        self.assertIn('单测报告', text)

    def test_setUpClass异常时报告仍然生成(self):
        """修复点验证：以前这里会抛 AttributeError 并留下 0 字节报告。"""
        _, result, html = _run(unittest.TestSuite([samples.BoomSetUpClassCase('test_never_runs')]))
        self.assertGreater(len(html), 0, '类级异常时报告必须仍然写出来')
        self.assertEqual(len(result.errors), 1)
        text = html.decode('utf-8', errors='replace')
        self.assertIn('模拟浏览器打不开', text, '真实原因必须体现在报告里')

    def test_注入自定义结果类生效(self):
        """一次执行同时产出 HTML + JUnit XML 的基础。"""
        _, result, html = _run(unittest.TestSuite([samples.PassCase('test_pass')]),
                               resultclass=JUnitResult)
        self.assertIsInstance(result, JUnitResult)
        self.assertEqual(len(result.cases), 1)
        self.assertEqual(result.cases[0]['status'], 'success')
        self.assertGreater(len(html), 0)

    def test_run始终返回结果对象(self):
        _, result, _ = _run(unittest.TestSuite([samples.PassCase('test_pass')]))
        self.assertTrue(hasattr(result, 'testsRun'))
        self.assertEqual(result.testsRun, 1)

    def test_报告标题与执行人可自定义(self):
        stream = io.BytesIO()
        runner = HTMLTestRunner(stream=stream, title='冒烟测试报告', tester='jenkins#128')
        runner.run(unittest.TestSuite([samples.PassCase('test_pass')]))
        text = stream.getvalue().decode('utf-8', errors='replace')
        self.assertIn('冒烟测试报告', text)
        self.assertIn('jenkins#128', text)


if __name__ == '__main__':
    unittest.main(verbosity=2)
