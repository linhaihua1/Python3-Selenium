# -*- coding: utf-8 -*-
"""
==========================================================================
 用例依赖声明 + 失败级联跳过（企业级「用例独立性」能力之一）
==========================================================================

【解决什么问题】
    业务流用例常常有先后依赖：test_5 查询依赖 test_4 上传的产物。
    一旦 test_4 失败，test_5 再跑只会"连坐失败"，报一堆误导性错误，
    真正的根因反而被淹没。企业级做法：声明依赖，前置失败时后继**自动跳过**，
    报告里清楚写"因依赖 test_4 失败而跳过"，一眼定位最早失败点。

【怎么用】
    from Common.dependency import depends_on

    class TestFlow(unittest.TestCase):
        def test_1login(self): ...
        @depends_on('test_1login')
        def test_2upload(self): ...      # test_1login 失败/出错 -> 本条自动跳过
        @depends_on('test_2upload')
        def test_3submit(self): ...      # 依赖可链式传递

【设计原则】
    1. 失败连坐只发生在"已声明的依赖"上；没声明的用例照常独立执行。
    2. 依赖判定基于**方法名**（unittest 最稳定的标识），不依赖类名/模块名，
       方便复制到其它系统。
    3. 与执行器解耦：纯函数可单测，失败只影响跳过、不抛异常。
==========================================================================
"""

import unittest

from Common.log import log1

#: 方法上挂依赖声明的属性名
_DEP_ATTR = '_ui_depends_on'

#: 本次运行内的用例结果登记：{用例方法名: 'pass'|'fail'|'error'|'skip'}
#  每次全量执行开始时由 runner 调 reset() 清空，避免跨次残留。
_outcomes = {}


def reset():
    """清空本次运行的结果登记。runner 在执行前调用。"""
    _outcomes.clear()


def record(name, status):
    """登记一条用例的执行结果。

    :param name:   用例方法名（如 'test_1login'）
    :param status: 'pass' / 'fail' / 'error' / 'skip'
    """
    if name:
        _outcomes[name] = status


def outcome_of(name):
    """取某用例的已登记结果；未执行返回 None。"""
    return _outcomes.get(name)


def depends_on(*names):
    """方法装饰器：声明这条用例依赖的前置用例（按方法名）。

    用法：
        @depends_on('test_1login')
        def test_2upload(self): ...

        @depends_on('test_2upload', 'test_1login')   # 可声明多个
        def test_3submit(self): ...
    """
    def decorator(func):
        # 去重并保持声明顺序
        seen = []
        for n in names:
            if n and n not in seen:
                seen.append(n)
        setattr(func, _DEP_ATTR, seen)
        return func
    return decorator


def deps_of(case):
    """取一条用例声明的依赖方法名列表；无依赖返回 []。

    :param case: unittest.TestCase 实例
    """
    method_name = getattr(case, '_testMethodName', None)
    if not method_name:
        return []
    method = getattr(type(case), method_name, None)
    return list(getattr(method, _DEP_ATTR, []) or [])


def failed_dependencies(case):
    """返回「已失败/出错」的依赖方法名列表；全部正常则返回 []。

    判定：依赖的结果为 'fail' 或 'error' 才算阻断；'skip' 也视为阻断
    （被跳过的前置意味着它没成功）。'pass' 或未登记（尚未执行到）不阻断。
    """
    bad = []
    for dep in deps_of(case):
        status = outcome_of(dep)
        if status in ('fail', 'error', 'skip'):
            bad.append((dep, status))
    return bad


def guard(case, result):
    """执行前守卫：若有失败依赖，则把本用例记为 skip 并返回 True（不执行）。

    :return: True 表示已跳过（调用方不要再执行该用例）；False 表示可正常执行
    """
    bad = failed_dependencies(case)
    if bad:
        reason = '依赖前置用例未成功：' + ', '.join('%s(%s)' % d for d in bad)
        log1.info('用例 [%s] 被级联跳过：%s' % (getattr(case, '_testMethodName', case), reason))
        result.addSkip(case, reason)
        record(getattr(case, '_testMethodName', None), 'skip')
        return True
    return False


# ---------------------------------------------------------------------------
# 结果登记桥：把 unittest 的结果回调翻译成 outcome 登记，供 guard 判定。
# runner 用本类（或其子类）作为 resultclass，即可让级联跳过生效。
# ---------------------------------------------------------------------------
class DependencyRecorderMixin(object):
    """混入 unittest.TestResult：在 addSuccess/Error/Failure/Skip 时登记结果。

    用法：class MyResult(DependencyRecorderMixin, unittest.TextTestResult): ...
    提供给 runner 的自定义结果类继承它即可，无需改业务用例。
    """

    def _record_from(self, test, status):
        record(getattr(test, '_testMethodName', None), status)

    def addSuccess(self, test):
        self._record_from(test, 'pass')
        super(DependencyRecorderMixin, self).addSuccess(test)

    def addFailure(self, test, err):
        self._record_from(test, 'fail')
        super(DependencyRecorderMixin, self).addFailure(test, err)

    def addError(self, test, err):
        self._record_from(test, 'error')
        super(DependencyRecorderMixin, self).addError(test, err)

    def addSkip(self, test, reason):
        self._record_from(test, 'skip')
        super(DependencyRecorderMixin, self).addSkip(test, reason)


# ---------------------------------------------------------------------------
# 套件守卫：在每条叶子用例执行前做级联跳过判定。
# 实现方式：给真实 TestCase 实例**挂一个同名实例属性**，覆盖其测试方法。
# 包装方法在依赖失败时抛 unittest.SkipTest（被结果类记为 skip），否则调用原方法。
# 这样做的好处：
#   - 对象身份/类型不变 → setUpClass、tearDownClass、countTestCases、id 全部正常
#   - setUp / tearDown 仍会执行（只是测试本体被跳过）
#   - 实例属性只影响这一条用例，不污染类、不影响其它用例
# ---------------------------------------------------------------------------
def _install_guard(case):
    """给单条用例安装依赖守卫（通过覆盖测试方法实现）。

    :return: 同一个 case 实例
    """
    method_name = getattr(case, '_testMethodName', None)
    if not method_name:
        return case
    original = getattr(case, method_name)

    def guarded_method(*args, **kwargs):
        # 依赖失败 -> 抛 SkipTest，结果类会记为 skipped 且不影响其它用例
        bad = failed_dependencies(case)
        if bad:
            reason = '依赖前置用例未成功：' + ', '.join('%s(%s)' % d for d in bad)
            log1.info('用例 [%s] 被级联跳过：%s' % (method_name, reason))
            raise unittest.SkipTest(reason)
        return original(*args, **kwargs)

    # 实例属性覆盖类属性：TestCase.run 用 getattr(self, _testMethodName) 取方法，
    # 因此会优先拿到这个守卫包装。
    setattr(case, method_name, guarded_method)
    return case


def wrap_suite(suite):
    """给 suite 里每条叶子用例安装依赖守卫（保留原结构、顺序与对象身份）。

    :return: 新的 unittest.TestSuite，结构同原 suite
    """
    new_suite = unittest.TestSuite()
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            new_suite.addTest(wrap_suite(item))
        else:
            new_suite.addTest(_install_guard(item))
    return new_suite
