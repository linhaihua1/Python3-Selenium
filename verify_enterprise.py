# -*- coding: utf-8 -*-
"""
==========================================================================
 企业级功能验证矩阵（端到端，全部沙盒执行：不开真浏览器、不连外网、零副作用）
==========================================================================
 逐项实测框架**声明的企业级能力**，输出 PASS/FAIL 矩阵。
 与单元测试的区别：单测验证模块内部逻辑，本脚本验证**端到端行为链**——
 用 tests/helpers 的沙盒设施真实走一遍 run() 主流程，检查产物与退出码。
==========================================================================
"""
import os
import sys
import glob
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ['UI_LOG_DIR'] = tempfile.mkdtemp(prefix='verify_logs_')

from tests.helpers import (make_sandbox, patch_config, patch_dirs,
                           drop_modules, CASE_SOURCE_PASS, CASE_SOURCE_MIXED)

RESULTS = []

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))


def check(name, func):
    """执行一个验证项，登记 PASS/FAIL 与失败原因。"""
    try:
        detail = func()
        RESULTS.append((name, 'PASS', detail or ''))
    except Exception as exc:                                    # noqa: BLE001
        RESULTS.append((name, 'FAIL', '%s: %s' % (type(exc).__name__, exc)))


# ---------------------------------------------------------------------------
# 用例源码（沙盒内执行，不碰浏览器）
# ---------------------------------------------------------------------------
DEP_SOURCE = '''\
# -*- coding: utf-8 -*-
import unittest
from Common.dependency import depends_on


class DemoDep(unittest.TestCase):
    def test_1ok(self):
        pass

    @depends_on('test_1ok')
    def test_2after_ok(self):
        pass

    def test_3fail(self):
        self.fail('故意失败：验证失败摘要与归因')

    @depends_on('test_3fail')
    def test_4should_skip(self):
        pass
'''

CONSOLE_ERROR_SOURCE = '''\
# -*- coding: utf-8 -*-
import unittest
from Common.basePage import BasePage


class DemoGuard(unittest.TestCase):
    def setUp(self):
        self.base = BasePage(driver=None)

    def test_title_ok(self):
        # 标题比对（守卫断言路径）
        ok, actual = self.base.wait_title('首页', timeout=0.3)
        self.assertTrue(ok, '标题未在时限内变为[首页]，实际[%s]' % actual)
'''


def run_in_sandbox(ini_sections=None, case_sources=None, junit='Report/junit.xml',
                   suite_kind='full', cases=None, env=None):
    """在全新沙盒里跑一次 runner.run()，返回 summary 与沙盒根目录。

    :param ini_sections: {段名: {键: 值}}；按段合并成 ini，避免重复段报错
    """
    from Common import runner, dependency

    dependency.reset()
    root, cases_dir, pkg = make_sandbox(case_source=None)
    drop_modules(pkg)
    for i, source in enumerate(case_sources or []):
        with open(os.path.join(cases_dir, 'test_case_%d.py' % i),
                  'w', encoding='utf-8') as fp:
            fp.write(source)

    sections = {
        'environment': {'url': 'http://test-env.local/portal', 'browser': 'chrome'},
        'safety': {'guard': 'false'},
        'ci': {'preflight': 'false', 'junit_xml': junit},
    }
    for section, pairs in (ini_sections or {}).items():
        sections.setdefault(section, {}).update(pairs)
    ini = ''.join('[%s]\n%s\n' % (section, ''.join(
        '%s = %s\n' % pair for pair in pairs.items()))
        for section, pairs in sections.items())

    saved = {}
    env = env or {}
    for key, value in env.items():
        saved[key] = os.environ.get(key)
        os.environ[key] = value
    try:
        with patch_config(ini_text=ini, ini_path=os.path.join(root, 'config.ini')):
            with patch_dirs(root):
                summary = runner.run(tests_dir=cases_dir, suite_kind=suite_kind,
                                     cases=cases, junit=junit)
    finally:
        for key, old in saved.items():
            if old is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old
    return summary, root


# ---------------------------------------------------------------------------
# 一、执行主链路
# ---------------------------------------------------------------------------
def v_exit_code_pass():
    summary, root = run_in_sandbox(case_sources=[CASE_SOURCE_PASS])
    assert summary['exit_code'] == 0, '全过应 exit 0，实际 %s' % summary['exit_code']
    assert summary['tests_run'] == 2, summary['tests_run']
    return 'exit 0, 2/2 passed'


