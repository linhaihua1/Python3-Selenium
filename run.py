# -*- coding: utf-8 -*-
"""
==========================================================================
 程序主入口（新人阅读顺序：第 1 个）
==========================================================================

【一句话说明】
    启动整个工程的 UI 自动化测试，跑完生成中文 HTML 报告 + JUnit XML 结果，
    并以「退出码」告诉调用方这次测试是通过还是失败。本工程共有两个入口，
    这个是主入口（本机执行和 Jenkins 流水线用的都是它）。

【在框架中的位置】
    命令行 / Jenkins 流水线
      └─> run.py                    <- 本文件。只做两件事：
      │                                ① 解析参数 ② 把参数翻译成配置覆盖
            └─> Common/runner.py    <- 真正干活的地方：收集用例 -> 执行 -> 出报告
                  └─> TestSuites/*.py   <- 被执行的测试用例

【怎么用】
    # ---- 本机开发 ----
    python run.py                                # 用 config.ini 里的配置（有界面，能看到浏览器操作）
    python run.py --env test                     # ★切到 [env_test] 档：地址/无头/写入范围一次到位
    python run.py --headless                     # 无头运行，和流水线上行为一致
    python run.py --suite smoke                  # 只跑冒烟用例（不产生数据副作用）
    python run.py --title 冒烟测试 --filename smoke.html
    python run.py --pattern 'test_Login*.py'     # 只跑文件名匹配的用例
    python run.py --url http://测试环境/sso-portal/#/?redirect=/launch   # 临时切环境
    python run.py --mail                         # 跑完把报告当附件发邮件

    # ---- Jenkins 里 ----
    python run.py --env test --suite smoke --headless --junit Report/junit-results.xml

    # ---- 排查环境问题（不跑用例）----
    python run.py --preflight                    # 体检这台机器能不能跑 UI 自动化
    python -m Common.preflight --quiet           # 等价写法，只列出有问题的项

【退出码（CI 判定构建成败的依据）】
    0 = 全部通过     1 = 有用例失败     2 = 环境/配置问题
    流水线的 junit 插件负责展示用例明细，退出码负责把构建标红，两者缺一不可。

【三道闸门（企业级的关键，跑错环境这种事必须由框架拦住）】
    ① 写入范围   [testcase] mode = readonly 时，只跑标记为只读的用例
                 标记方式：类属性 scope = 'readonly' 或方法上加 @readonly
    ② 环境守卫   地址为空/占位、不在白名单、疑似生产且含写用例 -> 直接中止（退出码 2）
                 配置在 config.ini -> [safety]，实现见 Common/env_guard.py
    ③ 环境自检   Python/selenium/浏览器/驱动版本/目录可写 有问题 -> 直接中止（退出码 2）
                 配置在 config.ini -> [ci] preflight，实现见 Common/preflight.py
    被拦下时不会有任何浏览器被打开，控制台会打印"原因"一行说明该改哪个配置。

【新人注意】
    1. 首次运行前先装依赖：pip install -r requirements.txt
    2. config.ini 里默认填的是**生产环境**地址，跑全量用例会真实上传视频、
       真实提交报送单，跑之前务必确认环境与数据影响！
       （现在有环境守卫兜底，但守卫靠配置判断，配置本身仍要填对）
    3. 本文件刻意保持"薄"：想改测试逻辑请去 TestSuites/ 或 Common/runner.py，
       不要把业务代码堆到这里。
    4. 参数是怎么生效的？全部转成 UI_ 开头的环境变量，再由 Common/config.py
       统一覆盖配置 —— 全工程只有"环境变量 > config.ini > 代码默认值"一条优先级链路。
    5. 常用定位手段：控制台输出的「失败摘要」、Logs/日期/Error_Logs/、
       Report/artifacts/日期/（失败自动截图与页面源码）、img/日期/（用例主动截图）。
    6. ★ 突然跑不起来（浏览器起不来、报 session not created、卡很久才抛错）？
       先跑 `python run.py --preflight`。它会告诉你是不是浏览器/驱动这类环境问题，
       并给出具体要改什么 —— 比对着堆栈猜快得多。
==========================================================================
"""

