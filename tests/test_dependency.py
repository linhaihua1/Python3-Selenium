# -*- coding: utf-8 -*-
"""单元测试：用例依赖声明 + 失败级联跳过（Common/dependency.py）"""

import unittest

from Common import dependency
from Common.dependency import (
    DependencyRecorderMixin, depends_on, deps_of, failed_dependencies, guard, reset,
)


class _RecResult(DependencyRecorderMixin, unittest.TestResult):
    """带结果登记的 TestResult：模拟 runner 里 JUnitResult 的登记行为。"""
    pass


class TestDecorator(unittest.TestCase):
    def setUp(self):
        reset()

    def test_声明依赖(self):
        @depends_on('test_a')
        def f(self): pass
        self.assertEqual(deps_of(type('C', (), {'test_x': f})()), [])  # 方法名不匹配
        # 直接读属性
        self.assertEqual(getattr(f, dependency._DEP_ATTR), ['test_a'])

    def test_多依赖去重保序(self):
        @depends_on('b', 'a', 'b', 'a')
        def f(self): pass
        self.assertEqual(getattr(f, dependency._DEP_ATTR), ['b', 'a'])


class TestCascadeSkip(unittest.TestCase):
    def setUp(self):
        reset()

    def _make(self, ran):
        class Flow(unittest.TestCase):
            def test_1(self):
                ran.append(1)
                raise AssertionError('前置故意失败')

            @depends_on('test_1')
            def test_2(self):
                ran.append(2)

            @depends_on('test_2')
            def test_3(self):
                ran.append(3)

            @depends_on('test_1')
            def test_4(self):
                ran.append(4)   # 依赖 test_1，test_1 失败则也被跳过
        return Flow

    def test_前置失败_后继被跳过_不连坐(self):
        ran = []
        Flow = self._make(ran)
        suite = dependency.wrap_suite(unittest.TestLoader().loadTestsFromTestCase(Flow))
        result = _RecResult()
        suite.run(result)
        # test_1 失败；test_2/3/4 因依赖失败被跳过；只有 test_1 真正执行
        self.assertEqual(ran, [1])
        self.assertEqual(len(result.failures), 1)
        self.assertEqual(len(result.skipped), 3)   # test_2,3,4 都被跳过
        # 跳过原因应能溯源到最早失败点：test_2/test_4 直连 test_1，
        # test_3 链式依赖 test_2（因 test_2 被跳过而跳过）
        reasons = [r for _, r in result.skipped]
        self.assertTrue(any('test_1' in r for r in reasons), reasons)
        self.assertTrue(any('test_2' in r for r in reasons), reasons)

    def test_无失败依赖_正常执行(self):
        ran = []

        class OK(unittest.TestCase):
            def test_a(self): ran.append('a')
            @depends_on('test_a')
            def test_b(self): ran.append('b')
        suite = dependency.wrap_suite(unittest.TestLoader().loadTestsFromTestCase(OK))
        result = unittest.TestResult()
        suite.run(result)
        self.assertEqual(ran, ['a', 'b'])
        self.assertEqual(len(result.skipped), 0)
        self.assertTrue(result.wasSuccessful())

    def test_依赖未执行_不阻断(self):
        # test_b 在 test_a 之前被收集到（字母序 test_a < test_b，正常）；
        # 但如果手工乱序让依赖尚未执行，guard 不应误判为失败
        dependency.record('test_a', 'pass')   # 已登记成功

        class C(unittest.TestCase):
            @depends_on('test_a')
            def test_b(self): pass
        case = C('test_b')
        self.assertEqual(failed_dependencies(case), [])
        self.assertFalse(guard(case, unittest.TestResult()))


class TestDependencyRecorderIntegration(unittest.TestCase):
    """★★ 集成回归：JUnitResult 必须经 MRO 触发依赖登记（2026-10-17 真 bug 防回退）。

    历史缺陷：JUnitResult.addSuccess/addFailure 直接调 _TestResult.xxx，
    绕过了 MRO 中间的 DependencyRecorderMixin —— dependency.record 永不执行，
    @depends_on 在 run.py 主链路上静默失效（前置失败后继照样跑）。

    为什么单元测试当初没拦住：test_dependency 只测 dependency 模块自身、
    test_junit_report 只测 JUnitResult 自身，**两者之间的集成点**没人管。
    本用例把两者接起来，直接复现"前置失败 -> 后继级联 skip"的主链路行为。
    """

    def setUp(self):
        reset()

    def test_JUnitResult触发依赖级联跳过(self):
        from Common.junitReport import JUnitResult
        from Common.dependency import _install_guard

        class Flow(unittest.TestCase):
            def test_a_fail(self):
                self.fail('前置失败')

            @depends_on('test_a_fail')
            def test_b_depends(self):
                pass

        suite = unittest.TestSuite([
            Flow('test_a_fail'),
            _install_guard(Flow('test_b_depends')),   # runner 主链路就是这么装的
        ])
        # 用与 runner 相同的结果类跑（JUnitResult 的 MRO 即被测对象）
        junit = JUnitResult(verbosity=0)
        suite.run(junit)

        self.assertEqual(len(junit.failures), 1, '前置应失败 1 条')
        self.assertEqual(len(junit.skipped), 1,
                         '后继依赖前置失败，必须级联 skip —— 若本断言失败，'
                         '说明 JUnitResult 的 add* 又绕过了 DependencyRecorderMixin '
                         '（直接调 _TestResult.xxx），@depends_on 在主链路上已静默失效')


if __name__ == '__main__':
    unittest.main()
