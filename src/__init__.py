# -*- coding:utf-8 -*-
# @Author      : Cao Zejun
# @Time        : 2025/07/08
# @File        : __init__.py
# @description : src包初始化文件

# 轻量依赖保持在包初始化阶段即可，避免测试或局部导入时被无关第三方依赖阻塞
from .crawler import WechatRequest
from .utils import (Message_Info, check_text_ratio, data_manager, headers,
                    jstime2realtime, message_is_delete, nunjucks_escape,
                    realtime2jstime, time_delta, time_now, url2text)

__all__ = [
    # 从crawler模块导入
    'WechatRequest',
    # 从processor模块导入
    'minHashLSH',
    'get_valid_message',
    # 从utils模块导入
    'data_manager',
    'Message_Info',
    'headers',
    'time_now',
    'time_delta',
    'jstime2realtime',
    'realtime2jstime',
    'url2text',
    'message_is_delete',
    'check_text_ratio',
    'nunjucks_escape',
    # 从web模块导入
    'generate_summary_markdown',
    'generate_single_posts',
]


def __getattr__(name):
    if name in {'minHashLSH', 'get_valid_message'}:
        from .processor import get_valid_message, minHashLSH

        return {
            'minHashLSH': minHashLSH,
            'get_valid_message': get_valid_message,
        }[name]
    if name in {'generate_summary_markdown', 'generate_single_posts'}:
        from .web import generate_single_posts, generate_summary_markdown

        return {
            'generate_summary_markdown': generate_summary_markdown,
            'generate_single_posts': generate_single_posts,
        }[name]
    raise AttributeError(f"module 'src' has no attribute {name!r}")
