#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
普通消息入口模块：处理用户发来的资源消息、Album 和消息链接。
"""

import asyncio
import logging

from telegram import Update
from telegram.ext import ContextTypes

from config import ALBUM_WAIT_SECONDS
from permissions import reject_if_not_allowed
from users import upsert_user, get_binding
from telegram_links import parse_message_link
from handlers.admin_bindings import handle_admin_text_input
from handlers.links import process_message_link
from handlers.albums import process_album
from handlers.single_resource import process_single_message

logger = logging.getLogger(__name__)

# 持有 Album 延迟处理任务的强引用，防止任务被垃圾回收中断；
# 任务结束后自动移除并记录未捕获异常。
_pending_album_tasks: set[asyncio.Task] = set()


def _log_album_task_exception(task: asyncio.Task) -> None:
    _pending_album_tasks.discard(task)
    if task.cancelled():
        return
    exc = task.exception()
    if exc:
        logger.error("Album 延迟处理任务异常: %s", exc)


async def message_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """处理所有非命令消息。

    优先级：
    1. 管理员绑定输入
    2. 权限检查
    3. 获取绑定
    4. 消息链接
    5. Album
    6. 单条资源
    """
    if not update.message or not update.effective_user:
        return

    # 仅处理私聊消息（bot.py 已按 ChatType.PRIVATE 过滤，此处双保险）。
    if not update.effective_chat or update.effective_chat.type != "private":
        return

    user = update.effective_user

    # 管理员绑定输入优先处理。
    if await handle_admin_text_input(update, context):
        return

    if await reject_if_not_allowed(update):
        return

    upsert_user(user)

    binding = get_binding(user.id)

    if not binding or not binding["enabled"]:
        await update.message.reply_text(
            "⚠️ 你目前没有有效的资源群组绑定，请联系管理员。"
        )
        return

    target_chat_id = int(binding["chat_id"])

    # 投票消息暂不支持保存，提前告知。
    if update.message.poll:
        await update.message.reply_text("⚠️ 暂不支持保存投票消息。")
        return

    # Telegram 消息链接：仅对无媒体消息生效，
    # 带媒体的 caption 链接按普通资源保存，避免媒体被丢弃。
    has_media = any([
        update.message.photo,
        update.message.video,
        update.message.document,
        update.message.audio,
        update.message.voice,
        update.message.animation,
        update.message.video_note,
    ])
    text = update.message.text or update.message.caption or ""
    link_info = parse_message_link(text) if not has_media else None

    if link_info:
        await process_message_link(
            update.message,
            link_info,
            context,
            user.id,
            target_chat_id,
        )
        return

    # Album。
    media_group_id = update.message.media_group_id

    if media_group_id:
        key = f"album:{user.id}:{media_group_id}"

        if key not in context.application.bot_data:
            context.application.bot_data[key] = []

        context.application.bot_data[key].append(update.message)

        logger.info(
            "收到 Album 消息 user_id=%s album_id=%s message_id=%s",
            user.id,
            media_group_id,
            update.message.message_id,
        )

        # 只有第一个消息负责创建处理任务。
        marker_key = f"album_task:{user.id}:{media_group_id}"

        if marker_key not in context.application.bot_data:
            context.application.bot_data[marker_key] = True

            async def delayed_process():
                await asyncio.sleep(ALBUM_WAIT_SECONDS)

                messages = context.application.bot_data.pop(
                    key,
                    [],
                )
                context.application.bot_data.pop(
                    marker_key,
                    None,
                )

                # 按 message_id 排序，确保 Album 顺序。
                messages.sort(key=lambda m: m.message_id)

                await process_album(
                    messages,
                    context,
                    user.id,
                    target_chat_id,
                )

            task = asyncio.create_task(delayed_process())
            _pending_album_tasks.add(task)
            task.add_done_callback(_log_album_task_exception)

        return

    await process_single_message(
        update.message,
        context,
        user.id,
        target_chat_id,
    )