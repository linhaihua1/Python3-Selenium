# Python3-Selenium Web UI 自动化框架

基于 **unittest + Selenium 4 + PageObject** 的 Web UI 自动化测试工程，支持本机执行与
**Jenkins CI/CD 流水线自动冒烟**。

一次执行产出两份报告：**中文 HTML 报告**（给人看）+ **JUnit XML**（给流水线看）。

---

##★ 这是一套通用框架，附一个示例业务

| 部分 | 是什么 | 换系统时怎么办 |
|---|---|---|
| `Common/` | **框架层**，与被测系统无关 | 一行都不用改 |
| `PageObject/genericPage.py` | 配置驱动的通用页面对象 | 一行都不用改 |
| `PageObject/loginPage.py`<br>`Common/elementPage.py`<br>`TestSuites/*.py` | **示例业务**：某个融媒体生产系统的登录/素材库流程 | 整体替换 |

**框架层不知道被测的是什么系统**，它只提供执行、配置、日志、报告、浏览器操作这些能力。
所有业务差异都被挡在配置与薄薄一层页面对象里。

> **★ 测试数据全部动态配置 ★**
> 页面标题、查询关键字、表单字段值、报告名称等**没有任何代码默认值**
> （历史上曾在代码里留"兜底默认值"，换系统后忘了改配置，会拿旧系统的标题
> 去比对，报出完全看不出原因的失败）。
> 现在统一用 `Config.get_required()`：配置缺失就在**打开浏览器之前**报错中止，
> 并打印该去 `config.ini` 哪一段补哪个键。换系统**只改 config.ini**。

---

## 文档索引

| 文档 | 内容 | 什么时候看 |
|---|---|---|
| 本文 README | 快速上手、目录结构、常用命令 | **先看这个** |
| [docs/新手入门指南.md](docs/新手入门指南.md) | 零基础入门：建立认知、阅读顺序、跑起来、接 Jenkins | **第一次接触本工程** |
| [docs/实战-写你的第一条用例.md](docs/实战-写你的第一条用例.md) | 一次真实实操的全过程：想测什么 → 加元素 → 加动作 → 加用例 → 验证 | **想动手加第一条用例** |
| [docs/用例编写模板.md](docs/用例编写模板.md) | 可照抄的代码模板（串行业务流 / 独立用例 / 页面对象） | 写用例时随手翻 |
| [docs/使用文档.md](docs/使用文档.md) | 完整代码逻辑梳理、模块详解、扩展指南、排错、单元测试 | 要改用例 / 排查问题 |
| [docs/接入新系统指南.md](docs/接入新系统指南.md) | 把框架套到党政 / 财务 / ERP / 商城 / 数据中台等系统 | 要接入别的系统 |
| [docs/CI-CD接入指南.md](docs/CI-CD接入指南.md) | Jenkins 接入步骤、环境变量、凭据、容器化 | 要接流水线 |

---

## 一、快速开始

### 1.1 本机运行

```bash
# 1. 安装依赖（只需 selenium，driver 由 Selenium 4 自动管理）
pip install -r requirements.txt

# 2. 准备配置：复制模板后按注释修改
#    Windows:     copy config.ini.example config.ini
#    Linux/Mac:   cp config.ini.example config.ini
#    ⚠️ config.ini 含明文账号密码，已被 .gitignore 排除，不会入库

# 3. 先跑冒烟（只覆盖登录链路，不产生数据副作用）
python run.py --suite smoke

# 4. 环境通了再跑全量（⚠️ 会上传视频、提交报送单）
python run.py
```

跑完看四处产出：

| 产出 | 位置 | 用途 |
|---|---|---|
| HTML 报告 | `Report/` 下（文件名由 `[report] filename` 决定） | 浏览器打开，给人看 |
| JUnit XML | `Report/junit-results.xml` | 给流水线看 |
| 日志 | `Logs/日期/Error_Logs/xxx.log` | 失败原因，带模块名与行号 |
| 失败截图 | `img/日期/xxx.png` | 断言失败瞬间的页面 |

