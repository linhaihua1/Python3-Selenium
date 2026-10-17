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
| `Common/elementPage.py` | 元素表：定位值的**默认值**（可被 `config.ini [elements]` 逐条覆盖） | 优先在 `[elements]` 段覆盖，零代码 |
| `PageObject/loginPage.py`<br>`TestSuites/*.py` | **示例业务**：某个融媒体生产系统的登录/素材库流程 | 整体替换 |

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
# 1. 安装依赖（推荐：一次性装齐运行+开发工具；driver 由 Selenium 4 自动管理）
pip install -e ".[dev]"
#    只跑测试不写代码的话，装最小集即可：
#    pip install -r requirements.lock     # 用锁定版本，可精确复现

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
│   ├── elementPage.py          元素表：定位默认值 + [elements] 配置覆盖层（接新系统只改配置）
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
│   ├── apiClient.py            ★接口层客户端（测试金字塔底层）
│   ├── failureClassifier.py    ★失败自动归因（7 类 + 处理建议）
│   ├── trend.py                ★通过率趋势与劣化告警
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
├── verify_enterprise.py        ★ 企业级功能验收矩阵（20 项端到端，发布前跑）
├── conftest.py                 pytest 适配层（第二执行引擎，unittest 用例原生兼容）
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
| `Common/elementPage.py` | 只放元素定位值 | 不放业务代码；定位值应优先用配置覆盖 |
| `Common/apiClient.py` | 封装 HTTP 细节 | 不做断言；`login_path`/`token_field` 不留默认值 |

一句话：**用例层管断言，页面对象管动作，基类管操作，元素表管定位。**

---

## 五之二、企业级约定（这几条是"红线"，都有单测把守）

### 1. 断言必须落在**业务结果**上

```python
# ✗ 只断言标题 —— 上传失败、报送被拒、接口 500 都会判绿（"假绿"）
self.check_title('上传视频', self.title_material)

# ✓ 断言业务结果 —— 上传后列表行数真的 +1
ok, count = self.login_page.wait_material_count(at_least=before + 1, timeout=30)
self.assertTrue(ok, '上传后行数未增加：%d -> %d' % (before, count))
```

自问一句：**如果这个功能坏了，我的断言会不会红？** 不会就说明断言不够。

### 2. 用例必须能**单独运行**

每条用例开头调 `ensure_login()` / `ensure_workbench()` / `ensure_material_page()`
补前置（幂等，顺序跑时零开销）。这样 `--cases test_5keyword` 才能单独跑。

### 3. 用**条件等待**，不要 `my_sleep`

`wait_title` / `wait_text` / `wait_any_text` / `wait_loading_gone` /
`wait_material_count` / `wait_status_changed` —— 对了就立刻返回，更快也更稳。
（门禁会扫描用例层，发现 `my_sleep` 调用直接让单测变红。）

### 4. 稳定性机制**默认生效**，不用手动调

`click()` / `type()` 已内置重试（瞬时错误重试、确定性错误立即失败）。
`retry()` / `safe_click()` 仍保留，但新代码不需要用。

### 5. 代码里不许有**业务数据**

页面标题、查询关键字、表单字段值、**元素定位**一律来自 `config.ini`，
用 `Config.get_required()` / `get_form_field()`（缺失即报错）。
理由：留兜底默认值的话，换系统忘了改配置会拿旧系统的标题去比对，
报出看不出原因的失败。门禁：`tests/test_no_hardcoded_data.py`（规则级 AST 扫描）

**元素定位也能配置化**（换系统零代码）——在 `config.ini` 加一段：

```ini
[elements]
Username    = xpath://input[@name='userName']
Sign_button = id:login-btn
```

取值优先级：`[elements]` > `elementPage.py` 里的默认值。
没配的元素继续用默认值，所以不必把整张表抄一遍。

### 5.1 门禁必须**规则级**，不能靠关键词枚举

历史教训：业务数据门禁曾经写成 `BANNED_LITERALS = ('统一门户', '云媒资', ...)`
这种枚举式黑名单 —— 它只认这 6 个词，换套业务名（"教务管理系统"）硬编码照样混得进来。
**这是最危险的一种失效：看起来在管，实际不管，还给出虚假的安全感。**

