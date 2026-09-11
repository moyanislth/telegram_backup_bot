#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
数据库模块：负责 SQLite 连接、初始化和时间工具。
"""

import logging
import sqlite3
from contextlib import closing
from datetime import datetime, timezone

from config import DB_FILE, DEFAULT_BINDINGS

logger = logging.getLogger(__name__)


def db_connect() -> sqlite3.Connection:
    """创建并返回一个 SQLite 数据库连接。

    Returns:
        sqlite3.Connection: 已设置 row_factory 的数据库连接。
    """
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """初始化数据库表结构，并写入首次启动的默认绑定。

    创建 users、bindings 表（如果不存在）。
    然后根据 DEFAULT_BINDINGS 插入默认用户和绑定，使用 INSERT OR IGNORE
    避免覆盖已有数据。
    """
    with closing(db_connect()) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                display_name TEXT,
                enabled INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS bindings (
                user_id INTEGER PRIMARY KEY,
                chat_id INTEGER NOT NULL,
                chat_title TEXT,
                enabled INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )

        conn.commit()

    now = utc_now()
    with closing(db_connect()) as conn:
        for user_id, chat_id in DEFAULT_BINDINGS.items():
            conn.execute(
                """
                INSERT OR IGNORE INTO users
                (user_id, username, display_name, enabled, created_at)
                VALUES (?, '', '', 1, ?)
                """,
                (user_id, now),
            )
            conn.execute(
                """
                INSERT OR IGNORE INTO bindings
                (user_id, chat_id, chat_title, enabled, created_at, updated_at)
                VALUES (?, ?, '', 1, ?, ?)
                """,
                (user_id, chat_id, now, now),
            )
        conn.commit()

    logger.info("数据库初始化完成: %s", DB_FILE)


def utc_now() -> str:
    """返回当前 UTC 时间的 ISO 格式字符串。

    Returns:
        str: ISO 8601 格式的 UTC 时间。
    """
    return datetime.now(timezone.utc).isoformat()