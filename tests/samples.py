# -*- coding: utf-8 -*-
"""
==========================================================================
 测试样例用例集（供其它测试文件复用，**本文件本身不参与收集**）
==========================================================================

【为什么要单独放一个文件】
    下面这些类都是 unittest.TestCase 的子类，用来模拟"通过/失败/出错/跳过/
    类级异常"等场景，给 junitReport、HTMLTestReportCN 这类"结果处理"模块
    当输入数据。

    但 unittest 的 discover 会把模块里**所有** TestCase 子类都收集成真实用例 ——
    如果把它们写在 test_xxx.py 里，就会额外多出几条"故意失败""故意报错"的用例，
    把测试结果搅乱（明明全绿却显示失败）。

    解决办法：放进这个名字不以 test 开头的模块里。
    discover 只扫 test*.py，因此这里的内容不会被当成用例执行。

【新增样例时的约定】
    - 类名以场景命名，一眼能看出它代表什么结果
    - 每个类只保留必要方法，不要有副作用
==========================================================================
"""

import unittest


class PassCase(unittest.TestCase):
    """模拟一条通过的用例。"""

    def test_pass(self):
        self.assertEqual(1, 1)


class TwoPassCases(unittest.TestCase):
    """模拟同一个类里有两条通过的用例。"""

    def test_ok(self):
        self.assertEqual(1, 1)

    def test_ok2(self):
        pass


class FailCase(unittest.TestCase):
    """模拟一条断言失败的用例。"""

    def test_fail(self):
        self.assertEqual(1, 2, '故意失败')


class ErrorCase(unittest.TestCase):
    """模拟一条抛异常的用例。"""

    def test_boom(self):
        raise RuntimeError('故意抛错')


class SkipCase(unittest.TestCase):
    """模拟一条被跳过的用例。"""

    @unittest.skip('暂不执行')
    def test_skip(self):
        pass


class SpecialCharsCase(unittest.TestCase):
    """模拟断言消息里含 XML 特殊字符（< > &）的用例。"""

    def test_特殊字符(self):
        self.fail('消息含 <标签> & 与 "引号"')


class BoomSetUpClassCase(unittest.TestCase):
    """模拟 setUpClass 抛异常（真实场景：浏览器起不来）。

    这类异常会让 unittest 用 _ErrorHolder 代替用例回调 addError，
    是报告器最容易崩的一条路径。
    """

    @classmethod
    def setUpClass(cls):
        raise RuntimeError('模拟浏览器打不开')

    def test_never_runs(self):
        pass


class PrintCase(unittest.TestCase):
    """模拟用例中向控制台打印内容（应被收进 system-out）。"""

    def test_print(self):
        print('用例里的输出内容')