现在改为 AST 规则扫描：用 `ast` 把源码切成注释/文档字符串/可执行代码，
只在可执行代码里找字符串字面量，再按"是否参与与被测系统比对"判定。
换任何业务名都照样生效。

判定要点（**首参数与末参数放行、只拦中间位置**）：

```python
self.assertEqual(actual, '旧系统标题', '标题不符')
                          ↑序号1：期望值 = 业务数据 -> 拦
                                       ↑序号2：失败消息 = 诊断文案 -> 放
self.check_title('上传视频', expected)   # 首参数是用例名 -> 放
log1.info('执行：%s' % x)                # 单参数 -> 放
```

> 门禁本身有**反向断言**（`test_门禁自身真的能检出违规`）：
> 拿一段真实违规代码喂给扫描器必须报错，拿合规代码必须放行。
> 否则就会出现"规则写错了也照样绿"的假门禁。

### 6. 断言失败要能**自动归因**

`Common/failureClassifier.py` 把失败分成 7 类
（定位/环境/配置/业务/数据/超时/未归类），每类给出"下一步找谁"。
控制台上会直接打印归因摘要 —— 不必逐条读堆栈。

---

## 五之三、质量门禁（本地 + CI 双保险）

```bash
python -m flake8                                    # 代码规范（0 输出 = 通过）
python tests/run_unit_tests.py                      # 框架单测 756 项 / 13 秒
python -m coverage run --source=Common,PageObject -m tests.run_unit_tests \
    && python -m coverage report                   # 覆盖率（阈值 82%）
python -m Common.locator_policy --fail-over 10      # 定位门禁（绝对路径必须 0）
python -m unittest tests.test_no_hardcoded_data      # ★ 业务数据硬编码门禁（AST 规则级）
python -m mypy Common/                              # 类型检查（渐进式）

pre-commit install                                  # 装一次，之后每次 commit 自动跑
```

| 门禁 | 阈值 | 只能…… |
|---|---|---|
| 覆盖率 | 82%（实测 87%） | 只升不降 |
| 脆弱定位 | 10 条（实测 10） | 只降不升 |
| 绝对路径 xpath | **0 条** | 红线，一条都不许有 |
| 业务数据硬编码 | 0 处（**AST 规则级扫描**，换任何业务词都生效） | 红线 |
| flake8 | 0 问题 | **缺失即失败**（不再静默跳过） |

> 阈值统一记在 `pyproject.toml` 与 `Jenkinsfile`，
> 并有单测校验"两处一致"（`tests/test_engineering_standards.py`）——
> 避免出现"本地过、CI 挂"这种最让人困惑的状态。

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

# ---- 企业级功能验收（发布前 / 大改后跑一次）----
python verify_enterprise.py                        # 20 项端到端矩阵（沙盒：不开浏览器、不连外网）
                                                   # 逐项验证双报告/退出码/三道闸门/级联跳过/取证/趋势/
                                                   # 并行/数据驱动/[elements]/归因/preflight 等，输出 PASS/FAIL

# ---- 质量门禁（本地自检，与 CI 同一套）----
python -m flake8                                    # 代码规范
python -m mypy Common/                              # 类型检查
python -m coverage run --source=Common,PageObject -m tests.run_unit_tests
python -m coverage report                           # 覆盖率（阈值 82%）

