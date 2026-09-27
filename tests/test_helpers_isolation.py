# -*- coding: utf-8 -*-
"""
单元测试：tests/helpers.py 的隔离能力（测试基座自检）

【为什么值得单独测】
    helpers.py 是"所有单元测试的地基"。它一旦失效，表现不是测试失败，
    而是**静默污染**：工程 Logs/ 多出一堆日志、系统临时目录里堆垃圾目录、
    或者某个用例把真实的 config.ini 改掉。这种问题没人会立刻发现，
    攒久了就变成"跑一次单测，git status 一排脏文件"。

    所以这里把三条硬约束变成可执行的断言：
        1. 临时目录一定登记进 _TEMP_DIRS，进程退出会被清掉（不留垃圾）
        2. patch_config 自建的 ini 用完即删；外部传入的绝不删
        3. patch_dirs 接管日志目录时会摘掉 UI_LOG_DIR，退出时原样还原
"""

import os
import shutil
import tempfile
import unittest

from tests import helpers
from tests.helpers import BASE_DIR, make_sandbox, patch_config, patch_dirs


class TestTempDirRegistration(unittest.TestCase):
    """所有临时目录都必须登记，否则系统临时目录会被堆满。"""

    def test_新建的临时根会被登记(self):
        with patch_dirs() as root:
            self.assertIn(root, helpers._TEMP_DIRS)

    def test_显式传入的根不被登记(self):
        """沙盒根归调用方所有，helpers 不应越权接管。"""
        outside = tempfile.mkdtemp(prefix='ut_owned_')
        try:
            with patch_dirs(root=outside):
                self.assertNotIn(outside, helpers._TEMP_DIRS)
        finally:
            shutil.rmtree(outside, ignore_errors=True)

    def test_配置目录会被登记(self):
        helpers._shared_config_dir()
        self.assertIn(helpers._SHARED_CONFIG_DIR[0], helpers._TEMP_DIRS)

    def test_沙盒目录会被登记(self):
        root, _cases, _pkg = make_sandbox()
        self.assertIn(root, helpers._TEMP_DIRS)

    def test_清理函数能真的删掉登记的目录(self):
        """只验证清理逻辑本身，不动其它用例登记过的目录（避免时序耦合）。"""
        victim = tempfile.mkdtemp(prefix='ut_victim_')
        saved = helpers._TEMP_DIRS[:]
        helpers._TEMP_DIRS[:] = [victim]
        try:
            helpers._cleanup_temp_dirs()
            self.assertFalse(os.path.exists(victim))
            self.assertEqual(helpers._TEMP_DIRS, [])
        finally:
            helpers._TEMP_DIRS[:] = saved


class TestPatchConfigOwnership(unittest.TestCase):
    """临时 ini 文件的归属规则：自己建的自己删，别人给的别动。"""

    def test_自建的ini在退出上下文后删除(self):
        with patch_config() as ini_path:
            self.assertTrue(os.path.isfile(ini_path))
        self.assertFalse(os.path.exists(ini_path), '自建的 ini 应该用完即删')

    def test_外部传入的ini不会被删除(self):
        """沙盒工程的 config.ini 属于沙盒，删了会让后续断言拿到不存在的文件。"""
        own = tempfile.mkdtemp(prefix='ut_own_')
        ini_path = os.path.join(own, 'config.ini')
        try:
            with patch_config(ini_path=ini_path):
                pass
            self.assertTrue(os.path.isfile(ini_path))
        finally:
            shutil.rmtree(own, ignore_errors=True)

    def test_多个上下文共用同一个临时目录(self):
        """历史性能问题：每个用例都新建临时目录，Windows 上删目录极慢。"""
        with patch_config() as first:
            pass
        with patch_config() as second:
            pass
        self.assertEqual(os.path.dirname(first), os.path.dirname(second))

    def test_配置内容写入了临时文件(self):
        with patch_config(ini_text='[ci]\nheadless = true\n') as ini_path:
            with open(ini_path, encoding='utf-8') as fp:
                self.assertIn('headless = true', fp.read())


class TestLogDirPriority(unittest.TestCase):
    """UI_LOG_DIR 与 patch_dirs 的优先级：用例级重定向必须能盖住进程级配置。"""

    def test_patch_dirs期间摘掉UI_LOG_DIR(self):
        original = os.environ.get('UI_LOG_DIR')
        try:
            os.environ['UI_LOG_DIR'] = 'process-level'
            with patch_dirs():
                self.assertNotIn('UI_LOG_DIR', os.environ,
                                 '不摘掉它，日志会被写到进程级目录，用例级断言就失效了')
            self.assertEqual(os.environ.get('UI_LOG_DIR'), 'process-level')
        finally:
            if original is None:
                os.environ.pop('UI_LOG_DIR', None)
            else:
                os.environ['UI_LOG_DIR'] = original

    def test_用例异常退出时也会还原UI_LOG_DIR(self):
        original = os.environ.get('UI_LOG_DIR')
        try:
            os.environ['UI_LOG_DIR'] = 'process-level'
            with self.assertRaises(RuntimeError):
                with patch_dirs():
                    raise RuntimeError('模拟用例炸了')
            self.assertEqual(os.environ.get('UI_LOG_DIR'), 'process-level')
        finally:
            if original is None:
                os.environ.pop('UI_LOG_DIR', None)
            else:
                os.environ['UI_LOG_DIR'] = original

    def test_patch_dirs的日志落在临时根下(self):
        from Common.log import get_log, _INITIALIZED
        name = 'ut_isdir_case'
        with patch_dirs() as root:
            logger = get_log(name, console=False)
            try:
                logger.info('隔离日志')
                target = os.path.join(root, 'Logs')
                self.assertTrue(os.path.isdir(target),
                                '日志目录应建在临时根下：%s' % target)
            finally:
                for handler in list(logger.handlers):
                    logger.removeHandler(handler)
                    handler.close()
                _INITIALIZED.discard(name)


class TestNoProjectPollution(unittest.TestCase):
    """测试基座本身不应在工程目录留下任何东西。"""

    def test_临时目录都落在系统临时目录下(self):
        with patch_dirs() as root:
            self.assertEqual(
                os.path.normcase(os.path.commonpath([root, tempfile.gettempdir()])),
                os.path.normcase(tempfile.gettempdir()),
            )

    def test_临时目录都在工程目录之外(self):
        with patch_dirs() as root:
            self.assertFalse(
                os.path.normcase(root).startswith(os.path.normcase(BASE_DIR)))


if __name__ == '__main__':
    unittest.main(verbosity=2)
