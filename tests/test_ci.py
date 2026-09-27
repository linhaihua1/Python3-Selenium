# -*- coding: utf-8 -*-
"""
单元测试：Common/ci.py（流水线环境识别与构建元信息）

为什么值得测：构建号/分支一旦取错，报告会标注成别的构建，
出问题时无法追溯；而本地跑（无这些变量）时又不能报错。
"""

import os
import unittest

from Common import ci


class _EnvGuard(unittest.TestCase):
    """隔离 CI 相关环境变量。"""

    KEYS = ('JENKINS_URL', 'BUILD_NUMBER', 'JOB_NAME', 'GITLAB_CI',
            'GITHUB_ACTIONS', 'TEAMCITY_VERSION', 'TRAVIS', 'CI',
            'BUILD_URL', 'GIT_BRANCH', 'BRANCH_NAME', 'GIT_COMMIT',
            'NODE_NAME', 'WORKSPACE', 'APP_BUILD_NO')

    def setUp(self):
        self._saved = {}
        for key in self.KEYS:
            if key in os.environ:
                self._saved[key] = os.environ.pop(key)

    def tearDown(self):
        for key in self.KEYS:
            os.environ.pop(key, None)
        os.environ.update(self._saved)


class TestIsCi(_EnvGuard):
    """CI 环境判定。"""

    def test_没有任何标记变量时判为本地(self):
        self.assertFalse(ci.is_ci())

    def test_Jenkins变量命中(self):
        for key in ('JENKINS_URL', 'BUILD_NUMBER', 'JOB_NAME'):
            os.environ[key] = 'x'
            self.assertTrue(ci.is_ci(), '%s 应被视为 CI 标记' % key)
            os.environ.pop(key)

    def test_其它平台标记也能识别(self):
        for key in ('GITLAB_CI', 'GITHUB_ACTIONS', 'TEAMCITY_VERSION', 'TRAVIS'):
            os.environ[key] = 'true'
            self.assertTrue(ci.is_ci(), '%s 应被视为 CI 标记' % key)
            os.environ.pop(key)

    def test_值为假时不判为CI(self):
        for value in ('', '0', 'false', 'no', 'none', 'FALSE'):
            os.environ['CI'] = value
            self.assertFalse(ci.is_ci(), 'CI=%r 不应判为流水线' % value)

    def test_值为真时判为CI(self):
        os.environ['CI'] = 'true'
        self.assertTrue(ci.is_ci())


class TestBuildInfo(_EnvGuard):
    """构建上下文采集。"""

    def test_字段完整(self):
        info = ci.build_info()
        for key in ('ci', 'job', 'build', 'build_url', 'branch', 'commit',
                    'node', 'workspace', 'app_build', 'python', 'os', 'time'):
            self.assertIn(key, info)

    def test_本地运行时字段为空且不报错(self):
        info = ci.build_info()
        self.assertFalse(info['ci'])
        self.assertEqual(info['job'], '')
        self.assertEqual(info['build'], '')

    def test_采集Jenkins变量(self):
        os.environ.update({
            'JOB_NAME': 'ui-smoke-test',
            'BUILD_NUMBER': '128',
            'BUILD_URL': 'http://jenkins/job/ui-smoke-test/128/',
            'GIT_COMMIT': 'abcdef1234567890',
            'NODE_NAME': 'win-node-01',
            'WORKSPACE': 'C:\\jenkins\\workspace\\ui',
            'APP_BUILD_NO': '20260925.3',
        })
        info = ci.build_info()
        self.assertTrue(info['ci'])
        self.assertEqual(info['job'], 'ui-smoke-test')
        self.assertEqual(info['build'], '128')
        self.assertEqual(info['commit'], 'abcdef12', '提交号应截取前 8 位')
        self.assertEqual(info['node'], 'win-node-01')
        self.assertEqual(info['app_build'], '20260925.3')

    def test_分支优先取GIT_BRANCH再退BRANCH_NAME(self):
        os.environ['GIT_BRANCH'] = 'origin/main'
        self.assertEqual(ci.build_info()['branch'], 'origin/main')

        os.environ.pop('GIT_BRANCH')
        os.environ['BRANCH_NAME'] = 'feature/ci'
        self.assertEqual(ci.build_info()['branch'], 'feature/ci')

    def test_提交号为空时不会报错(self):
        self.assertEqual(ci.build_info()['commit'], '')


class TestBuildLabel(_EnvGuard):
    """人类可读的构建标识。"""

    def test_本地运行返回固定文案(self):
        self.assertEqual(ci.build_label(), '本地运行')

    def test_拼接任务号与分支(self):
        os.environ.update({
            'JOB_NAME': 'ui-smoke-test',
            'BUILD_NUMBER': '128',
            'GIT_BRANCH': 'origin/main',
        })
        label = ci.build_label()
        self.assertIn('ui-smoke-test', label)
        self.assertIn('#128', label)
        self.assertIn('origin/main', label)

    def test_包含应用构建号(self):
        os.environ['APP_BUILD_NO'] = '20260925.3'
        self.assertIn('20260925.3', ci.build_label())


class TestLogContext(_EnvGuard):
    """把上下文写进日志。"""

    def test_返回字典且不抛异常(self):
        info = ci.log_context()
        self.assertIsInstance(info, dict)
        self.assertIn('ci', info)

    def test_CI环境下也能正常返回(self):
        os.environ['BUILD_NUMBER'] = '7'
        self.assertTrue(ci.log_context()['ci'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
