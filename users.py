#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
用户与绑定管理模块：提供用户信息更新、绑定查询/设置/删除/列表等功能。
"""

import logging
import sqlite3
from contextlib import closing
from typing import Optional

from database import db_connect, utc_now

logger = logging.getLogger(__name__)


def upsert_user(user) -> None:
    """插入或更新用户信息。

    如果用户已存在，则更新 username 和 display_name。

    Args:
        user: Telegram User 对象，需包含 id、first_name、last_name、username。
    """
    now = utc_now()
    display_name = " ".join(
        x for x in [user.first_name, user.last_name] if x
    ).strip()

    with closing(db_connect()) as conn:
        conn.execute(
            """
            INSERT INTO users
            (user_id, username, display_name, enabled, created_at)
            VALUES (?, ?, ?, 1, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                username = excluded.username,
                display_name = excluded.display_name
            """,
            (
                user.id,
                user.username or "",
                display_name,
                now,
            ),
        )
        conn.commit()


def get_binding(user_id: int) -> Optional[sqlite3.Row]:
    """获取指定用户的绑定信息。

    Args:
        user_id: Telegram 用户 ID。

    Returns:
        包含绑定信息和用户信息的 sqlite3.Row，如果不存在则返回 None。
    """
    with closing(db_connect()) as conn:
        return conn.execute(
            """
            SELECT b.*, u.username, u.display_name, u.enabled AS user_enabled
            FROM bindings b
            LEFT JOIN users u ON u.user_id = b.user_id
            WHERE b.user_id = ?
            """,
            (user_id,),
        ).fetchone()


def set_binding(
    user_id: int,
    chat_id: int,
    chat_title: str = "",
) -> None:
    """设置或更新用户与资源群组的绑定关系。

    如果用户不存在则先创建用户，然后插入或更新绑定，并确保用户启用。

    Args:
        user_id: Telegram 用户 ID。
        chat_id: 资源群组 Chat ID。
        chat_title: 群组标题，可选。
    """
    now = utc_now()

    with closing(db_connect()) as conn:
        conn.execute(
            """
            INSERT INTO users
            (user_id, username, display_name, enabled, created_at)
            VALUES (?, '', '', 1, ?)
            ON CONFLICT(user_id) DO NOTHING
            """,
            (user_id, now),
        )

        conn.execute(
            """
            INSERT INTO bindings
            (user_id, chat_id, chat_title, enabled, created_at, updated_at)
            VALUES (?, ?, ?, 1, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                chat_id = excluded.chat_id,
                chat_title = excluded.chat_title,
                enabled = 1,
                updated_at = excluded.updated_at
            """,
            (user_id, chat_id, chat_title, now, now),
        )

        conn.execute(
            """
            UPDATE users
            SET enabled = 1
            WHERE user_id = ?
            """,
            (user_id,),
        )

        conn.commit()


def remove_binding(user_id: int) -> None:
    """软删除指定用户的绑定关系。

    将 bindings.enabled 和 users.enabled 设置为 0，不物理删除记录。

    Args:
        user_id: Telegram 用户 ID。
    """
    with closing(db_connect()) as conn:
        conn.execute(
            "UPDATE bindings SET enabled = 0, updated_at = ? WHERE user_id = ?",
            (utc_now(), user_id),
        )
        conn.execute(
            "UPDATE users SET enabled = 0 WHERE user_id = ?",
            (user_id,),
        )
        conn.commit()


def list_bindings():
    """列出所有绑定关系，包含关联的用户信息。

    Returns:
        list[sqlite3.Row]: 绑定记录列表，按 user_id 排序。
    """
    with closing(db_connect()) as conn:
        return conn.execute(
            """
            SELECT
                b.user_id,
                b.chat_id,
                b.chat_title,
                b.enabled,
                u.username,
                u.display_name
            FROM bindings b
            LEFT JOIN users u ON u.user_id = b.user_id
            ORDER BY b.user_id
            """
        ).fetchall()