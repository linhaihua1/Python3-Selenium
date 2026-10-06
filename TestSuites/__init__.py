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
    testLogin.py           主用例集：6 条串行业务用例
                           （登录 -> 进系统 -> 素材库 -> 上传 -> 查询 -> 报送）
                           前 3 条标了 @readonly，后 3 条会写数据
    testMaterialCheck.py   只读用例样板：3 条独立校验，类上标了 scope = 'readonly'
                           新手写新用例建议先抄它

【写新用例的模板】
    from Common.testcase_meta import readonly

    class TestXxx(unittest.TestCase):
        # 整类都不写数据时加这一行；生产环境只跑只读用例时靠它放行
        scope = 'readonly'

        @classmethod
        def setUpClass(cls):        # 打开浏览器、建页面对象，整个类只跑一次
        @classmethod
        def tearDownClass(cls):     # 关闭浏览器
        def test_1_yyy(self):       # 方法名 test_ 开头才会被收集；加数字前缀可固定顺序
            页面对象.做某事()
            self.assertEqual(实际值, 期望值)

【★ 新增用例必须做的一件事：标作用域】
    告诉框架"这条用例会不会改动真实数据"，否则一律按"会写"对待，
    在生产特征的环境下会被环境守卫拦下（这是刻意的保守默认）。
        整类只读    -> 类属性 scope = 'readonly'
        单条只读    -> 方法上加 @readonly
        会写数据    -> 什么都不用加（默认就是写）
    规则与理由见 Common/testcase_meta.py；
    完整的上手演示见 docs/实战-写你的第一条用例.md。
==========================================================================
"""
