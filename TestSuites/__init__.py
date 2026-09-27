# -*- coding: utf-8 -*-
"""
==========================================================================
 TestSuites 用例层（包标识文件）
==========================================================================

【本层职责】
    写测试用例：组织业务步骤、断言期望结果。

【用例怎么被发现的】
    Common/runner.py 调用 unittest 的 discover：
        discover(start_dir=TestSuites, pattern='test*.py', top_level_dir=工程根)
    因此有两条硬性要求：
      1. 文件名必须匹配 test*.py（例如 testLogin.py）；
         叫 loginTest.py 是收集不到的。
      2. 本目录必须有 __init__.py（就是这个文件），否则 discover 扫不进来。

【本目录文件】
    testLogin.py   主用例集：6 条串行业务用例（登录 -> 进系统 -> 素材库 -> 上传 -> 查询 -> 报送）
    testHome.py    空占位模块，无用例，可删

【写新用例的模板】
    class TestXxx(unittest.TestCase):
        @classmethod
        def setUpClass(cls):        # 打开浏览器、建页面对象，整个类只跑一次
        @classmethod
        def tearDownClass(cls):     # 关闭浏览器
        def test_1_yyy(self):       # 方法名 test_ 开头才会被收集；加数字前缀可固定顺序
            页面对象.做某事()
            self.assertEqual(实际值, 期望值)
==========================================================================
"""
