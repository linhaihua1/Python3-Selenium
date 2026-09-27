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
    runner.py            执行器。收集用例 -> 执行 -> 生成 HTML 报告 + JUnit XML
    config.py            config.ini 读写封装（对外统一用 Config.get，
                         并支持 UI_<段>_<键> 环境变量覆盖 —— CI 上全靠它）
    configOverWriter.py  定制版 ConfigParser（保留键大小写 + 关闭 % 插值）
    log.py               日志。log1 对象，输出到 Logs/日期/ 与控制台
    dir_config.py        路径常量与 ensure_dir()
    sentMail.py          把报告作为附件发邮件（QQ 邮箱 SMTP）
    junitReport.py       JUnit XML 结果输出（给 Jenkins 等流水线解析）
    ci.py                CI 环境识别与构建元信息（任务名、构建号、分支）
    HTMLTestReportCN.py  中文版 HTML 报告模板（第三方，一般不需要改）
    HTMLTestRunnerNew.py 英文版旧报告模板（第三方遗留，当前未被引用）
    configTest.py        手工验证脚本：测 Config 的读写，可跳过
    logTest.py           手工验证脚本：测日志输出，可跳过

【新人阅读顺序建议】
    （本机开发 / 理解业务）
    工程根 run.py -> Common/runner.py -> TestSuites/testLogin.py
      -> PageObject/loginPage.py -> Common/elementPage.py -> Common/basePage.py
      -> Common/config.py -> Common/log.py
    其余文件（configOverWriter / dir_config / sentMail / 两个脚本）按需再看。

    （对接 CI/CD 流水线时再补这两个）
    Common/ci.py -> Common/junitReport.py，配合根目录 Jenkinsfile 一起看
    完整说明见 docs/使用文档.md 与 docs/CI-CD接入指南.md。
==========================================================================
"""
