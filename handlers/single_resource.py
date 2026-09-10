#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
单条资源处理模块：处理用户发来的单条资源消息。
"""

import logging

from telegram import Message
from telegram.ext import ContextTypes

from resources import (
    get_message_unique_key,
    save_resource_record,
    update_resource_message_id,
    delete_resource_record,
    resource_type,
)

logger = logging.getLogger(__name__)


async def process_single_message(
    message: Message,
    context: ContextTypes.DEFAULT_TYPE,
    owner_user_id: int,
    target_chat_id: int,
) -> None:
    """处理单条资源消息。

    流程：
    1. 生成去重 key。
    2. 先用占位记录插入 DB（message_id=0），利用 UNIQUE 约束抢锁。
    3. 占位失败说明重复，直接跳过。
    4. 复制消息到目标群组。
    5. 复制成功回填真实 message_id；复制失败回滚占位记录。

    Args:
        message: 用户发来的消息。
        context: Telegram 上下文。
        owner_user_id: 资源所属用户 ID。
        target_chat_id: 目标群组 Chat ID。
    """
    key = get_message_unique_key(message)

    logger.info(
        "收到资源 user_id=%s type=%s message_id=%s target=%s key=%s",
        owner_user_id,
        resource_type(message),
        message.message_id,
        target_chat_id,
        key,
    )

    # 占位插入 DB：先抢 UNIQUE 约束，防止并发重复复制。
    if key:
        inserted = save_resource_record(
            unique_key=key,
            resource_message_id=0,
            resource_type=resource_type(message),
            owner_user_id=owner_user_id,
            target_chat_id=target_chat_id,
        )
        if not inserted:
            logger.info(
                "重复资源，跳过 user_id=%s key=%s",
                owner_user_id,
                key,
            )
            await message.reply_text("♻️ 资源已存在，没有重复保存。")
            return

    try:
        copied = await message.copy(
            chat_id=target_chat_id,
        )

        if key:
            update_resource_message_id(
                unique_key=key,
                target_chat_id=target_chat_id,
                resource_message_id=copied.message_id,
            )

        logger.info(
            "资源保存成功 user_id=%s target=%s saved_message_id=%s",
            owner_user_id,
            target_chat_id,
            copied.message_id,
        )

        await message.reply_text("✅ 已保存到你的资源群组。")

    except Exception as exc:
        logger.exception(
            "资源保存失败 user_id=%s target=%s: %s",
            owner_user_id,
            target_chat_id,
            exc,
        )

        # 复制失败：回滚占位记录，避免 DB 里有记录但目标群没有消息。
        if key:
            delete_resource_record(key, target_chat_id)

        await message.reply_text(
            "❌ 保存失败，请检查目标资源群组和机器人的权限。"
        )