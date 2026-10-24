# -*- coding: utf-8 -*-
"""
==========================================================================
 运行环境自检（新人阅读顺序：第 18 个，跑不起来时第一个该看的）
==========================================================================

【一句话说明】
    在开浏览器之前，先把"这台机器到底能不能跑 UI 自动化"体检一遍：
    Python 版本 / selenium / 浏览器 / 驱动版本 / 目录可写性。
    发现问题就给**可以直接照做的修复提示**，而不是让人对着一屏堆栈猜。

【在框架中的位置】
    run.py --preflight                 <- 只想体检、不跑用例时走这里
    Common/runner.py 的 run()           <- 每次执行前自动体检一次（见 2.7 节）
          └─> Common/preflight.py       <- 本文件。只读文件系统与环境，不碰浏览器

【为什么需要它（这是真实踩过的坑）】
    本机 Python 安装目录里被塞过一个 ChromeDriver 114，而 Chrome 已经升到 154。
    Selenium Manager 其实早就把匹配的 154 驱动下载好了，但 PATH 上那个 114
    优先级更高、被直接采用，于是现象是：
        跑测试 -> 卡 60 秒 -> 抛 40 行 stacktrace -> session not created ...
    看到这堆东西的人根本想不到"是驱动版本不对"。而本模块 1 秒内就能说清：
        [错误] 驱动  PATH 上的 chromedriver 是 114，浏览器是 154，主版本不匹配
                修复：改名或删除 C:\\...\\Python311\\chromedriver.exe
    环境类问题就应该在开跑前一次性讲明白。

【五道检查（按顺序）】
    ① Python 版本     >= 3.9
    ② selenium        能导入且 >= 4（本工程按 Selenium 4 的 API 写，3.x 会 AttributeError）
    ③ 浏览器          按 browser 找可执行文件；容器里可用 [ci] chrome_binary 显式指定
    ④ 驱动版本比对    PATH 上存在 driver 时，主版本必须与浏览器一致
    ⑤ 目录可写        Logs / img / Report / Report/artifacts 是否可写

【配置（config.ini）】
    [ci] chrome_binary   浏览器可执行文件绝对路径（容器里必须填，如 /usr/bin/chromium）
    [ci] preflight       true=执行前自动体检（默认）；false=跳过

【新人注意】
    1. 本模块**只读**：不建目录、不删文件、不改配置。
       发现驱动版本不对时只告诉你"该去删哪个文件"，绝不替你删 ——
       删文件不可逆，必须由人确认。
    2. 任何检查失败都不抛异常，最坏情况是返回一条"没查出来"的警告。
       体检器自己把测试搞挂，比不体检更糟。
    3. 只有 LEVEL_ERROR 会中止执行；LEVEL_WARN 仅提示，不影响退出码。
==========================================================================
"""

import json
import os
import re
import shutil
import subprocess
import sys
from typing import Dict, Optional, Tuple

from Common import dir_config
from Common.log import log1

# --------------------------------------------------------------------------
# 结论等级：只有 ERROR 会拦住执行
# --------------------------------------------------------------------------
LEVEL_OK = 'ok'
LEVEL_WARN = 'warn'
LEVEL_ERROR = 'error'

#: 最低 Python 版本。低于它时工程里若干写法（如 dict 合并、类型标注）可能不可用
MIN_PYTHON = (3, 9)

#: 本地临时发现的浏览器版本缓存：一次体检里多个检查都要用，避免重复探测
#: 键是 (浏览器类型, 浏览器可执行文件路径)，值是主版本号
_BROWSER_MAJOR_CACHE: Dict[Tuple[str, str], Optional[int]] = {}

# --------------------------------------------------------------------------
# 各浏览器在不同平台上的常见安装位置。
# 这里只列"默认安装"的位置；装到别处时请在 config.ini 里配 [ci] chrome_binary。
# --------------------------------------------------------------------------
_BROWSER_PATHS = {
    'chrome': {
        'nt': [
            r'C:\Program Files\Google\Chrome\Application\chrome.exe',
            r'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe',
            os.path.expandvars(r'%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe'),
        ],
        'posix': [
            '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
            '/usr/bin/google-chrome',
            '/usr/bin/google-chrome-stable',
            '/usr/bin/chromium',
            '/usr/bin/chromium-browser',
            '/snap/bin/chromium',
        ],
    },
    'edge': {
        'nt': [
            r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe',
            r'C:\Program Files\Microsoft\Edge\Application\msedge.exe',
        ],
        'posix': [
            '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge',
            '/usr/bin/microsoft-edge',
            '/usr/bin/microsoft-edge-stable',
        ],
    },
    'firefox': {
        'nt': [
            r'C:\Program Files\Mozilla Firefox\firefox.exe',
            r'C:\Program Files (x86)\Mozilla Firefox\firefox.exe',
        ],
        'posix': [
            '/Applications/Firefox.app/Contents/MacOS/firefox',
            '/usr/bin/firefox',
            '/snap/bin/firefox',
        ],
    },
}

