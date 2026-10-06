# -*- coding: utf-8 -*-
"""
==========================================================================
单元测试：Common/env_guard.py（环境守卫）
==========================================================================

这一层测试拦住的是自动化里最贵的事故：本该打测试环境，结果打到生产。
所以这里的用例写得比较"抠细节"——每种该拦、该放的情况都要钉住。

覆盖四道检查：
    ① 地址是否配置了（空 / 还是占位符）
    ② 地址是否落在白名单正则内
    ③ 地址是否带生产特征
    ④ 环境能不能跑写用例

全都是纯函数调用，不打开浏览器、不连网络，跑一遍不到一秒。
==========================================================================
"""

import unittest

from Common import env_guard
from Common.env_guard import GuardVerdict, looks_like_placeholder, looks_like_production

TEST_URL = 'http://ui-test.company.cn/sso-portal'
PROD_URL = 'http://ui-prod.company.cn/sso-portal'


class TestPlaceholder(unittest.TestCase):
    """识别"照抄了配置示例但忘了改"。"""

    def test_空地址算占位(self):
        self.assertTrue(looks_like_placeholder(''))
        self.assertTrue(looks_like_placeholder(None))
        self.assertTrue(looks_like_placeholder('   '))

    def test_中文占位地址(self):
        self.assertTrue(looks_like_placeholder('http://测试环境地址/sso-portal'))

    def test_示例域名算占位(self):
        """example.com 是 IANA 保留域名，永远不会是真实环境。"""
        self.assertTrue(looks_like_placeholder('http://test.example.com/login'))
        self.assertTrue(looks_like_placeholder('http://your-host/login'))
        self.assertTrue(looks_like_placeholder('http://host/changeme'))

    def test_真实地址不算占位(self):
        self.assertFalse(looks_like_placeholder(TEST_URL))
        self.assertFalse(looks_like_placeholder(PROD_URL))


class TestProductionDetection(unittest.TestCase):
    """识别地址里的生产特征。"""

    def test_默认关键字命中(self):
        for url in ('http://ui-prod.host/', 'http://production.host/',
                    'http://ui.线上.host/', 'http://正式环境.host/',
                    'http://生产.host/'):
            hit, word = looks_like_production(url)
            self.assertTrue(hit, '%s 应被判为疑似生产' % url)
            self.assertTrue(word)

    def test_测试环境不误伤(self):
        hit, word = looks_like_production(TEST_URL)
        self.assertFalse(hit, '测试环境地址不该被判成生产：%s' % TEST_URL)
        self.assertIsNone(word)

    def test_自定义关键字(self):
        hit, _ = looks_like_production('http://stage.host/', ['stage'])
        self.assertTrue(hit)
        hit, _ = looks_like_production('http://stage.host/', ['uat'])
        self.assertFalse(hit)


class TestGuardVerdict(unittest.TestCase):
    """结论对象的易用性：要能直接当布尔值用。"""

    def test_可以当布尔值判断(self):
        self.assertTrue(GuardVerdict(True, 'ok', '通过'))
        self.assertFalse(GuardVerdict(False, 'no_url', '没地址'))

    def test_带出足够定位问题的信息(self):
        verdict = env_guard.check(url='')
        self.assertFalse(verdict)
        self.assertEqual(verdict.code, 'no_url')
        self.assertIn('未正确配置', verdict.reason)


class TestCheck(unittest.TestCase):
    """四道检查的完整行为。"""

    # ---- ① 地址是否配置 ----
    def test_空地址被拦下(self):
        verdict = env_guard.check(url='')
        self.assertEqual(verdict.code, 'no_url')

    def test_占位地址被拦下(self):
        verdict = env_guard.check(url='http://测试环境地址/sso-portal')
        self.assertEqual(verdict.code, 'no_url')
        self.assertIn('测试环境地址', verdict.reason, '报错里要带上当前值，便于对照')

    # ---- ② 白名单 ----
    def test_白名单不匹配时拦下(self):
        verdict = env_guard.check(url=TEST_URL, url_must_match=r'^http://only-this\.host')
        self.assertEqual(verdict.code, 'not_allowed')

    def test_白名单匹配时放行(self):
        verdict = env_guard.check(url=TEST_URL, url_must_match=r'^http://ui-test\.company\.cn')
        self.assertTrue(verdict)

    def test_白名单正则是坏的时拦下(self):
        """配置写错必须立刻暴露，不能静默跳过检查。"""
        verdict = env_guard.check(url=TEST_URL, url_must_match='[未闭合')
        self.assertEqual(verdict.code, 'bad_pattern')
        self.assertIn('不是合法正则', verdict.reason)

    def test_白名单留空则不校验(self):
        self.assertTrue(env_guard.check(url=TEST_URL, url_must_match=''))
        self.assertTrue(env_guard.check(url=TEST_URL, url_must_match=None))

    # ---- ③④ 生产特征 + 写用例 ----
    def test_生产环境加写用例被拦下(self):
        verdict = env_guard.check(url=PROD_URL, has_write_cases=True)
        self.assertEqual(verdict.code, 'prod_blocked')
        self.assertTrue(verdict.prod_like)
        self.assertIn('prod', verdict.reason, '要说清是哪个关键字命中的')

    def test_生产环境加只读用例放行(self):
        """这是整个设计的核心让步：只读用例在生产跑是安全的，也是必要的。"""
        verdict = env_guard.check(url=PROD_URL, has_write_cases=False)
        self.assertTrue(verdict)
        self.assertTrue(verdict.prod_like, '仍然要标记出"这是生产环境"，便于日志告警')

    def test_生产环境写用例显式允许时放行(self):
        verdict = env_guard.check(url=PROD_URL, has_write_cases=True, allow_write=True)
        self.assertTrue(verdict)

    def test_自定义黑名单生效(self):
        verdict = env_guard.check(url='http://stage.host/', has_write_cases=True,
                                  url_blocklist=['stage'])
        self.assertEqual(verdict.code, 'prod_blocked')

    def test_黑名单传空列表时退回内置默认(self):
        """★ 安全默认取更严的一侧：把配置清空不该成为绕过守卫的捷径。"""
        verdict = env_guard.check(url=PROD_URL, has_write_cases=True, url_blocklist=[])
        self.assertEqual(verdict.code, 'prod_blocked')

    # ---- 总开关 ----
    def test_守卫关闭时全部放行(self):
        verdict = env_guard.check(url='', has_write_cases=True, guard=False)
        self.assertTrue(verdict)
        self.assertEqual(verdict.code, 'guard_off')

    def test_正常情况下放行(self):
        verdict = env_guard.check(url=TEST_URL, has_write_cases=True)
        self.assertTrue(verdict)
        self.assertEqual(verdict.code, 'ok')
        self.assertFalse(verdict.prod_like)

    def test_检查顺序_地址缺失优先于生产判断(self):
        """地址都没配时，报"没配地址"比报"疑似生产"更有指导意义。"""
        verdict = env_guard.check(url='', has_write_cases=True)
        self.assertEqual(verdict.code, 'no_url')


if __name__ == '__main__':
    unittest.main(verbosity=2)
