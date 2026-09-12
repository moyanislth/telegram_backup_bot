#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
群组事件处理模块：机器人被加入群组/频道时发送欢迎与配置指引。
"""

import html
import logging

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


async def my_chat_member_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """处理机器人自身成员状态变化。

    机器人被加入群组/频道（member/administrator/creator）时，
    发送群组名称、Chat ID 与后续配置指引。
    被移出（left/kicked）时仅记录日志。
    """
    my_chat_member = update.my_chat_member
    if not my_chat_member:
        return

    # 只处理机器人自己的状态变化。
    if my_chat_member.from_user.id != context.bot.id:
        return

    chat = my_chat_member.chat
    new_status = my_chat_member.new_chat_member.status

    if new_status in ("left", "kicked"):
        logger.info(
            "机器人被移出 chat_id=%s title=%s status=%s",
            chat.id,
            chat.title,
            new_status,
        )
        return

    if new_status not in ("member", "administrator", "creator"):
        return

    logger.info(
        "机器人加入 chat_id=%s title=%s status=%s",
        chat.id,
        chat.title,
        new_status,
    )

    if new_status == "member":
        admin_hint = (
            "\n⚠️ 机器人目前只是普通成员，"
            "请把它设为管理员后才能正常保存资源。"
        )
    else:
        admin_hint = "\n✅ 机器人已是管理员，可以正常保存资源。"

    chat_type_name = "频道" if chat.type == "channel" else "群组"

    try:
        await context.bot.send_message(
            chat_id=chat.id,
            text=(
                f"👋 感谢将机器人加入{chat_type_name}！\n\n"
                f"📖 {chat_type_name}名称："
                f"<b>{html.escape(chat.title or str(chat.id))}</b>\n"
                f"🆔 Chat ID：<code>{chat.id}</code>\n"
                f"{admin_hint}\n\n"
                "下一步：\n"
                "• 在本群发送 /searchid 可随时查看 Chat ID\n"
                "• 私聊机器人，点击 ⚙️ 绑定管理，"
                "把「使用者 User ID → 本群 Chat ID」建立绑定"
            ),
            parse_mode=ParseMode.HTML,
        )
    except Exception as exc:
        # 部分频道禁止机器人发言，发送失败不影响主流程。
        logger.warning(
            "发送入群欢迎语失败 chat_id=%s: %s",
            chat.id,
            exc,
        )
