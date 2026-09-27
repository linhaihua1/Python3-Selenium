# -*- coding: utf-8 -*-
"""
==========================================================================
 备用入口：党建云主题报告（新人阅读顺序：第 13 个）
==========================================================================

【一句话说明】
    和 run.py 做的是同一件事，只是报告标题/文件名换成了「党建云生产系统」。
    历史上这是给另一个被测系统留的入口，现在两个入口共用同一套用例。

【在框架中的位置】
    entrance.py  ──>  Common/runner.py  ──>  TestSuites/*.py
    （和 run.py 完全平行，区别只在传入的 title / report_name）

【怎么用】
    python entrance.py                    # 全量
    python entrance.py smoke              # 冒烟（位置参数，可选）

【新人注意】
    1. 旧版本文件有两个坑：一是 `from HTMLTestReportCN import ...` 少了 Common 前缀，
       二是一整段重复 import，已在重构中清理。如果看到旧文档提到这些，已过时。
    2. 如果只想保留一个入口，可以只在 run.py 里用 --title/--filename 传参，
       本文件并非必需。
    3. 本入口同样遵循退出码约定（0 通过 / 1 用例失败 / 2 环境异常），
       所以也能被流水线直接调用；但流水线推荐用 run.py —— 它的参数更完整。
==========================================================================
"""

import os
import sys

# 同 run.py：保证从任意工作目录执行都能 import 到工程内的包
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 同 run.py：兜住 locale 为 C 的环境（Linux 容器），避免中文输出抛 UnicodeEncodeError
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding='utf-8', errors='replace')
    except (AttributeError, ValueError):
        pass

from Common import runner
from Common.log import log1

# 报告标题，同时也是报告文件名（见下方拼接逻辑）
DANGJIAN_TITLE = '党建云生产系统Ui自动化测试报告'

if __name__ == '__main__':
    # 支持 python entrance.py smoke 走冒烟子集，不传则跑全量
    suite_kind = sys.argv[1] if len(sys.argv) > 1 else 'full'
    log1.info('===== UI 自动化测试开始（entrance.py，模式=%s）=====' % suite_kind)

    summary = runner.run(
        title=DANGJIAN_TITLE,
        report_name=DANGJIAN_TITLE + '.html',
        description='党建云生产系统 UI 自动化测试',
        suite_kind=suite_kind,
    )

    log1.info('执行结束，退出码 %d' % summary['exit_code'])
    # 与 run.py 保持一致的退出码语义，便于流水线统一处理
    sys.exit(summary['exit_code'])
