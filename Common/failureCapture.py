# -*- coding: utf-8 -*-
"""
==========================================================================
 失败取证（新人阅读顺序：第 19 个，CI 上排查失败全靠它）
==========================================================================

【一句话说明】
    用例失败的那一刻，自动把"现场"存下来：一张截图 + 一份页面 HTML 源码。
    有了它，流水线上挂了以后不用再手工把用例跑一遍去找原因。

【为什么必须有它】
    没有自动取证时，CI 上的失败长这样：
        FAILED: test_3xxx —— AssertionError: '期望值' != '实际值'
    然后呢？值班的人只能：连 VPN -> 打开浏览器 -> 手工重放一遍 -> 也许还复现不了。
    有自动取证后，工件里直接能看到失败瞬间的页面长什么样、DOM 里到底有什么，
    平均定位时间能从"半小时"降到"看一眼"。

【在框架中的位置】
    Common/junitReport.py 的 JUnitResult.addFailure / addError
        └─> Common/failureCapture.py   <- 本文件（用例失败的瞬间被调用）
              ├─> Common/driverRegistry.py  取当前浏览器
              └─> Report/artifacts/日期/    截图与源码落盘

【落盘结构】
    Report/artifacts/2026-10-06/
      ├─ TestSuites_testLogin_TestLogin_test_6submitted_103512_431.png   失败截图
      └─ TestSuites_testLogin_TestLogin_test_6submitted_103512_431.html  页面源码

【为什么不复用用例里的 get_img()】
    用例在断言失败时手动调 get_img() 的做法有两个缺口：
      ① 不是所有失败路径都记得调（比如 setUp 里就抛了异常、或框架抛的异常）；
      ② 用例层的失败（ImportError、环境异常）根本没有页面对象可用。
    放在结果收集器里是**兜底**：只要用例失败就一定取证，与用例写得好不好无关。
    用例里已有的 get_img() 保留不动，两者互补。

【新人注意】
    1. 本模块**绝不向外抛异常**。取证失败不能反过来把测试结果搞乱 ——
       历史上很多测试框架都栽在"日志/截图模块自己崩了"上。
       所有异常都转成返回值里的 error 字段。
    2. 取不到 driver（比如用例在开浏览器之前就失败了）不算错误，正常跳过。
    3. 单个页面源码超过上限会截断，避免某个超大页面把磁盘写满。
==========================================================================
"""

import os
import time

from Common.driverRegistry import get_active
from Common.log import log1

#: 单个页面源码文件的写入上限（字符）。超出部分截断并注明。
#: 常规页面几十 KB；设这个上限是为了防"某个巨型页面把磁盘写满"。
MAX_SOURCE_CHARS = 2 * 1024 * 1024

#: 文件名里不允许出现的字符（Windows 尤其严格），统一换成下划线
_UNSAFE_CHARS = '<>:"/\\|?*'


def safe_name(text):
    """把用例 id 变成可作为文件名的字符串。

    :param text: 例如 'TestSuites.testLogin.TestLogin.test_6submitted'
    :return: 'TestSuites_testLogin_TestLogin_test_6submitted'

    用例 id 里带点号，直接当文件名虽然能用，但长短不一、还容易与扩展名混淆，
    统一转成下划线更好读，也避免 Windows 上非法字符导致的写入失败。
    """
    result = []
    for char in str(text):
        result.append('_' if (char in _UNSAFE_CHARS or char.isspace()) else char)
    return ''.join(result).replace('.', '_')


def resolve_dir(out_dir=None):
    """决定取证目录。

    :param out_dir: 显式指定；None 时读 config.ini [ci] artifacts_dir
    :return: (目录绝对路径, 是否启用)

    配置项：
        [ci] artifacts      = true/false   是否启用失败取证（默认 true）
        [ci] artifacts_dir  = Report/artifacts

    关闭方式：config.ini 写 artifacts = false，或设环境变量 UI_CI_ARTIFACTS=false。
    容器里磁盘紧张时可以关掉。
    """
    # 延迟导入：本模块会被结果收集器 import，避免模块级循环依赖
    import Common.dir_config as dir_config
    from Common.config import Config

    if not Config.get_bool('ci', 'artifacts', True):
        return None, False

    # 目录取值：优先 config.ini [ci] artifacts_dir；
    # 未配置时回退到 dir_config 的单一来源（artifacts_dir），
    # 避免 'Report/artifacts' 这个相对路径在两处各写一遍、改了一处漏另一处。
    if out_dir:
        raw = out_dir
    else:
        raw = Config.get('ci', 'artifacts_dir', '')
        if not raw:
            configured = dir_config.artifacts_dir
            raw = os.path.relpath(configured, dir_config.base_dir)
    if not os.path.isabs(raw):
        raw = os.path.join(dir_config.base_dir, raw)
    # normpath 归一化路径分隔符：配置里习惯写 'Report/artifacts'（正斜杠），
    # 拼接后会得到 'C:\\...\\Report/artifacts' 这种混合形式 ——
    # 虽然能用，但日志里难看，比较路径时也容易踩坑。
    # 按日期分子目录：一次回归跑几百条用例，全堆在一个目录里翻起来很痛苦
    return os.path.normpath(os.path.join(raw, time.strftime('%Y-%m-%d'))), True


