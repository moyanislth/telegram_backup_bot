#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Telegram Resource Backup Bot v3

功能：
1. 只有管理员和已授权用户可以使用机器人。
2. 管理员可以在菜单中管理“用户 -> 资源群组”的绑定关系。
3. 每个用户的资源自动保存到自己的绑定群组。
4. SQLite 持久化用户、绑定关系和去重记录。
5. 支持单条消息和 Telegram Album（相册/多图）。
6. 使用 file_unique_id / 文本 SHA256 防止重复保存。
7. 详细 Terminal 日志。
8. 支持 /myid 查看自己的 Telegram User ID。
9. 支持发送 Telegram 消息链接：机器人会尝试读取公开/机器人有权限访问的消息。
   注意：Bot API 无法绕过受保护内容、禁止保存/转发内容或机器人本身没有权限访问的消息。

安装：
    pip install python-telegram-bot

使用前：
- 将 BOT_TOKEN 改成新 token。
- 将 ADMIN_USER_IDS 改成你的 Telegram User ID。
- 将默认绑定（如果需要）填写到 DEFAULT_BINDINGS。
"""

import asyncio
import hashlib
import html
import logging
import re
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    Update,
)
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# =========================
# 配置
# =========================

BOT_TOKEN = "8881033725:AAHEVR3Z52HcYt_AhD7i7hQmLK6v7ZCvIAo"

# 机器人管理员 Telegram User ID。
# 可以填写多个管理员。
ADMIN_USER_IDS = {
    5822972759,
}

# 可选：首次启动时自动建立的绑定。
# 格式：{用户ID: 资源群组 Chat ID}
#
# 例如：
# DEFAULT_BINDINGS = {
#     123456789: -1003145884431,
# }
DEFAULT_BINDINGS = {
    5822972759: -1003145884431,
}

DB_FILE = Path("resource_backup.db")

# Album 等待时间
ALBUM_WAIT_SECONDS = 1.5

# 消息链接格式：
# https://t.me/c/1234567890/123
# https://t.me/channel_username/123
# https://t.me/username/123
MESSAGE_LINK_RE = re.compile(
    r"https?://t\.me/"
    r"(?:(?:c/)?([A-Za-z0-9_]+)/(\d+)|"
    r"c/(-?\d+)/(\d+))"
)

# =========================
# 日志
# =========================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)


# =========================
# SQLite
# =========================

def db_connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with closing(db_connect()) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                display_name TEXT,
                enabled INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS bindings (
                user_id INTEGER PRIMARY KEY,
                chat_id INTEGER NOT NULL,
                chat_title TEXT,
                enabled INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS resources (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                unique_key TEXT NOT NULL UNIQUE,
                resource_message_id INTEGER,
                resource_type TEXT NOT NULL,
                owner_user_id INTEGER NOT NULL,
                target_chat_id INTEGER NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )

        conn.commit()

    # 首次启动时建立默认绑定，但不会覆盖已有绑定。
    now = utc_now()
    with closing(db_connect()) as conn:
        for user_id, chat_id in DEFAULT_BINDINGS.items():
            conn.execute(
                """
                INSERT OR IGNORE INTO users
                (user_id, username, display_name, enabled, created_at)
                VALUES (?, '', '', 1, ?)
                """,
                (user_id, now),
            )
            conn.execute(
                """
                INSERT OR IGNORE INTO bindings
                (user_id, chat_id, chat_title, enabled, created_at, updated_at)
                VALUES (?, ?, '', 1, ?, ?)
                """,
                (user_id, chat_id, now, now),
            )
        conn.commit()

    logger.info("数据库初始化完成: %s", DB_FILE)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


# =========================
# 用户 / 权限 / 绑定
# =========================

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_USER_IDS


def upsert_user(user) -> None:
    now = utc_now()
    display_name = " ".join(
        x for x in [user.first_name, user.last_name] if x
    ).strip()

    with closing(db_connect()) as conn:
        conn.execute(
            """
            INSERT INTO users
            (user_id, username, display_name, enabled, created_at)
            VALUES (?, ?, ?, 1, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                username = excluded.username,
                display_name = excluded.display_name
            """,
            (
                user.id,
                user.username or "",
                display_name,
                now,
            ),
        )
        conn.commit()


def user_is_allowed(user_id: int) -> bool:
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


def get_binding(user_id: int) -> Optional[sqlite3.Row]:
    with closing(db_connect()) as conn:
        return conn.execute(
            """
            SELECT b.*, u.username, u.display_name, u.enabled AS user_enabled
            FROM bindings b
            LEFT JOIN users u ON u.user_id = b.user_id
            WHERE b.user_id = ?
            """,
            (user_id,),
        ).fetchone()


def set_binding(
    user_id: int,
    chat_id: int,
    chat_title: str = "",
) -> None:
    now = utc_now()

    with closing(db_connect()) as conn:
        conn.execute(
            """
            INSERT INTO users
            (user_id, username, display_name, enabled, created_at)
            VALUES (?, '', '', 1, ?)
            ON CONFLICT(user_id) DO NOTHING
            """,
            (user_id, now),
        )

        conn.execute(
            """
            INSERT INTO bindings
            (user_id, chat_id, chat_title, enabled, created_at, updated_at)
            VALUES (?, ?, ?, 1, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                chat_id = excluded.chat_id,
                chat_title = excluded.chat_title,
                enabled = 1,
                updated_at = excluded.updated_at
            """,
            (user_id, chat_id, chat_title, now, now),
        )

        conn.execute(
            """
            UPDATE users
            SET enabled = 1
            WHERE user_id = ?
            """,
            (user_id,),
        )

        conn.commit()


def remove_binding(user_id: int) -> None:
    with closing(db_connect()) as conn:
        conn.execute(
            "UPDATE bindings SET enabled = 0, updated_at = ? WHERE user_id = ?",
            (utc_now(), user_id),
        )
        conn.execute(
            "UPDATE users SET enabled = 0 WHERE user_id = ?",
            (user_id,),
        )
        conn.commit()


def list_bindings():
    with closing(db_connect()) as conn:
        return conn.execute(
            """
            SELECT
                b.user_id,
                b.chat_id,
                b.chat_title,
                b.enabled,
                u.username,
                u.display_name
            FROM bindings b
            LEFT JOIN users u ON u.user_id = b.user_id
            ORDER BY b.user_id
            """
        ).fetchall()


# =========================
# 去重
# =========================

def make_text_key(text: str) -> str:
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return f"text:{digest}"


def get_message_unique_key(message: Message) -> Optional[str]:
    # Telegram 的 file_unique_id 适合做跨消息去重。
    if message.photo:
        # 最大尺寸照片通常是最后一个 PhotoSize。
        return f"photo:{message.photo[-1].file_unique_id}"

    if message.video:
        return f"video:{message.video.file_unique_id}"

    if message.document:
        return f"document:{message.document.file_unique_id}"

    if message.audio:
        return f"audio:{message.audio.file_unique_id}"

    if message.voice:
        return f"voice:{message.voice.file_unique_id}"

    if message.animation:
        return f"animation:{message.animation.file_unique_id}"

    if message.video_note:
        return f"video_note:{message.video_note.file_unique_id}"

    if message.text:
        return make_text_key(message.text)

    return None


def resource_exists(unique_key: str, target_chat_id: int) -> bool:
    with closing(db_connect()) as conn:
        row = conn.execute(
            """
            SELECT 1
            FROM resources
            WHERE unique_key = ?
              AND target_chat_id = ?
            LIMIT 1
            """,
            (unique_key, target_chat_id),
        ).fetchone()

    return row is not None


def save_resource_record(
    unique_key: str,
    resource_message_id: int,
    resource_type: str,
    owner_user_id: int,
    target_chat_id: int,
) -> bool:
    try:
        with closing(db_connect()) as conn:
            conn.execute(
                """
                INSERT INTO resources
                (
                    unique_key,
                    resource_message_id,
                    resource_type,
                    owner_user_id,
                    target_chat_id,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    unique_key,
                    resource_message_id,
                    resource_type,
                    owner_user_id,
                    target_chat_id,
                    utc_now(),
                ),
            )
            conn.commit()
        return True
    except sqlite3.IntegrityError:
        # 同一资源同时被重复处理时，UNIQUE 约束负责最后一道保险。
        return False


def resource_type(message: Message) -> str:
    if message.photo:
        return "photo"
    if message.video:
        return "video"
    if message.document:
        return "document"
    if message.audio:
        return "audio"
    if message.voice:
        return "voice"
    if message.animation:
        return "animation"
    if message.video_note:
        return "video_note"
    if message.text:
        return "text"
    return "other"


# =========================
# UI
# =========================

def main_menu(user_id: int) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                "📖 使用说明",
                callback_data="help",
            )
        ]
    ]

    if is_admin(user_id):
        rows.append(
            [
                InlineKeyboardButton(
                    "⚙️ 绑定管理",
                    callback_data="binding_menu",
                )
            ]
        )

    return InlineKeyboardMarkup(rows)


