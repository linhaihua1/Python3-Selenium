# -*- coding: utf-8 -*-
"""
单元测试：企业级工程化标配（可安装性 / 质量门禁 / 依赖治理 / 合规）

★ 这个文件的存在本身就是一条工程约定：
  「工程标配」不是写在文档里的愿望，而是**可以被测试验证的事实**。

  它锁住的是 2026-10-11 那次"从项目脚本升级为企业级框架"的改造成果：
    1. pyproject.toml  —— 可安装 + 工具配置单一来源
    2. LICENSE / .editorconfig / .pre-commit-config.yaml —— 合规与协作标配
    3. 依赖有上界 + lock 文件 —— 供应链可复现
    4. 质量门禁真实生效 —— 不允许"装不上就跳过"的静默降级

  任何一条变红，都说明工程在退回到"没有门禁的项目脚本"状态。
"""

import os
import re
import unittest

from tests.helpers import BASE_DIR


def _read(relative_path):
    """读工程根下的文件；不存在返回 None。"""
    path = os.path.join(BASE_DIR, relative_path)
    if not os.path.isfile(path):
        return None
    with open(path, encoding='utf-8') as fp:
        return fp.read()


class TestProjectStandard(unittest.TestCase):
    """工程标配文件必须齐全 —— 缺一个都会让它在企业里"不合格"。"""

    #: 必备文件 -> 缺失后果（报错信息直接告诉人为什么需要它）
    REQUIRED_FILES = {
        'pyproject.toml': '可安装性与工具配置的唯一来源；缺它则 lint/类型/覆盖率配置无处安放',
        'LICENSE': '合规审计必查项；内部项目也需声明专有许可与第三方组件',
        '.editorconfig': '统一缩进与换行；缺它则 diff 里全是格式噪音',
        '.pre-commit-config.yaml': '提交前检查；缺它则问题只能到 CI 才暴露',
        '.flake8': '代码规范配置（flake8 不从 pyproject.toml 读配置）',
        'requirements.txt': '运行依赖清单',
        'requirements-dev.txt': '开发与质量工具依赖清单',
        'requirements.lock': '依赖锁定；缺它则"昨天能跑今天挂了"无法复现',
    }

    def test_必备工程文件齐全(self):
        missing = []
        for name, reason in self.REQUIRED_FILES.items():
            if not os.path.isfile(os.path.join(BASE_DIR, name)):
                missing.append('%s（%s）' % (name, reason))
        self.assertEqual(missing, [], '缺少工程标配文件：\n    ' + '\n    '.join(missing))

    def test_没有遗留的临时或备份文件(self):
        """工作区不该留 *.bak / *.orig / *.tmp 这类文件。"""
        offenders = []
        for name in os.listdir(BASE_DIR):
            if name.endswith(('.bak', '.orig', '.tmp', '.rej')):
                offenders.append(name)
        self.assertEqual(offenders, [], '工程根残留临时文件：%s' % offenders)


class TestPyproject(unittest.TestCase):
    """pyproject.toml 必须真的可被工具解析，且关键配置在位。"""

    @classmethod
    def setUpClass(cls):
        source = _read('pyproject.toml')
        if source is None:
            raise unittest.SkipTest('pyproject.toml 不存在（由上个用例报错）')
        cls.source = source
        try:
            import tomllib          # Python 3.11+
            cls.data = tomllib.loads(source)
        except ImportError:         # Python 3.9/3.10
            try:
                import tomli
                cls.data = tomli.loads(source)
            except ImportError:
                cls.data = None

    def test_toml语法合法(self):
        """语法错误的 pyproject.toml 会让所有工具静默失效。"""
        if self.data is None:
            self.skipTest('当前环境没有 tomllib/tomli，无法校验 TOML 语法')
        self.assertIsInstance(self.data, dict)

    def test_声明了项目元数据(self):
        if self.data is None:
            self.skipTest('无 TOML 解析器')
        project = self.data.get('project', {})
        for key in ('name', 'version', 'description', 'requires-python', 'license'):
            self.assertIn(key, project, 'pyproject.toml 缺少 project.%s' % key)

    def test_python版本要求不低于39(self):
        """低于 3.9 时工程里若干写法（dict 合并、unittest 特性）不可用。"""
        if self.data is None:
            self.skipTest('无 TOML 解析器')
        requires = self.data['project'].get('requires-python', '')
        self.assertIn('3.9', requires,
                      'requires-python 应显式声明 >=3.9，当前为 %r' % requires)

    def test_依赖有上界(self):
        """★★ 供应链治理的核心：无上界的依赖会让 CI 某天突然全红且不可复现。

        Selenium 5.x 一旦发布并改动 API，没有上界的本工程会直接挂 ——
        而"当时装的是哪个版本"根本无从查起。
        """
        if self.data is None:
            self.skipTest('无 TOML 解析器')
        deps = self.data['project'].get('dependencies', [])
        self.assertTrue(deps, '应声明运行依赖')
        unbounded = [d for d in deps if '<' not in d]
        self.assertEqual(
            unbounded, [],
            '这些依赖没有上界：%s\n'
            '    请写成 "包名>=下限,<上限"（如 selenium>=4.19,<5）——\n'
            '    否则上游发大版本时 CI 会毫无征兆地全红，且无法复现' % unbounded)

    def test_配置了覆盖率阈值(self):
        """★ 没有阈值的覆盖率报告等于没测：没人会看一个只涨不跌的数字。"""
        if self.data is None:
            self.skipTest('无 TOML 解析器')
        report = self.data.get('tool', {}).get('coverage', {}).get('report', {})
        self.assertIn('fail_under', report,
                      'coverage 必须设 fail_under 阈值，否则 CI 不会因覆盖率下降而失败')
        self.assertGreaterEqual(report['fail_under'], 80,
                                '覆盖率阈值不应低于 80（当前实测 85%%）')

    def test_配置了类型检查(self):
        if self.data is None:
            self.skipTest('无 TOML 解析器')
        mypy = self.data.get('tool', {}).get('mypy')
        self.assertIsNotNone(mypy, 'pyproject.toml 应包含 [tool.mypy] 配置')

    def test_覆盖率只统计框架层(self):
        """被测系统的 UI 用例要开浏览器，不纳入覆盖率统计。"""
        if self.data is None:
            self.skipTest('无 TOML 解析器')
        run_cfg = self.data.get('tool', {}).get('coverage', {}).get('run', {})
        self.assertEqual(sorted(run_cfg.get('source', [])), ['Common', 'PageObject'],
                         '覆盖率应只统计框架层 Common / PageObject')