import argparse
import os
import sys

# 把工程根目录塞进 sys.path，这样无论从哪个目录执行 python run.py，
# 都能 import 到 Common / PageObject / TestSuites 这些包。
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 保证中文输出在任何终端/CI 环境下都不会把构建搞挂。
# 场景：Linux 容器里若 locale 是 C/POSIX，stdout 编码会退化成 ascii，
# 此时 print 中文（报告结论、失败摘要）会抛 UnicodeEncodeError。
# errors='replace' 兜底：万一还有无法编码的字符，最多显示成 ?，不会中断测试。
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding='utf-8', errors='replace')
    except (AttributeError, ValueError):   # 老版本 Python 或被重定向的流
        pass

from Common import runner
from Common.log import log1


def parse_args(argv=None):
    """定义并解析命令行参数。

    所有参数都是可选的；不传时由 runner.run() 回退到 config.ini 的配置。
    返回 argparse.Namespace，形如 args.title / args.filename / args.mail ...
    """
    parser = argparse.ArgumentParser(
        description='融媒体生产系统 UI 自动化测试（支持 CI/CD 流水线调用）'
    )

    # ---- 报告元信息 ----
    parser.add_argument('--title', help='报告标题')
    parser.add_argument('--filename', help='报告文件名，如 冒烟测试.html')
    parser.add_argument('--tester', help='执行人（Jenkins 上建议传构建号，便于追溯）')
    parser.add_argument('--description', help='报告描述，不传则自动拼上构建信息')

    # ---- 用例选择 ----
    parser.add_argument('--pattern', default='test*.py', help='用例文件匹配规则')
    parser.add_argument('--suite', default='full', choices=('full', 'smoke'),
                        help='full=全部用例；smoke=只跑 [ci] smoke_cases 配置的冒烟用例')
    parser.add_argument('--cases',
                        help='按用例方法名过滤，逗号分隔，优先级高于 --suite，'
                             '如 test_1login,test_2select_scxt')

    # ---- 运行环境 ----
    # headless 用互斥组：不传时为 None（沿用 config.ini 配置），
    # 传了则强制覆盖，便于本机调试与流水线用同一份代码
    parser.set_defaults(headless=None)
    headless_group = parser.add_mutually_exclusive_group()
    headless_group.add_argument('--headless', dest='headless', action='store_true',
                                help='无头模式运行（流水线必须开启）')
    headless_group.add_argument('--no-headless', dest='headless', action='store_false',
                                help='强制有界面运行（本机调试用）')
    parser.add_argument('--browser', choices=('chrome', 'firefox', 'edge'),
                        help='浏览器类型，覆盖 config.ini [environment] browser')
    parser.add_argument('--url', help='被测地址，覆盖 config.ini [environment] url')
    # Selenium Grid 远程执行：把驱动交给远程 Hub（如 http://hub:4444）。
    # 不传则本机开浏览器（与历史行为一致）。
    parser.add_argument('--grid', dest='grid',
                        help='Selenium Grid Hub 地址（如 http://127.0.0.1:4444），'
                             '传入则远程执行；对应 [ci] grid_url / UI_CI_GRID_URL')

    # ---- 多系统切换 ----
    # 一套框架管理多个被测系统：在 config.ini 里为每个系统建一个 [system_名称] 段，
    # 填 url / username / password / pattern 等，用 --system 名称 一键切换。
    parser.add_argument('--system',
                        help='切换被测系统：读 config.ini 的 [system_名称] 段，'
                             '自动应用该系统的地址/账号/用例集。配合 --pattern 可再覆盖用例集')

    # ---- 多环境切换 ----
    # 「被测系统」和「运行环境」是两件事：
    #   --system erp          -> 换一个产品（账号、用例集都不同）
    #   --env prod            -> 同一个产品，换一套环境（地址不同、能不能写不同）
    # 两者都只是把配置翻译成环境变量，风格完全一致。
    parser.add_argument('--env',
                        help='切换运行环境：读 config.ini 的 [env_名称] 段（如 --env test），'
                             '自动应用该环境的地址/浏览器/无头模式/写入范围。'
                             '换环境只改配置，不改任何用例代码')

    # ---- 结果输出 ----
    parser.add_argument('--junit',
                        help='JUnit XML 输出路径；传 none 可关闭（默认取 [ci] junit_xml）')
    parser.add_argument('--mail', action='store_true', help='运行结束后发送邮件')
    parser.add_argument('--notify', action='store_true',
                        help='运行结束后把结果推送到群机器人（钉钉/企业微信，配置见 [notify]）')

    # ---- 环境自检 ----
    # 只体检、不跑用例：用于"Jenkins 节点第一次接入"和"本机突然跑不起来"两个场景。
    # 它不打开浏览器，所以哪怕环境坏得彻底也能跑出结论。
    parser.add_argument('--preflight', action='store_true',
                        help='只做运行环境自检（Python/selenium/浏览器/驱动/目录），不跑用例；'
                             '有致命问题时退出码 2')

    # ---- 并行执行 ----
    # 企业级规模化的关键：用例文件之间相互独立，可拆给多个进程同时跑。
    # 默认 1（串行，与历史行为完全一致）；传 2/4/8 即启用文件级并行。
    parser.add_argument('--workers', type=int, default=1,
                        help='并行进程数（按测试文件分片）。默认 1=串行；'
                             '传 2/4/8 启用多进程并行，用例多时显著提速')
    return parser.parse_args(argv)