# ---- pytest 引擎（第二执行引擎，unittest 用例原生兼容）----
#   ★ 与 run.py 互补：run.py = CI 完整报告链路（双报告+归因+趋势+三道闸门+preflight）；
#     pytest = 开发期快跑（-k 单条重跑、--collect-only 快速验证、断点调试更顺手）。
#     配置在 pyproject.toml [tool.pytest.ini_options]；适配层在根 conftest.py。
pytest tests/                                       # 框架 756 项单测（不开浏览器）
pytest TestSuites/ --collect-only -q                # 只看收集结果（不执行）
pytest TestSuites/ --suite smoke --collect-only -q  # 冒烟集（对齐 run.py --suite smoke）
pytest TestSuites/ -k test_1login                   # 单条重跑（pytest 的强项）
pytest TestSuites/ --junitxml Report/junit-pytest.xml \
       --html Report/pytest.html --self-contained-html   # 标准双报告
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
| `[testcase]` | `login_username` / `login_password` | 登录账号（**必填**） |
| `[testcase]` | `upload_file` | 上传文件绝对路径（必须真实存在） |
| `[testcase]` | `upload_mode` | `send_keys`（默认，推荐）/ `autoit` |
| `[assert]` | `title_login` / `title_workbench` / `title_material` | 断言期望标题（**必填**，换系统只改这里） |
| `[system]` | `username_placeholder` 等 | 登录页文案特征（**必填**，`GenericPage` 用） |
| `[elements]` | 与元素表属性同名 | ★ 元素定位覆盖：`id:xxx` / `css:xxx` / `xpath://xxx`，接新系统零代码 |
| `[api]` | `base_url` / `login_path` / `token_field` | 接口层（base_url 有值时后两项必填） |
| `[safety]` | `guard` / `url_must_match` / `allow_write` | 环境守卫：拦住误连生产 |
| `[env_名称]` / `[system_名称]` | — | 多环境档（`--env`）/ 多系统段（`--system`） |
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
| 流水线定义与容器镜像 | `Jenkinsfile`（9 个 stage：8 道门禁 + 冒烟）/ `Dockerfile` |
| 操作自动重试（降偶发失败） | `BasePage.retry/safe_click` / `[ci] retry_times` |
| 数据驱动用例（CSV/JSON/Excel） | `Common/dataDriver.py` |
| 多系统一键切换 | `--system` / `[system_名称]` 段 |
| 元素定位配置化（接新系统零代码） | `config.ini [elements]` 覆盖元素表 |
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
- 当前覆盖 **756 项 / 33 个模块**：配置、必填配置门禁、**业务数据 AST 门禁**、
  日志、CI 适配、元素表、基类、执行器、JUnit 报告、报告模板、邮件、页面对象、
  用例层结构、命令行入口、测试基座自检、**依赖级联跳过集成**等
- 全程 13 秒左右，跑完不留痕：不写工程 `Logs/`、不在系统临时目录留垃圾目录
  （日志走 `UI_LOG_DIR` 重定向，临时目录登记到 `atexit` 统一回收）
- 流水线里的 `框架单元测试` stage 已经接好（见 `Jenkinsfile`），比 UI 用例更早发现问题
- ★ **单测全绿 ≠ 功能可用**：模块间集成点可能无人看守（`@depends_on` 主链路失效 bug
  就是 755 项全绿时漏掉的）。发布前/大改后请跑 `python verify_enterprise.py`
  （20 项端到端验收矩阵，详见 docs/使用文档.md 8.8）

> 数字别照着抄 —— 用 `python tests/run_unit_tests.py` 现跑一次为准。
> 历史上这里写的是「350 项」，早已过时（说明手工维护的数字必然漂移）。

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
- ~~断言以页面标题为主~~ **已修复（2026-10-11）**：每条用例都有业务结果断言
  （上传断言行数 +1、报送断言状态变化、查询断言列表渲染）+ console 报错拦截。
  ⚠️ 这些断言依赖 `elementPage` 里新增的观察点定位，**需在真实环境验证一轮**。
- 元素定位仍以 xpath 为主：当前实测 21 条里 13 条偏脆弱（含 2 条绝对路径）。
  已建立**防劣化门禁**（`tests/test_locator_policy.py` 把脆弱度冻结成基线，
  新增脆弱定位会让测试红），并可在 CI 用
  `python -m Common.locator_policy --fail-over 13` 卡口。建议逐条替换为
  id / 可见文字 / 属性定位。
- 因用例强串行依赖，**不适合**做单用例失败重试；`Common/dependency.py`
  提供了失败级联跳过（前置挂了后继直接 skip，不再连坐报错；
  ★ 2026-10-17 功能验收矩阵抓出并修复了该机制在主链路的集成缺陷，
  现有集成防回退单测看守），6 条示例用例尚未声明 `@depends_on`，
  彻底解耦后即可引入失败重试。
- **单测全绿 ≠ 功能可用**：模块间的集成点可能无人看守（见上一条的教训）。
  发布前/大改后请跑 `python verify_enterprise.py`（20 项端到端验收矩阵）。
- `config.ini` 本地为明文，建议本机也不要放生产账号；CI 上统一用 Jenkins 凭据。
- 历史遗留文件已清理：`Common/HTMLTestRunnerNew.py`、`Common/configTest.py`、
  `Common/logTest.py`、`PageObject/homePage.py`、`TestSuites/testHome.py`。
