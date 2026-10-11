# -*- coding: utf-8 -*-
"""
==========================================================================
 接口层客户端（企业级「测试分层」的地基）
==========================================================================

【解决什么问题：测试金字塔倒置】
    本工程改造前只有 UI 层测试（9 条，全部开浏览器）。这带来三个问题：
      ① 慢 —— 每条用例几秒到几十秒，回归一次几分钟到几十分钟
      ② 脆 —— 前端改版、元素调整都会误伤，红的常常不是真问题
      ③ 贵 —— 维护成本最高，但不该由它来验证"接口返回对不对"

    企业级做法是**测试金字塔**：大量接口/单元测试打底，UI 只覆盖关键业务链路。
    接口层能验证的东西（字段校验、边界值、权限、状态流转），
    不应该放到 UI 层去验证。

【在框架中的位置】
    TestSuites/test*Api*.py       接口层用例：断言接口返回
        └─> Common/apiClient.py   <- 本文件：一个客户端封装所有 HTTP 细节
              └─> requests / urllib
    TestSuites/testLogin.py       UI 层用例：只验证关键链路的界面表现

【设计要点】
    1. **不引入第三方测试框架**：纯 unittest，与本工程其余部分一致
    2. **会话保持**：自动维持 Cookie/Token，省去每条用例手工登录取 Token
    3. **失败可读**：非 2xx 时抛出带「请求 + 响应片段」的异常，
       而不是让人对着一个 401 猜是账号错了还是 Token 过期了
    4. **可观测**：每个请求都记日志（方法、URL、状态码、耗时），
       CI 上排查"接口是不是返 500 了"只需 grep
==========================================================================
"""

import json
import time
import urllib.error
import urllib.parse
import urllib.request

from Common.config import Config
from Common.log import log1

#: 认为"成功"的状态码区间
SUCCESS_RANGE = (200, 300)


class ApiError(Exception):
    """接口调用失败（网络错误或非 2xx）。

    刻意把「请求信息」和「响应片段」都带上 —— 排查时最有用的就是这两样。
    """

    def __init__(self, message, method='', url='', status=None, body=''):
        self.method = method
        self.url = url
        self.status = status
        self.body = body
        super().__init__(message)

    def __str__(self):
        parts = [super().__str__()]
        if self.method or self.url:
            parts.append('    请求：%s %s' % (self.method, self.url))
        if self.status is not None:
            parts.append('    状态码：%s' % self.status)
        if self.body:
            parts.append('    响应片段：%s' % str(self.body)[:300])
        return '\n'.join(parts)


