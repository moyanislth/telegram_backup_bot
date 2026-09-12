#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
管理员绑定管理模块：处理绑定菜单、添加、删除、列表、检查以及文本输入流程。
"""

import html
import logging

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from permissions import is_admin
from users import list_bindings, get_binding, set_binding, remove_binding
from keyboards import binding_menu, cancel_keyboard, confirm_binding_keyboard
from states import (
    clear_state,
    set_state,
    STATE_KEY,
    PENDING_USER_KEY,
    PENDING_CHAT_KEY,
    PENDING_TITLE_KEY,
)
from chat_access import check_chat_access
from helpers import safe_display_name, safe_edit

logger = logging.getLogger(__name__)


async def binding_menu_handler(
    query,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """处理绑定管理菜单回调。

    权限已在 callback_handler 入口统一校验（binding_* 前缀）。
    """
    clear_state(context)

    await safe_edit(
        query,
        "⚙️ <b>绑定管理</b>\n\n"
        "这里管理「允许使用者 → 资源群组」的关系。",
        parse_mode=ParseMode.HTML,
        reply_markup=binding_menu(),
    )
    await query.answer()


async def binding_list_handler(
    query,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """处理查看全部绑定回调。权限已在入口统一校验。"""
    clear_state(context)
    rows = list_bindings()

    if not rows:
        text = "📋 <b>绑定列表</b>\n\n目前没有任何绑定。"
    else:
        lines = ["📋 <b>绑定列表</b>\n"]

        for row in rows:
            status = "✅" if row["enabled"] else "⛔"
            name = html.escape(safe_display_name(row))
            title = html.escape(
                row["chat_title"] or str(row["chat_id"])
            )

            lines.append(
                f"{status} <b>{name}</b>\n"
                f"   User ID: <code>{row['user_id']}</code>\n"
                f"   资源群: <code>{row['chat_id']}</code>"
                f" ({title})\n"
            )

        text = "\n".join(lines)

    await safe_edit(
        query,
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=binding_menu(),
    )
    await query.answer()


async def binding_add_handler(
    query,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """处理添加/修改绑定回调，进入等待 User ID 状态。权限已在入口统一校验。"""
    clear_state(context)
    set_state(context, "waiting_user_id")

    await safe_edit(
        query,
        "➕ <b>添加 / 修改绑定</b>\n\n"
        "请输入允许使用者的 Telegram User ID。\n\n"
        "例如：<code>123456789</code>",
        parse_mode=ParseMode.HTML,
        reply_markup=cancel_keyboard(),
    )
    await query.answer()


async def binding_delete_handler(
    query,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """处理删除绑定回调，进入等待删除 User ID 状态。权限已在入口统一校验。"""
    clear_state(context)
    set_state(context, "waiting_delete_user_id")

    await safe_edit(
        query,
        "🗑 <b>删除绑定</b>\n\n"
        "请输入要删除的 Telegram User ID。",
        parse_mode=ParseMode.HTML,
        reply_markup=cancel_keyboard(),
    )
    await query.answer()


async def binding_check_handler(
    query,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """处理检查群组回调，检查所有启用绑定的群组访问权限。权限已在入口统一校验。"""
    clear_state(context)
    await query.answer("检查中…")

    rows = list_bindings()

    if not rows:
        await safe_edit(
            query,
            "🔍 目前没有绑定可以检查。",
            reply_markup=binding_menu(),
        )
        return

    lines = ["🔍 <b>群组检查结果</b>\n"]

    for row in rows:
        if not row["enabled"]:
            continue

        ok, reason, chat = await check_chat_access(
            context,
            row["chat_id"],
        )

        name = html.escape(safe_display_name(row))
        title = (
            html.escape(chat.title)
            if chat and getattr(chat, "title", None)
            else html.escape(str(row["chat_id"]))
        )

        icon = "✅" if ok else "❌"
        lines.append(
            f"{icon} <b>{name}</b>\n"
            f"   {title}\n"
            f"   <code>{row['chat_id']}</code>\n"
            f"   {html.escape(reason)}\n"
        )

    await safe_edit(
        query,
        "\n".join(lines),
        parse_mode=ParseMode.HTML,
        reply_markup=binding_menu(),
    )


async def handle_admin_text_input(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> bool:
    """处理管理员在绑定管理流程中的文本输入。

    根据当前状态（waiting_user_id、waiting_chat_id、waiting_delete_user_id）
    执行相应操作。

    Args:
        update: Telegram Update。
        context: Telegram 上下文。

    Returns:
        如果已处理返回 True，否则 False。
    """
    if not update.message or not update.effective_user:
        return False

    # 绑定流程中收到非文本消息（图片、贴纸等）时静默忽略。
    if not update.message.text:
        return False

    user = update.effective_user

    if not is_admin(user.id):
        return False

    state = context.user_data.get(STATE_KEY)
    if not state:
        return False

    text = (update.message.text or "").strip()

    if state == "waiting_user_id":
        try:
            target_user_id = int(text)
        except ValueError:
            await update.message.reply_text(
                "❌ User ID 必须是数字，请重新输入。",
                reply_markup=cancel_keyboard(),
            )
            return True

        if target_user_id <= 0:
            await update.message.reply_text(
                "❌ User ID 不正确，请重新输入。",
                reply_markup=cancel_keyboard(),
            )
            return True

        context.user_data[PENDING_USER_KEY] = target_user_id
        set_state(context, "waiting_chat_id")

        await update.message.reply_text(
            "请输入这个用户对应的资源群组 Chat ID。\n\n"
            "机器人必须已经加入该群组，并且有发送消息权限。",
            parse_mode=ParseMode.HTML,
            reply_markup=cancel_keyboard(),
        )
        return True

    if state == "waiting_chat_id":
        try:
            chat_id = int(text)
        except ValueError:
            await update.message.reply_text(
                "❌ Chat ID 必须是数字。\n"
                "例如：<code>-1003145884431</code>",
                parse_mode=ParseMode.HTML,
                reply_markup=cancel_keyboard(),
            )
            return True

        pending_user_id = context.user_data.get(PENDING_USER_KEY)

        if not pending_user_id:
            clear_state(context)
            await update.message.reply_text(
                "❌ 操作状态已失效，请重新打开绑定管理。"
            )
            return True

        ok, reason, chat = await check_chat_access(
            context,
            chat_id,
        )

        if not ok:
            await update.message.reply_text(
                "❌ <b>无法使用这个群组</b>\n\n"
                f"{html.escape(reason)}\n\n"
                "请确认机器人已经加入群组，并有发送权限。",
                parse_mode=ParseMode.HTML,
                reply_markup=cancel_keyboard(),
            )
            return True

        title = getattr(chat, "title", None) or getattr(
            chat,
            "username",
            None,
        ) or str(chat_id)

        context.user_data[PENDING_CHAT_KEY] = chat_id
        context.user_data[PENDING_TITLE_KEY] = title
        set_state(context, "waiting_confirmation")

        existing = get_binding(pending_user_id)
        overwrite_warning = ""
        if existing and existing["enabled"]:
            overwrite_warning = (
                f"\n⚠️ 该用户当前已绑定到 <code>{existing['chat_id']}</code>，"
                "本次操作将覆盖。\n"
            )

        await update.message.reply_text(
            "确认绑定？\n\n"
            f"👤 用户：<code>{pending_user_id}</code>\n"
            f"📚 资源群：<b>{html.escape(str(title))}</b>\n"
            f"🆔 Chat ID：<code>{chat_id}</code>\n"
            f"{overwrite_warning}\n"
            "机器人检查结果："
            f" {html.escape(reason)}",
            parse_mode=ParseMode.HTML,
            reply_markup=confirm_binding_keyboard(),
        )
        return True

    if state == "waiting_delete_user_id":
        try:
            target_user_id = int(text)
        except ValueError:
            await update.message.reply_text(
                "❌ User ID 必须是数字，请重新输入。",
                reply_markup=cancel_keyboard(),
            )
            return True

        binding = get_binding(target_user_id)

        if not binding or not binding["enabled"]:
            await update.message.reply_text(
                "⚠️ 没有找到这个用户的有效绑定。",
                reply_markup=cancel_keyboard(),
            )
            return True

        remove_binding(target_user_id)

        logger.info(
            "管理员删除绑定 user_id=%s chat_id=%s",
            target_user_id,
            binding["chat_id"],
        )

        clear_state(context)

        await update.message.reply_text(
            "🗑 <b>绑定已删除</b>\n\n"
            f"用户：<code>{target_user_id}</code>\n"
            f"原资源群：<code>{binding['chat_id']}</code>",
            parse_mode=ParseMode.HTML,
            reply_markup=binding_menu(),
        )
        return True

    if state == "waiting_confirmation":
        await update.message.reply_text(
            "请点击上方的 ✅ 或 ❌ 按钮完成操作。",
            reply_markup=confirm_binding_keyboard(),
        )
        return True

    return False