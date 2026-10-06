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
# ★ 基线：当前工程元素表的实测值（2026-10-06）
#   改定位后允许这个数字变小；变大了就说明引入了新的脆弱定位，测试会失败。
# ==========================================================================
BASELINE_TOTAL = 21
BASELINE_FLAWED = 13          # INDEXED + DEEP_INDEX + ABSOLUTE
BASELINE_ABSOLUTE = 2         # first_trial / person_of_first_instance
BASELINE_DEEP_INDEX = 5
BASELINE_MISSING_COMMENT = 0


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

    def test_绝对路径xpath不得超过基线(self):
        self.assertLessEqual(self.stats['absolute'], BASELINE_ABSOLUTE,
                             '绝对路径 xpath 是维护成本最高的写法，不要再新增')

    def test_长链路定位不得超过基线(self):
        self.assertLessEqual(self.stats['deep_index'], BASELINE_DEEP_INDEX)

    def test_每条定位都要有注释(self):
        """元素表是多人共读的文件，没有注释的定位等于给后来人挖坑。"""
        missing = [e['name'] for e in self.entries if not e['comment']]
        self.assertLessEqual(len(missing), BASELINE_MISSING_COMMENT,
                             '这些定位缺注释：%s' % missing)

    def test_最脆弱的两条仍被标注出来(self):
        """锁定已知的最脆弱条目标记 —— 它们被改好时这条会失败，提醒更新基线。

        改好了就把它们从下面的集合里移除，并把 BASELINE_ABSOLUTE 减一。
        """
        known_fragile = {'first_trial', 'person_of_first_instance'}
        actual = {e['name'] for e in self.entries if e['rating'] == ABSOLUTE}
        self.assertEqual(actual, known_fragile,
                         '绝对路径定位清单变了：现在有 %s。若已改善，请下调基线' % actual)

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

    def test_git_head版本与当前版本的定位值一致(self):
        """用 git 里的上一版做对照，确认扫描器对同一份代码给出稳定的结果。

        没有 git 仓库时（比如导出的压缩包）跳过，不让它变成必然失败。
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
        # 允许新增条目，但已有条目的定位值不应被本次改动改动
        for name, value in old.items():
            if name in new:
                self.assertEqual(new[name], value,
                                 '[%s] 的定位值与上一版不一致，改定位必须有意为之' % name)


if __name__ == '__main__':
    unittest.main(verbosity=2)
