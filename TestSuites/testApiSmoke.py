# -*- coding: utf-8 -*-
"""
==========================================================================
 接口层用例（测试金字塔的底层）—— 样例模板
==========================================================================

【为什么要有这个文件】
    改造前本工程只有 UI 层测试（9 条，全部开浏览器）——
    这是"测试金字塔倒置"，代价是慢、脆、贵：
        · 一条用例几秒到几十秒，回归一次几分钟起
        · 前端改版就误伤，红的常常不是真问题
        · 维护成本最高，却承担了它不该承担的责任

    企业级做法：**能用接口验证的，不要用 UI 验证**。
    接口层该覆盖：字段校验、边界值、权限、状态流转、错误码。
    UI 层只保留关键业务链路（登录 -> 进系统 -> 核心操作）。

【怎么用这个文件】
    1. config.ini 里配置 [api] 段：
           [api]
           base_url   = http://测试环境地址/api
           login_path = /api/login
           token_field = data.token
    2. 把下面的样例用例替换成你系统的真实接口断言
    3. 没配 [api] base_url 时，整个文件**自动跳过**（不会红）——
       很多团队先上 UI 自动化、接口自动化后补，不该因为"还没配"就一片红

【接口层用例的三条约定】
    ① 断言落在**业务字段**上（返回体里的值），不只看状态码 ——
       200 也可能是业务失败（{"code": 500, "msg": "..."}）
    ② 数据自己造、自己清（不留垃圾数据拖累后续回归）
    ③ 只读用例与写用例要分开标记（与 UI 层同一套作用域机制）
==========================================================================
"""

import unittest

from Common.apiClient import ApiClient, ApiError, is_configured
from Common.config import Config
from Common.log import log1

#: 没配 [api] base_url 时整类跳过（而不是失败）
SKIP_REASON = ('未配置接口地址（config.ini -> [api] base_url）。'
               '接口层用例可选，配好地址后自动启用')


@unittest.skipUnless(is_configured(), SKIP_REASON)
class TestApiSmoke(unittest.TestCase):
    """接口层冒烟：验证"接口通不通、返回结构对不对"。

    ★ 这是样例模板，请按自己系统的接口改写。
      下面示范了三种最典型的接口断言：
        1. 健康检查 —— 服务是否可用（最快的一层，1 秒内出结果）
        2. 登录接口 —— 认证链路 + 令牌获取
        3. 列表接口 —— 业务字段断言（不只看状态码）
    """

    # 只读作用域：这些接口用例不改动数据，生产特征环境也敢跑
    # （与 UI 层同一套机制，见 Common/testcase_meta.py）
    scope = 'readonly'

    @classmethod
    def setUpClass(cls):
        """类级前置：建客户端并完成认证（同类用例共用一次登录）。"""
        cls.api = ApiClient()
        log1.info('接口层测试开始，base_url=%s' % cls.api.base_url)

    # ------------------------------------------------------------------ #
    # 1. 健康检查：最便宜的测试，先跑它
    # ------------------------------------------------------------------ #
    def test_1服务可用(self):
        """接口服务能正常响应。

        为什么先跑这条：
            如果服务本身挂了，后面所有接口用例都会失败 ——
            先跑健康检查能让"服务挂了"和"接口写错了"这两类问题一眼分开。
        """
        path = Config.get('api', 'health_path', '')
        if not path:
            self.skipTest('未配置 [api] health_path，跳过健康检查')
        # 健康检查通常返回 200 + 极简内容，不做深层断言
        self.api.get(path)
        self.assertEqual(self.api.last_status, 200)

    # ------------------------------------------------------------------ #
    # 2. 登录：拿到令牌，并验证返回结构
    # ------------------------------------------------------------------ #
    def test_2登录取到令牌(self):
        """登录接口必须返回令牌，且能被后续请求使用。

        断言点（三层，逐层深入）：
            ① 状态码 200           —— 链路通
            ② 返回里含令牌字段      —— 结构对
            ③ 令牌非空              —— 值有效
        """
        data = self.api.login()
        self.assertEqual(self.api.last_status, 200)
        self.assertIsInstance(data, dict, '登录接口应返回 JSON 对象')
        self.assertTrue(self.api.token,
                        '登录后未取得令牌 —— 请检查 config.ini [api] token_field '
                        '是否指向了正确的字段路径（如 data.token）')

    # ------------------------------------------------------------------ #
    # 3. 业务接口：断言业务字段，而不只看状态码
    # ------------------------------------------------------------------ #
    def test_3列表接口返回结构正确(self):
        """列表接口返回体应包含业务约定字段。

        ★ 关键点：**不要只断言状态码 200**。
          很多系统业务失败时也返回 200，靠返回体里的 code 区分。
          下面示范怎么把"业务成功"和"HTTP 成功"分开断言。
        """
        path = Config.get('api', 'list_path', '')
        if not path:
            self.skipTest('未配置 [api] list_path，跳过列表接口检查')

        data = self.api.get(path)
        self.assertEqual(self.api.last_status, 200)
        self.assertIsInstance(data, (dict, list), '列表接口应返回 JSON')

        # 业务错误码断言（若系统有统一的 code 字段）
        if isinstance(data, dict) and 'code' in data:
            self.assertIn(data['code'], (0, 200, '0', '200'),
                          '接口业务码非成功值：%s（msg=%s）'
                          % (data.get('code'), data.get('msg') or data.get('message')))

    # ------------------------------------------------------------------ #
    # 4. 异常路径：错误输入必须有可预期的错误响应
    # ------------------------------------------------------------------ #
    def test_4错误参数返回可预期错误(self):
        """错误参数不应导致 5xx（那是服务端 bug，不是"正常的报错"）。

        断言逻辑：能收到 4xx 或业务错误码 = 正常；
                 收到 5xx 或直接超时 = 服务端缺陷。
        """
        path = Config.get('api', 'list_path', '')
        if not path:
            self.skipTest('未配置 [api] list_path，跳过异常路径检查')

        try:
            self.api.get(path, params={'page': '-1', 'size': '-1'})
        except ApiError as exc:
            self.assertIsNotNone(exc.status, '错误参数应返回 HTTP 状态码')
            self.assertLess(exc.status, 500,
                            '错误参数导致服务端 %s（5xx 属于服务端缺陷，'
                            '应返回 4xx 并给出可读错误信息）' % exc.status)
            return
        # 没抛异常也正常：说明服务端宽容处理了非法参数
        self.assertLess(self.api.last_status, 500,
                        '错误参数导致 5xx，应作为服务端缺陷处理')


# ---------------------------------------------------------------------------
# 说明：ApiClient 自身的接线检查（URL 拼接、令牌头、JSON 解析等）
# 属于"框架自测"，不在本文件里 —— 见 tests/test_api_client.py。
# 本目录只放针对**被测系统**的接口用例。
# ---------------------------------------------------------------------------


if __name__ == '__main__':
    unittest.main(verbosity=2)