class ApiClient(object):
    """轻量 HTTP 客户端：会话保持 + 统一日志 + 可读错误。

    典型用法::

        api = ApiClient(base_url=Config.get('api', 'base_url'))
        api.login('/api/login', {'username': u, 'password': p})
        data = api.get('/api/materials', params={'keyword': '测试'})
        self.assertEqual(data['total'], 1)

    本类只负责"发请求、取数据、报错误"，**不做断言** ——
    断言是用例层的职责（与其他层一致）。
    """

    def __init__(self, base_url=None, headers=None, timeout=None, token=None):
        """
        :param base_url: 接口根地址；不传则读 config.ini -> [api] base_url
        :param headers:  默认请求头（会与每次请求的 headers 合并）
        :param timeout:  超时秒数；不传读 [api] timeout，默认 30
        :param token:    已持有的令牌；一般由 login() 自动获取
        """
        # ★ 必填读取：接口地址缺失时立刻报错并说明去哪配，
        #   而不是等到发请求时报一个看不懂的 URLError
        self.base_url = (base_url or Config.get_required(
            'api', 'base_url', '接口层测试的根地址')).rstrip('/')
        self.timeout = timeout or Config.get_int('api', 'timeout', 30)
        self.headers = {
            'Content-Type': 'application/json; charset=utf-8',
            'Accept': 'application/json',
        }
        if headers:
            self.headers.update(headers)
        self.token = token
        if token:
            self.headers['Authorization'] = 'Bearer %s' % token
        #: 最近一次响应，便于用例断言状态码
        self.last_status = None
        self.last_body = None

    # ------------------------------------------------------------------ #
    # 认证
    # ------------------------------------------------------------------ #
    def login(self, path=None, credentials=None):
        """登录并自动记住令牌。

        :param path:        登录接口路径；不传读 [api] login_path
        :param credentials: {'username':..,'password':..}；
                            不传则读 [testcase] 的账号密码（与 UI 层共用，避免两处维护）
        :return: 服务器返回的 JSON（dict）

        令牌位置可配（[api] token_field，默认 'token'），因为不同系统
        返回结构不一样（有的是 data.token，有的是 access_token）。
        """
        path = path or Config.get('api', 'login_path', '/api/login')
        if credentials is None:
            username, password = Config.get_account()
            credentials = {'username': username, 'password': password}

        data = self.post(path, credentials)
        field = Config.get('api', 'token_field', 'token')
        token = self._dig(data, field)
        if token:
            self.token = token
            self.headers['Authorization'] = 'Bearer %s' % token
            log1.info('接口登录成功，已获取令牌')
        else:
            log1.warning('接口登录返回里没找到令牌字段 [%s]，'
                         '若接口不需要认证可忽略；否则请检查 [api] token_field' % field)
        return data

    @staticmethod
    def _dig(data, field):
        """从返回结构里取字段，支持 a.b 形式的嵌套路径（如 data.token）。"""
        current = data
        for part in str(field).split('.'):
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                return None
        return current

    # ------------------------------------------------------------------ #
    # 通用动作
    # ------------------------------------------------------------------ #
    def get(self, path, params=None, headers=None):
        """GET 请求，返回解析后的 JSON（或原始文本）。"""
        return self.request('GET', path, params=params, headers=headers)

    def post(self, path, json_body=None, params=None, headers=None):
        """POST 请求（JSON 体）。"""
        return self.request('POST', path, json_body=json_body,
                            params=params, headers=headers)

    def put(self, path, json_body=None, params=None, headers=None):
        """PUT 请求（JSON 体）。"""
        return self.request('PUT', path, json_body=json_body,
                            params=params, headers=headers)

    def delete(self, path, params=None, headers=None):
        """DELETE 请求。"""
        return self.request('DELETE', path, params=params, headers=headers)

    def request(self, method, path, params=None, json_body=None, headers=None):
        """发一次请求。

        :param method:    GET / POST / PUT / DELETE
        :param path:      相对 base_url 的路径，或完整 URL
        :param params:    查询参数（dict）
        :param json_body: 请求体（会被 JSON 序列化）
        :param headers:   本次请求额外的头（覆盖默认头）
        :return: 解析后的响应体（JSON -> dict/list；否则原始文本）
        :raise ApiError: 网络错误或非 2xx 时抛出（消息里带请求与响应片段）
        """
        url = path if str(path).startswith('http') else self.base_url + '/' + str(path).lstrip('/')
        if params:
            query = urllib.parse.urlencode(
                {k: v for k, v in params.items() if v is not None})
            url = '%s%s%s' % (url, '&' if '?' in url else '?', query)

        merged = dict(self.headers)
        if headers:
            merged.update(headers)

        payload = None
        if json_body is not None:
            payload = json.dumps(json_body).encode('utf-8')

        req = urllib.request.Request(url, data=payload, headers=merged, method=method)
        started = time.time()
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                status = resp.status
                raw = resp.read().decode('utf-8', errors='replace')
        except urllib.error.HTTPError as exc:
            # 4xx/5xx：读一段响应体，这对排查最有价值（往往写着具体原因）
            body = ''
            try:
                body = exc.read().decode('utf-8', errors='replace')
            except Exception:       # pragma: no cover
                pass
            self.last_status, self.last_body = exc.code, body
            log1.error('接口返回非 2xx：%s %s -> %s' % (method, url, exc.code))
            raise ApiError('接口返回 %s' % exc.code, method, url, exc.code, body)
        except urllib.error.URLError as exc:
            log1.error('接口请求失败：%s %s -> %s' % (method, url, exc.reason))
            raise ApiError('接口请求失败：%s' % exc.reason, method, url)
        except Exception as exc:            # noqa: BLE001 - 兜底成 ApiError，便于用例统一处理
            log1.error('接口请求异常：%s %s -> %s' % (method, url, exc))
            raise ApiError('接口请求异常：%s' % exc, method, url)

        elapsed = round((time.time() - started) * 1000)
        self.last_status, self.last_body = status, raw
        log1.info('接口调用：%s %s -> %s（%d ms）' % (method, url, status, elapsed))

        if not (SUCCESS_RANGE[0] <= status < SUCCESS_RANGE[1]):
            raise ApiError('接口返回 %s（期望 2xx）' % status, method, url, status, raw)

        return self._parse(raw)

    @staticmethod
    def _parse(raw):
        """尽力解析 JSON；不是 JSON 就原样返回文本。"""
        text = (raw or '').strip()
        if not text:
            return None
        try:
            return json.loads(text)
        except ValueError:
            return text


def is_configured():
    """接口层是否已配置（[api] base_url 有值）。

    用途：接口层用例在没配接口地址时应**优雅跳过**，而不是失败 ——
    很多团队先上 UI 自动化，接口自动化后补，不该因为"还没配"就红一片。
    """
    value = Config.get('api', 'base_url')
    return bool(value and str(value).strip())
