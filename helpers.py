#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
辅助函数模块：提供安全显示名称、资源类型判断等小工具。
"""

from telegram import Message


def safe_display_name(row) -> str:
    """从数据库行中提取安全的显示名称。

    优先使用 display_name，其次 @username，最后 user_id。

    Args:
        row: sqlite3.Row 或类似字典对象，包含 display_name、username、user_id。

    Returns:
        显示名称字符串。
    """
    display_name = row["display_name"] if row and row["display_name"] else ""
    username = row["username"] if row and row["username"] else ""

    if display_name:
        return display_name
    if username:
        return f"@{username}"
    return str(row["user_id"]) if row else "未知用户"


def resource_type(message: Message) -> str:
    """判断消息的资源类型。

    Args:
        message: Telegram Message 对象。

    Returns:
        资源类型字符串：photo、video、document、audio、voice、animation、
        video_note、text 或 other。
    """
    if message.photo:
        return "photo"
    if message.video:
        return "video"
    if message.document:
        return "document"
    if message.audio:
        return "audio"
    if message.voice:
        return "voice"
    if message.animation:
        return "animation"
    if message.video_note:
        return "video_note"
    if message.text:
        return "text"
    return "other"