# -*- coding: utf-8 -*-
"""
==========================================================================
单元测试：Common/locator_policy.py（元素定位规范 + 防劣化门禁）
==========================================================================

这个文件有两类测试，目的完全不同：

一、工具本身的正确性
    解析器要认得元素表里真实存在的几种写法（行内注释、上一行注释、
    定位值拆成多行、xpath 值内部自带方括号）。解析错了，统计就是错的，
    门禁也就形同虚设。

二、★ 基线门禁（本文件真正的价值）
    元素定位的劣化是渐进的：每次赶工期随手复制一条长 xpath，单看没问题，
    半年后元素表就没法维护了。所以这里把**当前的脆弱程度冻结成基线**：
    新增脆弱定位 -> 测试直接红；把脆弱定位改好 -> 请把基线调低。

    基线只能降，不能升。这样规范才是"一步步收紧"，而不是写完就烂掉。
==========================================================================
"""

import contextlib
import io
import subprocess
import unittest

from Common import locator_policy
from Common.locator_policy import (
    ABSOLUTE, DEEP_INDEX, GOOD, INDEXED, analyze, parse_locators, rate_locator, scan,
)

# ==========================================================================
# ★ 基线：当前工程元素表的实测值
#   改定位后允许这个数字变小；变大了就说明引入了新的脆弱定位，测试会失败。
#
#   2026-10-06 首版：total 21 / flawed 13 / absolute 2 / deep_index 5
#   2026-10-11 治理后：把最脆弱的三条改成语义定位（详见 elementPage 文件头）
#       submission                 长链路+td[8]+button[3]  -> 按「报 送」文字锚定
#       first_trial                /html/body/div[4]/...  -> 按「初审」文字向上找
#       person_of_first_instance   "下拉第 8 项"（会静默选错人）
#                                  -> 改为按人名字构造的 first_trial_person()
#                                     （不再是固定条目，故总数少 1）
#       结果：absolute 2 -> 0，flawed 13 -> 10
#       （同时新增 3 条"业务断言观察点"：material_rows / total_count /
#         first_row_status，均用语义写法，未推高脆弱数）
# ==========================================================================
BASELINE_TOTAL = 23
BASELINE_FLAWED = 10          # INDEXED + DEEP_INDEX + ABSOLUTE
BASELINE_ABSOLUTE = 0         # 绝对路径已清零 —— 这是一条**不许回升**的红线
BASELINE_DEEP_INDEX = 4
BASELINE_MISSING_COMMENT = 0

#: 有意变更过定位值的条目（相对 git HEAD）。
#: 用途：让"定位治理"这种正确操作不被门禁拦住，同时保证**任何**变更都必须
#: 显式登记 —— 漏登记的改动仍然会让测试变红（见 TestCli.test_定位值变更必须是有意为之）。
BENIGN_CHANGES = {
    'submission',               # 长链路+td[8] -> 按「报 送」文字锚定
    'first_trial',              # 绝对路径 -> 按「初审」文字向上找表单项
    'person_of_first_instance',  # 已删除（改为 first_trial_person(姓名) 动态构造）
}


