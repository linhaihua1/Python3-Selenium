# -*- coding: utf-8 -*-
"""
单元测试：Common/failureClassifier.py（失败自动归因）

★ 归因的价值在于"准确"：分错类比不分类更糟 ——
  它会把排查的人引到错误的方向。所以这里逐条验证分类规则。
"""

import unittest

from Common import failureClassifier as fc


class TestClassifyMessage(unittest.TestCase):
    """按失败文本归类。"""

    def test_定位失效(self):
        cases = [
            "没有定位到元素,定位方式：xpath，使用的值：//div",
            "NoSuchElementException: Message: no such element: Unable to locate",
            "元素不存在，无法点击：['xpath', '//a']",
            "stale element reference: element is not attached to the page document",
        ]
        for text in cases:
            self.assertEqual(fc.classify_message(text), fc.LOCATOR, text)

    def test_环境问题(self):
        cases = [
            "session not created: This version of ChromeDriver only supports Chrome version 114",
            "chrome not reachable",
            "运行环境自检未通过，已中止执行（退出码 2）",
            "环境守卫拦截，已中止执行",
        ]
        for text in cases:
            self.assertEqual(fc.classify_message(text), fc.ENVIRONMENT, text)

    def test_配置问题(self):
        cases = [
            '缺少必填配置 [assert] title_login（登录后首页标题）',
            '未配置被测地址：请在 config.ini -> [environment] url 填写',
            "NoSectionError: No section: 'assert'",
        ]
        for text in cases:
            self.assertEqual(fc.classify_message(text), fc.CONFIG, text)

    def test_数据问题(self):
        """★ 与配置问题区分：'文件不存在'是数据问题，'没配置路径'是配置问题。

        两者处理人不同：前者看造数/清理，后者改 config.ini。
        """
        cases = [
            '上传文件不存在：D:\\videos\\demo.mp4',
            'FileNotFoundError: [Errno 2] No such file or directory',
        ]
        for text in cases:
            self.assertEqual(fc.classify_message(text), fc.DATA, text)

    def test_未配置路径归到配置问题而非数据问题(self):
        """'未配置' 优先归 CONFIG —— 因为改配置就能解决，不需要查数据。"""
        text = '未配置上传文件路径（config.ini -> [testcase] upload_file）'
        self.assertEqual(fc.classify_message(text), fc.CONFIG)

    def test_超时(self):
        cases = [
            'TimeoutException: Message: timeout',
            '等待标题超时(15s)：期望[A] 实际[B]',
            '接口请求失败：timed out',
        ]
        for text in cases:
            self.assertEqual(fc.classify_message(text), fc.TIMEOUT, text)

    def test_业务断言失败(self):
        """★ 最有价值的一类：可能是真 bug，不该被归到别处。"""
        text = "AssertionError: 上传后素材列表行数未增加：上传前 3 行，等待后仍为 3 行"
        self.assertEqual(fc.classify_message(text), fc.BUSINESS)

    def test_归不了类的返回unknown(self):
        self.assertEqual(fc.classify_message('some totally unrelated error'),
                         fc.UNKNOWN)

    def test_空消息不崩(self):
        self.assertEqual(fc.classify_message(None), fc.UNKNOWN)
        self.assertEqual(fc.classify_message(''), fc.UNKNOWN)

    def test_规则优先级_配置优先于定位(self):
        """同时命中多条时，按规则表顺序取更具体的那条。

        "缺少必填配置" 里可能带上一句元素定位失败，但根因是配置没配。
        """
        text = '缺少必填配置 [assert] title_login；同时 没有定位到元素'
        self.assertEqual(fc.classify_message(text), fc.CONFIG)


class TestClassify(unittest.TestCase):
    """按一条用例结果归类。"""

    def test_成功用例返回None(self):
        category, advice = fc.classify({'status': 'success', 'name': 'x'})
        self.assertIsNone(category)
        self.assertEqual(advice, '')

    def test_每条分类都有处理建议(self):
        """★ 分类的价值一半在"知道找谁"—— 没有建议的分类等于没分。"""
        for category in fc.CATEGORY_INFO:
            label, advice = fc.CATEGORY_INFO[category]
            self.assertTrue(advice.strip(), '%s 缺少处理建议' % category)

    def test_从detail兜底归类(self):
        """message 看不出来时，去堆栈里找线索。"""
        case = {
            'status': 'error', 'name': 'x',
            'message': 'unexpected error',
            'detail': 'Traceback...\nNoSuchElementException: Message: no such element',
        }
        category, _ = fc.classify(case)
        self.assertEqual(category, fc.LOCATOR)


class TestSummarize(unittest.TestCase):
    """批量汇兑 —— CI 上"这批失败主要是什么性质"。"""

    def _cases(self, *items):
        return [{'status': 'failure', 'name': n, 'message': m} for n, m in items]

    def test_成功用例不参与统计(self):
        cases = [{'status': 'success', 'name': 'ok', 'message': ''}]
        summary = fc.summarize(cases)
        self.assertEqual(summary['total_failed'], 0)
        self.assertIsNone(summary['primary'])

    def test_按分类聚合(self):
        cases = self._cases(
            ('test_1', '没有定位到元素'),
            ('test_2', 'NoSuchElementException'),
            ('test_3', '缺少必填配置 [assert] x'),
        )
        summary = fc.summarize(cases)
        self.assertEqual(summary['total_failed'], 3)
        self.assertEqual(len(summary['categories'][fc.LOCATOR]), 2)
        self.assertEqual(len(summary['categories'][fc.CONFIG]), 1)

    def test_数量最多的分类成为主要性质(self):
        cases = self._cases(
            ('test_1', '没有定位到元素'),
            ('test_2', 'NoSuchElementException'),
            ('test_3', '元素不存在，无法点击'),
            ('test_4', 'AssertionError'),
        )
        summary = fc.summarize(cases)
        self.assertEqual(summary['primary'], fc.LOCATOR)
        self.assertEqual(len(summary['categories'][fc.LOCATOR]), 3)

    def test_空列表不崩(self):
        summary = fc.summarize([])
        self.assertEqual(summary['total_failed'], 0)
        self.assertEqual(summary['categories'], {})


class TestFormatDigest(unittest.TestCase):

    def test_没有失败时返回空串(self):
        self.assertEqual(fc.format_digest([]), '')
        self.assertEqual(fc.format_digest([{'status': 'success', 'name': 'a'}]), '')

    def test_有失败时包含分类与建议(self):
        cases = [
            {'status': 'failure', 'name': 'test_4uplaodbutton',
             'message': 'AssertionError: 上传后素材列表行数未增加'},
        ]
        text = fc.format_digest(cases)
        self.assertIn('失败归因', text)
        self.assertIn('业务断言失败', text)
        self.assertIn('test_4uplaodbutton', text)
        self.assertIn('建议', text)
        self.assertIn('结论', text)

    def test_结论指出主要性质(self):
        cases = [
            {'status': 'failure', 'name': 'a', 'message': '没有定位到元素'},
            {'status': 'failure', 'name': 'b', 'message': 'NoSuchElementException'},
        ]
        text = fc.format_digest(cases)
        self.assertIn('定位失效', text)


if __name__ == '__main__':
    unittest.main(verbosity=2)
