# -*- coding: utf-8 -*-
"""
单元测试：Common/junitReport.py（给流水线看的 JUnit XML）

JUnit XML 是 Jenkins 判定构建成败、绘制测试趋势图的**唯一依据**，
所以这里重点验证：
    - 结果收集是否完整（四种状态都要有记录，且带耗时）
    - setUpClass 异常时的占位对象能否被正确解析出类名/方法名
    - 生成的 XML 是否**结构合法**（能被标准解析器读回来）
    - 用例名/断言消息里的 < > & 等特殊字符是否被正确转义

说明：模拟各类结果的用例类放在 tests/samples.py，
不放在本文件里 —— 否则会被 discover 当成真实用例执行。
"""

import os
import shutil
import tempfile
import unittest
import xml.etree.ElementTree as ET
from unittest.suite import _ErrorHolder

from Common.junitReport import JUnitResult, _case_meta, write_junit_xml

# ★ 必须以「模块」方式引用样例用例，不能用 from tests.samples import Xxx。
#   因为 unittest 在加载测试模块时，会把模块命名空间里所有 TestCase 子类
#   都当成测试用例收走 —— 用 from ... import 导入的样例类会被连带收集，
#   导致结果里凭空多出"故意失败""故意报错"的用例。
from tests import samples


def run_suite(*cases):
    """执行一组用例并返回结果对象（走 unittest 正常流程）。"""
    suite = unittest.TestSuite(cases)
    result = JUnitResult(verbosity=0)
    suite.run(result)
    return result


class TestCaseMeta(unittest.TestCase):
    """用例元信息解析。"""

    def test_普通用例解析出类名与方法名(self):
        classname, name = _case_meta(samples.TwoPassCases('test_ok'))
        self.assertTrue(classname.endswith('TwoPassCases'))
        self.assertEqual(name, 'test_ok')

    def test_类名为模块加点号形式(self):
        classname, _ = _case_meta(samples.TwoPassCases('test_ok'))
        self.assertIn('tests.samples', classname)

    def test_setUpClass异常时的占位对象(self):
        """setUpClass 抛错时 unittest 会用 _ErrorHolder 代替用例，
        它没有 _testMethodName，必须能从 id() 里拆出来。"""
        holder = _ErrorHolder('setUpClass (TestSuites.testLogin.TestLogin)')
        classname, name = _case_meta(holder)
        self.assertEqual(name, 'setUpClass')
        self.assertEqual(classname, 'TestSuites.testLogin.TestLogin')


class TestJUnitResult(unittest.TestCase):
    """结果收集。"""

    def test_记录通过的用例(self):
        result = run_suite(samples.TwoPassCases('test_ok'), samples.TwoPassCases('test_ok2'))
        self.assertEqual(result.testsRun, 2)
        self.assertEqual(len(result.cases), 2)
        self.assertTrue(all(item['status'] == 'success' for item in result.cases))

    def test_记录失败的用例(self):
        result = run_suite(samples.FailCase('test_fail'))
        self.assertEqual(len(result.failures), 1)
        self.assertEqual(result.cases[0]['status'], 'failure')
        self.assertIn('故意失败', result.cases[0]['message'])
        self.assertIn('AssertionError', result.cases[0]['detail'])

    def test_记录出错的用例(self):
        result = run_suite(samples.ErrorCase('test_boom'))
        self.assertEqual(len(result.errors), 1)
        self.assertEqual(result.cases[0]['status'], 'error')
        self.assertIn('故意抛错', result.cases[0]['message'])

    def test_记录跳过的用例(self):
        result = run_suite(samples.SkipCase('test_skip'))
        self.assertEqual(len(result.skipped), 1)
        self.assertEqual(result.cases[0]['status'], 'skipped')
        self.assertIn('暂不执行', result.cases[0]['message'])

    def test_每条用例都带耗时字段(self):
        result = run_suite(samples.TwoPassCases('test_ok'))
        self.assertIn('time', result.cases[0])
        self.assertIsInstance(result.cases[0]['time'], float)
        self.assertGreaterEqual(result.cases[0]['time'], 0.0)

    def test_混合结果计数正确(self):
        result = run_suite(samples.TwoPassCases('test_ok'), samples.FailCase('test_fail'),
                           samples.ErrorCase('test_boom'), samples.SkipCase('test_skip'))
        self.assertEqual(result.testsRun, 4)
        self.assertEqual(len(result.failures), 1)
        self.assertEqual(len(result.errors), 1)
        self.assertEqual(len(result.skipped), 1)
        statuses = sorted(item['status'] for item in result.cases)
        self.assertEqual(statuses, ['error', 'failure', 'skipped', 'success'])

    def test_用例print的内容被收集(self):
        result = run_suite(samples.PrintCase('test_print'))
        self.assertIn('用例里的输出内容', result.cases[0]['stdout'])