class TestRateLocator(unittest.TestCase):
    """单条定位的评级规则。"""

    def test_用id或css定位算好定位(self):
        for by, value in (('id', 'submit-btn'), ('css', '#app .btn'),
                          ('name', 'username'), ('link_text', '登录')):
            rating, _ = rate_locator(by, value)
            self.assertEqual(rating, GOOD, '%s 定位应该评为 GOOD' % by)

    def test_相对xpath无下标算可接受(self):
        rating, _ = rate_locator('xpath', "//input[@type='file']")
        self.assertEqual(rating, GOOD)

    def test_双斜杠不是绝对路径(self):
        """★ 容易搞错的一点：//div 是"从任意位置查找"，/html/body/div 才是绝对路径。"""
        rating, _ = rate_locator('xpath', "//div[@id='app']/span")
        self.assertNotEqual(rating, ABSOLUTE)

    def test_以html开头的才算绝对路径(self):
        rating, reasons = rate_locator('xpath', '/html/body/div[4]/section/form')
        self.assertEqual(rating, ABSOLUTE)
        self.assertTrue(any('绝对路径' in r for r in reasons))

    def test_三方下标判为长链路(self):
        rating, _ = rate_locator('xpath', "//div[1]/div[2]/form/div[3]/input")
        self.assertEqual(rating, DEEP_INDEX)

    def test_少量下标判为有下标(self):
        rating, _ = rate_locator('xpath', "//main/form/div[2]/div/div/input")
        self.assertEqual(rating, INDEXED)

    def test_用可见文字锚定的xpath放宽为可接受(self):
        """锚在文字上比锚在下标上稳得多，不该和纯下标定位同等对待。"""
        rating, _ = rate_locator(
            'xpath', "(.//*[normalize-space(text())='取 消'])[1]/following::span[1]")
        self.assertEqual(rating, GOOD)

    def test_未知定位方式不被当成好定位混过去(self):
        rating, reasons = rate_locator('sizlle', '#a')     # 故意拼错
        self.assertEqual(rating, INDEXED)
        self.assertTrue(any('未知' in r for r in reasons))


class TestParseLocators(unittest.TestCase):
    """解析器要认得元素表里真实存在的几种写法。"""

    def test_解析普通单行写法(self):
        entries = parse_locators("    Username = ['xpath', \"//input\"]  # 用户名框\n")
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]['name'], 'Username')
        self.assertEqual(entries[0]['by'], 'xpath')
        self.assertEqual(entries[0]['value'], '//input')
        self.assertEqual(entries[0]['comment'], '用户名框')

    def test_解析上一行的独立注释(self):
        """工程里两种注释写法都有，漏认一种会误报"缺注释"。"""
        source = "    # 用户名输入框\n    Username = ['xpath', \"//input\"]\n"
        entries = parse_locators(source)
        self.assertEqual(entries[0]['comment'], '用户名输入框')

    def test_空行会切断注释归属(self):
        """空行之后的那条定位，不该继承上面很远处那条注释。"""
        source = "    # 这是给上面那条的\n\n    Username = ['xpath', \"//input\"]\n"
        entries = parse_locators(source)
        self.assertEqual(entries[0]['comment'], '')

    def test_解析拆成多行的定位值(self):
        """长 xpath 为了不超行长会拆成多行 —— 漏认会让统计凭空少几条。"""
        source = (
            "    submission = ['xpath',\n"
            "                  \"//*[@id='app']/div[2]\"\n"
            "                  \"/table/tbody/tr[1]/td[8]/span\"]\n"
        )
        entries = parse_locators(source)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]['value'],
                         "//*[@id='app']/div[2]/table/tbody/tr[1]/td[8]/span")

    def test_定位值内部的方括号不会被当成收尾(self):
        """xpath 里本身就有 [n] 和 @id='app']，取第一个 ] 会把值截断。"""
        source = "    keyword = ['xpath', \"//*[@id='app']/div[1]/form/input\"]\n"
        entries = parse_locators(source)
        self.assertEqual(entries[0]['value'], "//*[@id='app']/div[1]/form/input")

    def test_普通赋值语句不会被误当成定位(self):
        source = "    DEFAULT_TIMEOUT = 15\n    name = 'abc'\n"
        self.assertEqual(parse_locators(source), [])


class TestAnalyze(unittest.TestCase):
    """统计口径。"""

    def test_统计各项数量(self):
        entries = parse_locators(
            "    a = ['xpath', \"/html/body/div\"]\n"          # ABSOLUTE
            "    b = ['xpath', \"//div[1]/div[2]/div[3]/p\"]\n"  # DEEP_INDEX
            "    c = ['xpath', \"//form/div[2]/input\"]\n"       # INDEXED
            "    d = ['id', 'ok']\n"                             # GOOD
        )
        stats = analyze(entries)
        self.assertEqual(stats['total'], 4)
        self.assertEqual(stats['absolute'], 1)
        self.assertEqual(stats['deep_index'], 1)
        self.assertEqual(stats['indexed'], 1)
        self.assertEqual(stats['flawed'], 3)
        self.assertEqual(stats['xpath_ratio'], 75.0)

    def test_空输入不除零(self):
        stats = analyze([])
        self.assertEqual(stats['total'], 0)
        self.assertEqual(stats['xpath_ratio'], 0.0)


