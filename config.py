#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
配置文件：从环境变量 / .env 读取所有配置项。
"""

import json
import logging
import os
import re
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# 机器人 Token，必须设置。
BOT_TOKEN = os.getenv("BOT_TOKEN", "")

# 管理员 User ID 集合，逗号分隔。
_admin_ids_str = os.getenv("ADMIN_USER_IDS", "")
ADMIN_USER_IDS = set()
if _admin_ids_str:
    for part in _admin_ids_str.split(","):
        part = part.strip()
        if part:
            try:
                ADMIN_USER_IDS.add(int(part))
            except ValueError:
                logger.warning(
                    "ADMIN_USER_IDS 中的 %r 不是有效整数，已忽略。",
                    part,
                )

# 默认绑定，JSON 格式，例如 {"用户ID": 群组ChatID}
_default_bindings_str = os.getenv("DEFAULT_BINDINGS", "{}")
DEFAULT_BINDINGS = {}
try:
    data = json.loads(_default_bindings_str)
    for k, v in data.items():
        DEFAULT_BINDINGS[int(k)] = int(v)
except (json.JSONDecodeError, ValueError, TypeError) as exc:
    logger.warning(
        "DEFAULT_BINDINGS 解析失败，已忽略。原始值=%r 错误=%s",
        _default_bindings_str,
        exc,
    )

# SQLite 数据库文件路径。
# 相对路径锚定到本文件所在目录，避免工作目录不同导致数据库位置漂移；
# 也可通过环境变量指定绝对路径覆盖。
_db_file_env = os.getenv("DB_FILE", "")
if _db_file_env:
    DB_FILE = Path(_db_file_env)
else:
    DB_FILE = Path(__file__).parent / "resource_backup.db"

# Album 等待时间（秒）。默认 3 秒：弱网下相册消息到达间隔可能超过 1.5 秒，
# 等待过短会把一个相册拆成多条消息保存。
ALBUM_WAIT_SECONDS = float(os.getenv("ALBUM_WAIT_SECONDS", "3.0"))

# 消息链接正则。
# 支持：
#   https://t.me/c/1234567890/123        （私有群组/频道，需要补 -100 前缀）
#   https://t.me/c/1234567890/5/123      （私有群组/频道 + 话题）
#   https://t.me/channel_username/123    （公开用户名）
#   https://t.me/channel_username/5/123  （公开用户名 + 话题）
# 最后一段数字始终是消息 ID，倒数第二段（若存在）是话题 ID。
MESSAGE_LINK_RE = re.compile(
    r"https?://t\.me/"
    r"(?:c/(\d+)|([A-Za-z0-9_]+))"
    r"(?:/(\d+))?"
    r"/(\d+)"
)