def apply_runtime_overrides(args):
    """把命令行参数翻译成 UI_ 开头的环境变量，交给 config 的覆盖机制生效。

    为什么走环境变量而不是直接改 Config：
        工程里"配置从哪来"只有一条链路 ——
            环境变量  >  config.ini  >  代码默认值
        命令行只是这条链路的又一个入口。这样新增参数时不用维护第二套优先级逻辑，
        也保证了「本机加参数跑」和「Jenkins 上设环境变量跑」的结果完全一致。

    :return: 本次生效的覆盖项列表（用于日志展示）
    """
    applied = []

    # 无头开关：对应 UI_CI_HEADLESS -> config.ini [ci] headless
    if args.headless is not None:
        os.environ['UI_CI_HEADLESS'] = 'true' if args.headless else 'false'
        applied.append('headless=%s' % args.headless)

    # 浏览器与地址：对应 UI_ENVIRONMENT_BROWSER / UI_ENVIRONMENT_URL
    if args.browser:
        os.environ['UI_ENVIRONMENT_BROWSER'] = args.browser
        applied.append('browser=%s' % args.browser)
    if args.url:
        os.environ['UI_ENVIRONMENT_URL'] = args.url
        applied.append('url=%s' % args.url)
    # Selenium Grid Hub：对应 UI_CI_GRID_URL -> config.ini [ci] grid_url
    if getattr(args, 'grid', None):
        os.environ['UI_CI_GRID_URL'] = args.grid
        applied.append('grid=%s' % args.grid)

    if applied:
        log1.info('命令行覆盖配置：%s' % ', '.join(applied))
    return applied


#: profile 段（[system_名称] / [env_名称]）里可写的键 -> 对应的环境变量名。
#: 新增可覆盖项时只改这张表，两种 profile 自动同时支持。
#: 键名是配置里写的，值必须与 Common/config.py 的 UI_<段>_<键> 规则一致。
PROFILE_KEY_MAP = {
    'url': 'UI_ENVIRONMENT_URL',
    'browser': 'UI_ENVIRONMENT_BROWSER',
    'headless': 'UI_CI_HEADLESS',
    'username': 'UI_TESTCASE_LOGIN_USERNAME',
    'password': 'UI_TESTCASE_LOGIN_PASSWORD',
    # mode：readonly 只跑只读用例 / all 不限（见 Common/testcase_meta.py）
    'mode': 'UI_TESTCASE_MODE',
    # allow_write：是否允许跑写操作用例（见 Common/env_guard.py）
    'allow_write': 'UI_SAFETY_ALLOW_WRITE',
}