def binding_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "➕ 添加 / 修改绑定",
                    callback_data="binding_add",
                )
            ],
            [
                InlineKeyboardButton(
                    "🗑 删除绑定",
                    callback_data="binding_delete",
                )
            ],
            [
                InlineKeyboardButton(
                    "📋 查看全部绑定",
                    callback_data="binding_list",
                )
            ],
            [
                InlineKeyboardButton(
                    "🔍 检查群组",
                    callback_data="binding_check",
                )
            ],
            [
                InlineKeyboardButton(
                    "⬅️ 返回",
                    callback_data="main_menu",
                )
            ],
        ]
    )


def cancel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "❌ 取消",
                    callback_data="binding_cancel",
                )
            ]
        ]
    )


def confirm_binding_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "✅ 确认绑定",
                    callback_data="binding_confirm",
                ),
                InlineKeyboardButton(
                    "❌ 取消",
                    callback_data="binding_cancel",
                ),
            ]
        ]
    )


# =========================
# Conversation-like state
# =========================

STATE_KEY = "binding_state"
PENDING_USER_KEY = "pending_binding_user_id"
PENDING_CHAT_KEY = "pending_binding_chat_id"
PENDING_TITLE_KEY = "pending_binding_chat_title"


def set_state(context: ContextTypes.DEFAULT_TYPE, state: str) -> None:
    context.user_data[STATE_KEY] = state


