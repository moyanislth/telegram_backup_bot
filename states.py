#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
状态管理模块：定义 user_data 中使用的状态键，并提供设置/清除状态的函数。
"""

from telegram.ext import ContextTypes

STATE_KEY = "binding_state"
PENDING_USER_KEY = "pending_binding_user_id"
PENDING_CHAT_KEY = "pending_binding_chat_id"
PENDING_TITLE_KEY = "pending_binding_chat_title"


def set_state(context: ContextTypes.DEFAULT_TYPE, state: str) -> None:
    """设置当前会话状态。

    Args:
        context: Telegram 上下文。
        state: 状态字符串。
    """
    context.user_data[STATE_KEY] = state


def clear_state(context: ContextTypes.DEFAULT_TYPE) -> None:
    """清除当前会话的所有绑定相关状态。

    Args:
        context: Telegram 上下文。
    """
    for key in [
        STATE_KEY,
        PENDING_USER_KEY,
        PENDING_CHAT_KEY,
        PENDING_TITLE_KEY,
    ]:
        context.user_data.pop(key, None)