### 1.2 流水线运行

```bash
python run.py --suite smoke --headless --junit Report/junit-results.xml
```

退出码：`0` 全部通过 / `1` 有用例失败 / `2` 环境或配置问题。
Jenkins 直接用它判定构建成败。详见 [CI-CD 接入指南](docs/CI-CD接入指南.md)。

---

## 二、代码阅读顺序

按这个顺序读，每个文件都花不了几分钟：

| 顺序 | 文件 | 读它是为了搞清什么 |
|---|---|---|
| 0 | `config.ini.example` | 有哪些可配的东西 |
| 1 | `run.py` | 程序从哪进、参数怎么生效 |
| 2 | `Common/runner.py` | 测试怎么被收集、执行、出报告，退出码怎么来 |
| 3 | `TestSuites/testLogin.py` | **在测什么业务**（最重要的一个文件） |
| 4 | `PageObject/loginPage.py` | 每个业务动作怎么操作页面 |
| 5 | `Common/elementPage.py` | 元素定位值放在哪、哪个最脆弱 |
| 6 | `Common/basePage.py` | 浏览器操作怎么封装（唯一直接调 Selenium 的文件） |
| 7 | `Common/config.py` | 配置怎么读、环境变量怎么覆盖 |
| 8 | `Common/log.py` | 日志写去哪、怎么看 |

**对接流水线时再补这两个**：`Common/ci.py`（构建上下文）、`Common/junitReport.py`（JUnit 结果）。

其余文件（`dir_config.py` / `sentMail.py` / `configOverWriter.py` / `getcwd.py`）按需再看。

---

## 三、被测业务是什么

```
示例业务的链路（换成你自己的系统时只改 config.ini 里的三个标题）：

 门户(登录)  →  业务系统(工作台)  →  素材库  →  上传 / 查询 / 报送
```

6 条用例串行走完这条链：

| 用例 | 做什么 | 断言（期望值来自配置） | 副作用 |
|---|---|---|---|
| `test_1login` | 输入账号密码登录 | `[assert] title_login` | 无 |
| `test_2select_scxt` | 点系统入口并切到新标签页 | `[assert] title_workbench` | 无 |
| `test_3material` | 菜单进入素材库 | `[assert] title_material` | 无 |
| `test_4uplaodbutton` | 选文件 → 填表单 → 上传 → 确定 | 标题未跳走 | **上传文件** |
| `test_5keyword` | 关键字查询 → 重置 | 标题未跳走 | 无 |
| `test_6submitted` | 刷新 → 报送 → 选审核人 → 保存 | 标题未跳走 | **提交单据** |

> ★ 表单字段值、查询关键字同样来自 `[testcase]`，不在代码里。
> 前 3 条无副作用，组成**冒烟集**（`--suite smoke`）；全量含后 3 条，会写真实数据。

---

## 四、目录结构

