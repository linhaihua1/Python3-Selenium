# -*- coding: utf-8 -*-
"""
==========================================================================
 浏览器实例登记处（新人阅读顺序：第 18 个，平时用不到，出问题时靠它）
==========================================================================

【一句话说明】
    记住"当前正开着的浏览器是哪一个"。这样框架在别的地方（比如用例失败要截图时）
    能拿到浏览器对象，而不需要从用例对象上一层层往上找。

【解决什么问题】
    失败自动截图需要在**结果收集器**里拿到 driver。但结果收集器是 unittest 回调的，
    手里只有一条 TestCase 对象，而 driver 挂在用例的类属性上（cls.driver），
    不同项目挂的位置还不一样（cls.driver / cls.base.driver / cls.page.driver…）。
    与其"猜属性名"，不如在浏览器创建时主动登记一次 —— 单一来源，稳定可靠。

【在框架中的位置】
    Common/basePage.py 的 open_browser()  -> register(driver)    创建时登记
    Common/basePage.py 的 dr_quit()       -> unregister(driver)  关闭时注销
    Common/failureCapture.py              -> get_active()        失败时取用

【新人注意】
    1. 本模块只是一张"通讯录"，不持有 driver 的生命周期 ——
       它**不会**替你关浏览器，关浏览器永远是 BasePage.dr_quit() 的事。
    2. 用列表而不是单个变量：并行执行（多个浏览器同时开着）时，
       get_active() 返回**最后登记的那一个**，语义简单可预期。
       真做多线程并行时需要按线程隔离，届时再改成 thread-local。
    3. 单元测试里可以用 clear() 清空，避免用例之间互相影响。
==========================================================================
"""

from typing import Any, List

from Common.log import log1

#: 已登记的 driver，按登记顺序排列；取用时总是取最后一个（最近创建的）
_ACTIVE: List[Any] = []

#: 上限保护：正常流程不会堆积，堆起来说明 dr_quit 忘了调，留个线索
MAX_KEEP = 10


def register(driver):
    """登记一个新创建的浏览器对象。【在用】

    :param driver: selenium WebDriver 实例
    :return: 传入的 driver，方便链式使用
    """
    if driver is None:
        return driver
    # 同一个对象重复登记只保留一份，避免 get_active 拿到"幽灵"引用
    if driver in _ACTIVE:
        _ACTIVE.remove(driver)
    _ACTIVE.append(driver)
    if len(_ACTIVE) > MAX_KEEP:
        # 正常不会发生：说明有浏览器创建了却没调 dr_quit()
        log1.warning('登记的浏览器实例已有 %d 个，可能存在未关闭的浏览器'
                     '（检查用例是否漏调 BasePage.dr_quit）' % len(_ACTIVE))
        del _ACTIVE[:-MAX_KEEP]
    log1.info('已登记浏览器实例，当前共 %d 个' % len(_ACTIVE))
    return driver


def unregister(driver):
    """注销已关闭的浏览器对象。【在用】

    关闭后仍留在列表里会导致失败取证时操作一个已死的 driver，
    抛出的 InvalidSessionIdException 会掩盖真正的失败原因。
    """
    if driver in _ACTIVE:
        _ACTIVE.remove(driver)
        log1.info('已注销浏览器实例，当前共 %d 个' % len(_ACTIVE))


def get_active():
    """取当前可用的浏览器对象；没有则返回 None。【在用】

    只返回**最后登记**的那个 —— 语义是"最近打开的那个浏览器"，
    与"测试正在操作哪个浏览器"通常是一致的。
    """
    return _ACTIVE[-1] if _ACTIVE else None


def clear():
    """清空登记表。【在用：单元测试用】

    注意：只清登记表，不会关闭浏览器。
    """
    del _ACTIVE[:]


def count():
    """当前登记了几个浏览器。【预留】"""
    return len(_ACTIVE)
