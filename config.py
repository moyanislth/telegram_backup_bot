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
DB_FILE = Path(os.getenv("DB_FILE", "resource_backup.db"))

# Album 等待时间（秒）。
ALBUM_WAIT_SECONDS = float(os.getenv("ALBUM_WAIT_SECONDS", "1.5"))

# 消息链接正则。
# 支持：
#   https://t.me/c/1234567890/123       （私有群组/频道，需要补 -100 前缀）
#   https://t.me/channel_username/123   （公开用户名）
#   https://t.me/username/123
MESSAGE_LINK_RE = re.compile(
    r"https?://t\.me/"
    r"(?:c/(\d+)|([A-Za-z0-9_]+))/(\d+)"
)