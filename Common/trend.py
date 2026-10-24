# -*- coding: utf-8 -*-
"""
==========================================================================
 通过率趋势（把"这次绿了"变成"最近是不是在变差"）
==========================================================================

【解决什么问题】
    改造前每次执行都是孤立的：报告只看这一次。于是：
        · 用例从 95% 通过率慢慢滑到 60%，没人察觉，直到某天全红
        · 同一个用例反复偶发失败，被当成"环境问题"糊过去
        · 无法回答"这次改动让质量变好了还是变差了"

【做法】
    每次执行追加一条记录到 Report/history.jsonl（JSON Lines，一行一次运行），
    再据此算最近 N 次的趋势。刻意用文本格式：
        · 可以直接 git diff、grep
        · 坏了只是多一行，不会像数据库那样整体不可读
        · 不需要任何额外依赖

【为什么不做成"数据平台"】
    当前规模（一个产品线、几十到几百条用例）下，一个 jsonl 文件足够。
    引入数据库/时序库的运维成本远大于收益 —— 等真的需要了再换，
    接口不变（append_run / load_history / trend）。
==========================================================================
"""

import json
import os
import time
from typing import Any, Dict

from Common.log import log1

#: 历史记录文件（相对工程根，随 Report/ 一起被 CI 归档）
HISTORY_FILE = 'history.jsonl'

#: 保留最近多少次记录（防止文件无限增长；够看趋势即可）
MAX_KEEP = 500

#: 趋势判断的窗口大小
TREND_WINDOW = 10


def _report_dir():
    """动态取报告目录。

    ★ 不能用模块级 `from Common.dir_config import htmlreport_dir`：
      那样会在导入时把值**绑死**，之后测试（或任何重定向目录的代码）
      改了 dir_config.htmlreport_dir 也影响不到这里 —— 趋势会写到真实工程目录去。
      改为每次现取，与 Common/failureCapture.py 同一处理方式。
    """
    import Common.dir_config as dir_config
    return dir_config.htmlreport_dir


def history_path():
    """历史文件的绝对路径。"""
    return os.path.join(_report_dir(), HISTORY_FILE)


def append_run(summary, extra=None):
    """追加一次执行记录。

    :param summary: runner 返回的汇总字典
    :param extra:   额外字段（如被测版本号），会合并进记录
    :return: 记录字典；写入失败返回 None（趋势是辅助功能，绝不能影响主流程）

    ★ 本函数**不抛异常**：趋势记录失败不该让一次成功的测试变成失败。
    """
    record = {
        'time': time.strftime('%Y-%m-%d %H:%M:%S'),
        'tests_run': summary.get('tests_run', 0),
        'failures': summary.get('failures', 0),
        'errors': summary.get('errors', 0),
        'skipped': summary.get('skipped', 0),
        'duration': summary.get('duration', 0.0),
        'exit_code': summary.get('exit_code', 0),
        'pass_rate': pass_rate(summary),
    }
    if extra:
        record.update(extra)

    try:
        import Common.dir_config as dir_config
        dir_config.ensure_dir(_report_dir())
        path = history_path()
        with open(path, 'a', encoding='utf-8') as fp:
            fp.write(json.dumps(record, ensure_ascii=False) + '\n')
        _trim(path)
        return record
    except OSError as exc:
        log1.error('写趋势记录失败（不影响测试结果）：%s' % exc)
        return None


def pass_rate(summary):
    """算通过率（%）。没有用例时返回 0.0，避免除零。"""
    total = summary.get('tests_run', 0) or 0
    if total <= 0:
        return 0.0
    failed = (summary.get('failures', 0) or 0) + (summary.get('errors', 0) or 0)
    return round((total - failed) * 100.0 / total, 2)


def load_history(limit=None):
    """读取历史记录（按时间正序）。

    :param limit: 只取最近 N 条
    :return: 记录列表；文件不存在或某行损坏时跳过坏行，不抛异常
    """
    path = history_path()
    if not os.path.isfile(path):
        return []
    records = []
    try:
        with open(path, encoding='utf-8') as fp:
            for line in fp:
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except ValueError:
                    # 单行损坏（例如写入被中断）只跳过这一行 ——
                    # 让整个趋势文件不可读是更糟的选择
                    continue
    except OSError:
        return []
    return records[-limit:] if limit else records


def _trim(path):
    """只保留最近 MAX_KEEP 条记录。"""
    records = load_history()
    if len(records) <= MAX_KEEP:
        return
    with open(path, 'w', encoding='utf-8') as fp:
        for item in records[-MAX_KEEP:]:
            fp.write(json.dumps(item, ensure_ascii=False) + '\n')


def trend(window=TREND_WINDOW):
    """计算最近的通过率趋势。

    :param window: 看最近多少次
    :return: {
        'samples': 样本数,
        'latest': 最新一次通过率,
        'previous': 上一次通过率,
        'average': 窗口内平均,
        'delta': 最新 - 上一次,
        'direction': 'up' | 'down' | 'flat',
        'alert': 是否需要告警（连续下滑或跌破阈值）,
        'message': 一句话说明,
    }
    """
    records = load_history(limit=window)
    # 显式标注：值有 int 也有 float / str / None，不标注会被推断成
    # dict[str, str | int | None]，后面的大小比较与取模都会被判错。
    result: Dict[str, Any] = {
        'samples': len(records), 'latest': None, 'previous': None,
        'average': None, 'delta': None, 'direction': 'flat',
        'alert': False, 'message': '',
    }
    if not records:
        result['message'] = '暂无历史记录，本次是第一次执行'
        return result

    rates = [r.get('pass_rate', 0.0) for r in records]
    result['latest'] = rates[-1]
    result['average'] = round(sum(rates) / len(rates), 2)
    if len(rates) >= 2:
        result['previous'] = rates[-2]
        result['delta'] = round(rates[-1] - rates[-2], 2)
        if result['delta'] > 0:
            result['direction'] = 'up'
        elif result['delta'] < 0:
            result['direction'] = 'down'

    # ---- 是否告警：只要"最近连续两次下降"或"低于 90%"就提示 ----
    recent = rates[-3:]
    if len(recent) >= 3 and recent[0] > recent[1] > recent[2]:
        result['alert'] = True
        result['message'] = ('通过率连续 %d 次下滑（%s%% -> %s%%），'
                             '建议排查是否有用例在缓慢劣化'
                             % (len(recent), recent[0], recent[-1]))
    elif result['latest'] < 90:
        result['alert'] = True
        result['message'] = '最新通过率 %s%%，低于 90%% 基线' % result['latest']
    else:
        result['message'] = ('最新通过率 %s%%，窗口平均 %s%%，趋势%s'
                             % (result['latest'], result['average'],
                                {'up': '向好', 'down': '转差', 'flat': '平稳'}
                                [result['direction']]))
    return result


def format_trend(window=TREND_WINDOW):
    """把趋势渲染成一段可打印文本。"""
    info = trend(window)
    if not info['samples']:
        return ''
    lines = ['', '==================== 通过率趋势 ====================']
    lines.append('样本    : 最近 %d 次执行' % info['samples'])
    lines.append('最新    : %s%%' % info['latest'])
    if info['previous'] is not None:
        arrow = {'up': '↑', 'down': '↓', 'flat': '→'}[info['direction']]
        lines.append('环比    : %s %s%%（上一次 %s%%）'
                     % (arrow, info['delta'], info['previous']))
    lines.append('平均值  : %s%%' % info['average'])
    lines.append('结论    : %s' % info['message'])
    lines.append('==================================================')
    lines.append('')
    return '\n'.join(lines)
