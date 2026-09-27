---
name: web-ui-test-framework
description: 将基于 unittest + Selenium + PageObject 的 UI 自动化测试框架通用化，使其能接入任意主流 Web 系统。在用户要求让框架适配多系统、去掉业务硬编码、接入新 Web 系统、或对该框架做工程化改造时使用。不适用于只写单条用例或纯文档任务。
---

# Web UI 自动化框架通用化

把某个具体业务系统的 UI 自动化框架，改造成能接入党政 / 财务 / ERP / 商城 / 数据中台等任意主流 Web 系统的通用框架。核心原则：**框架层（执行/配置/报告/浏览器操作）完全通用，系统差异只存在于配置和薄薄一层页面对象。**

## 触发后的标准流程

### 1. 建立基线（先确认现状再动手）
- 跑全量单元测试记录基线：`python tests/run_unit_tests.py`，记下用例总数（本框架约定必须 0 失败 0 错误）。
- 读核心文件确认与具体系统的耦合点：`Common/basePage.py`、`Common/runner.py`、`Common/config.py`、`PageObject/*`、`TestSuites/*`。
- 判断：执行器/配置/日志/报告层通常已与业务解耦，耦合一般集中在 elementPage、xxxPage、testXxx 这一层。

### 2. 为 BasePage 补齐「跨系统通用能力」
主流 Web 系统的 UI 模式高度相似，把这些沉淀进基类，新系统直接复用。纯新增方法，不改任何现有逻辑：
- 按可见文本定位/点击（`get_element_by_text` / `click_by_text`）——按钮、菜单、tab、链接，**首选，抗改版**
- 按 placeholder 输入（`type_by_placeholder`）——90% 表单通用
- 原生下拉选择（`select_option`）
- 等待加载遮罩消失（`wait_loading_gone`）——点查询/保存后必等，防偶发失败
- 表格按单元格文本定位行（`find_row_by_cell_text` / `get_table_rows`）
- 悬停展开菜单（`hover`）、滚动到元素（`scroll_to`）

实现约定（与现有方法保持一致）：找不到元素返回 `None` / 记日志、点击失败自动 JS 降级、不随意抛异常；xpath 里文本要做单引号转义（concat 拼接）。

### 3. 引入「系统适配」机制
- 新增系统无关的通用页面对象（如 `PageObject/genericPage.py`），提供配置驱动的 `login()/open_menu()/fill_form()/find_record()`，让标准登录的系统**零代码**跑通。
- 配置新增 `[system]` 段：用户名/密码框 placeholder、登录按钮文字、登录成功标识文字、元素超时。换系统只改配置不改代码，并支持环境变量覆盖（`UI_段_键` 全大写）。
- 复杂系统（验证码/SSO/特有页面）走方式二：新建 `PageObject/xxxPage.py` 继承 BasePage，复用通用能力。

### 4. 补单元测试 + 全量回归
- 用 `tests/helpers.py` 里的 `FakeDriver`/`FakeElement`/`patch_config` 为新方法写单测（不启动浏览器）。
  - 注意坑：`FakeDriver(element=None)` 会被替换成 `FakeElement()`，模拟"找不到"要用 `find_error=NoSuchElementException(...)`。
- 跑 `python tests/run_unit_tests.py`，确认新增用例通过且原有测试零回归。

### 5. 文档与提交
- 在 `docs/` 补「接入新系统指南」：两种接入方式、通用能力清单、检查清单。
- 提交前确认 `config.ini` 被 `.gitignore` 排除（含明文账号密码，不入库）。
- 本仓库是 git 仓库，改动后必须 commit。

## 不要做
- 不要改动执行器/配置/报告层的现有逻辑（它们已通用）。
- 不要把账号密码、生产地址写进代码或入库文件。
- 不要在未跑全量回归前宣称完成。
