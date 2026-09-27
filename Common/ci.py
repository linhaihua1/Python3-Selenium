# -*- coding: utf-8 -*-
"""
==========================================================================
 CI/CD 环境适配层（新人阅读顺序：第 13 个，只在对接流水线时才需要读）
==========================================================================

【一句话说明】
    让测试代码"知道自己在流水线里跑"，并把构建上下文（任务名、构建号、分支）
    带进日志和测试报告。这样在 Jenkins 上看到一份失败报告时，
    能立刻知道它是哪次构建、哪个分支产出的。

【在框架中的位置】
    Jenkinsfile / 任意 CI 脚本
        └─> run.py
              └─> Common/ci.py    <- 本文件（提供环境识别与构建元信息）
                    └─> Common/log.py  把上下文写进日志
    本文件不参与测试执行本身，纯"环境感知"，可安全忽略。

【为什么要单独一层】
    CI 与本机运行的差别主要在三点：
      1. 有没有构建号/分支这类上下文  -> build_info()
      2. 是无桌面环境，必须无头运行    -> 由 config 的环境变量覆盖机制解决
         （CI 里设 UI_CI_HEADLESS=true，见 Common/config.py 的 env 覆盖逻辑）
      3. 需要机器可读的结果文件        -> 由 Common/junitReport.py 解决
    本文件只负责第 1 点，保持职责单一。

【什么是"CI 环境变量"】
    主流 CI 平台运行时都会往进程里注入一批环境变量，例如 Jenkins 会注入
    BUILD_NUMBER / JOB_NAME / WORKSPACE。判断"是否在流水线中"就是看这些变量
    有没有值 —— 这是行业通用做法（本文件顶部的 _CI_MARKERS 就是这份名单）。

【新人注意】
    1. 本地运行时这些方法都不会报错，只是返回空字符串 / ci=False。
    2. 想让本地也模拟 CI，可以手工设置环境变量，例如 Windows:
           set UI_CI_HEADLESS=true
           set BUILD_NUMBER=999
       然后跑 python run.py，行为与流水线上一致。
==========================================================================
"""

import os
import platform
import time

from Common.log import log1

# ---------------------------------------------------------------------------
# 各 CI 平台用来标识"当前在流水线中"的环境变量名。
# 命中任意一个（且有值）即认为处于 CI 环境。
# ---------------------------------------------------------------------------
_CI_MARKERS = (
    'JENKINS_URL',          # Jenkins
    'BUILD_NUMBER',         # Jenkins / Hudson
    'JOB_NAME',             # Jenkins / Hudson
    'GITLAB_CI',            # GitLab CI
    'GITHUB_ACTIONS',       # GitHub Actions
    'TEAMCITY_VERSION',     # TeamCity
    'TRAVIS',               # Travis CI
    'CI',                   # 通用约定（很多平台都会设，值为 true）
)

# 值为这些时就当作"没开启"（有的平台会设成 false/0）
_FALSY = ('', '0', 'false', 'no', 'none')


def is_ci():
    """判断当前是否运行在 CI 流水线中。

    :return: True 表示处于流水线环境，False 表示本地运行
    """
    for name in _CI_MARKERS:
        value = os.environ.get(name)
        if value is not None and value.strip().lower() not in _FALSY:
            return True
    return False


def build_info():
    """收集当前构建的上下文信息，返回一个字典。

    键说明（取不到的项为空字符串）：
        ci          是否 CI 环境
        job         Jenkins 任务名，如 'ui-smoke-test'
        build       构建号，如 '128'
        build_url   构建页面地址，报告里可直接点开
        branch      分支名，如 'origin/main'
        commit      提交号前 8 位
        node        执行该构建的 Jenkins 节点名
        workspace   流水线工作目录
        app_build   被测应用自身的构建号（由参数 APP_BUILD_NO 注入，可空）
        python      执行测试的 Python 版本
        os          操作系统
        time        采集时刻
    """
    return {
        'ci': is_ci(),
        'job': os.environ.get('JOB_NAME', ''),
        'build': os.environ.get('BUILD_NUMBER', ''),
        'build_url': os.environ.get('BUILD_URL', ''),
        # Jenkins 用 GIT_BRANCH，多分支流水线用 BRANCH_NAME；两个都兜一下
        'branch': os.environ.get('GIT_BRANCH', '') or os.environ.get('BRANCH_NAME', ''),
        'commit': (os.environ.get('GIT_COMMIT', '') or '')[:8],
        'node': os.environ.get('NODE_NAME', ''),
        'workspace': os.environ.get('WORKSPACE', ''),
        # 被测应用自己的构建号：流水线里由 APP_BUILD_NO 参数传入，
        # 用于在报告里标注"这份结果对应哪个版本的应用"
        'app_build': os.environ.get('APP_BUILD_NO', ''),
        'python': platform.python_version(),
        'os': platform.platform(),
        'time': time.strftime('%Y-%m-%d %H:%M:%S'),
    }


def build_label():
    """生成一句人类可读的构建标识，用于拼进报告描述。

    :return: 例：'ui-smoke-test #128 分支=origin/main 应用构建=20260925.3'；
             本地运行时返回 '本地运行'
    """
    info = build_info()
    parts = []
    if info['job']:
        parts.append(info['job'])
    if info['build']:
        parts.append('#%s' % info['build'])
    if info['branch']:
        parts.append('分支=%s' % info['branch'])
    if info['commit']:
        parts.append('提交=%s' % info['commit'])
    if info['app_build']:
        parts.append('应用构建=%s' % info['app_build'])
    return ' '.join(parts) if parts else '本地运行'


def log_context():
    """把构建上下文写进日志（流水线控制台里能直接看到是哪个构建在跑）。

    :return: build_info() 的字典，方便调用方继续使用
    """
    info = build_info()
    log1.info(
        '运行环境：CI=%s | 任务=%s | 构建号=%s | 分支=%s | 节点=%s | Python=%s | 系统=%s'
        % (
            info['ci'],
            info['job'] or '-',
            info['build'] or '-',
            info['branch'] or '-',
            info['node'] or '-',
            info['python'],
            info['os'],
        )
    )
    return info


# 单独运行本文件可查看当前环境的 CI 上下文：python -m Common.ci
if __name__ == '__main__':
    log_context()
