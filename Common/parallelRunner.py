# -*- coding: utf-8 -*-
"""
==========================================================================
 并行执行器（企业级规模化的关键能力）
==========================================================================

【一句话说明】
    把用例文件拆成多份，分给多个进程**同时**跑，最后把结果合并成一份报告。
    用例从 9 条涨到几百条时，串行要几小时，并行能压到分钟级。

【为什么是"文件级"并行而不是"用例级"】
    本工程的用例是一条**串行业务流**（同一文件内 test_1…test_6 共用一个浏览器、
    有前置依赖）。文件内部不能拆，但**文件与文件之间是独立的**——不同测试文件
    各自开浏览器、互不影响。所以并行的最小单位是「测试文件」，既拿到了并行收益，
    又不破坏文件内的串行依赖。

【在框架中的位置】
    run.py --workers N
        └─> Common/parallelRunner.py   <- 本文件：分片 + 多进程调度 + 结果合并
              └─> Common/runner.py      每个进程仍调 runner.run 跑自己那一片

【为什么用多进程而不是多线程】
    Selenium 的 WebDriver 不是线程安全的；且每个进程有独立的浏览器和 Python
    解释器，互不污染（失败取证、driver 登记都天然隔离）。代价是进程启动开销，
    对"每条用例几秒、整体几分钟"的 UI 测试完全划算。

【合并策略】
    每个子进程返回自己的 summary 字典（含 cases 明细），主进程把它们的
    tests_run / failures / errors / skipped 相加，cases 列表拼接，
    再统一生成一份 JUnit XML 给 Jenkins。耗时取「最慢那个进程」的墙钟时间。
==========================================================================
"""

import multiprocessing
import os
from typing import Any, Dict, List

from Common import runner
from Common.config import Config
from Common.dir_config import testcases_dir
from Common.log import log1


# ---------------------------------------------------------------------------
# 一、纯函数：分片与聚合（无副作用，方便单测）
# ---------------------------------------------------------------------------
def shard(items, n):
    """把列表尽量均匀地分成 n 份。

    :param items: 待分片的列表（如测试文件路径）
    :param n:     分片数（<=0 或 >len 时会被规范到合理范围）
    :return: 列表的列表，长度 = min(n, len(items))；空列表返回 []

    采用"轮询发牌"而非"切块"：[a,b,c,d,e] 分 2 片 -> [[a,c,e],[b,d]]。
    好处是文件大小不均时，负载更均衡（大文件不会全挤在第一片）。
    """
    if not items:
        return []
    n = max(1, min(n, len(items)))
    buckets: List[List[Any]] = [[] for _ in range(n)]
    for i, item in enumerate(items):
        buckets[i % n].append(item)
    return buckets


def aggregate(summaries):
    """把多个子进程的 summary 字典合并成一份。

    :param summaries: summary 字典列表（每个都是 runner.run / _summary 的结构）
    :return: 合并后的 summary 字典

    规则：
      - tests_run / failures / errors / skipped ：相加
      - cases ：拼接（供统一生成 JUnit XML）
      - duration ：取最大值（墙钟时间 = 最慢进程），无则求和
      - exit_code ：取最大值（任一进程失败/异常，整体就非 0）
      - reason ：首个非空的（被守卫拦下时的说明）
      - report / junit ：保留主进程生成的（子进程各写各的，不合并 HTML）
    """
    merged = runner._summary()
    if not summaries:
        return merged
    durations = [s.get('duration', 0.0) for s in summaries]
    cases = []
    reasons = []
    for s in summaries:
        merged['tests_run'] += s.get('tests_run', 0)
        merged['failures'] += s.get('failures', 0)
        merged['errors'] += s.get('errors', 0)
        merged['skipped'] += s.get('skipped', 0)
        merged['exit_code'] = max(merged['exit_code'], s.get('exit_code', 0))
        for case in (s.get('cases') or []):
            # runner.run 返回时会剥离 stdout 字段（避免 summary 过大），
            # 但 write_junit_xml 需要它；这里补默认值，保证合并 XML 正常生成。
            case.setdefault('stdout', '')
            case.setdefault('artifacts', {})
            cases.append(case)
        if s.get('reason'):
            reasons.append(s['reason'])
    merged['cases'] = cases
    merged['duration'] = round(max(durations), 3) if durations else 0.0
    merged['reason'] = reasons[0] if reasons else None
    merged['success'] = merged['exit_code'] == runner.EXIT_OK
    return merged


# ---------------------------------------------------------------------------
# 二、收集可并行的用例文件
# ---------------------------------------------------------------------------
def list_test_files(tests_dir=None, pattern='test*.py'):
    """列出用例目录下匹配 pattern 的测试文件（绝对路径），用于分片。

    :return: 排序后的绝对路径列表
    """
    import fnmatch
    tests_dir = tests_dir or testcases_dir
    files: List[str] = []
    if not os.path.isdir(tests_dir):
        return files
    for name in sorted(os.listdir(tests_dir)):
        if name.endswith('.py') and fnmatch.fnmatch(name, pattern):
            files.append(os.path.join(tests_dir, name))
    return files