#: 浏览器 -> PATH 上可执行文件的名字（用于 shutil.which 兜底查找）
_BROWSER_WHICH = {
    'chrome': ('google-chrome', 'google-chrome-stable', 'chromium',
               'chromium-browser', 'chrome'),
    'edge': ('microsoft-edge', 'microsoft-edge-stable', 'msedge'),
    'firefox': ('firefox',),
}

#: 浏览器 -> 对应的 WebDriver 可执行文件名。PATH 上出现它才需要做版本比对
_DRIVER_NAMES = {
    'chrome': 'chromedriver',
    'edge': 'msedgedriver',
    'firefox': 'geckodriver',
}

#: 从任意含版本号的文本里抠出主版本号，例如
#:   'Google Chrome 154.0.8037.57' -> 154
#:   'ChromeDriver 114.0.5735.90 (386bc09e...)' -> 114
_MAJOR_RE = re.compile(r'(\d+)\.\d+\.\d+')

#: Chrome 在安装目录下按版本号建子目录（Application/154.0.8037.57/），
#: 这是 Windows 上拿到浏览器版本最稳的办法（详见 _release_version_dirs 的说明）
_VERSION_DIR_RE = re.compile(r'^(\d+)\.\d+\.\d+\.\d+$')


class Finding:
    """一条体检结论。

    属性：
        name   —— 检查项名称（Python / selenium / 浏览器 / 驱动 / 目录）
        level  —— LEVEL_OK / LEVEL_WARN / LEVEL_ERROR
        detail —— 查到了什么（人话，带具体版本号或路径）
        hint   —— 查出来有问题时，"下一步该做什么"
    """

    def __init__(self, name, level, detail, hint=''):
        self.name = name
        self.level = level
        self.detail = detail
        self.hint = hint

    def __repr__(self):
        return 'Finding(%s, %s, %s)' % (self.name, self.level, self.detail)


# ==========================================================================
# 小工具（都是"读"，不产生副作用）
# ==========================================================================
def _major(text):
    """从含版本号的文本里取主版本号（int）；取不到返回 None。"""
    if not text:
        return None
    found = _MAJOR_RE.search(str(text))
    if not found:
        # 也接受只写了主版本的写法，例如 'ChromeDriver 114'
        bare = re.search(r'\b(\d{2,3})\b', str(text))
        return int(bare.group(1)) if bare else None
    return int(found.group(1))


def _run_version(exe, timeout=10):
    """执行 `<exe> --version` 并返回输出文本；任何异常都返回空串。

    ⚠️ 只对**命令行程序**（chromedriver / geckodriver / msedgedriver）调用，
       绝不对浏览器主程序调用 —— 详见 _browser_major 里的说明。
    """
    try:
        proc = subprocess.run(
            [exe, '--version'],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
        )
    except (OSError, ValueError, subprocess.SubprocessError):
        return ''
    raw = proc.stdout or b''
    if isinstance(raw, bytes):
        return raw.decode('utf-8', 'replace').strip()
    return str(raw).strip()


def _explain_os_error(exc):
    """把"目录不可写"这类异常翻译成一句人话（用于体检结论，不是日志堆栈）。"""
    text = str(exc)
    if isinstance(exc, PermissionError):
        return '权限不足（%s）' % text
    return text


def _find_on_path(name):
    """在 PATH 上找可执行文件；找不到返回 None。"""
    try:
        return shutil.which(name)
    except (OSError, TypeError):
        return None


def _release_version_dirs(parent):
    """列出 parent 下形如 '154.0.8037.57' 的版本目录，返回主版本号列表。

    为什么用这个办法拿 Windows 上的 Chrome 版本：
        `chrome.exe --version` 在 Windows 上**不会打印版本**，
        而是直接启动一个浏览器窗口 —— 在 CI 上会莫名多出一个 Chrome 进程，
        所以绝对不能这么探测。而 Chrome 安装后会在 Application 目录下
        按版本号建子目录，扫一下就知道了，零风险。
    """
    try:
        entries = os.listdir(parent)
    except OSError:
        return []
    majors = []
    for entry in entries:
        matched = _VERSION_DIR_RE.match(entry)
        if matched and os.path.isdir(os.path.join(parent, entry)):
            majors.append(int(matched.group(1)))
    return majors