#: 不翻译成环境变量、而是返回给调用方的键：用例集匹配规则
PROFILE_PATTERN_KEY = 'pattern'

#: 敏感键：日志里打码，避免把密码写进 Jenkins 控制台（控制台是多人可见的）
PROFILE_SECRET_KEYS = ('password',)


def apply_profile(name, kind='system'):
    """按名称应用一个配置档：把 [<kind>_名称] 段翻译成环境变量覆盖。

    :param name: 档位名称，如 'test' / 'erp'
    :param kind: 'system'（被测系统）或 'env'（运行环境）
    :return: 该档位配置的 pattern（字符串或 None），供选定用例集
    :raise SystemExit: 段不存在时立即中止 —— 配置写错的代价必须远小于"跑错环境"

    为什么两个能力共用一个实现：
        --system 和 --env 本质上都是"选一组配置来覆盖默认值"，
        差别只在语义。共用后新增一个可覆盖键只需改 PROFILE_KEY_MAP。
    """
    if not name:
        return None
    from Common.config import Config
    section = '%s_%s' % (kind, name)
    if not Config.has_section(section):
        raise SystemExit(
            '未找到配置段 [%s]，请在 config.ini 中添加该段'
            '（可参考 config.ini.example 的示例）' % section)

    applied = []
    for key, env in PROFILE_KEY_MAP.items():
        value = Config.get(section, key, '')
        if value:
            os.environ[env] = value
            shown = '***' if key in PROFILE_SECRET_KEYS else value
            applied.append('%s=%s' % (key, shown))
    pattern = Config.get(section, PROFILE_PATTERN_KEY, '') or None
    if applied:
        log1.info('已应用配置档 [%s]：%s' % (section, ', '.join(applied)))
    return pattern


def apply_system(system_name):
    """按 --system 切换被测系统。

    保留这个函数名（而不是让调用方直接写 apply_profile(..., 'system')）：
    名称本身说明了用途，用例与单测里读起来更清楚。
    支持的键见 PROFILE_KEY_MAP：url / browser / headless / username /
    password / mode / allow_write，外加 pattern。

    :return: 该系统配置的 pattern（字符串或 None），供 run() 选用例集
    """
    return apply_profile(system_name, kind='system')


#: 被视为「生产/准生产」的环境档名。这些档位默认强制只读，写用例一律不许跑。
#: 之所以单独列名字（而不是只靠 url 关键字猜）：生产环境的地址未必带 prod 字样，
#: 用档位名做一层「代码级」硬保险，比纯靠正则更可靠。
PROD_TIER_NAMES = ('prod', 'production', 'online', 'release')


def enforce_prod_safety(env_name):
    """对生产/准生产档强制只读：写用例不允许在生产执行。

    实现为设置环境变量（走与命令行相同的覆盖链路）：
        UI_TESTCASE_MODE=readonly   —— 只收集只读用例（见 Common/testcase_meta.py）
        UI_SAFETY_ALLOW_WRITE=false —— 即便绕过了收集，环境守卫也会再次拦截（双保险）

    :param env_name: --env 指定的档位名（None/空表示无档位，不处理）
    :return: 是否触发了生产安全强制（True 表示已强制）
    """
    name = (env_name or '').strip().lower()
    if not name or name not in PROD_TIER_NAMES:
        return False
    os.environ['UI_TESTCASE_MODE'] = 'readonly'
    os.environ['UI_SAFETY_ALLOW_WRITE'] = 'false'
    log1.warning('生产安全守卫：[%s] 档已强制只读模式（仅跑只读用例、禁止写操作），'
                 '如需写操作请改用测试/预发环境' % env_name)
    return True


