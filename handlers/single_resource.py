#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
单条资源处理模块：处理用户发来的单条资源消息。

不做去重，直接复制到目标群组。
"""

import logging

from telegram import Message
from telegram.ext import ContextTypes

from helpers import resource_type

logger = logging.getLogger(__name__)


async def process_single_message(
    message: Message,
    context: ContextTypes.DEFAULT_TYPE,
    owner_user_id: int,
    target_chat_id: int,
) -> None:
    """处理单条资源消息，直接复制到目标群组。

    Args:
        message: 用户发来的消息。
        context: Telegram 上下文。
        owner_user_id: 资源所属用户 ID（仅用于日志）。
        target_chat_id: 目标群组 Chat ID。
    """
    logger.info(
        "收到资源 user_id=%s type=%s message_id=%s target=%s",
        owner_user_id,
        resource_type(message),
        message.message_id,
        target_chat_id,
    )

    try:
        copied = await message.copy(
            chat_id=target_chat_id,
        )

    except Exception as exc:
        logger.exception(
            "资源保存失败 user_id=%s target=%s: %s",
            owner_user_id,
            target_chat_id,
            exc,
        )
        await message.reply_text(
            "❌ 保存失败，请检查目标资源群组和机器人的权限。"
        )
        return

    logger.info(
        "资源保存成功 user_id=%s target=%s saved_message_id=%s",
        owner_user_id,
        target_chat_id,
        copied.message_id,
    )

    await message.reply_text("✅ 已保存到你的资源群组。")