class TestRealElementPage(unittest.TestCase):
    """针对真实元素表的断言 —— 基线门禁。"""

    @classmethod
    def setUpClass(cls):
        cls.entries, cls.stats = scan()

    def test_元素表能解析出条目(self):
        self.assertGreaterEqual(self.stats['total'], BASELINE_TOTAL,
                                '解析出来的条目比基线还少，说明解析器漏认了某种写法')

    def test_脆弱定位数不得超过基线(self):
        """★ 核心门禁：这条红了说明有人新增了脆弱定位。

        怎么办（二选一）：
          1. 把新定位改成 id / 可见文字 / 属性定位（推荐）
          2. 确实改不动，就在注释里写清原因并调高 BASELINE_FLAWED
        """
        self.assertLessEqual(
            self.stats['flawed'], BASELINE_FLAWED,
            '脆弱定位从 %d 条涨到 %d 条。新增：%s\n'
            '提示：python -m Common.locator_policy --issues 可看详情'
            % (BASELINE_FLAWED, self.stats['flawed'],
               '、'.join(n for n in self.stats['flawed_names'])))

    def test_绝对路径xpath为零(self):
        """★ 绝对路径 xpath 已全部清除，**任何一条回升都让测试变红**。

        绝对路径（/html/body/div[4]/...）是维护成本最高的写法：
        页面上多套一层 div 就失效，且失效时报的是"找不到元素"，
        排查时很难联想到是定位写法的问题。所以这里设成零容忍红线。
        """
        fragile_names = ('first_trial', 'person_of_first_instance', 'submission')
        self.assertEqual(
            self.stats['absolute'], BASELINE_ABSOLUTE,
            '绝对路径 xpath 出现 %d 条（应为 %d）：%s\n'
            '    请改用 id / 可见文字 / 属性定位；'
            '不依赖 DOM 层级的定位才扛得住前端改版'
            % (self.stats['absolute'], BASELINE_ABSOLUTE,
               '、'.join(n for n in self.stats['flawed_names'] if n in fragile_names)))

    def test_长链路定位不得超过基线(self):
        self.assertLessEqual(self.stats['deep_index'], BASELINE_DEEP_INDEX)

    def test_每条定位都要有注释(self):
        """元素表是多人共读的文件，没有注释的定位等于给后来人挖坑。"""
        missing = [e['name'] for e in self.entries if not e['comment']]
        self.assertLessEqual(len(missing), BASELINE_MISSING_COMMENT,
                             '这些定位缺注释：%s' % missing)

    def test_已知最脆弱的三条已改造成语义定位(self):
        """★ 锁定治理成果，防止被改回去。

        这三条曾经是全工程最脆弱的（两条绝对路径、"下拉第 8 项"写死序号），
        2026-10-11 已改成语义定位。若它们又变成 ABSOLUTE/DEEP_INDEX，
        说明有人回退了 —— 那会重新引入"改版必挂"和"静默选错人"两类缺陷。
        """
        fixed = {'submission', 'first_trial'}
        by_name = {e['name']: e for e in self.entries}
        for name in fixed:
            if name not in by_name:
                continue
            self.assertNotIn(
                by_name[name]['rating'], (ABSOLUTE, DEEP_INDEX),
                '[%s] 又变回脆弱定位了（%s）—— '
                '它应该是按可见文字锚定的语义定位' % (name, by_name[name]['rating']))

    def test_审核人定位不再依赖下拉序号(self):
        """★ 按人名字定位，不再写死"第 8 项"。

        写死序号的危险在于：人员列表顺序一变就**静默选错人** ——
        选错人不报错、用例照样绿，是最难发现的一类缺陷。
        """
        from Common.elementPage import Element1
        self.assertFalse(
            hasattr(Element1, 'person_of_first_instance'),
            'person_of_first_instance（下拉第 8 项）应已删除，'
            '改用 Element1.first_trial_person(姓名) 按人名字定位')
        self.assertTrue(callable(getattr(Element1, 'first_trial_person', None)),
                        '应提供 first_trial_person(name) 用于按姓名构造定位')
        selector = Element1.first_trial_person('张三')
        self.assertEqual(selector[0], 'xpath')
        self.assertIn('张三', selector[1])
        self.assertNotIn('li[8]', selector[1])

    def test_审核人姓名里的引号被安全转义(self):
        """姓名带单引号时不能让 xpath 语法崩掉。"""
        from Common.elementPage import Element1
        selector = Element1.first_trial_person("O'Brien")
        self.assertNotIn("'O'Brien'", selector[1], '单引号应被转义，否则 xpath 语法错误')

    def test_定位值都与工程实际一致(self):
        """扫描结果要和真实 import 出来的值对得上，防止解析器跑偏。"""
        from Common.elementPage import Element1
        real = {}
        for name in dir(Element1):
            if name.startswith('_'):
                continue
            item = getattr(Element1, name)
            if isinstance(item, list) and len(item) == 2:
                real[name] = item[1]
        parsed = {e['name']: e['value'] for e in self.entries}
        self.assertEqual(sorted(parsed), sorted(real),
                         '解析出的条目名与元素表实际属性不一致')
        for name, value in real.items():
            self.assertEqual(parsed[name], value,
                             '[%s] 解析出的值与元素表实际值不一致' % name)


