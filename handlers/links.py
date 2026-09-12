#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
消息链接处理模块：复制 Telegram 消息链接指向的内容到目标群组。

不做去重，直接复制。
"""

import logging

from telegram import Message
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


async def process_message_link(
    message: Message,
    link_info,
    context: ContextTypes.DEFAULT_TYPE,
    owner_user_id: int,
    target_chat_id: int,
) -> bool:
    """处理 Telegram 消息链接，尝试复制到目标群组。

    Args:
        message: 用户发送的包含链接的消息。
        link_info: parse_message_link 返回的字典，包含 chat 和 message_id。
        context: Telegram 上下文。
        owner_user_id: 资源所属用户 ID（仅用于日志）。
        target_chat_id: 目标群组 Chat ID。

    Returns:
        成功返回 True，失败返回 False。
    """
    source_chat = link_info["chat"]
    source_message_id = link_info["message_id"]

    logger.info(
        "收到消息链接 user_id=%s source=%s message_id=%s target=%s",
        owner_user_id,
        source_chat,
        source_message_id,
        target_chat_id,
    )

    try:
        await context.bot.copy_message(
            chat_id=target_chat_id,
            from_chat_id=source_chat,
            message_id=source_message_id,
        )

    except Exception as exc:
        logger.warning(
            "消息链接保存失败 source=%s message_id=%s: %s",
            source_chat,
            source_message_id,
            exc,
        )

        await message.reply_text(
            "❌ 这个消息链接无法由机器人读取或复制。\n\n"
            "常见原因：\n"
            "• 机器人无法访问源群组/频道\n"
            "• 内容受到 Telegram 的保护，禁止保存/转发\n"
            "• 源消息已删除\n"
            "• 链接指向私有内容，而机器人没有权限\n\n"
            "机器人不会绕过 Telegram 的内容保护限制。"
        )
        return False

    await message.reply_text(
        "✅ 已从消息链接保存到你的资源群组。"
    )
    return True