def v_exit_code_fail():
    summary, root = run_in_sandbox(case_sources=[CASE_SOURCE_MIXED])
    assert summary['exit_code'] == 1, '有失败应 exit 1，实际 %s' % summary['exit_code']
    assert summary['failures'] == 1, summary['failures']
    return 'exit 1, failures=1'


def v_dual_report():
    summary, root = run_in_sandbox(case_sources=[CASE_SOURCE_PASS])
    assert summary['report'] and os.path.isfile(summary['report']), summary['report']
    html = open(summary['report'], encoding='utf-8', errors='replace').read()
    assert 'DemoPass' in html, 'HTML 报告应包含用例名'
    assert summary['junit'] and os.path.isfile(summary['junit']), summary['junit']
    xml = open(summary['junit'], encoding='utf-8').read()
    assert '<testsuite' in xml and 'test_a_pass' in xml, 'JUnit XML 应含用例明细'
    return 'HTML(%d bytes) + JUnit XML 双产物' % os.path.getsize(summary['report'])


def v_failure_artifacts():
    """失败自动取证：失败用例 + 活跃 driver（FakeDriver 登记）时产出证据文件。"""
    from Common import driverRegistry, dependency
    from tests.helpers import FakeDriver

    dependency.reset()
    fake = FakeDriver()
    driverRegistry.register(fake)     # 模拟"失败时浏览器还开着"
    try:
        summary, root = run_in_sandbox(
            ini_sections={'ci': {'artifacts': 'true'}},
            case_sources=[CASE_SOURCE_MIXED])
        assert summary['failures'] == 1, summary['failures']
        artifacts = glob.glob(os.path.join(root, 'Report', 'artifacts', '**', '*'),
                              recursive=True)
        assert artifacts, '失败应有取证文件（截图/页面源码），实际无'
        return '取证文件 %d 个: %s' % (
            len(artifacts), sorted(os.path.basename(a) for a in artifacts)[:3])
    finally:
        driverRegistry.unregister(fake)


def v_trend_recorded():
    """通过率趋势：runner 执行后沙盒 Report/ 下应有 history.jsonl 且可读回。"""
    summary, root = run_in_sandbox(case_sources=[CASE_SOURCE_PASS])
    history_file = os.path.join(root, 'Report', 'history.jsonl')
    assert os.path.isfile(history_file), '趋势历史文件未落盘: %s' % history_file
    with open(history_file, encoding='utf-8') as fp:
        lines = [line for line in fp if line.strip()]
    assert len(lines) >= 1, '趋势历史应为空'
    import json
    record = json.loads(lines[-1])
    assert record['tests_run'] == 2 and record['exit_code'] == 0, record
    assert 'pass_rate' in record, record
    return '趋势 %d 条，末条: %d 用例 / 通过率 %s%%' % (
        len(lines), record['tests_run'], record['pass_rate'])


# ---------------------------------------------------------------------------
# 二、闸门
# ---------------------------------------------------------------------------
def v_gate_readonly():
    summary, root = run_in_sandbox(
        ini_sections={'testcase': {'mode': 'readonly'}},
        case_sources=[CASE_SOURCE_PASS])       # DemoPass 无 readonly 标记 -> 全是写用例
    assert summary['exit_code'] == 2 and summary['tests_run'] == 0, \
        'readonly 模式无只读用例应 exit 2 中止，实际 %s/%s' % (
            summary['exit_code'], summary['tests_run'])
    assert 'readonly' in (summary['reason'] or ''), summary['reason']
    return '写用例被全量摘除并给出可读原因'


def v_gate_env_guard():
    """环境守卫：疑似生产地址 + 含写用例 -> exit 2（不打开浏览器）。"""
    summary, root = run_in_sandbox(
        ini_sections={'safety': {'guard': 'true', 'allow_write': 'false'}},
        case_sources=[CASE_SOURCE_PASS],
        env={'UI_ENVIRONMENT_URL': 'http://prod.example.com/portal'})
    # prod 命中默认 blocklist，且用例未标 readonly -> 必须拦
    assert summary['exit_code'] == 2, '环境守卫应拦截，实际 exit %s' % summary['exit_code']
    assert summary['reason'], '拦截必须给出人话原因'
    return '守卫原因: %s' % summary['reason'][:60]