def _selenium_manager_major(driver_name):
    """从 Selenium Manager 的缓存里读它已知的"浏览器主版本"。

    Selenium Manager 每次跑都会把探测结果写进 ~/.cache/selenium/se-metadata.json，
    里面 drivers[].major_browser_version 就是浏览器主版本。

    读它是"顺手占便宜"：拿不到就返回 None，不影响体检结论 ——
    这个文件属于 Selenium 的内部实现，未来格式可能变，所以必须容错。
    """
    cache = os.path.join(os.path.expanduser('~'), '.cache', 'selenium', 'se-metadata.json')
    if not os.path.isfile(cache):
        return None
    try:
        with open(cache, encoding='utf-8') as fp:
            data = json.load(fp)
    except (OSError, ValueError):
        return None
    for item in data.get('drivers') or []:
        if not isinstance(item, dict):
            continue
        if item.get('driver_name') != driver_name:
            continue
        return _major(item.get('major_browser_version'))
    return None


# ==========================================================================
# 五道检查
# ==========================================================================
def check_python(min_version=MIN_PYTHON):
    """① Python 解释器版本。【在用】"""
    current = sys.version_info[:3]
    shown = '.'.join(str(part) for part in current)
    need = '.'.join(str(part) for part in min_version)
    if current < tuple(min_version):
        return Finding('Python', LEVEL_ERROR,
                       '当前 %s，要求 >= %s' % (shown, need),
                       '换用更高版本的 Python 运行本工程，'
                       '或确认低版本下所有用例仍能跑通后再下调 MIN_PYTHON')
    return Finding('Python', LEVEL_OK, '%s（>= %s）' % (shown, need))


def check_selenium():
    """② selenium 是否可用，以及版本是否满足。【在用】"""
    try:
        import selenium
    except ImportError:
        return Finding('selenium', LEVEL_ERROR,
                       '未安装',
                       'pip install -r requirements.txt')
    version = getattr(selenium, '__version__', '')
    major = _major(version)
    if major is None:
        return Finding('selenium', LEVEL_WARN,
                       '已安装，但读不到版本号（%s）' % version,
                       'pip install -U selenium 换成正式发行版')
    if major < 4:
        return Finding('selenium', LEVEL_ERROR,
                       '当前 %s，本工程要求 >= 4.0' % version,
                       'pip install -U "selenium>=4.19"  '
                       '（Selenium 3 的 find_element_by_id 等写法在 4 里已删除）')
    return Finding('selenium', LEVEL_OK, version)


def find_browser(browser='chrome', browser_binary=''):
    """③ 找浏览器可执行文件。返回绝对路径；找不到返回 None。【在用】

    :param browser:        chrome / edge / firefox（对应 [environment] browser）
    :param browser_binary: 显式指定的路径（对应 [ci] chrome_binary）；填了就用它
    """
    if browser_binary:
        candidate = os.path.expanduser(browser_binary.strip())
        return candidate if os.path.isfile(candidate) else None

    name = (browser or 'chrome').strip().lower()
    platform_key = 'nt' if os.name == 'nt' else 'posix'
    for candidate in _BROWSER_PATHS.get(name, {}).get(platform_key, []):
        if candidate and os.path.isfile(candidate):
            return candidate
    for exe_name in _BROWSER_WHICH.get(name, ()):
        found = _find_on_path(exe_name)
        if found:
            return found
    return None


def check_browser(browser='chrome', browser_binary=''):
    """③ 包装：浏览器是否存在。【在用】"""
    path = find_browser(browser, browser_binary)
    if path:
        return Finding('浏览器', LEVEL_OK, '%s -> %s' % (browser, path)), path
    if browser_binary:
        return Finding('浏览器', LEVEL_ERROR,
                       '[ci] chrome_binary 指向的文件不存在：%s' % browser_binary,
                       '改成真实的浏览器可执行文件路径；'
                       '容器里通常是 /usr/bin/chromium'), None
    return Finding('浏览器', LEVEL_ERROR,
                   '找不到 %s 的可执行文件' % browser,
                   '装一个浏览器；若装在非默认位置，把绝对路径写进 '
                   'config.ini -> [ci] chrome_binary'), None