class TestCli(unittest.TestCase):
    """命令行入口的行为（CI 里靠它当门禁）。

    注意：这里统一把 stdout 吞掉。`main()` 会打印一整份定位清单，
    直接跑会让框架单测的输出被几十行报告淹没，看不出哪里红了。
    """

    def _run_cli(self, argv):
        """调用 CLI 并返回退出码，同时屏蔽它打印的报告。"""
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            return locator_policy.main(argv)

    def test_正常返回0(self):
        self.assertEqual(self._run_cli([]), 0)

    def test_超过阈值时返回1(self):
        self.assertEqual(self._run_cli(['--fail-over', '0']), 1)

    def test_阈值足够大时返回0(self):
        self.assertEqual(self._run_cli(['--fail-over', '999']), 0)

    def test_定位值变更必须是有意为之(self):
        """扫描器对同一份代码要给出稳定结果；定位值变更必须显式登记。

        【为什么改了这条测试】
            旧版直接断言"与上一版逐条一致"，本意是防止有人手滑改错定位。
            但定位治理本身就是要**有意改动**定位值 —— 那条断言会让
            "把绝对路径改成语义定位"这种正确操作反而失败，属于把门禁设反了。

            现在的做法：允许变更，但要求把变更过的条目名写进 BENIGN_CHANGES，
            等于"改定位必须是有意为之并留下记录"。漏登记的变更照样变红。
        """
        try:
            old_src = subprocess.check_output(
                ['git', 'show', 'HEAD:Common/elementPage.py'],
                stderr=subprocess.DEVNULL).decode('utf-8')
        except (subprocess.CalledProcessError, FileNotFoundError, OSError):
            self.skipTest('当前环境没有 git 或没有历史版本')

        with open(locator_policy.default_source_path(), encoding='utf-8') as fp:
            new_src = fp.read()
        old = {e['name']: e['value'] for e in parse_locators(old_src)}
        new = {e['name']: e['value'] for e in parse_locators(new_src)}

        unexpected = []
        for name, value in old.items():
            if name in new and new[name] != value and name not in BENIGN_CHANGES:
                unexpected.append(name)
        self.assertEqual(
            unexpected, [],
            '这些定位值变了但没有登记：%s\n'
            '    若是有意的定位治理，请把它们加入本文件的 BENIGN_CHANGES；\n'
            '    若是手滑改错，请还原。' % unexpected)


if __name__ == '__main__':
    unittest.main(verbosity=2)
