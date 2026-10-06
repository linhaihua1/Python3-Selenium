# -*- coding: utf-8 -*-
"""
==========================================================================
 用例作用域标记（新人阅读顺序：第 16 个，写用例时才会用到）
==========================================================================

【一句话说明】
    给用例贴一个标签，说明它"会不会动真实数据"：
        readonly —— 只看不写（打开页面、读文字、校验控件存不存在）
        write    —— 会产生业务副作用（上传文件、提交表单、保存、报送）
    企业里跑自动化最怕的事故就是"不小心在生产环境跑了写用例"，
    这个标签就是用来拦住它的。

【在框架中的位置】
    TestSuites/testXxx.py
        └─> Common/testcase_meta.py       <- 本文件（提供标记与识别）
              └─> Common/runner.py         执行前按标签过滤 / 按环境拦截

【怎么用（两种写法，二选一）】

    写法 A —— 整个类都是只读（最常见）：
        class TestMaterialCheck(unittest.TestCase):
            scope = 'readonly'
            ...

    写法 B —— 同一个类里既有只读又有写用例，逐条标：
        from Common.testcase_meta import readonly

        class TestLogin(unittest.TestCase):
            @readonly
            def test_1login(self): ...      # 登录本身不产生业务数据

            def test_4upload(self): ...     # 没标 = 写用例（默认值）

【为什么默认是 write 而不是 readonly】
    这是刻意的"失败安全"（fail-safe）设计：
    忘了标记 → 被当成写用例 → 在生产环境被拦下 → 最多是"跑不了"；
    反过来若默认只读，忘了标记的写用例就会直接放过，
    后果是真实上传、真实报送 —— 两种错误代价完全不对等。

【新人注意】
    1. 标成 readonly 前请确认：这条用例不点任何"确定/保存/报送/上传"按钮。
       判断标准是「页面数据有没有变」，不是「代码里有没有 click」。
    2. 标记只影响"能不能跑"，不改变用例本身的执行顺序与逻辑。
    3. 冒烟集（config.ini [ci] smoke_cases）会出现写用例时，
       框架会在日志里明确告警（见 Common/runner.py）。
==========================================================================
"""

# ---------------------------------------------------------------------------
# 两个作用域取值。写成常量而不是到处手打字符串，避免拼错（'readonly' vs 'readOnly'）
# ---------------------------------------------------------------------------
READONLY = 'readonly'
WRITE = 'write'

#: 未显式标记时的默认作用域。刻意取 write，理由见文件头「为什么默认是 write」。
DEFAULT_SCOPE = WRITE

#: 允许的取值集合，用于校验配置与标记是否写错
VALID_SCOPES = (READONLY, WRITE)

#: 方法上挂作用域的属性名。用双下划线前缀做"弱私有"，避免与用例自己的属性撞名。
_SCOPE_ATTR = '_ui_case_scope'


def readonly(func):
    """方法装饰器：把这条用例标记为「只读」。【在用】

    用法：
        @readonly
        def test_3keyword(self): ...

    :return: 原函数本身（只是挂了个属性），不会改变执行顺序和行为
    """
    setattr(func, _SCOPE_ATTR, READONLY)
    return func


def write(func):
    """方法装饰器：把这条用例显式标记为「写」。【预留】

    默认就是 write，所以只在"类标了 readonly、但某条想改回写"时才需要它。
    """
    setattr(func, _SCOPE_ATTR, WRITE)
    return func


def _normalize(value):
    """把各种写法统一成小写字符串；空值返回 None。"""
    if value is None:
        return None
    text = str(value).strip().lower()
    return text or None


def scope_of(case):
    """判断一条用例属于 readonly 还是 write。

    :param case: unittest.TestCase 实例（或类，两者都支持）
    :return: 'readonly' 或 'write'

    查找优先级（越具体越优先）：
        1. 用例方法上的标记（@readonly / @write）
        2. 用例类上的 scope 属性
        3. DEFAULT_SCOPE（write）

    为什么要分两级：一个测试类里往往只有一两条会写数据，
    但前置的登录、跳转等步骤本身不写数据。类级标记适合"整类只读"，
    方法级标记适合"只有某几条是写的"。
    """
    # 取出方法与类：传实例时经 type() 拿类，传类时直接用
    if isinstance(case, type):
        cls, method_name = case, None
    else:
        cls = type(case)
        method_name = getattr(case, '_testMethodName', None)

    # 1. 方法级标记
    if method_name:
        method = getattr(cls, method_name, None)
        marked = _normalize(getattr(method, _SCOPE_ATTR, None))
        if marked in VALID_SCOPES:
            return marked

    # 2. 类级标记
    marked = _normalize(getattr(cls, 'scope', None))
    if marked in VALID_SCOPES:
        return marked

    # 3. 兜底
    return DEFAULT_SCOPE


def is_readonly(case):
    """这条用例是否只读（scope_of 的布尔版，用例里读起来更顺）。【在用】"""
    return scope_of(case) == READONLY
