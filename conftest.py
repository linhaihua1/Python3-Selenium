# -*- coding: utf-8 -*-
"""
==========================================================================
 pytest 适配层（conftest.py）—— 让 pytest 成为工程的第二执行引擎
==========================================================================

【为什么需要这个文件】
    本工程原生的执行引擎是 unittest（run.py -> Common/runner.py -> HTMLTestRunner）。
    pytest 对 unittest.TestCase 用例**原生兼容**，但直接 `pytest TestSuites/` 会遇到
    两个问题（均在本文件解决，实测通过）：

        1. 收集不到用例：用例文件名是 testLogin.py（无下划线），
           不匹配 pytest 默认的 `test_*.py` 规则 —— 规则已在 pyproject.toml 放宽为 test*.py
        2. 收集报错：tests/test_runner.py 引用的 unittest 私有占位类
           `unittest.loader._FailedTest` 会被 pytest 当测试类实例化 —— 本文件跳过所有
           下划线开头的类（私有类本就不该被收集）

【本文件做了什么（对齐工程既有语义）】
    1. collect：跳过下划线开头的 TestCase 子类（修复 _FailedTest 实例化报错）
    2. 闸门①写入范围：[testcase] mode = readonly 时摘掉写用例（对齐 runner.py）
    3. --suite smoke：按 [ci] smoke_cases 关键字过滤（对齐 run.py --suite smoke）
    4. 依赖级联跳过：@depends_on 的失败结果登记 + 前置失败后继 skip
       （对齐 Common/dependency 的 wrap_suite，pytest 下改用钩子实现）

【pytest 与 run.py 的报告取舍（重要）】
    run.py 一次产出中文 HTML + JUnit XML 双报告，且带失败归因/趋势/失败取证；
    pytest 路径下：
        JUnit XML  ->  pytest 自带 --junitxml（Jenkins 直接用，格式更标准）
        HTML 报告  ->  pytest-html（--html），样式与 HTMLTestReportCN 不同
        失败归因/趋势/失败自动取证 -> pytest 路径暂不生效（挂在 unittest 结果对象上）
    所以两条路径的关系是互补而非替换：
        本机开发/快速过滤/单条重跑  ->  pytest（快、-k 过滤灵活、失败即停可调）
        CI 完整报告链路             ->  run.py（双报告 + 归因 + 趋势 + preflight 自检）

【怎么用】
    pytest tests/                                    # 框架单测（不开浏览器）
    pytest TestSuites/ --collect-only -q             # 只看收集结果（不执行）
    pytest TestSuites/ --suite smoke --collect-only  # 冒烟集（对齐 run.py --suite smoke）
    pytest TestSuites/ -k test_1login                # 单条重跑（pytest 的强项）
    pytest TestSuites/ --junitxml Report/junit-pytest.xml --html Report/pytest.html --self-contained-html
==========================================================================
"""

import os

import pytest


# ---------------------------------------------------------------------------
# 收集规则
# ---------------------------------------------------------------------------

def pytest_pycollect_makeitem(collector, name, obj):
    """两条收集排除规则（都是在适配 pytest 与 unittest 的行为差异）。"""
    # 规则 1：跳过下划线开头的类。
    #   tests/test_runner.py 引用了 unittest 私有占位类 _FailedTest，
    #   pytest 实例化它时因缺 exception 参数而 TypeError，整个收集中断。
    #   下划线开头 = 模块私有，本就不该被当测试收集。
    if name.startswith('_'):
        return []

    # 规则 2：tests/ 单测文件里 import 进来的 TestSuites 真实用例类，不收集。
    #   背景：单测需要 import 真实的 TestMaterialCheck / TestLogin 做结构校验
    #   （源码扫描、setUpClass 行为验证），unittest 靠模块级 load_tests()
    #   白名单把它们排除；**pytest 不支持 load_tests 钩子**，会照常收集 ——
    #   于是 setUpClass 真开浏览器连被测环境（实测 SessionNotCreated）。
    #   这里按「文件在 tests/ 下 && 类定义自 TestSuites 包」补上同语义排除：
    #   定义处永远是 TestSuites/*.py，被 import 的引用处才在 tests/ 下。
    try:
        collector_dir = os.path.basename(os.path.dirname(str(collector.fspath)))
        module = getattr(obj, '__module__', '') or ''
        if collector_dir == 'tests' and module.startswith('TestSuites'):
            return []
    except (AttributeError, TypeError, OSError):
        pass
    return None


