#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
命令处理模块：/start、/help、/myid。
"""

import html
import logging

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from permissions import is_admin, user_is_allowed, reject_if_not_allowed
from users import upsert_user, get_binding
from keyboards import main_menu

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
        binding_text = "\n⚠️ 你当前还没有资源群绑定。"
    else:
        binding_text = "\n⚠️ 你当前没有有效的资源群绑定。"

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
        "📖 <b>使用说明</b>\n\n"
        "• 发送图片、视频、文件、音频、文字等资源\n"
        "• 多图 Album 会等待片刻后一起处理\n"
        "• 已保存过的资源会自动跳过\n"
        "• 每个用户只会保存到自己的绑定群组\n"
        "• 管理员可以通过「⚙️ 绑定管理」管理用户和群组\n\n"
        "发送 Telegram 消息链接时，机器人会尝试读取它；"
        "但无法绕过 Telegram 的受保护内容、禁止保存/转发限制，"
        "也无法访问机器人没有权限读取的消息。",
        parse_mode=ParseMode.HTML,
        reply_markup=main_menu(update.effective_user.id),
    )


async def myid_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """处理 /myid 命令，显示当前用户的 Telegram User ID。"""
    user = update.effective_user
    if not user:
        return

    await update.message.reply_text(
        f"你的 Telegram User ID 是：\n<code>{user.id}</code>",
        parse_mode=ParseMode.HTML,
    )