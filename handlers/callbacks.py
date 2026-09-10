#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
回调处理模块：统一处理 InlineKeyboard 回调。
"""

import html
import logging

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from permissions import is_admin
from keyboards import main_menu, binding_menu
from states import clear_state, PENDING_USER_KEY, PENDING_CHAT_KEY, PENDING_TITLE_KEY
from users import set_binding
from handlers.admin_bindings import (
    binding_menu_handler,
    binding_add_handler,
    binding_delete_handler,
    binding_list_handler,
    binding_check_handler,
)

logger = logging.getLogger(__name__)


async def callback_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """处理所有 InlineKeyboard 回调。

    根据 callback_data 分发到不同处理函数。
    """
    query = update.callback_query
    if not query:
        return

    await query.answer()

    user = query.from_user

    # 管理按钮严格只允许管理员。
    if query.data.startswith("binding_") and not is_admin(user.id):
        await query.answer("只有管理员可以使用绑定管理。", show_alert=True)
        return

    if query.data == "help":
        await query.edit_message_text(
            "📖 <b>使用说明</b>\n\n"
            "直接发送资源给机器人即可。\n"
            "机器人会按照你的绑定关系保存到对应资源群组。\n\n"
            "如果发送 Telegram 消息链接，机器人只能处理"
            "它有权限读取的公开/授权内容，不能绕过受保护内容限制。",
            parse_mode=ParseMode.HTML,
            reply_markup=main_menu(user.id),
        )
        return

    if query.data == "main_menu":
        clear_state(context)
        await query.edit_message_text(
            "主菜单：",
            reply_markup=main_menu(user.id),
        )
        return

    if query.data == "binding_menu":
        await binding_menu_handler(query, context)
        return

    if query.data == "binding_add":
        await binding_add_handler(query, context)
        return

    if query.data == "binding_delete":
        await binding_delete_handler(query, context)
        return

    if query.data == "binding_list":
        await binding_list_handler(query, context)
        return

    if query.data == "binding_check":
        await binding_check_handler(query, context)
        return

    if query.data == "binding_cancel":
        clear_state(context)
        await query.edit_message_text(
            "已取消。",
            reply_markup=binding_menu(),
        )
        return

    if query.data == "binding_confirm":
        pending_user_id = context.user_data.get(PENDING_USER_KEY)
        pending_chat_id = context.user_data.get(PENDING_CHAT_KEY)
        pending_title = context.user_data.get(PENDING_TITLE_KEY, "")

        if not pending_user_id or not pending_chat_id:
            clear_state(context)
            await query.edit_message_text(
                "❌ 绑定信息已失效，请重新操作。",
                reply_markup=binding_menu(),
            )
            return

        set_binding(
            int(pending_user_id),
            int(pending_chat_id),
            str(pending_title),
        )

        logger.info(
            "管理员完成绑定 user_id=%s -> chat_id=%s title=%s",
            pending_user_id,
            pending_chat_id,
            pending_title,
        )

        clear_state(context)

        await query.edit_message_text(
            "✅ <b>绑定成功</b>\n\n"
            f"用户：<code>{pending_user_id}</code>\n"
            f"资源群：<code>{pending_chat_id}</code>\n"
            f"名称：{html.escape(str(pending_title or '未获取到名称'))}",
            parse_mode=ParseMode.HTML,
            reply_markup=binding_menu(),
        )
        return