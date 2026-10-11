# -*- coding: utf-8 -*-
"""
==========================================================================
 JUnit XML 结果输出（新人阅读顺序：第 14 个，只在对接流水线时才需要读）
==========================================================================

【一句话说明】
    把测试结果写成 JUnit XML 文件 —— 这是 Jenkins / GitLab CI 等流水线
    **唯一认得的**测试结果格式。有了它，流水线才能自动把构建标记为
    「成功」或「失败」，并在构建页面上画出"通过 N 条 / 失败 M 条"的曲线。

【在框架中的位置】
    Common/runner.py
        ├─> Common/HTMLTestReportCN.py   给人看的 HTML 报告
        └─> Common/junitReport.py        <- 本文件：给机器看的 XML 结果

【为什么要专门写一个结果类】
    HTML 报告器内部用 _TestResult 收集结果，但它不记录"每条用例花了多久"，
    也没有 JUnit XML 需要的"类名 + 方法名"结构。
    所以这里继承它（JUnitResult），补上耗时和状态记录，
    再通过 HTMLTestRunner(resultclass=...) 注入。
    ★ 关键点：测试**只跑一遍**，同一份结果同时产出 HTML + XML 两种报告。

【JUnit XML 长什么样】
    <?xml version='1.0' encoding='utf-8'?>
    <testsuites tests="6" failures="1" errors="0" time="83.4">
      <testsuite name="TestSuites.testLogin.TestLogin" tests="6" ...>
        <testcase classname="TestSuites.testLogin.TestLogin" name="test_1login" time="8.1"/>
        <testcase classname="..." name="test_5keyword" time="4.2">
          <failure message="'期望标题' != '实际标题'">完整堆栈...</failure>
        </testcase>
        <system-out>用例打印的输出</system-out>
      </testsuite>
    </testsuites>

【新人注意】
    1. JUnit XML 对**结构**要求严格（标签名、属性名固定），
       但内容是自由的。改本文件时不要改标签名和属性名。
    2. 生成后可用一句话自检是否合法：
           python -c "import xml.etree.ElementTree as E; E.parse('Report/junit-results.xml')"
       能正常解析就说明 Jenkins 也能读。
    3. 用例失败时失败详情用 CDATA 思路（ElementTree 会自动转义），
       不要手工拼字符串，否则 Java 堆栈里的 < > 会让 XML 直接失效。
==========================================================================
"""

import os
import time
import traceback
import xml.etree.ElementTree as ET

# 复用 HTML 报告器的结果类：JUnitResult 在它的基础上扩展，
# 这样 HTMLTestRunner 可以直接拿本类当 resultclass 使用。
from Common.HTMLTestReportCN import _TestResult
from Common.dependency import DependencyRecorderMixin as _DependencyRecorderMixin
from Common.dir_config import ensure_dir
from Common.log import log1

# 单条用例的标准输出最多记录多少字符（防止日志把 XML 撑得过大）
MAX_OUTPUT_CHARS = 4000


def _case_meta(test):
    """解析一条用例的 `类名` 与 `方法名`，这是 JUnit XML 的必需字段。

    :param test: TestCase 实例，或 setUpClass 失败时的 _ErrorHolder 占位对象
    :return: (classname, name)

    两种情况：
      正常用例          -> ('TestSuites.testLogin.TestLogin', 'test_1login')
      setUpClass 报错   -> ('TestSuites.testLogin.TestLogin', 'setUpClass')
        （此时 unittest 用 _ErrorHolder 代替用例，它没有 _testMethodName，
          只能从 id() 形如 'setUpClass (TestSuites.testLogin.TestLogin)' 里拆）
    """
    try:
        classname = '%s.%s' % (test.__class__.__module__, test.__class__.__qualname__)
        name = test._testMethodName
    except AttributeError:
        # 兜底分支：setUpClass / tearDownClass 阶段的错误占位对象
        case_id = test.id()
        name = case_id.split(' ')[0]
        classname = case_id.split(' ')[-1].strip('()')
    return classname, name