# ---------------------------------------------------------------------------
# 三、子进程入口：跑一个分片。必须是模块级函数，才能被 multiprocessing pickle。
# ---------------------------------------------------------------------------
def _run_shard(modules, run_kwargs):
    """子进程执行体：只跑给定的一组用例文件，返回 summary。

    关键：子进程里**不写 JUnit XML、不发邮件、不推群通知**——
    这些由主进程在聚合后统一做一次，避免多进程争抢同一个输出文件。
    """
    # 子进程独立写自己的 HTML 报告（文件名带分片序号，避免互相覆盖）
    shard_index = run_kwargs.pop('__shard_index', 0)
    title = run_kwargs.get('title') or Config.get('report', 'title', runner.DEFAULT_TITLE)
    report_name = 'parallel_shard_%d.html' % shard_index

    summary = runner.run(
        tests_dir=run_kwargs.get('tests_dir'),
        pattern=run_kwargs.get('pattern', 'test*.py'),
        title=title,
        report_name=report_name,
        tester=run_kwargs.get('tester'),
        description=run_kwargs.get('description'),
        send_mail=False,
        suite_kind=run_kwargs.get('suite_kind', 'full'),
        cases=run_kwargs.get('cases'),
        junit='none',          # ★ 子进程不写 JUnit，主进程统一写
        modules=modules,       # ★ 只加载本分片的文件
    )
    return summary


# ---------------------------------------------------------------------------
# 四、主入口：调度并行执行
# ---------------------------------------------------------------------------
def run_parallel(workers=2, tests_dir=None, pattern='test*.py', **run_kwargs):
    """并行执行测试并返回合并后的 summary。

    :param workers: 并行进程数；实际分片数 = min(workers, 文件数)
    :return: 合并后的 summary 字典（结构同 runner.run 的返回值）

    流程：
      1. 列出测试文件 -> 分成 workers 片
      2. 起进程池，每片丢给一个子进程跑
      3. 收集各片 summary -> 聚合
      4. 主进程统一生成一份 JUnit XML（含全部分片的用例明细）
    """
    files = list_test_files(tests_dir, pattern)
    if not files:
        log1.error('并行执行：未找到任何匹配 %s 的用例文件' % pattern)
        return runner._summary(exit_code=runner.EXIT_ENV_ERROR,
                               reason='未收集到可并行的用例文件')

    shards = shard(files, workers)
    actual = len(shards)
    log1.info('并行执行：%d 个用例文件拆成 %d 片，每片约 %d 个文件'
              % (len(files), actual, -(-len(files) // actual)))

    summaries = []
    if actual == 1:
        # 只有一片时没必要起进程池，直接本进程跑（少一层开销，也便于调试）
        summaries.append(_run_shard(shards[0], dict(run_kwargs, __shard_index=0)))
    else:
        # spawn 方式：每个子进程是干净的 Python 解释器，浏览器互不干扰
        ctx = multiprocessing.get_context('spawn')
        with ctx.Pool(processes=actual) as pool:
            jobs = [
                pool.apply_async(_run_shard, (shards[i], dict(run_kwargs, __shard_index=i)))
                for i in range(actual)
            ]
            for job in jobs:
                try:
                    summaries.append(job.get())
                except BaseException:
                    # 某个子进程崩了：记一条环境异常，不让整次执行崩在主进程
                    log1.error('并行子进程执行异常', exc_info=1)
                    summaries.append(runner._summary(
                        exit_code=runner.EXIT_ENV_ERROR,
                        reason='并行子进程执行异常'))

    merged = aggregate(summaries)

    # 主进程统一写 JUnit XML（全部分片的明细合并到一份，Jenkins 看到的是完整结果）
    junit_path = runner.resolve_junit_path(run_kwargs.get('junit'))
    if junit_path:
        _write_merged_junit(merged, junit_path, run_kwargs.get('title'))
        merged['junit'] = junit_path

    log1.info('并行执行完成：%d 片，用例 %d，失败 %d，错误 %d，退出码 %d'
              % (actual, merged['tests_run'], merged['failures'],
                 merged['errors'], merged['exit_code']))
    return merged


def _write_merged_junit(merged, path, title):
    """把合并后的 cases 写成一份 JUnit XML。

    JUnitResult.write_junit_xml 需要 result 对象的 cases/testsRun 等字段，
    这里用一个轻量包装对象喂给它，避免为并行再维护一套 XML 生成逻辑。
    """
    from Common.junitReport import write_junit_xml

    class _MergedResult(object):
        # 只声明字段，不赋默认值：写 JUnit 的代码按属性取用，
        # 声明后类型检查能看懂，运行时也不会因此在类上留下共享的可变对象。
        cases: List[Dict[str, Any]]
        testsRun: int
        failures: List[Any]
        errors: List[Any]
        skipped: List[Any]

    cases = merged.get('cases', [])
    res = _MergedResult()
    res.cases = cases
    res.testsRun = merged.get('tests_run', 0)
    res.failures = [c for c in cases if c.get('status') == 'failure']
    res.errors = [c for c in cases if c.get('status') == 'error']
    res.skipped = [c for c in cases if c.get('status') == 'skipped']
    try:
        write_junit_xml(res, path, suite_name=title or 'UI 自动化测试（并行）')
    except BaseException:
        log1.error('并行模式 JUnit XML 生成失败', exc_info=1)