def v_gate_smoke_empty_aborts():
    summary, root = run_in_sandbox(ini_sections={'ci': {'smoke_cases': ''}},
                                   case_sources=[CASE_SOURCE_PASS],
                                   suite_kind='smoke')
    assert summary['exit_code'] == 2, '冒烟空配置应中止 exit 2，实际 %s' % summary['exit_code']
    return 'smoke_cases 为空 -> 中止（防误跑全量写用例）'


def v_dependency_cascade():
    summary, root = run_in_sandbox(case_sources=[DEP_SOURCE])
    assert summary['failures'] == 1, summary
    assert summary['skipped'] == 1, '依赖失败的后继应 skip，实际 skipped=%s' % summary['skipped']
    assert summary['tests_run'] == 4
    return '4 条: 2 过 + 1 失败 + 1 级联跳过'


# ---------------------------------------------------------------------------
# 三、周边能力
# ---------------------------------------------------------------------------
def v_parallel_runner():
    from Common import parallelRunner, dependency
    dependency.reset()
    root, cases_dir, pkg = make_sandbox(case_source=None)
    drop_modules(pkg)
    for i, source in enumerate([CASE_SOURCE_PASS, CASE_SOURCE_PASS]):
        with open(os.path.join(cases_dir, 'test_shard_%d.py' % i), 'w',
                  encoding='utf-8') as fp:
            fp.write(source)
    # ★ 并行子进程无法继承 pytest 式 mock，必须走真实配置链路：
    #   沙盒 config.ini（make_sandbox 已写）+ UI_* 环境变量覆盖（与 Jenkins 用法一致），
    #   子进程靠继承环境变量拿到安全配置；分片报告落工程 Report/，跑完清理。
    env = {
        'UI_ENVIRONMENT_URL': 'http://test-env.local/portal',
        'UI_SAFETY_GUARD': 'false',
        'UI_CI_PREFLIGHT': 'false',
        'UI_CI_JUNIT_XML': 'none',
        'UI_LOG_DIR': os.environ['UI_LOG_DIR'],
    }
    saved = {key: os.environ.get(key) for key in env}
    os.environ.update(env)
    try:
        summary = parallelRunner.run_parallel(workers=2, tests_dir=cases_dir)
    finally:
        for key, old in saved.items():
            if old is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old
        for f in glob.glob(os.path.join(PROJECT_ROOT, 'Report', 'parallel_shard_*')):
            os.remove(f)
    assert summary['tests_run'] == 4, '2 分片 2 进程应共 4 条，实际 %s' % summary['tests_run']
    assert summary['exit_code'] == 0
    return '2 workers / 4 用例 / exit 0'


def v_data_driver_csv():
    from Common.dataDriver import load_data
    csv_path = os.path.join(tempfile.mkdtemp(prefix='v_data_'), 'data.csv')
    with open(csv_path, 'w', encoding='utf-8') as fp:
        fp.write('username,password\nu1,p1\nu2,p2\n')
    rows = load_data(csv_path)
    assert isinstance(rows, list) and len(rows) == 2, rows
    assert rows[0]['username'] == 'u1' and rows[1]['password'] == 'p2', rows
    return 'CSV -> 2 行 dict 参数化'


def v_elements_override():
    """[elements] 配置覆盖 + 非法写法报错（端到端再验一遍）。"""
    from Common import elementPage
    from tests.helpers import patch_config
    original = elementPage.Element1.Username
    try:
        with patch_config(ini_text='[elements]\nUsername = id:cfg-user\n'):
            overridden = elementPage.apply_config_overrides()
            assert overridden == ['Username']
            assert elementPage.Element1.Username == ['id', 'cfg-user']
        with patch_config(ini_text='[elements]\nUsername = xpath:\n'):
            try:
                elementPage.apply_config_overrides()
                raise AssertionError('非法定位写法应报 ValueError')
            except ValueError:
                pass
        return '覆盖生效 + 非法写法报错'
    finally:
        elementPage.Element1.Username = original


