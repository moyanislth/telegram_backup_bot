#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
权限模块：判断用户是否为管理员、是否有权使用机器人，以及拒绝未授权请求。
"""

import logging
from contextlib import closing

from telegram import Update
from telegram.ext import ContextTypes

from config import ADMIN_USER_IDS
from database import db_connect

logger = logging.getLogger(__name__)


def is_admin(user_id: int) -> bool:
    """判断用户是否为机器人管理员。

    Args:
        user_id: Telegram 用户 ID。

    Returns:
        是管理员返回 True，否则 False。
    """
    return user_id in ADMIN_USER_IDS


def user_is_allowed(user_id: int) -> bool:
    """判断用户是否有权使用机器人。

    管理员始终允许；普通用户必须同时满足：
    users.enabled = 1 且 bindings.enabled = 1。

    Args:
        user_id: Telegram 用户 ID。

    Returns:
        有权限返回 True，否则 False。
    """
    if is_admin(user_id):
        return True

    with closing(db_connect()) as conn:
        row = conn.execute(
            """
            SELECT 1
            FROM users u
            JOIN bindings b ON b.user_id = u.user_id
            WHERE u.user_id = ?
              AND u.enabled = 1
              AND b.enabled = 1
            """,
            (user_id,),
        ).fetchone()

    return row is not None


async def reject_if_not_allowed(
    update: Update,
) -> bool:
    """检查用户是否有权限，无权限则回复拒绝消息。

    如果用户无权限，会根据是 callback_query 还是普通消息进行回复，
    并记录警告日志。

    Args:
        update: Telegram Update 对象。

    Returns:
        如果用户无权限并已拒绝，返回 True；否则返回 False。
    """
    user = update.effective_user
    if not user:
        return True

    if not user_is_allowed(user.id):
        if update.callback_query:
            await update.callback_query.answer(
                "你没有使用权限。",
                show_alert=True,
            )
        elif update.effective_message:
            await update.effective_message.reply_text(
                "⛔ 你没有使用这个机器人的权限。\n"
                "请联系管理员添加你的绑定。"
            )
        logger.warning(
            "拒绝未授权用户 user_id=%s username=%s",
            user.id,
            user.username,
        )
        return True

    return False