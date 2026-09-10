#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Album 处理模块：处理 Telegram 相册（多图/多视频）。
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
from helpers import send_saved_notification

logger = logging.getLogger(__name__)


async def process_album(
    messages: list[Message],
    context: ContextTypes.DEFAULT_TYPE,
    owner_user_id: int,
    target_chat_id: int,
) -> None:
    """处理一个 Album 中的所有消息。

    逐条独立处理，每条都遵循：
    占位插入 → 复制 → 成功回填 / 失败回滚。
    单条失败不影响其他条目，避免批量复制部分失败导致孤儿消息。

    Args:
        messages: Album 中的消息列表，已按 message_id 排序。
        context: Telegram 上下文。
        owner_user_id: 资源所属用户 ID。
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

    saved_count = 0
    duplicate_count = 0
    failed_count = 0

    for msg in messages:
        key = get_message_unique_key(msg)

        # 占位插入 DB：先抢 UNIQUE 约束。
        if key:
            inserted = save_resource_record(
                unique_key=key,
                resource_message_id=0,
                resource_type=resource_type(msg),
                owner_user_id=owner_user_id,
                target_chat_id=target_chat_id,
            )
            if not inserted:
                duplicate_count += 1
                logger.info(
                    "Album 重复资源 user_id=%s key=%s",
                    owner_user_id,
                    key,
                )
                continue

        try:
            copied = await msg.copy(
                chat_id=target_chat_id,
            )

            if key:
                update_resource_message_id(
                    unique_key=key,
                    target_chat_id=target_chat_id,
                    resource_message_id=copied.message_id,
                )

            saved_count += 1

        except Exception as exc:
            logger.exception(
                "Album 单条保存失败 message_id=%s: %s",
                msg.message_id,
                exc,
            )

            if key:
                delete_resource_record(key, target_chat_id)

            failed_count += 1

    logger.info(
        "Album 保存完成 user_id=%s album_id=%s saved=%s duplicate=%s failed=%s",
        owner_user_id,
        album_id,
        saved_count,
        duplicate_count,
        failed_count,
    )

    await send_saved_notification(
        messages[0],
        saved_count,
        duplicate_count,
        failed_count,
    )