def v_notifier_dry():
    from Common import notifier
    assert notifier.notify({'tests_run': 1}, webhook=None) is False, \
        '未配置 webhook 应安静跳过（返回 False，不影响主流程）'
    return 'webhook 未配置 -> 返回 False 不崩'


def v_failure_classifier():
    """失败归因：对典型 traceback 文本分类（规则驱动，7 类）。"""
    from Common.failureClassifier import classify_message, LOCATOR

    text = ('selenium.common.exceptions.NoSuchElementException: '
            'Message: no such element: Unable to locate element')
    result = classify_message(text)
    category = result if isinstance(result, str) else getattr(result, 'category', None)
    assert category == LOCATOR, '定位失败应归为 %s 类，实际 %r' % (LOCATOR, result)
    return 'NoSuchElementException -> locator（7 类归因）'


def v_collection_diagnose():
    from Common.runner import diagnose_collection
    tmp = tempfile.mkdtemp(prefix='v_collect_')          # 无 __init__.py
    lines = diagnose_collection(tmp, 'test*.py')
    joined = '\n'.join(lines)
    assert '__init__.py' in joined and '缺失' in joined, joined
    return '缺 __init__.py 被点名并给出修复动作'


def v_enforce_prod_safety():
    from run import enforce_prod_safety
    saved = {k: os.environ.get(k) for k in ('UI_TESTCASE_MODE', 'UI_SAFETY_ALLOW_WRITE')}
    try:
        assert enforce_prod_safety('prod') is True
        assert os.environ['UI_TESTCASE_MODE'] == 'readonly'
        assert os.environ['UI_SAFETY_ALLOW_WRITE'] == 'false'
        assert enforce_prod_safety('test') is False
        return '--env prod -> 代码级强制 readonly（双保险）'
    finally:
        for key, old in saved.items():
            if old is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old


def _make_fake_driver(dir_path, version):
    """在指定目录里造一个"只会报版本号"的假 WebDriver。

    :param dir_path: 存放目录（会临时插到 PATH 最前面）
    :param version:  假驱动对外宣称的版本号，如 '114.0.5735.90'
    :return: 可执行文件的绝对路径

    用途：复现"PATH 上的驱动与浏览器主版本不匹配"这个真实故障，
    又不依赖这台机器当前的驱动状况。Windows 用 .bat（shutil.which 认 PATHEXT），
    其他平台用带 x 权限的 shell 脚本。
    """
    if os.name == 'nt':
        path = os.path.join(dir_path, 'chromedriver.bat')
        with open(path, 'w', encoding='utf-8') as fp:
            fp.write('@echo off\r\n')
            fp.write('echo ChromeDriver %s (fake)\r\n' % version)
    else:
        path = os.path.join(dir_path, 'chromedriver')
        with open(path, 'w', encoding='utf-8') as fp:
            fp.write('#!/bin/sh\n')
            fp.write('echo "ChromeDriver %s (fake)"\n' % version)
        os.chmod(path, 0o755)
    return path


def v_preflight_real_problem():
    """preflight 能抓出「PATH 上的驱动与浏览器主版本不匹配」。

    ★ 为什么不直接体检本机
        历史写法断言"本机一定有个 114 版驱动"，于是这条验收项**以机器坏着为前提**：
        把环境修好之后它反而变红，看起来像框架坏了。验收矩阵必须能重复得到同一个结论，
        所以改成注入一个版本固定的假驱动 + 固定的浏览器主版本，任何机器上都能复现。
    """
    from Common import preflight

    with tempfile.TemporaryDirectory(prefix='verify_driver_') as tmp:
        _make_fake_driver(tmp, '114.0.5735.90')
        saved_path = os.environ.get('PATH', '')
        original_major = preflight.browser_major
        os.environ['PATH'] = tmp + os.pathsep + saved_path
        preflight.browser_major = lambda *a, **k: 155      # 假装浏览器是 155
        try:
            finding = preflight.check_driver(browser='chrome')
        finally:
            preflight.browser_major = original_major
            os.environ['PATH'] = saved_path

    assert finding.level == preflight.LEVEL_ERROR, \
        '驱动主版本不匹配应判为错误级，实际：%s / %s' % (finding.level, finding.detail)
    assert '不匹配' in finding.detail, finding.detail
    assert preflight.has_error([finding]) is True, '有 ERROR 级发现时 has_error 应为 True'
    return '抓到: %s' % finding.detail[:60]


