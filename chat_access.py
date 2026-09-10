#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
群组访问检查模块：检查机器人是否有权限访问指定群组。
"""

import logging
from typing import Optional

from telegram import Chat
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


async def check_chat_access(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
) -> tuple[bool, str, Optional[Chat]]:
    """检查机器人是否有权限访问指定群组。

    尝试 get_chat，然后检查机器人成员状态和发送权限。

    Args:
        context: Telegram 上下文。
        chat_id: 目标群组 Chat ID。

    Returns:
        (是否可访问, 原因描述, Chat 对象或 None)
    """
    try:
        chat = await context.bot.get_chat(chat_id)

        # 对群组/超级群组/频道检查 Bot 自身权限。
        try:
            me = await context.bot.get_me()
            member = await context.bot.get_chat_member(chat_id, me.id)

            status = getattr(member, "status", "")
            if status in ("left", "kicked"):
                return False, "机器人不在这个群组/频道中。", chat

            # administrator / creator 一般有发送权限。
            if status in ("administrator", "creator"):
                return True, "机器人有管理员权限。", chat

            # 普通成员在 supergroup 中通常可以发送，但具体权限可能被限制。
            if status == "member":
                can_send = getattr(member, "can_send_messages", True)
                if can_send is False:
                    return False, "机器人当前没有发送消息权限。", chat

            return True, "群组访问检查通过。", chat

        except Exception as exc:
            logger.warning(
                "检查机器人成员状态失败 chat_id=%s: %s",
                chat_id,
                exc,
            )
            # 如果成员状态接口失败，至少成功 get_chat。
            return True, "已获取群组，但无法进一步确认权限。", chat

    except Exception as exc:
        logger.warning("检查群组失败 chat_id=%s: %s", chat_id, exc)
        return False, f"无法访问这个 Chat ID：{exc}", None