#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
资源去重与记录模块：生成去重 key、检查资源是否存在、保存资源记录。
"""

import hashlib
import logging
import sqlite3
from contextlib import closing
from typing import Optional

from telegram import Message

from database import db_connect, utc_now

logger = logging.getLogger(__name__)


def make_text_key(text: str) -> str:
    """为文本内容生成 SHA256 去重 key。

    Args:
        text: 文本内容。

    Returns:
        格式为 "text:<sha256>" 的去重 key。
    """
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return f"text:{digest}"


def get_message_unique_key(message: Message) -> Optional[str]:
    """根据消息内容生成去重 key。

    支持 photo、video、document、audio、voice、animation、video_note、text。
    使用 Telegram 的 file_unique_id 或文本 SHA256。

    Args:
        message: Telegram Message 对象。

    Returns:
        去重 key 字符串，如果不支持则返回 None。
    """
    if message.photo:
        # 最大尺寸照片通常是最后一个 PhotoSize。
        return f"photo:{message.photo[-1].file_unique_id}"

    if message.video:
        return f"video:{message.video.file_unique_id}"

    if message.document:
        return f"document:{message.document.file_unique_id}"

    if message.audio:
        return f"audio:{message.audio.file_unique_id}"

    if message.voice:
        return f"voice:{message.voice.file_unique_id}"

    if message.animation:
        return f"animation:{message.animation.file_unique_id}"

    if message.video_note:
        return f"video_note:{message.video_note.file_unique_id}"

    if message.text:
        return make_text_key(message.text)

    return None


def resource_exists(unique_key: str, target_chat_id: int) -> bool:
    """检查资源是否已存在于目标群组。

    注意：新流程不再依赖这个函数做并发保护，
    UNIQUE 约束才是最终保险。保留此函数供查询场景使用。

    Args:
        unique_key: 资源去重 key。
        target_chat_id: 目标群组 Chat ID。

    Returns:
        已存在返回 True，否则 False。
    """
    with closing(db_connect()) as conn:
        row = conn.execute(
            """
            SELECT 1
            FROM resources
            WHERE unique_key = ?
              AND target_chat_id = ?
            LIMIT 1
            """,
            (unique_key, target_chat_id),
        ).fetchone()

    return row is not None


def save_resource_record(
    unique_key: str,
    resource_message_id: int,
    resource_type: str,
    owner_user_id: int,
    target_chat_id: int,
) -> bool:
    """保存资源记录到数据库。

    新流程中用于“占位插入”：在复制前先插入一条 message_id=0 的记录，
    利用 UNIQUE 约束抢锁，避免并发重复复制。复制成功后由
    update_resource_message_id 回填真实 message_id。

    Args:
        unique_key: 资源去重 key。
        resource_message_id: 保存到目标群组后的消息 ID；占位时为 0。
        resource_type: 资源类型字符串。
        owner_user_id: 资源所属用户 ID。
        target_chat_id: 目标群组 Chat ID。

    Returns:
        插入成功返回 True，重复插入返回 False。
    """
    try:
        with closing(db_connect()) as conn:
            conn.execute(
                """
                INSERT INTO resources
                (
                    unique_key,
                    resource_message_id,
                    resource_type,
                    owner_user_id,
                    target_chat_id,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    unique_key,
                    resource_message_id,
                    resource_type,
                    owner_user_id,
                    target_chat_id,
                    utc_now(),
                ),
            )
            conn.commit()
        return True
    except sqlite3.IntegrityError:
        # UNIQUE 约束触发：说明并发或重复请求已被另一路先占用。
        return False


def update_resource_message_id(
    unique_key: str,
    target_chat_id: int,
    resource_message_id: int,
) -> bool:
    """回填资源的真实 message_id。

    占位插入后，复制成功时调用，把 message_id=0 的占位更新为真实 ID。

    Args:
        unique_key: 资源去重 key。
        target_chat_id: 目标群组 Chat ID。
        resource_message_id: 复制成功后目标群组中的消息 ID。

    Returns:
        更新成功返回 True，否则 False。
    """
    try:
        with closing(db_connect()) as conn:
            cursor = conn.execute(
                """
                UPDATE resources
                SET resource_message_id = ?
                WHERE unique_key = ?
                  AND target_chat_id = ?
                """,
                (resource_message_id, unique_key, target_chat_id),
            )
            conn.commit()
            return cursor.rowcount > 0
    except sqlite3.Error as exc:
        logger.warning(
            "回填 message_id 失败 key=%s target=%s: %s",
            unique_key,
            target_chat_id,
            exc,
        )
        return False


def delete_resource_record(unique_key: str, target_chat_id: int) -> bool:
    """删除资源记录，用于复制失败时回滚占位。

    Args:
        unique_key: 资源去重 key。
        target_chat_id: 目标群组 Chat ID。

    Returns:
        删除成功返回 True，否则 False。
    """
    try:
        with closing(db_connect()) as conn:
            cursor = conn.execute(
                """
                DELETE FROM resources
                WHERE unique_key = ?
                  AND target_chat_id = ?
                """,
                (unique_key, target_chat_id),
            )
            conn.commit()
            return cursor.rowcount > 0
    except sqlite3.Error as exc:
        logger.warning(
            "回滚资源记录失败 key=%s target=%s: %s",
            unique_key,
            target_chat_id,
            exc,
        )
        return False


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