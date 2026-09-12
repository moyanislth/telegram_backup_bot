#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Telegram 消息链接解析模块。
"""

from config import MESSAGE_LINK_RE


def parse_message_link(text: str):
    """从文本中解析 Telegram 消息链接。

    支持格式：
    - https://t.me/c/1234567890/123        （私有群组/频道）
    - https://t.me/c/1234567890/5/123      （私有群组/频道 + 话题）
    - https://t.me/channel_username/123    （公开用户名）
    - https://t.me/channel_username/5/123  （公开用户名 + 话题）

    话题链接的最后一段数字是消息 ID，倒数第二段是话题 ID。

    Args:
        text: 包含链接的文本。

    Returns:
        包含 chat 和 message_id 的字典，解析失败返回 None。
    """
    match = MESSAGE_LINK_RE.search(text)
    if not match:
        return None

    private_id, public_ref, topic_id, message_id_str = match.groups()

    if private_id:
        # 私有群组/频道的 chat_id 形如 -100<数字>
        chat_ref = int(f"-100{private_id}")
    else:
        chat_ref = public_ref
        try:
            chat_ref = int(chat_ref)
        except ValueError:
            # 公开用户名保持字符串
            pass

    return {
        "chat": chat_ref,
        "message_id": int(message_id_str),
        "topic_id": int(topic_id) if topic_id else None,
    }