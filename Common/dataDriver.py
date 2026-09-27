# -*- coding: utf-8 -*-
"""
==========================================================================
 数据驱动测试（Data-Driven Testing）
==========================================================================

【一句话说明】
    让一条用例跑多组数据。把"测试数据"从用例代码里抽出来，放到 CSV / JSON / Excel，
    改数据不用改代码、也不用重复写用例。覆盖更多场景、回归更充分、维护更省事。

【在框架中的位置】
    data/*.csv|json|xlsx   测试数据文件（放在工程根或用例同目录）
        └─> Common/dataDriver.py   <- 本文件：加载数据 + 参数化用例
              └─> TestSuites/testXxx.py  用例里用 @data_driven 或 load_data()

【两种用法】
    方式 A —— 手动加载（最灵活）：
        from Common.dataDriver import load_data
        rows = load_data('data/users.csv')          # -> [{'name':'张三',...}, ...]
        for row in rows:
            self.login(row['name'], row['pwd'])

    方式 B —— 参数化生成多条用例（推荐，报告里每组数据是独立用例）：
        from Common.dataDriver import data_driven, load_data
        @data_driven(load_data('data/login.csv'))
        def test_login(self, row):
            self.login(row['name'], row['pwd'])
    运行后，每组数据会变成 test_login[0]、test_login[1]... 分别报告、互不影响。

【支持的数据格式】
    CSV   ：第一行是表头（字段名），其余行是数据；逗号分隔，utf-8
    JSON  ：对象数组，如 [{"name":"张三"}, {"name":"李四"}]
    Excel ：.xlsx，第一个 sheet，第一行表头；需 pip install openpyxl
==========================================================================
"""

import csv
import json
import os

from Common.log import log1


def _resolve_path(path):
    """把相对路径解析成绝对路径（相对工程根目录）。"""
    if os.path.isabs(path):
        return path
    import getcwd
    return os.path.join(getcwd.get_cwd(), path)


def load_csv(path):
    """加载 CSV，返回字典列表（第一行作字段名）。"""
    path = _resolve_path(path)
    with open(path, 'r', encoding='utf-8-sig', newline='') as f:
        return [dict(row) for row in csv.DictReader(f)]


def load_json(path):
    """加载 JSON，返回对象数组。"""
    path = _resolve_path(path)
    with open(path, 'r', encoding='utf-8-sig') as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError('JSON 数据文件必须是数组（对象列表）：%s' % path)
    return data


def load_excel(path, sheet=0):
    """加载 Excel(.xlsx) 第一个 sheet，第一行作表头，返回字典列表。

    依赖 openpyxl；未安装时给出明确提示，而不是抛一个看不懂的 ImportError。
    """
    try:
        import openpyxl                       # 延迟导入：不用 Excel 就无需装这个依赖
    except ImportError:
        raise ImportError('读取 Excel 需要 openpyxl，请先执行：pip install openpyxl')
    path = _resolve_path(path)
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb[sheet] if isinstance(sheet, int) else wb[sheet]
    rows = list(ws.iter_rows(values_only=True))
    wb.close()
    if not rows:
        return []
    headers = [str(h).strip() if h is not None else '' for h in rows[0]]
    result = []
    for r in rows[1:]:
        if all(c is None or str(c).strip() == '' for c in r):
            continue                          # 跳过全空行
        result.append({headers[i]: (r[i] if i < len(r) else None) for i in range(len(headers))})
    return result


# 扩展名 -> 加载函数 的路由表；新增格式只需在这里加一项
_LOADERS = {
    '.csv': load_csv,
    '.json': load_json,
    '.xlsx': load_excel,
    '.xls': load_excel,
}


def load_data(path, sheet=0):
    """按扩展名自动选择加载器，返回字典列表。

    :param path:  数据文件路径（相对工程根或绝对路径）
    :param sheet: Excel 的 sheet（序号或名称），其它格式忽略
    :return: list[dict]
    """
    ext = os.path.splitext(path)[1].lower()
    loader = _LOADERS.get(ext)
    if loader is None:
        raise ValueError('不支持的数据格式 %s，支持：%s' % (ext, ', '.join(_LOADERS)))
    data = loader(path) if ext in ('.xlsx', '.xls') else loader(path)
    log1.info('加载数据文件 %s，共 %d 条' % (path, len(data)))
    return data


def data_driven(dataset):
    """参数化装饰器：把一条用例方法展开成「每组数据一条」用例。

    用法：
        @data_driven(load_data('data/login.csv'))
        def test_login(self, row):
            ...

    实现原理：给被装饰的方法打上 `_ddt_dataset` 属性，
    由 Common/ddt_loader.py（或用例基类）在收集时展开成多条用例。
    为兼容 unittest 默认发现机制，这里采用「子用例索引」命名：
        test_login -> test_login_0 / test_login_1 / ...

    注意：被装饰的方法签名必须是 (self, row)。
    """
    def decorator(func):
        func._ddt_dataset = list(dataset)
        return func
    return decorator


def expand_ddt_cases(test_case):
    """把一个 TestCase 实例里带 @data_driven 的方法展开成多条独立用例。

    返回一个新的 TestSuite，每个子用例执行时会把对应那行数据传进去。
    供用例基类或收集层调用，普通用例直接用装饰器即可。

    设计：不依赖 pytest，纯 unittest 实现，保持框架零额外依赖。
    """
    import unittest

    suite = unittest.TestSuite()
    cls = type(test_case)
    for name in dir(cls):
        method = getattr(cls, name, None)
        dataset = getattr(method, '_ddt_dataset', None)
        if not callable(method) or dataset is None:
            continue
        for idx, row in enumerate(dataset):
            sub_name = '%s_%d' % (name, idx)

            def _make(meth, data):
                def _runner(self):
                    meth(self, data)
                return _runner

            runner = _make(method, row)
            # 动态建一个带单条子用例的临时类，让 unittest 能正常收集与报告
            sub_cls = type('%s_%s' % (cls.__name__, sub_name), (unittest.TestCase,), {sub_name: runner})
            suite.addTest(sub_cls(sub_name))
    return suite