class TestDependencyGovernance(unittest.TestCase):
    """依赖治理：范围与锁定分离，且两者一致。"""

    def test_requirements有上界(self):
        source = _read('requirements.txt') or ''
        lines = [ln.strip() for ln in source.splitlines()
                 if ln.strip() and not ln.strip().startswith('#')]
        # 只看真正 pin 的行（-r 之类的引用跳过）
        pins = [ln for ln in lines if not ln.startswith('-')]
        unbounded = [ln for ln in pins if '<' not in ln]
        self.assertEqual(unbounded, [],
                         'requirements.txt 里这些依赖没有上界：%s' % unbounded)

    def test_lock文件锁定了selenium(self):
        source = _read('requirements.lock')
        self.assertIsNotNone(source, 'requirements.lock 必须存在（保证环境可复现）')
        self.assertRegex(source, r'(?m)^selenium==\d+\.\d+',
                         'lock 文件里 selenium 必须用 == 锁死精确版本')

    def test_lock覆盖了传递依赖(self):
        """只锁直接依赖不够 —— 传递依赖变了同样会挂。"""
        source = _read('requirements.lock') or ''
        lines = [ln for ln in source.splitlines()
                 if re.match(r'^[A-Za-z]', ln) and '==' in ln]
        self.assertGreaterEqual(
            len(lines), 5,
            'lock 文件应包含 selenium 及其主要传递依赖（trio/urllib3/attrs 等），'
            '当前只锁定了 %d 个包' % len(lines))

    def test_requirements与lock中的selenium大版本一致(self):
        """两个文件对 Selenium 大版本的说法必须一致，否则装出来的东西不确定。"""
        req = _read('requirements.txt') or ''
        lock = _read('requirements.lock') or ''
        req_match = re.search(r'selenium>=([\d.]+)(?:,<(\d+))?', req)
        lock_match = re.search(r'selenium==(\d+)\.', lock)
        if not (req_match and lock_match):
            self.skipTest('未能从两个文件中解析出 selenium 版本约束')
        req_lower_major = req_match.group(1).split('.')[0]
        self.assertEqual(
            req_lower_major, lock_match.group(1),
            'requirements.txt 的下限（%s）与 lock 锁定的版本（%s）大版本不一致'
            % (req_lower_major, lock_match.group(1)))

    def test_开发依赖不写死版本范围(self):
        """上界只应有一个来源（pyproject.toml），否则两边会各自漂移。"""
        source = _read('requirements-dev.txt') or ''
        offenders = []
        for line in source.splitlines():
            line = line.strip()
            if not line or line.startswith('#') or line.startswith('-'):
                continue
            if '<' in line or '==' in line:
                offenders.append(line)
        self.assertEqual(
            offenders, [],
            'requirements-dev.txt 里不要重复写版本范围：%s\n'
            '    上界的唯一来源是 pyproject.toml [project.optional-dependencies]；'
            '    两处都写必然漂移' % offenders)