```
├── Common/                     公共层
│   ├── basePage.py             基类：浏览器、定位、交互、上传、截图（唯一直接调 Selenium）
│   │├── 第七节跨系统通用能力    按文字/placeholder/属性定位、表格行定位、遮罩等待…
│   ├── elementPage.py          元素表：示例业务的 xpath（换系统时整体替换）
│   ├── runner.py               执行器：收集用例 → [三道闸门] → 执行 → HTML 报告 + JUnit XML
│   ├── config.py               config.ini 读写 + UI_* 环境变量覆盖
│   ├── configOverWriter.py     定制 ConfigParser（保留键大小写 + 关闭 % 插值）
│   ├── log.py                  日志：All_Logs 全量 + Error_Logs 仅错误 + 控制台
│   ├── dir_config.py           路径常量 + ensure_dir()
│   ├── sentMail.py             报告邮件发送（QQ 邮箱 SMTP）
│   ├── junitReport.py          JUnit XML 输出（给 Jenkins 解析）
│   ├── ci.py                   CI 环境识别与构建元信息
│   ├── HTMLTestReportCN.py     中文版 HTML 报告模板（第三方）
│   ├── testcase_meta.py        ★ 用例作用域标记（只读 / 写操作），闸门①的依据
│   ├── env_guard.py            ★ 环境守卫：拦住"误连生产"，闸门②
│   ├── preflight.py            ★ 运行环境自检：浏览器 / 驱动版本 / 目录可写，闸门③
│   ├── failureCapture.py       ★ 失败自动取证：截图 + 页面源码
│   ├── driverRegistry.py       浏览器实例登记处（取证用）
│   ├── locator_policy.py       元素定位规范检查（可在 CI 当门禁）
│   ├── dataGovernance.py       测试数据治理：造数-清数、并行下唯一数据标记
│   ├── dataDriver.py           数据驱动：CSV / JSON / Excel
│   ├── dependency.py           用例依赖声明 + 失败级联跳过
│   ├── parallelRunner.py       多进程并行执行（按文件分片）
│   ├── notifier.py             结果推送到钉钉 / 企业微信
│   └── getcwd.py               返回工程根目录
├── PageObject/                 页面对象层
│   ├── loginPage.py           ★示例业务：门户登录 + 素材库操作（换系统时替换）
│   └── genericPage.py          配置驱动的通用页面对象（接新系统用，不用改）
├── TestSuites/                 用例层（UI 用例，会被 run.py 执行）★示例业务
│   ├── testLogin.py            主用例集（6 条串行业务用例）
│   └── testMaterialCheck.py    只读校验样板（3 条，标了 readonly）
├── tests/                      框架单元测试（不开浏览器、零业务副作用）
│   ├── helpers.py              测试基座：假 driver、临时目录隔离、沙盒
│   ├── samples.py              样例用例类（故意失败/出错等，不参与收集）
│   ├── run_unit_tests.py       一键入口：python tests/run_unit_tests.py
│   └── test_*.py               各模块的测试（含测试基座自检）
├── docs/                       使用文档 + CI/CD 接入指南 + 企业级适用性评估
├── Logs/  img/  Report/        运行产物（已 gitignore）
│     └── Report/artifacts/日期/  失败自动取证：截图 + 页面源码
├── config.ini                  本地配置（含账号密码，已 gitignore）
├── config.ini.example          配置模板（入库）
├── run.py                      唯一入口（参数解析 + 配置档翻译）
├── Jenkinsfile                 Jenkins 声明式流水线
├── Dockerfile                  容器化运行环境（Chromium + 中文字体）
├── requirements.txt            运行依赖（只需要 selenium）
├── requirements-dev.txt        开发依赖（flake8，跑测试不需要）
├── .flake8                     代码规范规则（CI 门禁用）
└── .gitignore / .dockerignore  忽略规则
```

---

## 五、分层规则（写新代码时请遵守）

| 层 | 允许做的事 | 禁止做的事 |
|---|---|---|
| `TestSuites/` 用例层 | 调页面对象方法、写断言 | 不写 xpath、不直接点元素 |
| `PageObject/` 页面对象层 | 一个方法 = 一个业务动作 | 不写断言、不出现 xpath 字符串 |
| `Common/basePage.py` | 封装浏览器与元素操作 | 不掺业务逻辑 |
| `Common/elementPage.py` | 只放元素定位值 | 不放业务代码 |

一句话：**用例层管断言，页面对象管动作，基类管操作，元素表管定位。**

---

## 六、运行方式

