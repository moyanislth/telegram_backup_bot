#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Telegram Resource Backup Bot v3

入口文件：负责初始化日志、数据库、构建 Application 并注册 handlers。
"""

import logging

from telegram.ext import (
    Application,
    CallbackQueryHandler,
    ChatMemberHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

from config import BOT_TOKEN, ADMIN_USER_IDS, DB_FILE, ALBUM_WAIT_SECONDS
from database import init_db
from handlers.commands import start, help_command, searchid_command, cancel_command
from handlers.callbacks import callback_handler
from handlers.messages import message_handler
from handlers.group_events import my_chat_member_handler
from handlers.errors import error_handler

from health import start_health_server

logger = logging.getLogger(__name__)


def main() -> None:
    """启动机器人主程序。"""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )

    if not BOT_TOKEN or BOT_TOKEN == "YOUR_NEW_BOT_TOKEN":
        raise RuntimeError(
            "请在 .env 文件中设置有效的 BOT_TOKEN。"
        )

    if not ADMIN_USER_IDS or 123456789 in ADMIN_USER_IDS:
        logger.warning(
            "ADMIN_USER_IDS 仍可能使用示例 ID，请确认已经改成你的 Telegram User ID。"
        )

    init_db()

    # 启动健康检查 HTTP 服务，满足 Render 等平台对 Web Service 的要求。
    start_health_server()

    logger.info("========================================")
    logger.info("Telegram Resource Backup Bot v3 启动")
    logger.info("管理员: %s", ADMIN_USER_IDS)
    logger.info("数据库: %s", DB_FILE.resolve())
    logger.info("Album 等待: %.1f 秒", ALBUM_WAIT_SECONDS)
    logger.info("========================================")

    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .build()
    )

    application.add_handler(
        CommandHandler("start", start)
    )
    application.add_handler(
        CommandHandler("help", help_command)
    )
    application.add_handler(
        CommandHandler("searchid", searchid_command)
    )
    application.add_handler(
        CommandHandler("cancel", cancel_command)
    )

    application.add_handler(
        CallbackQueryHandler(callback_handler)
    )

    # 机器人被加入群组/频道时发送欢迎与配置指引。
    # my_chat_member 属于 Telegram 默认更新集，无需额外 allowed_updates。
    application.add_handler(
        ChatMemberHandler(
            my_chat_member_handler,
            chat_member_types=ChatMemberHandler.MY_CHAT_MEMBER,
        )
    )

    application.add_handler(
        MessageHandler(
            filters.ChatType.PRIVATE & ~filters.COMMAND,
            message_handler,
        )
    )

    application.add_error_handler(error_handler)

    # 删除 Bot 离线期间积压的旧消息，避免启动后批量处理历史消息。
    application.run_polling(
        drop_pending_updates=True,
    )


if __name__ == "__main__":
    main()