def clear_state(context: ContextTypes.DEFAULT_TYPE) -> None:
    for key in [
        STATE_KEY,
        PENDING_USER_KEY,
        PENDING_CHAT_KEY,
        PENDING_TITLE_KEY,
    ]:
        context.user_data.pop(key, None)


# =========================
# 辅助
# =========================

def safe_display_name(row) -> str:
    display_name = row["display_name"] if row and row["display_name"] else ""
    username = row["username"] if row and row["username"] else ""

    if display_name:
        return display_name
    if username:
        return f"@{username}"
    return str(row["user_id"]) if row else "未知用户"


async def check_chat_access(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
) -> tuple[bool, str, Optional[object]]:
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


async def reject_if_not_allowed(
    update: Update,
) -> bool:
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


async def send_saved_notification(
    message: Message,
    saved_count: int,
    duplicate_count: int = 0,
) -> None:
    if saved_count and duplicate_count:
        text = (
            f"✅ 已保存 {saved_count} 个资源\n"
            f"♻️ 跳过 {duplicate_count} 个重复资源"
        )
    elif saved_count:
        text = f"✅ 已保存 {saved_count} 个资源"
    else:
        text = "♻️ 资源已存在，没有重复保存。"

    await message.reply_text(text)


# =========================
# 命令
# =========================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
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
    user = update.effective_user
    if not user:
        return

    await update.message.reply_text(
        f"你的 Telegram User ID 是：\n<code>{user.id}</code>",
        parse_mode=ParseMode.HTML,
    )


