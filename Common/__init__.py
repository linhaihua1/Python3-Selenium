# -*- coding: utf-8 -*-
"""
==========================================================================
 Common 公共层（包标识文件）
==========================================================================

本文件的作用只有两个：

1. 把这个目录声明成 Python 包，这样 `from Common.xxx import yyy` 才能工作。
   —— 没有它，unittest 的 discover 也扫不到子目录，用例会一个都收集不到。

2. 说明本目录里每个文件的职责，方便按需跳读：

    basePage.py          测试基类。浏览器、元素定位、交互、上传、截图的唯一封装层
    elementPage.py       元素表。全工程所有 xpath/定位值都集中在这里
    runner.py            执行器。收集用例 -> [安全守卫] -> 执行 -> HTML 报告 + JUnit XML
    config.py            config.ini 读写封装（对外统一用 Config.get，
                         并支持 UI_<段>_<键> 环境变量覆盖 —— CI 上全靠它）
    configOverWriter.py  定制版 ConfigParser（保留键大小写 + 关闭 % 插值）
    log.py               日志。log1 对象，输出到 Logs/日期/ 与控制台
    dir_config.py        路径常量与 ensure_dir()
    sentMail.py          把报告作为附件发邮件（QQ 邮箱 SMTP）
    junitReport.py       JUnit XML 结果输出（给 Jenkins 等流水线解析）
    ci.py                CI 环境识别与构建元信息（任务名、构建号、分支）
    HTMLTestReportCN.py  中文版 HTML 报告模板（第三方，一般不需要改）
    testcase_meta.py     用例作用域标记：只读 / 写操作（安全守卫与分级执行的基础）
    env_guard.py         环境守卫：防止误连生产环境（地址、白名单、写用例）
    preflight.py         运行环境自检：Python/selenium/浏览器/驱动版本/目录可写
    failureCapture.py    失败自动取证：截图 + 页面源码（CI 上排查失败靠它）
    driverRegistry.py    浏览器实例登记处（失败取证要从这里拿 driver）
    locator_policy.py    元素定位规范检查（只读源码，可在 CI 当门禁用）
    dataDriver.py        数据驱动：从 CSV / JSON / Excel 读测试数据
    notifier.py          结果推送到群机器人（钉钉 / 企业微信 / 自定义 webhook）
    parallelRunner.py    多进程并行执行（按用例文件分片，结果合并成一份）
    getcwd.py            工程根目录探测（供日志与截图定位）

【新人阅读顺序建议】
    （本机开发 / 理解业务）
    工程根 run.py -> Common/runner.py -> TestSuites/testLogin.py
      -> PageObject/loginPage.py -> Common/elementPage.py -> Common/basePage.py
      -> Common/config.py -> Common/log.py
    写新用例前再看两个：Common/testcase_meta.py（给用例标作用域）、
      Common/env_guard.py（搞清什么情况下会被拦下）。
    其余文件按需再看。

    （对接 CI/CD 流水线时再补这两个）
    Common/ci.py -> Common/junitReport.py，配合根目录 Jenkinsfile 一起看
    完整说明见 docs/使用文档.md 与 docs/CI-CD接入指南.md。

【安全 / 稳定性相关的五个模块（企业级的关键，别在重构中丢掉）】
    testcase_meta.py + env_guard.py     跑之前拦住"误连生产"
    preflight.py                        跑之前说清"这台机器到底能不能跑"
    failureCapture.py + driverRegistry.py  跑挂了自动留下现场
==========================================================================
"""
