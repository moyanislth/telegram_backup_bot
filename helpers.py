#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
辅助函数模块：提供安全显示名称和保存通知发送。
"""

import logging

from telegram import Message

logger = logging.getLogger(__name__)


def safe_display_name(row) -> str:
    """从数据库行中提取安全的显示名称。

    优先使用 display_name，其次 @username，最后 user_id。

    Args:
        row: sqlite3.Row 或类似字典对象，包含 display_name、username、user_id。

    Returns:
        显示名称字符串。
    """
    display_name = row["display_name"] if row and row["display_name"] else ""
    username = row["username"] if row and row["username"] else ""

    if display_name:
        return display_name
    if username:
        return f"@{username}"
    return str(row["user_id"]) if row else "未知用户"


async def send_saved_notification(
    message: Message,
    saved_count: int,
    duplicate_count: int = 0,
    failed_count: int = 0,
) -> None:
    """发送资源保存结果通知。

    根据 saved / duplicate / failed 组合生成不同提示文案。

    Args:
        message: 用于回复的消息对象。
        saved_count: 成功保存的数量。
        duplicate_count: 跳过的重复数量。
        failed_count: 处理失败的数量。
    """
    lines = []

    if saved_count:
        lines.append(f"✅ 已保存 {saved_count} 个资源")
    if duplicate_count:
        lines.append(f"♻️ 跳过 {duplicate_count} 个重复资源")
    if failed_count:
        lines.append(f"❌ 失败 {failed_count} 个资源")

    if not lines:
        # 三个计数都为 0 的兜底情况。
        text = "♻️ 资源已存在，没有重复保存。"
    else:
        text = "\n".join(lines)

    await message.reply_text(text)