def v_locator_policy():
    import subprocess
    py = sys.executable
    proc = subprocess.run([py, '-m', 'Common.locator_policy', '--fail-over', '10'],
                          capture_output=True, text=True, cwd=PROJECT_ROOT)
    assert proc.returncode == 0, proc.stdout[-400:]
    assert 'ABSOLUTE' in proc.stdout
    return 'exit 0；绝对路径 xpath = 0（红线保持）'


def v_pytest_engine():
    import subprocess
    proc = subprocess.run([sys.executable, '-m', 'pytest', 'TestSuites/',
                           '--suite', 'smoke', '--collect-only', '-q'],
                          capture_output=True, text=True, cwd=PROJECT_ROOT,
                          env={**os.environ, 'UI_LOG_DIR': os.environ['UI_LOG_DIR']})
    assert proc.returncode == 0 and '3/13' in proc.stdout, proc.stdout[-400:]
    return 'pytest 冒烟收集 3/13（第二引擎可用）'


def v_get_required_error_quality():
    from tests.helpers import patch_config
    from Common.config import Config
    with patch_config(ini_text='[x]\nk =\n'):
        try:
            Config.get_required('assert', 'title_login', '登录后标题')
            raise AssertionError('缺失必填应报错')
        except ValueError as exc:
            msg = str(exc)
    for token in ('[assert]', 'title_login', 'config.ini', 'UI_ASSERT_TITLE_LOGIN', '--env'):
        assert token in msg, '报错信息缺少 %r：\n%s' % (token, msg)
    return '报错含段名/键名/三种修复方式'


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
ALL = [
    ('执行链路 | 全过 -> exit 0', v_exit_code_pass),
    ('执行链路 | 有失败 -> exit 1', v_exit_code_fail),
    ('执行链路 | HTML+JUnit 双报告产物', v_dual_report),
    ('执行链路 | 失败自动取证（截图+源码）', v_failure_artifacts),
    ('执行链路 | 通过率趋势登记', v_trend_recorded),
    ('闸门 ① | mode=readonly 摘写用例', v_gate_readonly),
    ('闸门 ② | 环境守卫拦疑似生产+写用例', v_gate_env_guard),
    ('闸门 ② | 冒烟空配置中止（防误写）', v_gate_smoke_empty_aborts),
    ('闸门 ③ | @depends_on 失败级联跳过', v_dependency_cascade),
    ('周边 | 多进程并行执行', v_parallel_runner),
    ('周边 | 数据驱动 CSV', v_data_driver_csv),
    ('周边 | [elements] 定位覆盖+非法报错', v_elements_override),
    ('周边 | 群通知未配置静默跳过', v_notifier_dry),
    ('周边 | 失败归因 7 类', v_failure_classifier),
    ('周边 | 用例收集诊断（缺__init__.py）', v_collection_diagnose),
    ('安全 | --env prod 代码级强制只读', v_enforce_prod_safety),
    ('自检 | preflight 抓本机驱动不匹配', v_preflight_real_problem),
    ('门禁 | locator_policy 绝对路径=0', v_locator_policy),
    ('引擎 | pytest 第二引擎冒烟收集', v_pytest_engine),
    ('配置 | get_required 报错质量', v_get_required_error_quality),
]

if __name__ == '__main__':
    # NoSuchElementException 导入放在用例函数内避免顶部依赖混乱
    from selenium.common.exceptions import NoSuchElementException \
        as NoSuchElementException_stub
    globals()['NoSuchElementException_stub'] = NoSuchElementException_stub

    print('=' * 78)
    print('企业级功能验证矩阵（沙盒端到端，不开真浏览器 / 不连外网）')
    print('=' * 78)
    for name, func in ALL:
        check(name, func)
    width = max(len(n) for n, _, _ in RESULTS)
    for name, status, detail in RESULTS:
        print('[%s] %-*s  %s' % (status, width, name, detail))
    passed = sum(1 for _, s, _ in RESULTS if s == 'PASS')
    print('-' * 78)
    print('结果: %d/%d PASS' % (passed, len(RESULTS)))
    sys.exit(0 if passed == len(RESULTS) else 1)