def print_conclusion(summary):
    """打印执行结论块，让流水线日志一眼就能看清结果。

    内容与退出码一致：通过就写 PASSED，不通过就写 FAILED 并给出退出码含义。
    """
    code = summary['exit_code']
    if code == runner.EXIT_OK:
        verdict = '通过（PASSED）'
    elif code == runner.EXIT_TEST_FAILED:
        verdict = '失败（FAILED）—— 有用例未通过，请查看报告与失败截图'
    else:
        verdict = '异常（ABORTED）—— 环境或配置问题，测试未真正执行'

    print('')
    print('====================== 执行结论 ======================')
    print('结果      : %s' % verdict)
    print('用例      : %d 条（失败 %d / 错误 %d / 跳过 %d）'
          % (summary['tests_run'], summary['failures'], summary['errors'], summary['skipped']))
    print('耗时      : %.1f 秒' % summary['duration'])
    # 被守卫拦下时把原因打出来：值班的人看日志就知道该改哪个配置，不用去翻代码
    if summary.get('reason'):
        print('原因      : %s' % summary['reason'])
    print('HTML 报告 : %s' % (summary['report'] or '未生成'))
    print('JUnit XML : %s' % (summary['junit'] or '未生成'))
    print('退出码    : %d' % code)
    print('=====================================================')
    print('')


# ---------------------------------------------------------------------------
# 只有「直接运行本文件」时才执行下面的代码。
# 被别的模块 import 时不会触发，避免误跑测试。
# ---------------------------------------------------------------------------
if __name__ == '__main__':
    args = parse_args()
    log1.info('===== UI 自动化测试开始 =====')

    # 1) 先应用配置档：--system 换产品，--env 换环境。
    #    顺序有讲究 —— 后应用的覆盖先应用的，而"环境"比"产品"更具体
    #    （同一个产品在不同环境地址不同），所以 env 放后面。
    system_pattern = apply_system(args.system)
    env_pattern = apply_profile(args.env, kind='env')
    # 生产档安全强制：prod 等档位一律只读，写用例在生产永不执行（双保险）
    enforce_prod_safety(args.env)
    # 用例集优先级：命令行 --pattern > 环境档 pattern > 系统档 pattern > 默认 test*.py
    pattern = args.pattern if args.pattern != 'test*.py' else (
        env_pattern or system_pattern or args.pattern)

    # 2) 命令行参数 -> 环境变量 -> config 覆盖（在 system 之后，保证命令行优先级最高）
    apply_runtime_overrides(args)

    # 2.5) 只做运行环境自检：体检完直接结束，不进 runner ——
    #      不收集用例、不开浏览器。用在"新节点接入先验环境"和"突然跑不起来先排环境"。
    if args.preflight:
        from Common import preflight
        from Common.config import Config
        findings = preflight.collect(
            browser=Config.get('environment', 'browser', 'chrome'),
            browser_binary=Config.get('ci', 'chrome_binary', ''),
        )
        print(preflight.format_report(findings))
        sys.exit(2 if preflight.has_error(findings) else 0)

    # 3) 执行测试。runner.run() 返回汇总字典，例如：
    # {'report': '...报告.html', 'junit': '...junit-results.xml',
    #  'tests_run': 6, 'failures': 0, 'errors': 0, 'exit_code': 0, ...}
    if args.workers and args.workers > 1:
        # 并行模式：按测试文件分片，多进程同时跑，结果合并成一份
        from Common.parallelRunner import run_parallel
        summary = run_parallel(
            workers=args.workers,
            pattern=pattern,
            title=args.title,
            tester=args.tester,
            description=args.description,
            suite_kind=args.suite,
            cases=args.cases,
            junit=args.junit,
        )
        # 并行模式下邮件/群通知仍在主进程统一触发（见下方）
        if args.mail:
            from Common.sentMail import sent_mail
            if summary.get('report'):
                sent_mail(summary['report'])
    else:
        summary = runner.run(
            pattern=pattern,
            title=args.title,
            report_name=args.filename,
            tester=args.tester,
            description=args.description,
            suite_kind=args.suite,
            cases=args.cases,
            junit=args.junit,
            send_mail=args.mail,
        )

    print_conclusion(summary)

    # 4) 可选：把结果推送到群机器人（钉钉/企业微信）
    if args.notify:
        from Common.notifier import notify as _notify
        _notify(summary)

    # 把退出码交给操作系统/Jenkins。
    sys.exit(summary['exit_code'])
