# -*- coding: utf-8 -*-
"""
==========================================================================
 定制版 ConfigParser（新人阅读顺序：第 12 个，用到配置出问题再来看）
==========================================================================

【一句话说明】
    Python 标准库 configparser.ConfigParser 的一个小改造版，
    只改了两处默认行为，都是被真实故障逼出来的。

【在框架中的位置】
    Common/config.py 里 `config = ConfigOverWrite()` 用的就是它。
    本文件不依赖任何其他工程模块。

【改造点 1：保留键名大小写】
    标准 ConfigParser 会把所有键名转成小写，于是：
        [addressed]
        张三 = zs@qq.com      ->  被读成  '张三' 还好，但英文键会变成小写
    这在收件人姓名、需要区分大小写的配置上会出问题，所以重写 optionxform 原样返回。

【改造点 2：关闭 % 插值】
    标准 ConfigParser 默认把 % 当插值符，配置里出现单个 % 会直接抛
    InterpolationSyntaxError，例如：
        upload_file = D:\\视频\\100%素材\\a.mp4
        login_password = ab%cd123
    本工程按「原样字符串」处理配置，不需要插值，所以传 interpolation=None 关掉。

【新人注意】
    如果你发现"配置读出来的值和文件里写的不一样"，先怀疑是不是这两个行为没生效 ——
    确认 config = ConfigOverWrite() 而不是 ConfigParser()。
==========================================================================
"""

import configparser


class ConfigOverWrite(configparser.ConfigParser):
    """保留键名大小写、且不做 % 插值的配置解析器。"""

    def __init__(self, defaults=None):
        # interpolation=None 关闭 % 插值，避免路径/密码中的 % 触发解析异常
        super().__init__(defaults=defaults, interpolation=None)

    def optionxform(self, optionstr):
        """覆盖父类的键名转换逻辑：父类默认 str.lower()，这里原样返回。

        因此 config.ini 里 [addressed] 段的键写成什么样，读出来就是什么样。
        """
        return optionstr