def capture(test_id, driver=None, out_dir=None, tag='failure'):
    """对一条失败的用例取证：截图 + 页面源码。

    :param test_id: 用例 id（如 'TestSuites.testLogin.TestLogin.test_1login'）
    :param driver:  浏览器对象；不传则从 driverRegistry 取当前活动的
    :param out_dir: 取证目录；不传按 config.ini 解析
    :param tag:     文件名中的阶段标记，'failure' / 'error' / 'setUpClass' 等
    :return: 结果字典：
        {'enabled': bool, 'dir': str|None, 'screenshot': str|None,
         'source': str|None, 'error': str|None}

    ★ 本函数不抛异常。任何一步失败都写进返回值的 error 字段。
    """
    result = {'enabled': False, 'dir': None, 'screenshot': None,
              'source': None, 'error': None}

    try:
        folder, enabled = resolve_dir(out_dir)
        if not enabled:
            result['error'] = '失败取证已关闭（[ci] artifacts = false）'
            return result
        result['enabled'] = True
        result['dir'] = folder
    except Exception as exc:            # pragma: no cover - 配置读取异常
        result['error'] = '解析取证目录失败：%s' % exc
        return result

    # 取浏览器：用例可能在开浏览器之前就失败了，这属于正常情况，不算错误
    if driver is None:
        driver = get_active()
    if driver is None:
        result['error'] = '未找到可用的浏览器实例（用例可能未启动浏览器）'
        return result

    try:
        os.makedirs(folder, exist_ok=True)
    except OSError as exc:
        result['error'] = '创建取证目录失败：%s' % exc
        return result

    # 文件名：用例名 + 阶段 + 时间（含毫秒），保证同一用例多次失败不会互相覆盖
    stamp = '%s_%03d' % (time.strftime('%H%M%S'), int(time.time() * 1000) % 1000)
    base = '%s_%s_%s' % (safe_name(test_id), tag, stamp)

    # ---- 1. 截图 ----
    shot_path = os.path.join(folder, base + '.png')
    try:
        driver.save_screenshot(shot_path)
        result['screenshot'] = shot_path
    except Exception as exc:
        # 常见原因：浏览器已崩、driver 会话失效（InvalidSessionIdException）
        result['error'] = _append(result['error'], '截图失败：%s' % exc)

    # ---- 2. 页面源码 ----
    # 页面源码是截图的重要补充：截图只能看出"长什么样"，
    # 源码能看出"DOM 里到底有没有那个元素、它的 id/文字是什么"，
    # 定位元素失效类问题基本都要靠它。
    try:
        html = driver.page_source or ''
    except Exception as exc:
        result['error'] = _append(result['error'], '读取页面源码失败：%s' % exc)
        html = None

    if html is not None:
        src_path = os.path.join(folder, base + '.html')
        try:
            if len(html) > MAX_SOURCE_CHARS:
                html = html[:MAX_SOURCE_CHARS] + '\n<!-- 页面源码超长，已截断 -->'
            with open(src_path, 'w', encoding='utf-8', errors='replace') as fp:
                fp.write(html)
            result['source'] = src_path
        except OSError as exc:
            result['error'] = _append(result['error'], '保存页面源码失败：%s' % exc)

    if result['screenshot'] or result['source']:
        log1.info('已保存失败现场：截图=%s 源码=%s'
                  % (os.path.basename(result['screenshot'] or '无'),
                     os.path.basename(result['source'] or '无')))
    return result


def _append(existing, message):
    """把多条错误信息拼起来，保留第一手的失败原因不被后续覆盖。"""
    return message if not existing else '%s；%s' % (existing, message)