```bash
# ---- 用例选择 ----
python run.py                                      # 全量
python run.py --suite smoke                        # 冒烟（前 3 条，不写数据）
python run.py --cases test_1login,test_2select_scxt # 自定义过滤（优先级高于 --suite）
python run.py --pattern 'test_Login*.py'           # 按文件名过滤

# ---- 运行环境 ----
python run.py --no-headless                        # 有界面跑，方便盯流程
python run.py --headless                           # 无头跑，与流水线一致
python run.py --url http://测试环境/sso-portal/#/?redirect=/launch
python run.py --browser firefox

# ---- 报告 ----
python run.py --title 冒烟测试 --filename smoke.html
python run.py --junit none                         # 不生成 JUnit XML
python run.py --mail                               # 跑完发邮件
python run.py --notify                             # 跑完推送到钉钉/企业微信群
python run.py --system erp                         # 切换到 config.ini 的 [system_erp] 系统
python run.py --env test                           # ★ 切到 config.ini 的 [env_test] 环境档
python run.py --workers 4                          # 4 进程并行执行（按文件分片），用例多时提速

# ---- 排查环境问题（不跑用例，不打开浏览器）----
python run.py --preflight                          # 体检这台机器能不能跑 UI 自动化
python -m Common.preflight --quiet                  # 等价写法，只列出有问题的项

# ---- 其他 ----
python -m Common.sentMail                          # 单独验证发信
python -m Common.ci                                # 查看当前 CI 上下文
python -m Common.locator_policy --issues           # 看元素表里哪些定位很脆弱
python run.py --help                               # 全部参数
```

**参数优先级**：`命令行 / 环境变量` > `config.ini` > `代码默认值`。

> **被测系统 vs 运行环境，别搞混**
> - `--system erp` 换的是**产品**（账号、用例集都不同）→ 读 `[system_erp]`
> - `--env test` 换的是**环境**（同一个产品，地址/能不能写不同）→ 读 `[env_test]`
>
> 两者都只是把配置翻译成 `UI_*` 环境变量，风格完全一致；换环境不需要动任何用例代码。

---

## 七、配置说明（config.ini）

