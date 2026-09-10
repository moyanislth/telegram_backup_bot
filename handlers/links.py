#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
消息链接处理模块：复制 Telegram 消息链接指向的内容到目标群组。
"""

import logging

from telegram import Message
from telegram.ext import ContextTypes

from resources import (
    save_resource_record,
    update_resource_message_id,
    delete_resource_record,
)

logger = logging.getLogger(__name__)


async def process_message_link(
    message: Message,
    link_info,
    context: ContextTypes.DEFAULT_TYPE,
    owner_user_id: int,
    target_chat_id: int,
) -> bool:
    """处理 Telegram 消息链接，尝试复制到目标群组。

    流程与单条资源一致：先占位插入 DB，再 copy_message，
    成功回填 message_id，失败回滚占位。

    Args:
        message: 用户发送的包含链接的消息。
        link_info: parse_message_link 返回的字典，包含 chat 和 message_id。
        context: Telegram 上下文。
        owner_user_id: 资源所属用户 ID。
        target_chat_id: 目标群组 Chat ID。

    Returns:
        成功返回 True，失败返回 False。
    """
    source_chat = link_info["chat"]
    source_message_id = link_info["message_id"]

    # 链接级去重 key：源 chat + 源 message_id 唯一确定一条源消息。
    unique_key = f"link:{source_chat}:{source_message_id}"

    # 占位插入 DB：先抢 UNIQUE 约束，防止重复链接重复复制。
    inserted = save_resource_record(
        unique_key=unique_key,
        resource_message_id=0,
        resource_type="message_link",
        owner_user_id=owner_user_id,
        target_chat_id=target_chat_id,
    )
    if not inserted:
        logger.info(
            "消息链接已存在，跳过 user_id=%s key=%s target=%s",
            owner_user_id,
            unique_key,
            target_chat_id,
        )
        await message.reply_text("♻️ 资源已存在，没有重复保存。")
        return False

    logger.info(
        "收到消息链接 user_id=%s source=%s message_id=%s target=%s",
        owner_user_id,
        source_chat,
        source_message_id,
        target_chat_id,
    )

    # Bot API 的 copy_message 需要机器人可以访问源消息。
    # from_chat_id 既支持 int（私有群 -100...）也支持 str（公开用户名）。
    try:
        copied = await context.bot.copy_message(
            chat_id=target_chat_id,
            from_chat_id=source_chat,
            message_id=source_message_id,
        )

        # copy_message 返回 MessageId，而不是完整 Message。
        copied_message_id = getattr(copied, "message_id", None)

        if copied_message_id:
            update_resource_message_id(
                unique_key=unique_key,
                target_chat_id=target_chat_id,
                resource_message_id=copied_message_id,
            )

        await message.reply_text(
            "✅ 已从消息链接保存到你的资源群组。"
        )
        return True

    except Exception as exc:
        logger.warning(
            "消息链接保存失败 source=%s message_id=%s: %s",
            source_chat,
            source_message_id,
            exc,
        )

        # 复制失败：回滚占位记录。
        delete_resource_record(unique_key, target_chat_id)

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