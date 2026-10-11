# -*- coding: utf-8 -*-
"""
单元测试：PageObject/loginPage.py（页面对象）

页面对象是"业务动作"的落脚点，用例失败往往是因为某个动作点错了元素或顺序错了。
这里用 FakeDriver 记录**元素定位值的调用序列**，把每个业务动作的操作步骤钉死：
    登录 -> 填账号、填密码、点登录
    上传 -> 选文件、填三个字段、提交、收起列表、确定
    报送 -> 点报送、开初审下拉、选初审人、保存

这样一旦有人误改顺序或改错元素，测试立刻报出来。

★ 不启动浏览器、不连生产系统。
"""

import os
import shutil
import tempfile
import unittest
from unittest import mock

from selenium.common.exceptions import NoSuchElementException

from tests.helpers import FakeDriver, FakeElement, patch_config, patch_dirs
from Common.basePage import BasePage
from Common.elementPage import Element1
from PageObject.loginPage import LoginPage


class _LoginPageTestCase(unittest.TestCase):
    """基类：隔离配置与目录，并拦住所有强制等待。"""

    def setUp(self):
        self._config = patch_config()
        self._config.__enter__()

        self.sleep_calls = []
        self._sleep = mock.patch.object(
            BasePage, 'my_sleep',
            side_effect=lambda seconds: self.sleep_calls.append(seconds))
        self._sleep.start()

        self.tmpdir = tempfile.mkdtemp(prefix='ut_login_')
        self.video = os.path.join(self.tmpdir, '演示视频.mp4')
        with open(self.video, 'wb') as fp:
            fp.write(b'fake-video')

        self._dirs = patch_dirs()
        self._dirs.__enter__()

    def tearDown(self):
        self._dirs.__exit__(None, None, None)
        self._sleep.stop()
        self._config.__exit__(None, None, None)
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    # ---- 辅助 ----
    def make_page(self, element=None):
        self.driver = FakeDriver(element=element or FakeElement())
        self.page = LoginPage(self.driver)
        return self.page

    def located_values(self):
        """按调用顺序取出所有被定位的定位值。"""
        # 注意别用两个下划线做占位：它们会互相覆盖，导致过滤条件失效
        return [value for kind, _by, value in self.driver.calls
                if kind == 'find_element']


class TestPortalActions(_LoginPageTestCase):
    """统一门户：登录与跳转。"""

    def test_登录按顺序填账号密码并点登录(self):
        element = FakeElement()
        page = self.make_page(element)
        page.login('unit_user', 'pwd123')

        self.assertEqual(
            self.located_values(),
            [Element1.Username[1], Element1.Password[1], Element1.Sign_button[1]],
            '登录必须严格按「账号 -> 密码 -> 登录按钮」的顺序操作',
        )
        self.assertIn('unit_user', element.sent)
        self.assertIn('pwd123', element.sent)

    def test_登录后留一张截图便于回溯(self):
        self.make_page().login('u', 'p')
        self.assertEqual(len(self.driver.screenshots), 1)

    def test_点发布系统进入生产系统(self):
        page = self.make_page()
        page.click_sign_in()
        self.assertEqual(self.located_values(), [Element1.button[1]])


class TestMaterialNavigation(_LoginPageTestCase):
    """素材库导航。"""

    def test_先点内容管理再点素材库(self):
        page = self.make_page()
        page.click_material()
        self.assertEqual(
            self.located_values(),
            [Element1.content[1], Element1.material[1]],
            '素材库是二级菜单，必须先点「内容管理」再点「素材库」',
        )