class JUnitResult(_DependencyRecorderMixin, _TestResult):
    """测试结果收集器：在 HTML 报告结果的基础上，补上「耗时」与「状态明细」。

    继承 DependencyRecorderMixin：每次用例成功/失败/出错/跳过都会登记到
    Common.dependency，供「依赖级联跳过」判定使用（见 Common/dependency.py）。

    字段 `cases` 是给 junitReport.write_junit_xml() 消费的结构化数据，
    每条形如：
        {'classname': ..., 'name': ..., 'status': 'success|failure|error|skipped',
         'time': 8.123, 'message': '断言消息', 'detail': '完整堆栈', 'stdout': '...'}
    """

    def __init__(self, verbosity=1):
        # 先按 HTML 报告器的要求初始化（它会准备好 result / passrate 等字段）
        _TestResult.__init__(self, verbosity)
        self._case_start = {}   # 用例 id -> 开始时间戳（用于算耗时）
        self.cases = []         # 结构化结果，供 JUnit XML 输出

    # ------------------------------------------------------------------ #
    # 计时：每条用例的耗时靠 startTest / 被记录时的时间差算出来
    # ------------------------------------------------------------------ #
    def startTest(self, test):
        _TestResult.startTest(self, test)
        self._case_start[test.id()] = time.time()

    def _elapsed(self, test):
        """取出并清除该用例的开始时间，返回耗时（秒，保留 3 位小数）。"""
        start = self._case_start.pop(test.id(), None)
        return round(time.time() - start, 3) if start else 0.0

    def _output(self):
        """取本次用例执行期间页面/代码打印到 stdout/stderr 的内容。

        说明：基类的 complete_output() 会反复恢复 sys.stdout 而不会清空缓冲区，
        所以在记录结果时再读一次 getvalue() 仍能拿到完整输出。
        """
        try:
            return self.outputBuffer.getvalue()[:MAX_OUTPUT_CHARS]
        except Exception:   # pragma: no cover - 缓冲区异常不应影响测试结果
            return ''

    def _record(self, test, status, message='', detail='', artifacts=None):
        classname, name = _case_meta(test)
        self.cases.append({
            'classname': classname,
            'name': name,
            'status': status,
            'time': self._elapsed(test),
            'message': message,
            'detail': detail,
            'stdout': self._output(),
            'artifacts': artifacts or {},
        })

    def _capture(self, test, status):
        """失败/出错时自动取证：截图 + 页面源码。【在用】

        放在结果收集器里而不是用例里，是为了**兜底**：
        只要用例失败就一定取证，不管用例自己有没有记得截图，
        也不管失败发生在 setUp、断言还是框架内部。

        ★ 本方法绝不向外抛异常 —— 取证失败不能反过来把测试结果搞乱。
        """
        try:
            from Common.failureCapture import capture
            info = capture(test.id(), tag=status)
        except Exception:       # pragma: no cover - 取证自身的任何问题都不该影响结果
            log1.error('失败取证过程异常（不影响测试结果）', exc_info=1)
            return None
        if info and info.get('error') and not (info.get('screenshot') or info.get('source')):
            # 没有产出文件时把原因记下来，避免"以为有截图、其实没有"
            log1.info('失败取证未产生文件：%s' % info['error'])
        return info

    # ------------------------------------------------------------------ #
    # 四种结果：unittest 执行到对应分支时会回调这里
    # ------------------------------------------------------------------ #
    def addSuccess(self, test):
        _TestResult.addSuccess(self, test)      # 让 HTML 报告也能收到这条结果
        self._record(test, 'success')

    def addFailure(self, test, err):
        _TestResult.addFailure(self, test, err)
        # err 是 (异常类型, 异常对象, traceback)；拼成完整堆栈便于贴进缺陷单
        detail = ''.join(traceback.format_exception(*err))
        # 先取证再记录：取证要读"失败瞬间"的页面，晚一点页面可能已经变了
        artifacts = self._capture(test, 'failure')
        self._record(test, 'failure', message=str(err[1]), detail=detail,
                     artifacts=artifacts)

    def addError(self, test, err):
        _TestResult.addError(self, test, err)
        detail = ''.join(traceback.format_exception(*err))
        artifacts = self._capture(test, 'error')
        self._record(test, 'error', message=str(err[1]), detail=detail,
                     artifacts=artifacts)

    def addSkip(self, test, reason):
        # 基类没有重写 addSkip，直接用 unittest 标准实现记录到 self.skipped
        _TestResult.addSkip(self, test, reason)
        self._record(test, 'skipped', message=str(reason))


def _timestamp(epoch=None):
    """把时间戳格式化成 JUnit 要求的 ISO 形式：2026-09-25T09:05:53。"""
    return time.strftime('%Y-%m-%dT%H:%M:%S', time.localtime(epoch or time.time()))