# =========================
# 管理菜单
# =========================

async def binding_menu_handler(
    query,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    user = query.from_user

    if not is_admin(user.id):
        await query.answer("只有管理员可以管理绑定。", show_alert=True)
        return

    clear_state(context)

    await query.edit_message_text(
        "⚙️ <b>绑定管理</b>\n\n"
        "这里管理「允许使用者 → 资源群组」的关系。",
        parse_mode=ParseMode.HTML,
        reply_markup=binding_menu(),
    )


async def binding_list_handler(
    query,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if not is_admin(query.from_user.id):
        await query.answer("没有权限。", show_alert=True)
        return

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

    await query.edit_message_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=binding_menu(),
    )


async def binding_add_handler(
    query,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if not is_admin(query.from_user.id):
        await query.answer("没有权限。", show_alert=True)
        return

    clear_state(context)
    set_state(context, "waiting_user_id")

    await query.edit_message_text(
        "➕ <b>添加 / 修改绑定</b>\n\n"
        "请输入允许使用者的 Telegram User ID。\n\n"
        "例如：<code>123456789</code>",
        parse_mode=ParseMode.HTML,
        reply_markup=cancel_keyboard(),
    )


async def binding_delete_handler(
    query,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if not is_admin(query.from_user.id):
        await query.answer("没有权限。", show_alert=True)
        return

    clear_state(context)
    set_state(context, "waiting_delete_user_id")

    await query.edit_message_text(
        "🗑 <b>删除绑定</b>\n\n"
        "请输入要删除的 Telegram User ID。",
        parse_mode=ParseMode.HTML,
        reply_markup=cancel_keyboard(),
    )


async def binding_check_handler(
    query,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if not is_admin(query.from_user.id):
        await query.answer("没有权限。", show_alert=True)
        return

    rows = list_bindings()

    if not rows:
        await query.edit_message_text(
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

    await query.edit_message_text(
        "\n".join(lines),
        parse_mode=ParseMode.HTML,
        reply_markup=binding_menu(),
    )


# =========================
# Callback
# =========================

async def callback_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
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


# =========================
# 管理员输入流程
# =========================

async def handle_admin_text_input(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> bool:
    if not update.message or not update.effective_user:
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

        await update.message.reply_text(
            "确认绑定？\n\n"
            f"👤 用户：<code>{pending_user_id}</code>\n"
            f"📚 资源群：<b>{html.escape(str(title))}</b>\n"
            f"🆔 Chat ID：<code>{chat_id}</code>\n\n"
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

    return False


# =========================
# Telegram 消息链接
# =========================

def parse_message_link(text: str):
    match = MESSAGE_LINK_RE.search(text)
    if not match:
        return None

    # username / c-style
    if match.group(3) and match.group(4):
        return {
            "chat": int(match.group(3)),
            "message_id": int(match.group(4)),
        }

    if match.group(1) and match.group(2):
        chat_ref = match.group(1)
        try:
            chat_ref = int(chat_ref)
        except ValueError:
            pass

        return {
            "chat": chat_ref,
            "message_id": int(match.group(2)),
        }

    return None


async def process_message_link(
    message: Message,
    link_info,
    context: ContextTypes.DEFAULT_TYPE,
    owner_user_id: int,
    target_chat_id: int,
) -> bool:
    source_chat = link_info["chat"]
    source_message_id = link_info["message_id"]

    logger.info(
        "收到消息链接 user_id=%s source=%s message_id=%s target=%s",
        owner_user_id,
        source_chat,
        source_message_id,
        target_chat_id,
    )

    # Bot API 的 forward/copy_message 需要机器人可以访问源消息。
    try:
        if isinstance(source_chat, int):
            copied = await context.bot.copy_message(
                chat_id=target_chat_id,
                from_chat_id=source_chat,
                message_id=source_message_id,
            )
        else:
            copied = await context.bot.copy_message(
                chat_id=target_chat_id,
                from_chat_id=source_chat,
                message_id=source_message_id,
            )

        # copy_message 返回 MessageId，而不是完整 Message。
        copied_message_id = getattr(copied, "message_id", None)

        # 链接本身无法可靠拿到源文件的 file_unique_id，
        # 因此用 source chat + source message 做链接级去重。
        unique_key = (
            f"link:{source_chat}:{source_message_id}"
        )

        if copied_message_id:
            save_resource_record(
                unique_key=unique_key,
                resource_message_id=copied_message_id,
                resource_type="message_link",
                owner_user_id=owner_user_id,
                target_chat_id=target_chat_id,
            )

        await message.reply_text(
            "✅ 已从消息链接保存到你的资源群组。"
        )
        return True

    except Exception as exc:
        logger.warning(
            "消息链接保存失败 source=%s message_id=%s: %s",
            source_chat,
            source_message_id,
            exc,
        )

        await message.reply_text(
            "❌ 这个消息链接无法由机器人读取或复制。\n\n"
            "常见原因：\n"
            "• 机器人无法访问源群组/频道\n"
            "• 内容受到 Telegram 的保护，禁止保存/转发\n"
            "• 源消息已删除\n"
            "• 链接指向私有内容，而机器人没有权限\n\n"
            "机器人不会绕过 Telegram 的内容保护限制。"
        )
        return False


# =========================
# Album
# =========================

async def process_album(
    messages: list[Message],
    context: ContextTypes.DEFAULT_TYPE,
    owner_user_id: int,
    target_chat_id: int,
) -> None:
    if not messages:
        return

    album_id = messages[0].media_group_id

    logger.info(
        "开始处理 Album user_id=%s album_id=%s count=%s target=%s",
        owner_user_id,
        album_id,
        len(messages),
        target_chat_id,
    )

    unique_messages = []
    duplicate_count = 0

    for msg in messages:
        key = get_message_unique_key(msg)

        if key and resource_exists(key, target_chat_id):
            duplicate_count += 1
            logger.info(
                "Album 重复资源 user_id=%s key=%s",
                owner_user_id,
                key,
            )
            continue

        unique_messages.append((msg, key))

    if not unique_messages:
        await messages[0].reply_text(
            f"♻️ Album 中 {duplicate_count} 个资源都已存在，没有重复保存。"
        )
        return

    # Telegram media group 主要是 photo/video。
    media_messages = [item[0] for item in unique_messages]

    try:
        copied_messages = await context.bot.copy_messages(
            chat_id=target_chat_id,
            from_chat_id=media_messages[0].chat_id,
            message_ids=[m.message_id for m in media_messages],
        )

        saved_count = 0

        # copy_messages 返回的 Message 列表与 message_ids 顺序对应。
        for (source_msg, key), copied in zip(
            unique_messages,
            copied_messages,
        ):
            if not key:
                continue

            copied_id = getattr(copied, "message_id", None)

            if save_resource_record(
                unique_key=key,
                resource_message_id=copied_id or 0,
                resource_type=resource_type(source_msg),
                owner_user_id=owner_user_id,
                target_chat_id=target_chat_id,
            ):
                saved_count += 1

        logger.info(
            "Album 保存完成 user_id=%s album_id=%s saved=%s duplicate=%s",
            owner_user_id,
            album_id,
            saved_count,
            duplicate_count,
        )

        await send_saved_notification(
            messages[0],
            saved_count,
            duplicate_count,
        )

    except AttributeError:
        # 某些 PTB 版本没有 copy_messages，退回逐条 copy。
        logger.warning(
            "当前 python-telegram-bot 不支持 copy_messages，使用逐条复制。"
        )

        saved_count = 0

        for source_msg, key in unique_messages:
            try:
                copied = await source_msg.copy(
                    chat_id=target_chat_id,
                )

                if key and save_resource_record(
                    unique_key=key,
                    resource_message_id=copied.message_id,
                    resource_type=resource_type(source_msg),
                    owner_user_id=owner_user_id,
                    target_chat_id=target_chat_id,
                ):
                    saved_count += 1

            except Exception as exc:
                logger.exception(
                    "Album 单条保存失败 message_id=%s: %s",
                    source_msg.message_id,
                    exc,
                )

        await send_saved_notification(
            messages[0],
            saved_count,
            duplicate_count,
        )

    except Exception as exc:
        logger.exception(
            "Album 保存失败 user_id=%s album_id=%s: %s",
            owner_user_id,
            album_id,
            exc,
        )

        await messages[0].reply_text(
            "❌ Album 保存失败，请检查机器人在目标群组中的权限。"
        )


# =========================
# 普通资源处理
# =========================

async def process_single_message(
    message: Message,
    context: ContextTypes.DEFAULT_TYPE,
    owner_user_id: int,
    target_chat_id: int,
) -> None:
    key = get_message_unique_key(message)

    logger.info(
        "收到资源 user_id=%s type=%s message_id=%s target=%s key=%s",
        owner_user_id,
        resource_type(message),
        message.message_id,
        target_chat_id,
        key,
    )

    if key and resource_exists(key, target_chat_id):
        logger.info(
            "重复资源，跳过 user_id=%s key=%s",
            owner_user_id,
            key,
        )
        await message.reply_text("♻️ 资源已存在，没有重复保存。")
        return

    try:
        copied = await message.copy(
            chat_id=target_chat_id,
        )

        if key:
            inserted = save_resource_record(
                unique_key=key,
                resource_message_id=copied.message_id,
                resource_type=resource_type(message),
                owner_user_id=owner_user_id,
                target_chat_id=target_chat_id,
            )

            if not inserted:
                logger.info(
                    "数据库检测到重复插入 user_id=%s key=%s",
                    owner_user_id,
                    key,
                )
                await message.reply_text(
                    "♻️ 资源已存在，没有重复保存。"
                )
                return

        logger.info(
            "资源保存成功 user_id=%s target=%s saved_message_id=%s",
            owner_user_id,
            target_chat_id,
            copied.message_id,
        )

        await message.reply_text("✅ 已保存到你的资源群组。")

    except Exception as exc:
        logger.exception(
            "资源保存失败 user_id=%s target=%s: %s",
            owner_user_id,
            target_chat_id,
            exc,
        )
        await message.reply_text(
            "❌ 保存失败，请检查目标资源群组和机器人的权限。"
        )


# =========================
# 普通消息入口
# =========================

async def message_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if not update.message or not update.effective_user:
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

    # Telegram 消息链接。
    text = update.message.text or update.message.caption or ""
    link_info = parse_message_link(text)

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

            asyncio.create_task(delayed_process())

        return

    await process_single_message(
        update.message,
        context,
        user.id,
        target_chat_id,
    )


# =========================
# 错误处理
# =========================

async def error_handler(
    update: object,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    logger.exception(
        "Unhandled exception: %s",
        context.error,
    )


# =========================
# 主程序
# =========================

def main() -> None:
    if BOT_TOKEN == "YOUR_NEW_BOT_TOKEN":
        raise RuntimeError(
            "请先把 BOT_TOKEN 修改成你新的 Telegram Bot Token。"
        )

    if not ADMIN_USER_IDS or 123456789 in ADMIN_USER_IDS:
        logger.warning(
            "ADMIN_USER_IDS 仍可能使用示例 ID，请确认已经改成你的 Telegram User ID。"
        )

    init_db()

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
        CommandHandler("myid", myid_command)
    )

    application.add_handler(
        CallbackQueryHandler(callback_handler)
    )

    application.add_handler(
        MessageHandler(
            filters.ALL & ~filters.COMMAND,
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