class TestPreCommitConfig(unittest.TestCase):
    """.pre-commit-config.yaml 必须真的能拦住问题。"""

    @classmethod
    def setUpClass(cls):
        cls.source = _read('.pre-commit-config.yaml') or ''

    def test_配置了钩子(self):
        self.assertIn('repos:', self.source, 'pre-commit 配置里应有 repos 段')

    def test_有代码规范钩子(self):
        self.assertIn('flake8', self.source,
                      'pre-commit 应包含 flake8 钩子（本地就能拦住规范问题）')

    def test_有私钥检测钩子(self):
        """★ 避免把私钥/凭据提交上去 —— 这是安全事故，不是代码风格问题。"""
        self.assertIn('detect-private-key', self.source,
                      'pre-commit 应包含 detect-private-key 钩子')

    def test_有本工程特有的定位门禁(self):
        self.assertIn('locator-policy', self.source,
                      'pre-commit 应包含元素定位规范钩子（本工程特有，防定位劣化）')

    def test_有业务数据门禁(self):
        self.assertIn('test_config_required', self.source,
                      'pre-commit 应包含"业务数据不得硬编码"的钩子')

    def test_定位门禁阈值与Jenkinsfile一致(self):
        """★ 提交钩子与 CI 用同一阈值，否则本地过了 CI 挂（或反之）。"""
        pre_commit = self.source
        jenkins = _read('Jenkinsfile') or ''
        hook_match = re.search(r'locator_policy --fail-over (\d+)', pre_commit)
        ci_match = re.search(r'maxFlawedLocators = (\d+)', jenkins)
        self.assertIsNotNone(hook_match, 'pre-commit 里应能解析出定位门禁阈值')
        self.assertIsNotNone(ci_match, 'Jenkinsfile 里应能解析出定位门禁阈值')
        self.assertEqual(
            hook_match.group(1), ci_match.group(1),
            '定位门禁阈值不一致：pre-commit=%s, Jenkinsfile=%s。\n'
            '    两处必须同步，否则会出现"本地过、CI 挂"这种最让人困惑的状态'
            % (hook_match.group(1), ci_match.group(1)))


class TestCiGatesAreReal(unittest.TestCase):
    """★★ CI 门禁必须真实生效 —— 不允许静默降级。

    这是本轮改造最该锁住的一条：
    旧 Jenkinsfile 里写的是 `flake8 装不上 -> echo 跳过`，
    等于门禁可以永久失效而无人察觉。文档里写着"有门禁"，
    实际 CI 从来没拦过任何东西 —— 这比没有门禁更糟，因为它给了虚假的安全感。
    """

    @classmethod
    def setUpClass(cls):
        cls.jenkins = _read('Jenkinsfile') or ''

    def test_flake8缺失时不会静默跳过(self):
        """★ 反向断言：不允许出现"装不上就跳过"的降级分支。"""
        self.assertNotIn(
            '跳过代码规范检查', self.jenkins,
            'Jenkinsfile 又出现了"跳过代码规范检查"的静默降级 ——\n'
            '    门禁如果不能保证生效，就不配叫门禁。请让它直接失败（exit 2）')
        self.assertIn('【门禁失败】未安装 flake8', self.jenkins,
                      'flake8 缺失时应有明确的失败提示，而不是继续往下跑')

    def test_包含覆盖率门禁(self):
        self.assertIn('coverage', self.jenkins,
                      'Jenkinsfile 应包含覆盖率检查（只跑测试不看覆盖率 = 门禁不完整）')

    def test_包含类型检查(self):
        self.assertIn('mypy', self.jenkins, 'Jenkinsfile 应包含类型检查 stage')

    def test_优先使用lock文件(self):
        """★ 安装依赖优先用锁定的版本，否则"昨天过的今天挂了"无法解释。"""
        self.assertIn('requirements.lock', self.jenkins,
                      'Jenkinsfile 安装依赖时应优先使用 requirements.lock')

    def test_包含前置自愈后的冒烟用例(self):
        self.assertIn('--suite', self.jenkins)

    def test_归档覆盖率报告(self):
        self.assertIn('Report/**', self.jenkins,
                      'Report/ 整目录归档已覆盖 coverage 产物（确认路径未被改窄）')


class TestLicenseCompliance(unittest.TestCase):
    """许可合规：专有声明 + 第三方组件归属。"""

    @classmethod
    def setUpClass(cls):
        cls.license = _read('LICENSE') or ''

    def test_有版权与保留权利声明(self):
        self.assertIn('Copyright', self.license)
        self.assertIn('All rights reserved', self.license)

    def test_声明了第三方组件(self):
        """★ 用了别人的代码就必须声明 —— 否则是合规风险。"""
        self.assertIn('第三方', self.license,
                      'LICENSE 应含第三方组件声明段')
        self.assertIn('HTMLTestReportCN', self.license,
                      '内置的第三方报告模板（BSD）必须声明来源与许可')
        self.assertIn('Selenium', self.license, '依赖的许可应一并声明')

    def test_第三方文件保留了原始版权头(self):
        """★ BSD 许可要求保留版权声明，删掉即违约。"""
        source = _read(os.path.join('Common', 'HTMLTestReportCN.py')) or ''
        self.assertIn('Wai Yip Tung', source,
                      'HTMLTestReportCN.py 必须保留原始作者的版权声明（BSD 许可要求）')
        self.assertIn('All rights reserved', source)


if __name__ == '__main__':
    unittest.main(verbosity=2)