def write_junit_xml(result, path, suite_name='UI Automation Test', properties=None,
                    run_start=None):
    """把 JUnitResult 的结果写成 JUnit XML 文件。

    :param result:     JUnitResult 实例
    :param path:       XML 输出路径（目录不存在会自动创建）
    :param suite_name: 顶层套件名，流水线页面上会显示它
    :param properties: 额外属性字典，例如构建号、分支、被测地址（会展示在 Jenkins 报告页）
    :param run_start:  整体开始时间戳，用于计算总耗时与 timestamp
    :return: 实际写入的文件路径

    结构约定：按「测试类」拆成多个 <testsuite>，每个类里的用例放一个 <testcase>。
    这样 Jenkins 的测试趋势图能按类维度展示，定位问题更快。
    """
    # ---- 1. 汇总统计（来自 unittest 的标准统计字段）----
    cases = result.cases
    total = result.testsRun
    failures = len(result.failures)
    errors = len(result.errors)
    skipped = len(result.skipped)
    total_time = round(sum(item['time'] for item in cases), 3)
    started = run_start or (time.time() - total_time)

    # ---- 2. 顶层节点 ----
    root = ET.Element('testsuites', {
        'name': suite_name,
        'tests': str(total),
        'failures': str(failures),
        'errors': str(errors),
        'skipped': str(skipped),
        'time': str(total_time),
        'timestamp': _timestamp(started),
    })

    # ---- 3. 按测试类分组，逐组生成 testsuite ----
    groups = {}
    order = []
    for item in cases:
        key = item['classname']
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(item)

    for classname in order:
        items = groups[classname]
        group_failures = len([i for i in items if i['status'] == 'failure'])
        group_errors = len([i for i in items if i['status'] == 'error'])
        group_skipped = len([i for i in items if i['status'] == 'skipped'])

        testsuite = ET.SubElement(root, 'testsuite', {
            'name': classname,
            'tests': str(len(items)),
            'failures': str(group_failures),
            'errors': str(group_errors),
            'skipped': str(group_skipped),
            'time': str(round(sum(i['time'] for i in items), 3)),
            'timestamp': _timestamp(started),
            # hostname 非必需，但 Jenkins 上多节点执行时便于区分机器
            'hostname': suite_name,
        })

        # 属性：构建号、分支、被测地址等，Jenkins 报告页会单列一块展示
        if properties:
            props = ET.SubElement(testsuite, 'properties')
            for key, value in properties.items():
                if value in (None, ''):
                    continue
                ET.SubElement(props, 'property', {'name': str(key), 'value': str(value)})

        # 逐条用例
        for item in items:
            case_node = ET.SubElement(testsuite, 'testcase', {
                'classname': item['classname'],
                'name': item['name'],
                'time': str(item['time']),
            })
            if item['status'] == 'failure':
                node = ET.SubElement(case_node, 'failure', {
                    'message': item['message'] or 'assertion failed',
                    'type': 'AssertionError',
                })
                node.text = item['detail']
            elif item['status'] == 'error':
                node = ET.SubElement(case_node, 'error', {
                    'message': item['message'] or 'unexpected error',
                    'type': 'Error',
                })
                node.text = item['detail']
            elif item['status'] == 'skipped':
                node = ET.SubElement(case_node, 'skipped', {
                    'message': item['message'] or 'skipped',
                })
                node.text = None

        # 该组用例的标准输出汇总（Jenkins 报告页可展开查看）
        # 失败用例额外附上"失败现场"的落盘路径，值班的人不用翻整个工作区找截图
        blocks = []
        for item in items:
            text = item['stdout']
            artifacts = item.get('artifacts') or {}
            shot, source = artifacts.get('screenshot'), artifacts.get('source')
            if shot or source:
                lines = ['[失败现场] %s' % item['name']]
                if shot:
                    lines.append('  截图     : %s' % shot)
                if source:
                    lines.append('  页面源码 : %s' % source)
                text = '%s\n%s' % (text, '\n'.join(lines)) if text else '\n'.join(lines)
            if text.strip():
                blocks.append(text)
        if blocks:
            out_node = ET.SubElement(testsuite, 'system-out')
            out_node.text = '\n'.join(blocks)

    # ---- 4. 落盘 ----
    # 目录不存在就创建，避免 Jenkins 首次执行因目录缺失而失败
    ensure_dir(os.path.dirname(os.path.abspath(path)))
    # indent 让 XML 可读（Python 3.9+），不影响 Jenkins 解析
    try:
        ET.indent(root, space='  ')
    except AttributeError:   # pragma: no cover - Python 3.8 及以下没有 indent
        pass
    ET.ElementTree(root).write(path, encoding='utf-8', xml_declaration=True)

    log1.info('JUnit XML 已生成：%s（用例 %d，失败 %d，错误 %d，跳过 %d）'
              % (path, total, failures, errors, skipped))
    return path