完整配置项说明见 [使用文档 5.3](docs/使用文档.md#53-配置项一览configini)。常用几项：

| 段 | 键 | 说明 |
|---|---|---|
| `[environment]` | `url` / `browser` | 被测地址；浏览器 chrome / firefox / edge |
| `[testcase]` | `login_username` / `login_password` | 登录账号 |
| `[testcase]` | `upload_file` | 上传文件绝对路径（必须真实存在） |
| `[testcase]` | `upload_mode` | `send_keys`（默认，推荐）/ `autoit` |
| `[report]` | `title` / `filename` / `tester` / `description` | 报告元信息 |
| `[ci]` | `headless` | 无头开关（**流水线必须 true**） |
| `[ci]` | `element_timeout` / `implicit_wait` | 等待时长，CI 慢时可调大 |
| `[ci]` | `smoke_cases` | 冒烟用例关键字 |
| `[ci]` | `junit_xml` | JUnit XML 输出路径 |
| `[sender]` / `[addressed]` | — | 邮件发件人（含 SMTP 授权码）、收件人 |

### 环境变量覆盖（CI 的关键机制）

任意配置项都能被同名环境变量覆盖，规则 `UI_ + 段名 + _ + 键名`（全大写）：

```bash
set UI_ENVIRONMENT_URL=http://测试环境/portal      # 覆盖 [environment] url
set UI_CI_HEADLESS=true                            # 开启无头
set UI_TESTCASE_LOGIN_PASSWORD=xxx                 # 覆盖密码（CI 上用凭据注入）
```

日志里会出现 `配置 [environment] url 被环境变量 UI_ENVIRONMENT_URL 覆盖`。
要整体关闭该机制：`UI_ENV_OVERRIDE=false`。

---

## 八、CI/CD 接入

工程已为流水线做好适配，接入只需配置 Jenkins：

| 已具备的能力 | 实现位置 |
|---|---|
| 标准退出码（0/1/2） | `run.py` → `sys.exit(summary['exit_code'])` |
| JUnit XML 结果（用例明细 + 趋势图） | `Common/junitReport.py` |
| 无头模式（节点无桌面也能跑） | `[ci] headless` / `UI_CI_HEADLESS` |
| 冒烟子集（不写数据，可每次构建跑） | `--suite smoke` / `[ci] smoke_cases` |
| 凭据注入（密码不落仓库） | `UI_TESTCASE_LOGIN_*` 环境变量覆盖 |
| 构建上下文写进报告 | `Common/ci.py` |
| 流水线定义与容器镜像 | `Jenkinsfile` / `Dockerfile` |
| 操作自动重试（降偶发失败） | `BasePage.retry/safe_click` / `[ci] retry_times` |
| 数据驱动用例（CSV/JSON/Excel） | `Common/dataDriver.py` |
| 多系统一键切换 | `--system` / `[system_名称]` 段 |
| 群机器人结果通知 | `Common/notifier.py` / `--notify` |

**5 步接入**：

1. Jenkins 新建 Pipeline 任务，脚本路径填 `Jenkinsfile`
2. 创建两个 Secret text 凭据：`ui-test-login-username`、`ui-test-login-password`
3. 首次执行选 `TEST_SUITE=smoke`、填 `TARGET_URL`（**测试环境**）
4. 确认构建页面出现「测试结果」与 HTML 报告链接
5. 在上游构建任务里加 Post-build Action 触发本任务

详细步骤、参数说明、容器化方案与排查表见 **[docs/CI-CD接入指南.md](docs/CI-CD接入指南.md)**。

---

## 九、框架单元测试

`tests/` 是**框架自身的单元测试**：不开浏览器、不联网、几十秒跑完、零业务副作用。
改过 `Common/` 或 `PageObject/` 里的代码后，先跑它，再跑 UI 用例 ——
这样能把"框架坏了"和"页面改版了"两类问题分开。

```bash
python tests/run_unit_tests.py                          # 全部（推荐）
python tests/run_unit_tests.py tests.test_config         # 只跑某个模块（几秒）
python tests/run_unit_tests.py --junit Report/unit-tests.xml   # 流水线用
```

- 退出码与 `run.py` 一致：`0` 通过、`1` 有失败
- 当前覆盖 **350 项 / 15 个模块**：配置、日志、CI 适配、元素表、基类、执行器、JUnit 报告、
  报告模板、邮件、页面对象、用例层结构、命令行入口、测试基座自检
- 全程 26 秒左右，跑完不留痕：不写工程 `Logs/`、不在系统临时目录留垃圾目录
  （日志走 `UI_LOG_DIR` 重定向，临时目录登记到 `atexit` 统一回收）
- 流水线里的 `框架单元测试` stage 已经接好（见 `Jenkinsfile`），比 UI 用例更早发现问题

常用开关：

| 变量 | 作用 |
|---|---|
| `UT_SHOW_LOG=1` | 打开工程日志，排查单测失败原因 |
| `UT_KEEP_LOG=1` | 日志留在工程 `Logs/` 下（会污染工作区，仅需留证时用） |

写新测试的三条铁律与两个坑（样例用例类不能被 discover 收走、`load_tests` 白名单）
见 **[docs/使用文档.md](docs/使用文档.md) 第八章**。

---

## 十、新人最容易踩的坑

1. **用例有严格顺序**：`test_1login` → `test_6submitted` 是一条业务流，
   方法名的数字前缀就是用来固定顺序的。**不要改方法名**，也**不能只跑中间某一条**。
2. **切换标签页**：点「发布系统」会新开标签页，不调 `switch_other_window()`
   后续元素全都定位不到 —— 这是最常见的"莫名失败"原因。
3. **元素定位是绝对 xpath**：`elementPage.py` 里很多 `/html/body/div[4]/...`，
   前端多套一层 div 就失效。改版后优先检查 `submission`、`first_trial`、
   `person_of_first_instance` 三条。
4. **`get_element()` 找不到元素返回 `None` 而不抛异常**，调用方必须判空，
   否则会得到 `AttributeError: 'NoneType' object has no attribute 'click'`。
5. **上传文件必须存在**：`upload_file` 配的路径不存在时，上传用例会以
   `FileNotFoundError` 失败（冒烟集不含该用例）。
6. **别用 print 打日志**：控制台看得到但文件里没有，事后无法回溯。统一用 `log1`。
7. **改用户例方法名要同步改 `[ci] smoke_cases`**，否则冒烟集会失配（日志会打印「命中 N/M 条」）。
8. **生产环境警告**：`config.ini` 默认指向生产环境。跑全量前务必确认，
   流水线请用 `UI_ENVIRONMENT_URL` 指向测试环境。
   ★ 现在有**环境守卫**兜底：地址是占位符、不在白名单、或"疑似生产 + 本次含写用例"时，
   `run.py` 会在**打开浏览器之前**直接以退出码 2 中止，并打印一行人话原因。
   配置在 `config.ini -> [safety]`，实现见 `Common/env_guard.py`。
9. **「一条用例都没收集到」先看日志，别急着改代码**。四条硬性约束：
   `TestSuites/__init__.py` 不能删；文件名必须以 `test` 开头；文件名只能是
   字母/数字/下划线（`test-login.py` 会被 discover **静默跳过**）；
   子目录同样需要 `__init__.py`，否则整棵子树被跳过。
   ⚠️ Windows 的文件名匹配不区分大小写、Linux 区分，
   所以 `TestLogin.py` 这类命名会出现"**本机能跑、Jenkins 收集不到**"。
   现在日志会直接给出中文原因与目录体检结果，完整对照表见
   [使用文档 7.1](docs/使用文档.md#71-一条用例都没收集到深度排查)。
10. **中文输出不要依赖终端编码**：入口已把 stdout/stderr 强制为 UTF-8，
   Linux 容器里 locale 为 `C` 时也不会因 `print` 中文而崩。
11. **★ 浏览器起不来、报 `session not created`、卡很久才抛一屏堆栈** ——
   九成是环境问题，不是用例问题。先跑 `python run.py --preflight`。
   典型场景：`PATH` 上有个**旧版 chromedriver**（例如 114），
   Selenium Manager 下好的匹配版会被它覆盖，于是启动浏览器直接失败。
   自检 1 秒就能指名"把哪个文件改名或删掉"。
   `run.py` 每次执行前也会自动自检一次，所以这类问题不会再以"用例失败"的面貌出现。
12. **写用例时别忘了标作用域**。没标的用例一律算**写用例**（刻意的失败安全设计）：
   只读用例请加 `scope = 'readonly'` 类属性或 `@readonly` 装饰器，
   这样 `[testcase] mode = readonly` 时它们才会被保留。
   详见 [使用文档](docs/使用文档.md) 与 `Common/testcase_meta.py`。

---

## 十一、已知限制与改进方向

- **用例之间的数据治理**：`Common/dataGovernance.py` 提供 `IsolatedTestCase`
  （造数-清数 + 并行下唯一数据标记），新写写操作用例建议继承它；
  已有的 6 条串行业务流尚未改造，任一步失败仍会导致后续用例连续失败 ——
  排错时优先修**最早失败**的那条。
- 断言以页面标题为主，业务数据（上传成功、查询命中数、报送状态）未被断言；
  `BasePage.get_text()` / `get_value()` 已提供能力，可逐步补强。
- 元素定位仍以 xpath 为主：当前实测 21 条里 13 条偏脆弱（含 2 条绝对路径）。
  已建立**防劣化门禁**（`tests/test_locator_policy.py` 把脆弱度冻结成基线，
  新增脆弱定位会让测试红），并可在 CI 用
  `python -m Common.locator_policy --fail-over 13` 卡口。建议逐条替换为
  id / 可见文字 / 属性定位。
- 因用例强串行依赖，**不适合**做单用例失败重试；`Common/dependency.py`
  提供了失败级联跳过（前置挂了后继直接 skip，不再连坐报错），
  彻底解耦后即可引入失败重试。
- `config.ini` 本地为明文，建议本机也不要放生产账号；CI 上统一用 Jenkins 凭据。
- 历史遗留文件已清理：`Common/HTMLTestRunnerNew.py`、`Common/configTest.py`、
  `Common/logTest.py`、`PageObject/homePage.py`、`TestSuites/testHome.py`。
