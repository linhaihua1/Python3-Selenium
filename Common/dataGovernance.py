# -*- coding: utf-8 -*-
"""
==========================================================================
 测试数据治理 + 用例隔离（企业级「测试数据治理」能力）
==========================================================================

【解决什么问题】
    企业级自动化里，写操作用例（上传、提交、创建单据）会在被测系统里留下数据。
    如果不清理，多次跑就会：
      ① 数据膨胀，干扰后续用例的查询/列表断言
      ② 用例失败时半途而废，"半成品数据"污染环境
      ③ 并行执行时，两个用例创建的同名数据互相撞车
    本模块提供一套与业务无关的治理骨架，让"造数—清数"成为用例的标准动作。

【在框架中的位置】
    用例基类可继承 IsolatedTestCase，或直接实例化 TestDataGovernor：

        from Common.dataGovernance import IsolatedTestCase

        class TestUpload(IsolatedTestCase):
            def test_create_material(self):
                name = 'auto_%s' % self.data.tag          # 唯一标记，永不撞名
                self.page.create(name)
                self.data.record('素材:%s' % name, lambda: self.page.delete(name))
                # 用例结束（即使断言失败）-> tearDown 自动调用 delete 清理

【设计原则】
    1. 清理永远不抛异常：清理失败只记日志，绝不能掩盖用例本身的失败结果。
    2. 每条用例独立数据标记：tag 含时间戳+随机串，天然适合并行。
    3. 与业务解耦：治理器只负责"登记回调 + 兜底执行"，清什么由用例自己决定。
==========================================================================
"""

import random
import string
import time
import unittest

from Common.config import Config
from Common.log import log1


def _new_tag():
    """生成唯一数据标记：日期+时分秒+4位随机串。

    形如 20261006_153012_a7f9。同一秒内并行的用例靠随机串区分，
    足够支撑单机数十进程并发不重名。
    """
    ts = time.strftime('%Y%m%d_%H%M%S')
    rand = ''.join(random.choices(string.ascii_lowercase + string.digits, k=4))
    return '%s_%s' % (ts, rand)


class TestDataGovernor(object):
    """单条用例的数据治理器：登记创建的数据，结束时统一清理。

    用法：
        gov = TestDataGovernor()
        gov.record('素材:abc', cleaner_callable)   # 创建数据后登记
        gov.record('报送单:123', cleaner_callable)
        ...
        gov.cleanup_all()                           # tearDown 里调用，全部清理

    每条用例应持有**自己的** governor 实例，互不影响（便于并行与隔离）。
    """

    def __init__(self, tag=None):
        self.tag = tag or _new_tag()
        self._cleanups = []          # [(标识, 清理回调), ...]，按登记顺序
        self._cleaned = False

    # ------------------------------------------------------------------ API
    def record(self, label, cleaner):
        """登记一条待清理数据。

        :param label:   人类可读标识，只用于日志（如 '素材:abc_20261006...'）
        :param cleaner: 无参可调用对象，执行真正的清理（如删除该数据）
        """
        if not callable(cleaner):
            raise TypeError('cleaner 必须是可调用对象，得到: %r' % type(cleaner))
        self._cleanups.append((label, cleaner))
        log1.info('登记待清理数据：%s（当前累计 %d 条）' % (label, len(self._cleanups)))

    def cleanup_all(self):
        """执行全部清理回调。**永不抛异常**。

        :return: 清理结果列表 [(label, ok, error_msg), ...]
        """
        if self._cleaned:
            return []
        self._cleaned = True
        results = []
        # 倒序清理：后创建的先清，避免依赖顺序的清理被前置对象挡住
        for label, cleaner in reversed(self._cleanups):
            try:
                cleaner()
                results.append((label, True, ''))
                log1.info('清理数据成功：%s' % label)
            except BaseException as exc:
                # 清理失败绝不能影响用例结果，只记日志
                results.append((label, False, repr(exc)))
                log1.error('清理数据失败：%s（原因：%r）' % (label, exc))
        self._cleanups = []
        return results

    @property
    def pending(self):
        """尚未清理的待清理数据条数。"""
        return len(self._cleanups)


def cleanup_enabled():
    """是否启用自动清理。读 [testcase] auto_cleanup，默认开启。

    对应环境变量 UI_TESTCASE_AUTO_CLEANUP。调试时可设为 false 保留现场。
    """
    return Config.get_bool('testcase', 'auto_cleanup', True)


class IsolatedTestCase(unittest.TestCase):
    """用例隔离基类：让"造数—清数"和"状态复位"成为标准动作。

    继承它的用例自动获得：
      1. self.data ：一条用例一个 TestDataGovernor，登记的清理在 tearDown 必执行
      2. self.data.tag ：唯一数据标记，创建数据时带上它，避免撞名与污染
      3. reset_state() 钩子：tearDown 里调用，子类可覆盖以"回到已知起始页"

    【为什么清理放在 tearDown 且用 try/finally】
        用例中途断言失败会直接跳到 tearDown。若清理不放在 tearDown，
        失败用例留下的数据就没人管。这里保证：**只要 setUp 成功，
        清理就一定会跑**，且清理异常不会把"用例失败"改写成"用例错误"。
    """

    # 子类可覆盖治理器类型（如接入数据库清数器）
    governor_class = TestDataGovernor

    def setUp(self):
        """每条用例前置：创建独立的数据治理器。"""
        super(IsolatedTestCase, self).setUp()
        self.data = self.governor_class()

    def reset_state(self):
        """状态复位钩子。tearDown 时调用。

        默认什么都不做。子类可覆盖，例如让浏览器回到固定起始页、
        关闭弹窗等，保证下一条用例从干净状态开始。
        """
        pass

    def tearDown(self):
        """每条用例后置：先复位状态，再清理数据。任何一步异常都不影响用例结果。"""
        try:
            try:
                self.reset_state()
            except BaseException as exc:
                log1.error('状态复位失败（不影响用例结果）：%r' % exc)
            if cleanup_enabled() and getattr(self, 'data', None) is not None:
                self.data.cleanup_all()
        finally:
            try:
                super(IsolatedTestCase, self).tearDown()
            except BaseException:
                pass
