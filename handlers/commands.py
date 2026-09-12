#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
命令处理模块：/start、/help、/searchid、/cancel。
"""

import html
import logging

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from permissions import is_admin, user_is_allowed, reject_if_not_allowed
from users import upsert_user, get_binding
from keyboards import main_menu
from states import clear_state, STATE_KEY
from helpers import HELP_TEXT

logger = logging.getLogger(__name__)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """处理 /start 命令。

    如果用户未授权，显示其 User ID 以便联系管理员。
    如果已授权，显示欢迎信息和当前绑定状态。
    """
    user = update.effective_user
    if not user:
        return

    # /start 允许所有人查看自己的 ID，方便首次配置。
    if not user_is_allowed(user.id):
        await update.message.reply_text(
            "⛔ 你还没有使用权限。\n\n"
            "你的 Telegram User ID 是：\n"
            f"<code>{user.id}</code>\n\n"
            "请把这个 ID 发给机器人管理员。",
            parse_mode=ParseMode.HTML,
        )
        logger.warning("未授权 /start user_id=%s", user.id)
        return

    upsert_user(user)

    binding = get_binding(user.id)

    if binding and binding["enabled"]:
        target = (
            binding["chat_title"]
            or str(binding["chat_id"])
        )
        binding_text = f"\n📚 当前资源群：<code>{html.escape(str(target))}</code>"
    elif is_admin(user.id):
        binding_text = (
            "\n\n⚠️ 你还没有任何绑定。请先：\n"
            "1️⃣ 邀请机器人到目标群组/频道并设为管理员；\n"
            "2️⃣ 在群内发送 /searchid 获取 Chat ID；\n"
            "3️⃣ 点击下方 ⚙️ 绑定管理完成绑定。"
        )
    else:
        binding_text = (
            "\n\n⚠️ 你当前没有有效的资源群绑定，请联系管理员。"
        )

    await update.message.reply_text(
        "👋 欢迎使用资源备份机器人！\n\n"
        "直接把图片、视频、文件、文字等资源发给我，"
        "机器人会自动保存到你绑定的资源群组。"
        f"{binding_text}",
        parse_mode=ParseMode.HTML,
        reply_markup=main_menu(user.id),
    )


async def help_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """处理 /help 命令，显示使用说明。"""
    if await reject_if_not_allowed(update):
        return

    await update.message.reply_text(
        HELP_TEXT,
        parse_mode=ParseMode.HTML,
        reply_markup=main_menu(update.effective_user.id),
    )


async def searchid_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """处理 /searchid 命令。

    私聊返回当前用户的 User ID；群组/频道内返回该群组的 Chat ID。
    群内命令不受隐私模式影响，始终送达机器人。
    """
    user = update.effective_user
    chat = update.effective_chat
    if not user or not chat:
        return

    if chat.type == "private":
        reply = (
            "你的 Telegram User ID 是：\n"
            f"<code>{user.id}</code>"
        )
    else:
        reply = (
            f"本{('频道' if chat.type == 'channel' else '群组')} Chat ID 是：\n"
            f"<code>{chat.id}</code>"
        )

    await update.message.reply_text(
        reply,
        parse_mode=ParseMode.HTML,
    )


async def cancel_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """处理 /cancel 命令，取消当前进行中的操作（如绑定流程）。"""
    if not update.effective_user:
        return

    had_state = bool(context.user_data.get(STATE_KEY))
    clear_state(context)

    await update.message.reply_text(
        "✅ 已取消当前操作。" if had_state else "当前没有进行中的操作。"
    )