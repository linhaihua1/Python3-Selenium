# -*- coding: utf-8 -*-
"""
==========================================================================
 手工验证脚本：日志输出（新人阅读顺序：可跳过）
==========================================================================

【一句话说明】
    用来手工验证 Common/log.py 的日志能不能正常落到文件，
    不是测试用例，不会被 unittest 收集（文件名不匹配 test*.py）。

【怎么运行】
    python -m Common.logTest

【它做了什么】
    故意制造一个 ZeroDivisionError（除以零），观察三件事：
      1. log1.info 会不会写进 Logs/日期/All_Logs/
      2. log1.error(exc_info=1) 会不会写进 Error_Logs/ 并带上异常堆栈
      3. 控制台有没有同步输出

【新人重点看这一行】
    log1.error('test', exc_info=1)
    exc_info=1 表示"把当前异常堆栈一起记下来"，
    这是排错时最有价值的信息，捕获异常时务必带上它。
    如果写成 log1.info('结果:', r) 这种多参数形式会报错 ——
    logging 不支持这种写法，必须自己用 % 或 f-string 拼好字符串。
==========================================================================
"""

from Common.log import log1


def main():
    """制造一次异常，验证三个 handler（全量/错误/控制台）都在正常工作。"""
    log1.info('开始测试')
    try:
        result = 10 / 0
        # 下面这行不会执行到；这里演示正确的格式化写法：
        log1.info('result: %s' % result)
    except ZeroDivisionError:
        # exc_info=1 会把异常堆栈一并写进日志，排错必用
        log1.error('test', exc_info=1)
    log1.info('end')


if __name__ == '__main__':
    main()
