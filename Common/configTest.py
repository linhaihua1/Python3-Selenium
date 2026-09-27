# -*- coding: utf-8 -*-
"""
==========================================================================
 手工验证脚本：配置读写（新人阅读顺序：可跳过）
==========================================================================

【一句话说明】
    用来手工验证 Common/config.py 能不能正常读写 config.ini，
    不是测试用例，不会被 unittest 收集（文件名不匹配 test*.py）。

【怎么运行】
    python -m Common.configTest

【它做了什么】
    1. 在 config.ini 里新增一个 [demo] 段
    2. 写入 username / password 两个键，再读回来打印
    3. 列出该段所有键名
    4. 最后把 [demo] 段整体删掉，恢复原样

【注意】
    - 运行会真实修改 config.ini 文件，请勿在测试执行期间运行。
    - 内容已经包在 if __name__ == '__main__' 里，
      被 import 时不会执行，可放心引用。
==========================================================================
"""

from Common.config import Config


def main():
    """依次演示「建段 -> 写键值 -> 读 -> 列键 -> 删段」整套配置操作。"""
    section = 'demo'
    test = Config()

    test.config_write(section)                          # 新增空段 [demo]
    test.set_value(section, 'username', '测试')          # 写 username
    test.set_value(section, 'password', '一下')          # 写 password

    print(test.config_read(section, 'username'))         # 读回来：测试
    print(test.config_read(section, 'password'))         # 读回来：一下
    print(test.options(section))                         # ['username', 'password']

    test.config_delete(section)                          # 删掉整段，清理现场


if __name__ == '__main__':
    main()