# ---------------------------------------------------------------------------
# 命令行参数：--suite（对齐 run.py --suite smoke / full）
# ---------------------------------------------------------------------------
def pytest_addoption(parser):
    group = parser.getgroup('ui-automation', '本工程 UI 自动化扩展参数')
    group.addoption(
        '--suite', default='full', choices=('full', 'smoke'),
        help='full=全部用例；smoke=只跑 config.ini [ci] smoke_cases 的冒烟集')


def _ui_case_of(item):
    """从 pytest item 里取出 unittest.TestCase 实例；非 unittest 用例返回 None。

    为什么需要转换：Common/testcase_meta.scope_of 认的是 TestCase 实例/类
    （用 _testMethodName 找方法级标记），pytest 的 item 不直接满足这个约定。
    """
    instance = getattr(item, 'instance', None)   # pytest 的 unittest 项有 .instance
    method_name = getattr(instance, '_testMethodName', None)
    if instance is None or not method_name:
        return None
    return instance


def pytest_collection_modifyitems(session, config, items):
    """收集后过滤：写入范围闸门 + 冒烟集过滤（对齐 Common/runner.py 的闸门①）。

    顺序与 runner.run 保持一致：先按 mode 过滤，再做冒烟关键字过滤。
    """
    # 延迟导入：纯单测场景（pytest tests/）也要能工作，不强制依赖被测配置
    from Common.config import Config
    from Common.testcase_meta import is_readonly

    # ---- 闸门①：mode = readonly 时摘掉写用例 ----
    mode = (Config.get('testcase', 'mode', 'all') or 'all').strip().lower()
    if mode == 'readonly':
        kept, dropped = [], []
        for item in items:
            case = _ui_case_of(item)
            # 非 unittest 用例（框架自身单测函数）不受 UI 写入闸门约束，保留
            if case is None or is_readonly(case):
                kept.append(item)
            else:
                dropped.append(item)
        if dropped:
            config.hook.pytest_deselected(items=dropped)
            items[:] = kept

    # ---- 冒烟集：按 [ci] smoke_cases 关键字过滤（大小写不敏感、部分匹配）----
    if config.getoption('--suite') == 'smoke':
        keywords = Config.get_list('ci', 'smoke_cases', fallback=[])
        if not keywords:
            # 安全兜底与 runner.run 一致：冒烟模式没配用例 -> 中止而不是跑全量，
            # 避免"误删 smoke_cases 配置后在 CI 上真跑写用例"
            raise SystemExit(
                '冒烟模式未配置任何用例（config.ini -> [ci] smoke_cases 为空）。'
                '为避免误跑全量用例产生真实数据，已中止')
        lowered = [k.lower() for k in keywords]
        kept, dropped = [], []
        for item in items:
            text = '%s %s' % (item.name, item.nodeid)
            if any(k in text.lower() for k in lowered):
                kept.append(item)
            else:
                dropped.append(item)
        config.hook.pytest_deselected(items=dropped)
        items[:] = kept


# ---------------------------------------------------------------------------
# 依赖级联跳过：@depends_on 的 pytest 版（对齐 Common/dependency.wrap_suite）
#   unittest 版是在每条用例上包装守卫方法；pytest 改用两个钩子实现同等语义：
#     setup 阶段    -> 查依赖，前置失败则 pytest.skip（记为 skip，不连坐报错）
#     makereport    -> 把结果登记进 dependency 的结果表（供后续用例判定）
# ---------------------------------------------------------------------------
def pytest_runtest_setup(item):
    """执行前守卫：声明的依赖里有失败/出错/跳过的，本条直接 skip。"""
    from Common import dependency

    function = getattr(item, 'function', None)
    deps = list(getattr(function, '_ui_depends_on', []) or [])
    bad = [(name, dependency.outcome_of(name)) for name in deps
           if dependency.outcome_of(name) in ('fail', 'error', 'skip')]
    if bad:
        reason = '依赖前置用例未成功：' + ', '.join('%s(%s)' % pair for pair in bad)
        pytest.skip(reason)


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """把执行结果登记进 Common.dependency 的结果表（按用例方法名）。"""
    outcome = yield
    report = outcome.get_result()

    from Common import dependency

    # 取"裸方法名"：unittest 项的 function 是绑定方法，__name__ 即用例方法名
    name = getattr(getattr(item, 'function', None), '__name__', None)

    if report.when == 'setup' and report.failed:
        dependency.record(name, 'error')          # setUpClass/setUp 挂了
    elif report.when == 'setup' and report.skipped:
        dependency.record(name, 'skip')
    elif report.when == 'call':
        if report.passed:
            dependency.record(name, 'pass')
        elif hasattr(report, 'wasxfail'):
            dependency.record(name, 'pass')       # xfail 且意外通过按通过算
        else:
            dependency.record(name, 'fail')