class TestUpload(_LoginPageTestCase):
    """上传视频（本工程最主要的业务动作）。"""

    def test_默认用send_keys方式上传(self):
        element = FakeElement()
        page = self.make_page(element)
        page.upload_file(self.video)

        self.assertEqual(self.located_values(), [Element1.FileInput[1]])
        self.assertEqual(element.sent, [self.video])

    def test_上传控件不可用时回退到autoit(self):
        """只有"技术性失败"才回退：file 控件拿不到，才需要改走系统对话框。"""
        page = self.make_page()
        with mock.patch.object(page, 'files_upload',
                               side_effect=NoSuchElementException('没找到 file 控件')), \
                mock.patch.object(page, 'upload_by_autoit') as fallback:
            page.upload_file(self.video)

        self.assertEqual(fallback.call_count, 1, 'send_keys 失败必须回退到 autoit 方案')
        self.assertEqual(
            self.located_values(),
            [Element1.uplaodbutton[1]],
            '回退时应改为点击页面上可见的上传按钮，再交给 autoit 处理系统对话框',
        )

    def test_配置为autoit时直接走对话框方案(self):
        ini = '[testcase]\nupload_mode = autoit\n'
        with patch_config(ini_text=ini):
            self.driver = FakeDriver(element=FakeElement())
            page = LoginPage(self.driver)
            with mock.patch.object(page, 'upload_by_autoit') as fallback:
                page.upload_file(self.video)

        self.assertEqual(fallback.call_count, 1)
        self.assertEqual(self.located_values(), [Element1.uplaodbutton[1]])

    def test_未配置上传文件且未传路径时报错(self):
        """不能静默跳过，否则用例会在"没上传"的情况下判为通过。

        同时必须**直接抛出配置错误**：早期实现会把这类错误也当作
        "send_keys 方案失败"去回退 autoit，结果真实原因被盖成一句
        莫名其妙的 autoit 报错，排查时完全摸不着头脑。
        """
        ini = '[testcase]\nupload_mode = send_keys\nupload_file =\n'
        with patch_config(ini_text=ini):
            self.driver = FakeDriver(element=FakeElement())
            page = LoginPage(self.driver)
            with mock.patch.object(page, 'upload_by_autoit') as fallback:
                with self.assertRaises(ValueError):
                    page.upload_file()
        self.assertEqual(fallback.call_count, 0, '配置类错误不应触发 autoit 回退')

    def test_文件不存在时直接报错不回退(self):
        ini = '[testcase]\nupload_mode = send_keys\n'
        with patch_config(ini_text=ini):
            self.driver = FakeDriver(element=FakeElement())
            page = LoginPage(self.driver)
            with mock.patch.object(page, 'upload_by_autoit') as fallback:
                with self.assertRaises(FileNotFoundError):
                    page.upload_file(os.path.join(self.tmpdir, '没有这个文件.mp4'))
        self.assertEqual(fallback.call_count, 0)

    def test_填写上传表单并提交(self):
        page = self.make_page()
        page.fill_upload_form('张三', '13800000000', '深圳')

        self.assertEqual(
            self.located_values(),
            [Element1.videoauthor[1], Element1.phone[1], Element1.reporting[1],
             Element1.upload[1], Element1.showbuttons[1], Element1.confirm[1]],
            '必须先填完三个字段才能提交，提交后还要收起文件列表并关闭弹窗',
        )

    def test_表单字段内容被正确输入(self):
        element = FakeElement()
        page = self.make_page(element)
        page.fill_upload_form('张三', '13800000000', '深圳')
        self.assertIn('张三', element.sent)
        self.assertIn('13800000000', element.sent)
        self.assertIn('深圳', element.sent)


class TestQueryAndSubmit(_LoginPageTestCase):
    """关键字查询与报送。"""

    def test_查询后重置(self):
        page = self.make_page()
        page.keyword_query('测试')
        self.assertEqual(
            self.located_values(),
            [Element1.keyword[1], Element1.querybutton[1], Element1.replacement[1]],
            '查询后必须点重置，为后续用例恢复初始列表状态',
        )

    def test_报送流程四步(self):
        """报送：点「报 送」-> 开「初审」下拉 -> 按姓名选审核人 -> 保存。

        ★ 第三条断言验证的是"按姓名定位"而不是"按第 N 项定位"：
          写死序号的话，人员列表顺序一变就会静默选错人。
        """
        page = self.make_page()
        with patch_config(ini_text='[testcase]\nfirst_trial_person = 张三\n'):
            page.submitted()
        expected_person = Element1.first_trial_person('张三')[1]
        self.assertEqual(
            self.located_values(),
            [Element1.submission[1], Element1.first_trial[1],
             expected_person, Element1.save[1]],
            '报送必须：点报送 -> 开初审下拉 -> 按姓名选审核人 -> 保存',
        )

    def test_报送可显式指定审核人(self):
        """姓名也可以由调用方直接传入（便于用例层按数据驱动换人）。"""
        page = self.make_page()
        page.submitted('李四')
        self.assertIn(Element1.first_trial_person('李四')[1], self.located_values())

    def test_审核人姓名必须来自配置(self):
        """没配审核人时应明确报错，而不是静默选第一个。"""
        page = self.make_page()
        with patch_config(ini_text='[testcase]\nlogin_username = u\n'):
            with self.assertRaises(ValueError):
                page.submitted()


class TestLayering(unittest.TestCase):
    """分层约定（防止后续维护时把逻辑放错层）。"""

    def test_页面对象不写断言(self):
        import inspect
        source = inspect.getsource(LoginPage)
        for banned in ('assertEqual', 'assertTrue', 'assertFalse', 'assertIn'):
            self.assertNotIn(banned, source, '页面对象层不应写断言：%s' % banned)

    def test_页面对象不出现xpath字面量(self):
        import inspect
        source = inspect.getsource(LoginPage)
        self.assertNotIn('//', source, '页面对象层不允许出现 xpath，元素一律从 Element1 取')

    def test_页面对象继承自基类(self):
        self.assertTrue(issubclass(LoginPage, BasePage))


if __name__ == '__main__':
    unittest.main(verbosity=2)
