#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
辅助函数模块：提供安全显示名称、资源类型判断等小工具。
"""

import logging

from telegram import Message
from telegram.error import BadRequest

logger = logging.getLogger(__name__)

# 统一的使用说明文案：/help 命令与 help 回调共用（设计愿景要求两处一致）。
HELP_TEXT = (
    "📖 <b>使用说明</b>\n\n"
    "• 发送图片、视频、文件、音频、文字等资源\n"
    "• 多图 Album 会等待片刻后一起处理\n"
    "• 每个用户只会保存到自己的绑定群组\n"
    "• 管理员可以通过「⚙️ 绑定管理」管理用户和群组\n\n"
    "发送 Telegram 消息链接时，机器人会尝试读取它；"
    "但无法绕过 Telegram 的受保护内容、禁止保存/转发限制，"
    "也无法访问机器人没有权限读取的消息。"
)


async def safe_edit(query, text, **kwargs) -> None:
    """编辑回调消息，Telegram 判定内容未变化时静默忽略。

    Args:
        query: CallbackQuery 对象。
        text: 要设置的文本。
        **kwargs: 透传给 edit_message_text 的其他参数
            （如 parse_mode、reply_markup）。
    """
    try:
        await query.edit_message_text(text, **kwargs)
    except BadRequest as exc:
        if "not modified" in str(exc).lower():
            return
        raise


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