def browser_major(browser='chrome', browser_path=''):
    """尽力探测浏览器主版本号；探不到返回 None。【在用】

    探测顺序（只用"安全"的手段，绝不启动浏览器进程）：
        1. Windows：扫安装目录下的版本号子目录（最准，且不会弹出窗口）
        2. Selenium Manager 缓存里记录过的主版本
        3. 非 Windows：执行 `<浏览器> --version`（Linux/macOS 上是安全的）
    """
    key = (browser, browser_path)
    if key in _BROWSER_MAJOR_CACHE:
        return _BROWSER_MAJOR_CACHE[key]

    name = (browser or 'chrome').strip().lower()
    driver_name = _DRIVER_NAMES.get(name, 'chromedriver')
    major = None

    if browser_path and os.name == 'nt':
        majors = _release_version_dirs(os.path.dirname(browser_path))
        if majors:
            major = max(majors)
    if major is None:
        major = _selenium_manager_major(driver_name)
    if major is None and browser_path and os.name != 'nt':
        major = _major(_run_version(browser_path))

    _BROWSER_MAJOR_CACHE[key] = major
    return major


def check_driver(browser='chrome', browser_path=''):
    """④ PATH 上的 WebDriver 与浏览器版本是否匹配。【在用】

    这是本模块最有价值的一条检查：驱动版本不匹配时，
    Selenium 报的是 "session not created"，看不出跟版本有关，
    而实际上几秒钟就能判定。

    没找到 driver 时算**正常** —— Selenium 4 的 Selenium Manager
    会自动下载匹配的那一个，这正是我们想要的。
    """
    name = (browser or 'chrome').strip().lower()
    driver = _DRIVER_NAMES.get(name, 'chromedriver')
    driver_path = _find_on_path(driver)

    if not driver_path:
        return Finding('驱动', LEVEL_OK,
                       'PATH 上没有 %s，由 Selenium Manager 自动匹配下载（正常）' % driver)

    text = _run_version(driver_path)
    driver_major = _major(text)
    if driver_major is None:
        return Finding('驱动', LEVEL_WARN,
                       'PATH 上存在 %s（%s），但读不出它的版本号' % (driver, driver_path),
                       '若报 "session not created" 之类的启动失败，'
                       '可以先把 %s 改名或删除，让 Selenium Manager 自己下匹配版' % driver_path)

    major = browser_major(name, browser_path)
    if major is None:
        return Finding('驱动', LEVEL_WARN,
                       'PATH 上存在 %s（主版本 %s），但没能确认浏览器版本，无法比对'
                       % (driver, driver_major),
                       '若报 "This version of ChromeDriver only supports Chrome version X"，'
                       '就是它不匹配：把 %s 改名或删除即可' % driver_path)

    if driver_major != major:
        return Finding('驱动', LEVEL_ERROR,
                       'PATH 上的 %s 是 %s，而浏览器是 %s，主版本不匹配'
                       % (driver, driver_major, major),
                       'Selenium Manager 下载的匹配驱动会被 PATH 上这个覆盖掉。'
                       '请把 %s 改名（例如 %s.bak）或删除后重跑；'
                       '或直接升级成 %s 版驱动' % (driver_path, driver, major))

    return Finding('驱动', LEVEL_OK,
                   'PATH 上的 %s 主版本 %s，与浏览器一致（%s）'
                   % (driver, driver_major, driver_path))


def check_dirs(extra=None):
    """⑤ 运行产物目录是否可写。【在用】

    只判断"最近的已存在祖先目录"能否写入，**不创建任何目录** ——
    体检不应该改变机器状态。
    """
    targets = [
        ('日志 Logs', os.environ.get('UI_LOG_DIR') or os.path.join(dir_config.base_dir, 'Logs')),
        ('截图 img', os.path.join(dir_config.base_dir, 'img')),
        ('报告 Report', dir_config.htmlreport_dir),
        ('失败取证 artifacts', dir_config.artifacts_dir),
    ]
    if extra:
        targets.extend(extra)

    bad = []
    for label, path in targets:
        probe = path
        while probe and not os.path.isdir(probe):
            parent = os.path.dirname(probe)
            if parent == probe:
                break
            probe = parent
        if not os.path.isdir(probe):
            bad.append('%s（没有可用的父目录：%s）' % (label, path))
        elif not os.access(probe, os.W_OK):
            bad.append('%s（不可写：%s）' % (label, probe))

    if bad:
        return Finding('目录', LEVEL_ERROR, '；'.join(bad),
                       '检查工程目录权限（CI 上常见于工作区只读、'
                       '或容器用户与挂载卷属主不一致）')
    return Finding('目录', LEVEL_OK, 'Logs / img / Report / artifacts 均可写')