class TestWriteJunitXml(unittest.TestCase):
    """XML 生成与结构合法性。"""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix='ut_junit_')
        self.path = os.path.join(self.tmpdir, 'junit-results.xml')

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _write(self, result, **kwargs):
        path = write_junit_xml(result, self.path, **kwargs)
        self.assertTrue(os.path.exists(path))
        # 能被标准解析器读回来，才说明 Jenkins 也能读
        return ET.parse(path).getroot()

    def test_生成的文件能被标准解析器读取(self):
        root = self._write(run_suite(samples.TwoPassCases('test_ok')), suite_name='单测')
        self.assertEqual(root.tag, 'testsuites')

    def test_顶层统计属性正确(self):
        result = run_suite(samples.TwoPassCases('test_ok'), samples.FailCase('test_fail'))
        root = self._write(result, suite_name='单测')
        self.assertEqual(root.get('tests'), '2')
        self.assertEqual(root.get('failures'), '1')
        self.assertEqual(root.get('errors'), '0')
        self.assertEqual(root.get('name'), '单测')

    def test_按测试类分组(self):
        result = run_suite(samples.TwoPassCases('test_ok'), samples.FailCase('test_fail'))
        root = self._write(result)
        names = [node.get('name') for node in root.findall('testsuite')]
        self.assertEqual(len(names), 2, '两个测试类应生成两个 testsuite 节点')
        self.assertTrue(any(n.endswith('TwoPassCases') for n in names))
        self.assertTrue(any(n.endswith('FailCase') for n in names))

    def test_每条用例生成一个testcase节点(self):
        result = run_suite(samples.TwoPassCases('test_ok'), samples.TwoPassCases('test_ok2'))
        root = self._write(result)
        cases = root.findall('.//testcase')
        self.assertEqual(len(cases), 2)
        for case in cases:
            self.assertIn('classname', case.attrib)
            self.assertIn('time', case.attrib)

    def test_失败用例带failure节点(self):
        root = self._write(run_suite(samples.FailCase('test_fail')))
        node = root.find('.//testcase/failure')
        self.assertIsNotNone(node)
        self.assertIn('故意失败', node.get('message'))
        self.assertEqual(node.get('type'), 'AssertionError')

    def test_出错用例带error节点(self):
        root = self._write(run_suite(samples.ErrorCase('test_boom')))
        node = root.find('.//testcase/error')
        self.assertIsNotNone(node)
        self.assertIn('故意抛错', node.get('message'))

    def test_跳过用例带skipped节点(self):
        root = self._write(run_suite(samples.SkipCase('test_skip')))
        node = root.find('.//testcase/skipped')
        self.assertIsNotNone(node)
        self.assertIn('暂不执行', node.get('message'))

    def test_特殊字符被正确转义且可还原(self):
        """用例名或断言消息里出现 < > & 时，XML 不能因此变成非法文件。"""
        root = self._write(run_suite(samples.SpecialCharsCase('test_特殊字符')))
        node = root.find('.//testcase/failure')
        self.assertIsNotNone(node)
        self.assertIn('<标签>', node.get('message'))
        self.assertIn('&', node.get('message'))

    def test_写入构建属性(self):
        root = self._write(
            run_suite(samples.TwoPassCases('test_ok')),
            properties={'job': 'ui-smoke', 'build': '128', 'branch': ''},
        )
        props = {node.get('name'): node.get('value')
                 for node in root.findall('.//property')}
        self.assertEqual(props.get('job'), 'ui-smoke')
        self.assertEqual(props.get('build'), '128')
        self.assertNotIn('branch', props, '空值属性应被跳过，避免 Jenkins 展示空白项')

    def test_空结果也能生成合法文件(self):
        root = self._write(JUnitResult(verbosity=0))
        self.assertEqual(root.get('tests'), '0')
        self.assertEqual(root.findall('testsuite'), [])

    def test_时间戳格式符合JUnit约定(self):
        root = self._write(run_suite(samples.TwoPassCases('test_ok')))
        timestamp = root.get('timestamp')
        self.assertRegex(timestamp, r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$')

    def test_目录不存在时自动创建(self):
        nested = os.path.join(self.tmpdir, 'a', 'b', 'results.xml')
        write_junit_xml(run_suite(samples.TwoPassCases('test_ok')), nested)
        self.assertTrue(os.path.exists(nested))

    def test_用例的标准输出写入system_out(self):
        root = self._write(run_suite(samples.PrintCase('test_print')))
        node = root.find('.//system-out')
        self.assertIsNotNone(node)
        self.assertIn('用例里的输出内容', node.text)


if __name__ == '__main__':
    unittest.main(verbosity=2)
