# -*- coding: utf-8 -*-
"""
==========================================================================
单元测试：Common/testcase_meta.py（用例作用域标记）
==========================================================================

测的是"框架怎么判断一条用例会不会写数据"——企业级里最关键的一条判断，
因为它直接决定"生产环境上会不会被拦下"。

覆盖：
    1. 两条设置途径：类属性 scope、方法装饰器 @readonly / @write
    2. 优先级：方法级 > 类级 > 默认
    3. 默认值是 write（刻意的失败安全设计）
    4. 非法值安静退回默认，绝不抛异常
    5. 装饰器不改变方法本身的行为与顺序

样例类统一放在 tests/samples.py，用 `samples.XxxCase('方法名')` 引用 ——
这是本工程的硬性约定，详见该文件头部说明。
==========================================================================
"""

import unittest

from Common.testcase_meta import (
    DEFAULT_SCOPE, READONLY, WRITE, is_readonly, readonly, scope_of, write,
)
from tests import samples


class TestScopeOf(unittest.TestCase):
    """scope_of() 的判定规则。"""

    def test_类级标记只读时整类生效(self):
        case = samples.ReadonlyByClassCase('test_a')
        self.assertEqual(scope_of(case), READONLY)
        self.assertTrue(is_readonly(case))

    def test_没有标记时默认算写用例(self):
        """★ 这是最重要的一个断言：默认必须偏保守。

        若把默认改成只读，那么"忘了标记的写用例"会被放行到生产环境，
        代价是真实上传、真实报送 —— 两种错误的代价完全不对等。
        """
        case = samples.WriteByDefaultCase('test_a')
        self.assertEqual(scope_of(case), WRITE)
        self.assertFalse(is_readonly(case))
        self.assertEqual(DEFAULT_SCOPE, WRITE, '默认作用域必须是 write')

    def test_类级显式写(self):
        case = samples.WriteByClassCase('test_a')
        self.assertEqual(scope_of(case), WRITE)

    def test_方法级标记优先于类级(self):
        """类标了 readonly，某条方法用 @write 改回来 —— 认方法级的。"""
        inherited = samples.MixedScopeCase('test_inherit_readonly')
        overridden = samples.MixedScopeCase('test_override_write')
        self.assertEqual(scope_of(inherited), READONLY)
        self.assertEqual(scope_of(overridden), WRITE)

    def test_只有方法标记也能生效(self):
        ro = samples.OnlyMarkedReadonlyCase('test_readonly_one')
        wr = samples.OnlyMarkedReadonlyCase('test_write_one')
        self.assertEqual(scope_of(ro), READONLY)
        self.assertEqual(scope_of(wr), WRITE)

    def test_非法值退回默认而不抛异常(self):
        """scope = '只读'（写成中文）时应安静退回 write，不能把执行搞挂。"""
        case = samples.BadScopeValueCase('test_a')
        self.assertEqual(scope_of(case), WRITE)

    def test_传类或传实例结果一致(self):
        by_class = scope_of(samples.ReadonlyByClassCase)
        by_instance = scope_of(samples.ReadonlyByClassCase('test_a'))
        self.assertEqual(by_class, by_instance)


class TestDecorators(unittest.TestCase):
    """@readonly / @write 这两个装饰器本身的契约。"""

    def test_readonly返回原函数不改变调用(self):
        calls = []

        @readonly
        def func(value):
            calls.append(value)
            return value * 2

        self.assertEqual(func(3), 6, '装饰后仍应能正常调用并返回原值')
        self.assertEqual(calls, [3])
        self.assertEqual(scope_of(type('T', (unittest.TestCase,), {'test_x': func})('test_x')),
                         READONLY)

    def test_write可以覆盖类级只读(self):
        class Cls(unittest.TestCase):
            scope = 'readonly'

            @write
            def test_x(self):
                pass

        self.assertEqual(scope_of(Cls('test_x')), WRITE)

    def test_装饰后方法名不变(self):
        """名字变了会导致 unittest 收集不到用例，这是个隐蔽的坑。"""

        @readonly
        def test_something(self):
            pass

        self.assertEqual(test_something.__name__, 'test_something')


class TestRealSuitesScope(unittest.TestCase):
    """拿真实用例集验证一遍 —— 防止"标记写了但没生效"这种低级问题。

    注意：这里只 import 用例类并读属性，**不会执行 setUpClass**，
    所以不会真的打开浏览器。
    """

    def test_素材库自检整类为只读(self):
        from TestSuites.testMaterialCheck import TestMaterialCheck
        for name in ('test_1ready', 'test_2controls', 'test_3keyword'):
            self.assertEqual(scope_of(TestMaterialCheck(name)), READONLY,
                             '%s 应标记为只读（它不产生任何业务数据）' % name)

    def test_登录用例前三条只读后三条为写(self):
        from TestSuites.testLogin import TestLogin
        readonly_names = ('test_1login', 'test_2select_scxt', 'test_3material')
        write_names = ('test_4uplaodbutton', 'test_5keyword', 'test_6submitted')
        for name in readonly_names:
            self.assertEqual(scope_of(TestLogin(name)), READONLY,
                             '%s 只是登录/跳页，应标为只读' % name)
        for name in write_names:
            self.assertEqual(scope_of(TestLogin(name)), WRITE,
                             '%s 会改动真实数据，必须保持写作用域' % name)


if __name__ == '__main__':
    unittest.main(verbosity=2)
