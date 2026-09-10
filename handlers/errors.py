#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
错误处理模块：全局异常日志记录，并尽量通知用户。
"""

import logging

from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


async def error_handler(
    update: object,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """记录未处理异常，并尽量给用户发送提示。

    Args:
        update: Telegram Update 或 None。
        context: Telegram 上下文，包含 error。
    """
    logger.exception(
        "Unhandled exception: %s",
        context.error,
    )

    # 尽量通知用户，但通知本身失败时不再抛出。
    try:
        effective_message = getattr(update, "effective_message", None)
        if effective_message:
            await effective_message.reply_text(
                "❌ 处理时发生异常，请稍后重试。"
            )
    except Exception as notify_exc:
        logger.warning("发送错误提示失败: %s", notify_exc)