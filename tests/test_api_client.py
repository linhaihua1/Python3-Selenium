# -*- coding: utf-8 -*-
"""
单元测试：Common/apiClient.py（接口层客户端）

★ 这是"框架自测"，不依赖任何真实接口 —— 全部用假响应替身。

  验证的四件事（都是接口层最容易出错、又最难排查的）：
    1. URL 拼接 —— 双斜杠、缺少斜杠都会导致 404，而报错信息看不出原因
    2. 认证 —— 令牌有没有真的写进请求头（写错位置 = 全部 401）
    3. 错误可读性 —— 非 2xx 时抛出的异常必须带请求与响应片段
    4. 缺配置的报错 —— 必须说清去哪配，而不是抛一个 URLError
"""

import io
import json
import unittest
import urllib.error
from unittest import mock

from tests.helpers import patch_config
from Common.apiClient import ApiClient, ApiError, is_configured


class _FakeResponse(object):
    """假的 urlopen 返回值。"""

    def __init__(self, body=b'{"ok": true}', status=200):
        self._body = body
        self.status = status

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _make_client(**kwargs):
    """在配置隔离的前提下建一个客户端。"""
    return ApiClient(base_url='http://api.local', **kwargs)


class TestUrlBuilding(unittest.TestCase):
    """URL 拼接 —— 错了就是 404，而 404 的报错看不出是拼错还是真没有。"""

    def setUp(self):
        self.api = _make_client()
        self.seen = {}

    def _capture(self, body=b'{}', status=200):
        """把 urlopen 换成记录器，返回它收到的 Request。"""
        def fake_urlopen(req, timeout=None):
            self.seen['url'] = req.full_url
            self.seen['method'] = req.get_method()
            self.seen['headers'] = dict(req.headers)
            self.seen['data'] = req.data
            return _FakeResponse(body, status)
        return mock.patch('Common.apiClient.urllib.request.urlopen',
                          side_effect=fake_urlopen)

    def test_基地址末尾斜杠被归一(self):
        self.assertEqual(_make_client().base_url, 'http://api.local')

    def test_相对路径拼接正确(self):
        with self._capture():
            self.api.get('/api/materials')
        self.assertEqual(self.seen['url'], 'http://api.local/api/materials')

    def test_路径不带前导斜杠也能拼对(self):
        with self._capture():
            self.api.get('api/materials')
        self.assertEqual(self.seen['url'], 'http://api.local/api/materials')

    def test_不会出现双斜杠(self):
        """http://api.local//api/x 这类 URL 有些网关直接 404。"""
        with self._capture():
            self.api.get('//api/materials')
        self.assertNotIn('local//', self.seen['url'])

    def test_查询参数被正确编码(self):
        with self._capture():
            self.api.get('/api/search', params={'keyword': '中文 词', 'page': 1})
        self.assertIn('keyword=', self.seen['url'])
        self.assertNotIn(' ', self.seen['url'], '查询参数必须 URL 编码')

    def test_查询参数跳过None值(self):
        with self._capture():
            self.api.get('/api/search', params={'a': 1, 'b': None})
        self.assertIn('a=1', self.seen['url'])
        self.assertNotIn('b=', self.seen['url'], 'None 值不应出现在查询串里')

    def test_完整url不被改写(self):
        with self._capture():
            self.api.get('http://other.local/api/x')
        self.assertEqual(self.seen['url'], 'http://other.local/api/x')

    def test_POST请求体被序列化成JSON(self):
        with self._capture():
            self.api.post('/api/create', json_body={'name': '张三'})
        self.assertEqual(self.seen['method'], 'POST')
        self.assertEqual(json.loads(self.seen['data'].decode('utf-8')),
                         {'name': '张三'})

    def test_各HTTP方法都能用(self):
        for method in ('get', 'post', 'put', 'delete'):
            with self._capture():
                getattr(self.api, method)('/api/x')
            self.assertEqual(self.seen['method'], method.upper())


class TestAuth(unittest.TestCase):
    """认证 —— 令牌写错位置的话，所有接口都 401，且报错信息毫无提示。"""

    def test_构造时传令牌写入请求头(self):
        api = _make_client(token='T123')
        self.assertEqual(api.headers.get('Authorization'), 'Bearer T123')

    def test_登录后自动记住令牌(self):
        api = _make_client()
        with mock.patch.object(api, 'post', return_value={'token': 'NEW'}):
            api.login('/api/login', {'username': 'u', 'password': 'p'})
        self.assertEqual(api.token, 'NEW')
        self.assertEqual(api.headers.get('Authorization'), 'Bearer NEW')

    def test_支持嵌套令牌字段(self):
        """很多系统返回 {"data": {"token": "..."}}，token_field 要能配 data.token。"""
        api = _make_client()
        with patch_config(ini_text='[api]\ntoken_field = data.token\n'):
            with mock.patch.object(api, 'post',
                                   return_value={'data': {'token': 'NESTED'}}):
                api.login('/api/login', {'username': 'u', 'password': 'p'})
        self.assertEqual(api.token, 'NESTED')

    def test_登录默认复用UI层的账号密码(self):
        """★ 账号只维护一处：接口层默认读 [testcase]，避免两处漂移。

        注意配置里必须带上 [api] token_field ——
        它现在是必填项（代码里不再兜底 'token'），
        所以"只读账号不读令牌字段"的写法在真实配置里是不成立的。
        """
        api = _make_client()
        with patch_config(ini_text=(
                '[testcase]\nlogin_username = api_user\nlogin_password = api_pwd\n'
                '[api]\ntoken_field = token\n')):
            with mock.patch.object(api, 'post', return_value={'token': 'T'}) as post:
                api.login('/api/login')
        self.assertEqual(post.call_args[0][1],
                         {'username': 'api_user', 'password': 'api_pwd'})

    def test_令牌字段缺失时明确报错(self):
        """★★ 反向断言：token_field 不再有代码兜底，缺失必须报错。

        旧版兜底成 'token'，换系统（返回 access_token 之类）忘了改配置时，
        会静默取不到令牌、后续所有带鉴权的请求 401，
        报出来的却是"未取得令牌"，把排查方向完全带偏。
        """
        api = _make_client()
        with patch_config(ini_text='[testcase]\nlogin_username = u\nlogin_password = p\n'):
            with mock.patch.object(api, 'post', return_value={'token': 'T'}):
                with self.assertRaises(ValueError) as ctx:
                    api.login('/api/login', {'u': 1, 'p': 1})
        self.assertIn('token_field', str(ctx.exception),
                      '报错信息应指出缺的是 [api] token_field')
        self.assertIn('UI_API_TOKEN_FIELD', str(ctx.exception),
                      '报错信息应给出环境变量名，便于 CI 注入')

    def test_找不到令牌字段时只告警不中断(self):
        """有些接口不需要认证，不该因为没返回 token 就崩。"""
        api = _make_client()
        with mock.patch.object(api, 'post', return_value={'foo': 'bar'}):
            result = api.login('/api/login', {'u': 1})
        self.assertEqual(result, {'foo': 'bar'})
        self.assertIsNone(api.token)