# ==========================================================================
# 汇总与输出
# ==========================================================================
def collect(browser='chrome', browser_binary='', check_dirs_too=True):
    """跑完所有检查，返回 Finding 列表。【在用】

    :param browser:        对应 config.ini -> [environment] browser
    :param browser_binary: 对应 config.ini -> [ci] chrome_binary
    :param check_dirs_too: 是否检查目录可写（单元测试里可关掉，避免依赖真实目录）
    :return: [Finding, ...]，顺序与文档里的①~⑤一致
    """
    findings = [check_python(), check_selenium()]

    browser_finding, browser_path = check_browser(browser, browser_binary)
    findings.append(browser_finding)
    if browser_path:
        findings.append(check_driver(browser, browser_path))
    else:
        # 浏览器都没找到，驱动比对没有意义，给一条说明而不是留空
        findings.append(Finding('驱动', LEVEL_WARN,
                                '跳过比对：未找到浏览器可执行文件',
                                '先解决上一行的浏览器问题'))

    if check_dirs_too:
        findings.append(check_dirs())
    return findings


def has_error(findings):
    """这批结论里是否有致命项（决定要不要中止执行）。【在用】"""
    return any(item.level == LEVEL_ERROR for item in findings)


def worst_level(findings):
    """取最严重的等级，便于上层一句话判断。【在用】"""
    for level in (LEVEL_ERROR, LEVEL_WARN):
        if any(item.level == level for item in findings):
            return level
    return LEVEL_OK


def format_report(findings, only_problems=False):
    """把结论渲染成一段可读文本（给日志/控制台用）。【在用】

    :param only_problems: True 时只输出 warn/error，CI 日志更短
    """
    marks = {LEVEL_OK: '[正常]', LEVEL_WARN: '[警告]', LEVEL_ERROR: '[错误]'}
    lines = ['==================== 运行环境自检 ====================']
    for item in findings:
        if only_problems and item.level == LEVEL_OK:
            continue
        lines.append('%s %-10s %s' % (marks.get(item.level, '[?]'), item.name, item.detail))
        if item.hint and item.level != LEVEL_OK:
            lines.append('       修复：%s' % item.hint)

    if not any(item.level != LEVEL_OK for item in findings):
        lines.append('[正常] 全部检查通过')
    lines.append('======================================================')
    return '\n'.join(lines)


def log_findings(findings):
    """把结论写进日志：正常项走 info，警告/错误走对应级别。【在用】

    为什么要分级别而不是全打 info：
        CI 上"日志里搜 ERROR"是最快的排查动作，环境问题必须能被搜到。
    """
    for item in findings:
        if item.level == LEVEL_ERROR:
            log1.error('环境自检 %s：%s（修复：%s）' % (item.name, item.detail, item.hint or '—'))
        elif item.level == LEVEL_WARN:
            log1.warning('环境自检 %s：%s（建议：%s）' % (item.name, item.detail, item.hint or '—'))
        else:
            log1.info('环境自检 %s：%s' % (item.name, item.detail))


def main(argv=None):
    """命令行入口：python -m Common.preflight。【在用】

    :return: 0 = 无致命问题；2 = 存在致命问题（与 runner 的环境异常退出码一致）

    用途：
        1. Jenkins 节点第一次接入时，先跑它确认环境齐备，再谈跑用例
        2. 本机突然跑不起来时，先跑它排除环境因素
    """
    import argparse
    parser = argparse.ArgumentParser(description='UI 自动化运行环境自检（不跑用例）')
    parser.add_argument('--browser', default='chrome', choices=('chrome', 'firefox', 'edge'),
                        help='按哪种浏览器检查（默认 chrome）')
    parser.add_argument('--binary', default='', help='浏览器可执行文件路径（等同 [ci] chrome_binary）')
    parser.add_argument('--quiet', action='store_true', help='只显示有问题的项')
    args = parser.parse_args(argv)

    findings = collect(browser=args.browser, browser_binary=args.binary)
    print(format_report(findings, only_problems=args.quiet))
    return 2 if has_error(findings) else 0


if __name__ == '__main__':
    sys.exit(main())
