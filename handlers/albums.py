#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Album 处理模块：处理 Telegram 相册（多图/多视频）。

不做去重，直接使用 copy_messages 保留相册结构。
"""

import logging

from telegram import Message
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


async def process_album(
    messages: list[Message],
    context: ContextTypes.DEFAULT_TYPE,
    owner_user_id: int,
    target_chat_id: int,
) -> None:
    """处理一个 Album 中的所有消息。

    Args:
        messages: Album 中的消息列表，已按 message_id 排序。
        context: Telegram 上下文。
        owner_user_id: 资源所属用户 ID（仅用于日志）。
        target_chat_id: 目标群组 Chat ID。
    """
    if not messages:
        return

    album_id = messages[0].media_group_id

    logger.info(
        "开始处理 Album user_id=%s album_id=%s count=%s target=%s",
        owner_user_id,
        album_id,
        len(messages),
        target_chat_id,
    )

    try:
        await context.bot.copy_messages(
            chat_id=target_chat_id,
            from_chat_id=messages[0].chat_id,
            message_ids=[m.message_id for m in messages],
        )

    except Exception as exc:
        logger.exception(
            "Album 保存失败 user_id=%s album_id=%s: %s",
            owner_user_id,
            album_id,
            exc,
        )

        await messages[0].reply_text(
            "❌ Album 保存失败，请检查机器人在目标群组中的权限。"
        )
        return

    logger.info(
        "Album 保存成功 user_id=%s album_id=%s count=%s",
        owner_user_id,
        album_id,
        len(messages),
    )

    await messages[0].reply_text(
        f"✅ 已保存 {len(messages)} 个资源"
    )