class TestErrorReporting(unittest.TestCase):
    """错误可读性 —— 接口失败时最需要的就是"请求 + 响应片段"。"""

    def setUp(self):
        self.api = _make_client()

    def test_非2xx抛出ApiError并带状态码(self):
        def raise_http(req, timeout=None):
            body = '{"msg":"内部错误"}'.encode('utf-8')
            raise urllib.error.HTTPError(
                req.full_url, 500, 'Server Error', {}, io.BytesIO(body))

        with mock.patch('Common.apiClient.urllib.request.urlopen',
                        side_effect=raise_http):
            with self.assertRaises(ApiError) as ctx:
                self.api.get('/api/x')
        self.assertEqual(ctx.exception.status, 500)
        self.assertIn('500', str(ctx.exception))

    def test_错误信息包含响应片段(self):
        """★ 排查时最有价值的就是服务端返回的那句话。"""
        def raise_http(req, timeout=None):
            raise urllib.error.HTTPError(
                req.full_url, 400, 'Bad Request', {},
                io.BytesIO('{"msg":"参数 size 超出范围"}'.encode('utf-8')))

        with mock.patch('Common.apiClient.urllib.request.urlopen',
                        side_effect=raise_http):
            with self.assertRaises(ApiError) as ctx:
                self.api.get('/api/x')
        message = str(ctx.exception)
        self.assertIn('请求', message, '错误信息要带请求信息')
        self.assertIn('参数 size 超出范围', message, '错误信息要带响应片段')

    def test_网络错误也转成ApiError(self):
        with mock.patch('Common.apiClient.urllib.request.urlopen',
                        side_effect=urllib.error.URLError('连接被拒绝')):
            with self.assertRaises(ApiError) as ctx:
                self.api.get('/api/x')
        self.assertIn('连接被拒绝', str(ctx.exception))

    def test_超时不会泄漏原始异常类型(self):
        """用例层只需 except ApiError 即可，不必关心底层是哪种网络异常。"""
        with mock.patch('Common.apiClient.urllib.request.urlopen',
                        side_effect=TimeoutError('timed out')):
            with self.assertRaises(ApiError):
                self.api.get('/api/x')


class TestResponseParsing(unittest.TestCase):
    """响应解析 —— 接口不一定返回 JSON，硬解析会崩。"""

    def test_json被解析成对象(self):
        self.assertEqual(ApiClient._parse('{"a": 1}'), {'a': 1})

    def test_数组也被解析(self):
        self.assertEqual(ApiClient._parse('[1, 2]'), [1, 2])

    def test_非json原样返回文本(self):
        self.assertEqual(ApiClient._parse('<html>oops</html>'), '<html>oops</html>')

    def test_空响应返回None(self):
        self.assertIsNone(ApiClient._parse(''))

    def test_记录最近一次响应(self):
        api = _make_client()
        with mock.patch('Common.apiClient.urllib.request.urlopen',
                        return_value=_FakeResponse(b'{"a": 1}', 200)):
            api.get('/api/x')
        self.assertEqual(api.last_status, 200)
        self.assertEqual(api.last_body, '{"a": 1}')


class TestConfiguration(unittest.TestCase):
    """配置缺失时的行为 —— 必须说清去哪配。"""

    def test_缺地址时抛出可操作报错(self):
        with patch_config(ini_text='[ci]\nheadless = true\n'):
            with self.assertRaises(ValueError) as ctx:
                ApiClient()
        message = str(ctx.exception)
        self.assertIn('api', message)
        self.assertIn('base_url', message)
        self.assertIn('config.ini', message)

    def test_未配置时is_configured为假(self):
        with patch_config(ini_text='[ci]\nheadless = true\n'):
            self.assertFalse(is_configured())

    def test_配置后is_configured为真(self):
        with patch_config(ini_text='[api]\nbase_url = http://x.local/api\n'):
            self.assertTrue(is_configured())

    def test_地址为空白视为未配置(self):
        with patch_config(ini_text='[api]\nbase_url =   \n'):
            self.assertFalse(is_configured())

    def test_超时可配(self):
        with patch_config(ini_text='[api]\nbase_url = http://x.local\ntimeout = 5\n'):
            self.assertEqual(ApiClient().timeout, 5)


if __name__ == '__main__':
    unittest.main(verbosity=2)
