import asyncio
import hashlib
import logging
import sqlite3
from pathlib import Path

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
    InputMediaVideo,
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

# =========================================================
# 配置
# =========================================================

# ⚠️ 请使用你重新生成的 Bot Token
BOT_TOKEN = "8881033725:AAHEVR3Z52HcYt_AhD7i7hQmLK6v7ZCvIAo"

# 私人资源群
RESOURCE_CHAT_ID = -1003145884431

# =========================================================
# 【功能 1】允许使用 Bot 的 Telegram User ID
# =========================================================
#
# 把下面的 123456789 换成你自己的 Telegram User ID。
#
# 如果只有你一个人：
# ALLOWED_USER_IDS = {123456789}
#
# 如果以后需要允许多人：
# ALLOWED_USER_IDS = {123456789, 987654321}
#
# =========================================================

ALLOWED_USER_IDS = {
    5822972759,  # <-- 改成你的 Telegram User ID
}

# Album 等待时间
ALBUM_WAIT_SECONDS = 1.5

# SQLite 数据库
DB_FILE = Path("resource_backup.db")


# =========================================================
# 日志
# =========================================================

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)

logger = logging.getLogger("resource_backup_bot")


# =========================================================
# Album 临时缓存
# =========================================================

album_tasks = {}


# =========================================================
# 数据库
# =========================================================

db_lock = asyncio.Lock()


def init_database():
    """
    创建资源去重数据库。

    unique_key:
        文件资源使用 Telegram file_unique_id。
        文字消息使用内容 SHA256。
    """

    conn = sqlite3.connect(DB_FILE)

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS resources (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            unique_key TEXT NOT NULL UNIQUE,
            resource_message_id INTEGER,
            resource_type TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    conn.commit()
    conn.close()

    logger.info(
        "DATABASE READY | %s",
        DB_FILE.absolute(),
    )


def is_duplicate_sync(unique_key: str) -> bool:
    conn = sqlite3.connect(DB_FILE)

    row = conn.execute(
        """
        SELECT id
        FROM resources
        WHERE unique_key = ?
        LIMIT 1
        """,
        (unique_key,),
    ).fetchone()

    conn.close()

    return row is not None


def save_resource_sync(
    unique_key: str,
    resource_message_id: int,
    resource_type: str,
):
    conn = sqlite3.connect(DB_FILE)

    try:
        conn.execute(
            """
            INSERT OR IGNORE INTO resources
            (
                unique_key,
                resource_message_id,
                resource_type
            )
            VALUES (?, ?, ?)
            """,
            (
                unique_key,
                resource_message_id,
                resource_type,
            ),
        )

        conn.commit()

    finally:
        conn.close()


async def is_duplicate(unique_key: str) -> bool:
    async with db_lock:
        return await asyncio.to_thread(
            is_duplicate_sync,
            unique_key,
        )


async def save_resource(
    unique_key: str,
    resource_message_id: int,
    resource_type: str,
):
    async with db_lock:
        await asyncio.to_thread(
            save_resource_sync,
            unique_key,
            resource_message_id,
            resource_type,
        )


# =========================================================
# 获取消息唯一 ID
# =========================================================

def get_message_unique_key(message):
    """
    获取资源的稳定唯一标识。

    Telegram 文件：
        使用 file_unique_id。

    文字：
        使用 SHA256。

    其他类型：
        暂时返回 None，不做去重。
    """

    if message.photo:
        # 使用最大尺寸照片的 file_unique_id
        photo = message.photo[-1]

        return (
            f"photo:{photo.file_unique_id}"
        )

    if message.video:
        return (
            f"video:{message.video.file_unique_id}"
        )

    if message.document:
        return (
            f"document:{message.document.file_unique_id}"
        )

    if message.audio:
        return (
            f"audio:{message.audio.file_unique_id}"
        )

    if message.animation:
        return (
            f"animation:{message.animation.file_unique_id}"
        )

    if message.voice:
        return (
            f"voice:{message.voice.file_unique_id}"
        )

    if message.video_note:
        return (
            f"video_note:{message.video_note.file_unique_id}"
        )

    # =====================================================
    # 文字消息
    # =====================================================

    if message.text:
        raw = message.text.encode(
            "utf-8"
        )

        digest = hashlib.sha256(
            raw
        ).hexdigest()

        return f"text:{digest}"

    return None


# =========================================================
# 判断消息类型
# =========================================================

def get_message_type(message):
    if message.photo:
        return "PHOTO"
    if message.video:
        return "VIDEO"
    if message.document:
        return "DOCUMENT"
    if message.audio:
        return "AUDIO"
    if message.voice:
        return "VOICE"
    if message.animation:
        return "ANIMATION"
    if message.video_note:
        return "VIDEO_NOTE"
    if message.text:
        return "TEXT"
    if message.sticker:
        return "STICKER"
    if message.contact:
        return "CONTACT"
    if message.location:
        return "LOCATION"

    return "OTHER"


# =========================================================
# 权限检查
# =========================================================

def is_allowed_user(update: Update) -> bool:
    user = update.effective_user

    if not user:
        return False

    return user.id in ALLOWED_USER_IDS


async def reject_unauthorized(
    update: Update,
):
    user = update.effective_user

    if not user:
        return

    logger.warning(
        "ACCESS DENIED | user_id=%s | username=%s",
        user.id,
        user.username or "-",
    )

    if update.callback_query:
        try:
            await update.callback_query.answer(
                "❌ 你没有使用权限。",
                show_alert=True,
            )
        except Exception:
            pass

        return

    if update.message:
        try:
            await update.message.reply_text(
                "⛔ 你没有使用此 Bot 的权限。"
            )
        except Exception:
            pass


# =========================================================
# /myid
# =========================================================

async def myid_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    """
    用于第一次配置白名单。

    任何人都只能看到自己的 ID，不会看到别人的。
    """

    if not update.message:
        return

    user = update.effective_user

    if not user:
        return

    await update.message.reply_text(
        "🆔 你的 Telegram User ID：\n\n"
        f"<code>{user.id}</code>\n\n"
        "把这个数字加入代码里的 "
        "ALLOWED_USER_IDS 即可。",
        parse_mode="HTML",
    )

    logger.info(
        "MYID | user_id=%s | username=%s",
        user.id,
        user.username or "-",
    )


# =========================================================
# 工具：生成资源链接
# =========================================================

def make_message_link(
    chat_id: int,
    message_id: int,
) -> str:
    chat_id_str = str(chat_id)

    if chat_id_str.startswith("-100"):
        chat_id_str = chat_id_str[4:]

    return f"https://t.me/c/{chat_id_str}/{message_id}"


# =========================================================
# 主菜单
# =========================================================

def main_menu_keyboard():
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "📖 使用说明",
                    callback_data="help",
                )
            ]
        ]
    )


def main_menu_text():
    return (
        "📦 <b>个人资源备份 Bot</b>\n\n"
        "你好！我是你的 Telegram 个人资源备份助手。\n\n"
        "你可以直接把 Telegram 中的：\n"
        "🎬 视频\n"
        "🖼️ 图片\n"
        "📄 文件\n"
        "📝 文字\n\n"
        "转发给我，我会自动保存到你的私人资源群。\n\n"
        "✨ 支持保留原始文字说明\n"
        "✨ 不需要下载到电脑再上传\n\n"
        "直接转发资源给我即可。"
    )


# =========================================================
# /start
# =========================================================

async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if not is_allowed_user(update):
        await reject_unauthorized(update)
        return

    if not update.message:
        return

    logger.info(
        "START | user=%s | chat=%s",
        update.effective_user.id,
        update.effective_chat.id,
    )

    await update.message.reply_text(
        main_menu_text(),
        parse_mode="HTML",
        reply_markup=main_menu_keyboard(),
    )


# =========================================================
# /help
# =========================================================

async def help_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if not is_allowed_user(update):
        await reject_unauthorized(update)
        return

    if not update.message:
        return

    await send_help_message(
        update.message
    )


async def send_help_message(message):
    text = (
        "📖 <b>使用说明</b>\n\n"
        "① 在 Telegram 找到你想保存的资源\n"
        "② 点击转发\n"
        "③ 转发给这个 Bot\n"
        "④ Bot 会自动复制到你的私人资源群\n\n"
        "支持：\n"
        "🎬 视频\n"
        "🖼️ 图片\n"
        "📄 文件\n"
        "📝 文字消息"
    )

    keyboard = [
        [
            InlineKeyboardButton(
                "⬅️ 返回主菜单",
                callback_data="home",
            )
        ]
    ]

    await message.reply_text(
        text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            keyboard
        ),
    )


# =========================================================
# Inline Keyboard
# =========================================================

async def button_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if not is_allowed_user(update):
        await reject_unauthorized(update)
        return

    query = update.callback_query

    if not query:
        return

    # 必须 answer，否则 Telegram 客户端可能一直转圈
    await query.answer()

    logger.info(
        "BUTTON | user=%s | data=%s",
        update.effective_user.id,
        query.data,
    )

    if query.data == "home":

        await query.message.edit_text(
            main_menu_text(),
            parse_mode="HTML",
            reply_markup=main_menu_keyboard(),
        )

        return

    if query.data == "help":

        text = (
            "📖 <b>使用说明</b>\n\n"
            "① 在 Telegram 找到你想保存的资源\n"
            "② 点击转发\n"
            "③ 转发给这个 Bot\n"
            "④ Bot 会自动复制到你的私人资源群\n\n"
            "支持：\n"
            "🎬 视频\n"
            "🖼️ 图片\n"
            "📄 文件\n"
            "📝 文字消息"
        )

        keyboard = [
            [
                InlineKeyboardButton(
                    "⬅️ 返回主菜单",
                    callback_data="home",
                )
            ]
        ]

        await query.message.edit_text(
            text,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(
                keyboard
            ),
        )


# =========================================================
# 保存成功通知
# =========================================================

async def send_saved_notification(
    message,
    saved_message_id: int,
    text: str = "✅ <b>资源已保存</b>",
):
    link = make_message_link(
        RESOURCE_CHAT_ID,
        saved_message_id,
    )

    keyboard = [
        [
            InlineKeyboardButton(
                "🔗 查看资源",
                url=link,
            )
        ]
    ]

    await message.reply_text(
        text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            keyboard
        ),
    )


# =========================================================
# 重复资源通知
# =========================================================

async def send_duplicate_notification(
    message,
):
    await message.reply_text(
        "♻️ <b>资源已存在</b>\n\n"
        "这个资源之前已经保存过了。",
        parse_mode="HTML",
    )


# =========================================================
# 保存单条消息
# =========================================================

async def save_single_message(
    message,
    bot,
):
    message_type = get_message_type(
        message
    )

    unique_key = get_message_unique_key(
        message
    )

    logger.info(
        "SAVE CHECK | message_id=%s | type=%s | unique_key=%s",
        message.message_id,
        message_type,
        unique_key or "-",
    )

    # =====================================================
    # 去重
    # =====================================================

    if unique_key:

        if await is_duplicate(
            unique_key
        ):
            logger.info(
                "DUPLICATE | message_id=%s | type=%s",
                message.message_id,
                message_type,
            )

            await send_duplicate_notification(
                message
            )

            return

    # =====================================================
    # 保存
    # =====================================================

    try:
        logger.info(
            "SAVE START | message_id=%s | type=%s",
            message.message_id,
            message_type,
        )

        saved = await message.copy(
            chat_id=RESOURCE_CHAT_ID,
        )

        # -------------------------------------------------
        # 保存数据库记录
        # -------------------------------------------------

        if unique_key:

            await save_resource(
                unique_key,
                saved.message_id,
                message_type,
            )

        logger.info(
            "SAVE OK | message_id=%s -> resource_message_id=%s | type=%s",
            message.message_id,
            saved.message_id,
            message_type,
        )

        await send_saved_notification(
            message,
            saved.message_id,
        )

    except Exception:

        logger.exception(
            "SAVE FAILED | message_id=%s | type=%s",
            message.message_id,
            message_type,
        )

        try:
            await message.reply_text(
                "❌ 保存失败，请检查 Bot 是否有权限发送到资源群。"
            )
        except Exception:
            pass


# =========================================================
# Album 处理
# =========================================================

async def process_album(
    album_id,
    messages,
    bot,
):
    try:

        logger.info(
            "ALBUM WAIT | album_id=%s | messages=%s",
            album_id,
            len(messages),
        )

        await asyncio.sleep(
            ALBUM_WAIT_SECONDS
        )

        messages = sorted(
            messages,
            key=lambda x: x.message_id,
        )

        # =================================================
        # 先过滤已经存在的资源
        # =================================================

        new_messages = []

        duplicate_count = 0

        for message in messages:

            unique_key = get_message_unique_key(
                message
            )

            if unique_key:

                if await is_duplicate(
                    unique_key
                ):
                    duplicate_count += 1

                    logger.info(
                        "ALBUM DUPLICATE | album_id=%s | message_id=%s",
                        album_id,
                        message.message_id,
                    )

                    continue

            new_messages.append(
                message
            )

        # =================================================
        # 全部重复
        # =================================================

        if not new_messages:

            logger.info(
                "ALBUM ALL DUPLICATE | album_id=%s | count=%s",
                album_id,
                duplicate_count,
            )

            await messages[0].reply_text(
                "♻️ <b>资源已存在</b>\n\n"
                "这个 Album 中的资源之前已经保存过了。",
                parse_mode="HTML",
            )

            return

        # =================================================
        # 构造 Media Group
        # =================================================

        media = []

        for message in new_messages:

            if message.photo:

                photo = message.photo[-1]

                media.append(
                    InputMediaPhoto(
                        media=photo.file_id,
                        caption=message.caption,
                        caption_entities=message.caption_entities,
                    )
                )

            elif message.video:

                media.append(
                    InputMediaVideo(
                        media=message.video.file_id,
                        caption=message.caption,
                        caption_entities=message.caption_entities,
                    )
                )

        # =================================================
        # 两个以上媒体
        # =================================================

        if len(media) >= 2:

            logger.info(
                "ALBUM SAVE START | album_id=%s | new=%s | duplicate=%s",
                album_id,
                len(media),
                duplicate_count,
            )

            saved_messages = await bot.send_media_group(
                chat_id=RESOURCE_CHAT_ID,
                media=media,
            )

            # -------------------------------------------------
            # 写入数据库
            # -------------------------------------------------

            saved_index = 0

            for message in new_messages:

                unique_key = get_message_unique_key(
                    message
                )

                if not unique_key:
                    continue

                if saved_index >= len(saved_messages):
                    break

                await save_resource(
                    unique_key,
                    saved_messages[
                        saved_index
                    ].message_id,
                    get_message_type(message),
                )

                saved_index += 1

            first_saved_message = (
                saved_messages[0]
            )

            logger.info(
                "ALBUM SAVE OK | album_id=%s | saved=%s | duplicate=%s | first_message_id=%s",
                album_id,
                len(saved_messages),
                duplicate_count,
                first_saved_message.message_id,
            )

            link = make_message_link(
                RESOURCE_CHAT_ID,
                first_saved_message.message_id,
            )

            keyboard = [
                [
                    InlineKeyboardButton(
                        "🔗 查看资源",
                        url=link,
                    )
                ]
            ]

            result_text = (
                "✅ <b>资源已保存</b>\n\n"
                f"保存：{len(saved_messages)} 个"
            )

            if duplicate_count:
                result_text += (
                    f"\n已跳过重复：{duplicate_count} 个"
                )

            await messages[0].reply_text(
                result_text,
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(
                    keyboard
                ),
            )

        # =================================================
        # 只有一个新媒体
        # =================================================

        elif len(new_messages) == 1:

            await save_single_message(
                new_messages[0],
                bot,
            )

        # =================================================
        # 没有可处理媒体
        # =================================================

        else:

            logger.warning(
                "ALBUM NO MEDIA | album_id=%s",
                album_id,
            )

            for message in new_messages:
                await save_single_message(
                    message,
                    bot,
                )

    except asyncio.CancelledError:

        logger.info(
            "ALBUM CANCELLED | album_id=%s",
            album_id,
        )

        raise

    except Exception:

        logger.exception(
            "ALBUM SAVE FAILED | album_id=%s",
            album_id,
        )

        try:

            if messages:

                await messages[0].reply_text(
                    "❌ Album 保存失败，请稍后再试。"
                )

        except Exception:
            pass

    finally:

        current = album_tasks.get(
            album_id
        )

        if current:

            current_task = current.get(
                "task"
            )

            if current_task is asyncio.current_task():

                album_tasks.pop(
                    album_id,
                    None,
                )


# =========================================================
# 普通消息 / Album
# =========================================================

async def handle_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    # =====================================================
    # 权限
    # =====================================================

    if not is_allowed_user(update):

        await reject_unauthorized(
            update
        )

        return

    message = update.message

    if not message:
        return

    user_id = update.effective_user.id

    message_type = get_message_type(
        message
    )

    logger.info(
        "MESSAGE | user=%s | message_id=%s | type=%s | album=%s",
        user_id,
        message.message_id,
        message_type,
        message.media_group_id or "-",
    )

    # =====================================================
    # Album
    # =====================================================

    if message.media_group_id:

        album_id = message.media_group_id

        if album_id not in album_tasks:

            album_tasks[album_id] = {
                "messages": [],
                "task": None,
            }

        album = album_tasks[album_id]

        existing_ids = {
            msg.message_id
            for msg in album["messages"]
        }

        if message.message_id not in existing_ids:

            album["messages"].append(
                message
            )

        old_task = album.get(
            "task"
        )

        if old_task and not old_task.done():

            old_task.cancel()

        messages_snapshot = list(
            album["messages"]
        )

        new_task = asyncio.create_task(
            process_album(
                album_id,
                messages_snapshot,
                context.bot,
            )
        )

        album["task"] = new_task

        return

    # =====================================================
    # 普通消息
    # =====================================================

    await save_single_message(
        message,
        context.bot,
    )


# =========================================================
# 错误处理
# =========================================================

async def error_handler(
    update: object,
    context: ContextTypes.DEFAULT_TYPE,
):
    logger.exception(
        "UNHANDLED ERROR",
        exc_info=context.error,
    )


# =========================================================
# Bot 启动
# =========================================================

async def post_init(
    application: Application,
):
    logger.info(
        "========================================"
    )

    logger.info(
        "🤖 Telegram 资源备份 Bot"
    )

    logger.info(
        "========================================"
    )

    logger.info(
        "Bot 正在启动..."
    )

    logger.info(
        "Resource Chat ID: %s",
        RESOURCE_CHAT_ID,
    )

    logger.info(
        "Album Wait: %s seconds",
        ALBUM_WAIT_SECONDS,
    )

    logger.info(
        "Allowed Users: %s",
        len(ALLOWED_USER_IDS),
    )

    init_database()

    # =====================================================
    # 检查白名单是否还是默认值
    # =====================================================

    if ALLOWED_USER_IDS == {123456789}:

        logger.warning(
            "⚠️ 你还没有修改 ALLOWED_USER_IDS！"
        )

        logger.warning(
            "请把 123456789 改成你自己的 Telegram User ID。"
        )

    try:

        me = await application.bot.get_me()

        logger.info(
            "Bot connected: @%s (id=%s)",
            me.username,
            me.id,
        )

        logger.info(
            "✅ Bot 启动成功，等待消息..."
        )

        logger.info(
            "========================================"
        )

    except Exception:

        logger.exception(
            "❌ 无法连接 Telegram"
        )


# =========================================================
# 主程序
# =========================================================

def main():

    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .build()
    )

    # =====================================================
    # /myid
    #
    # 放在权限检查之外，方便第一次获取自己的 ID
    # =====================================================

    application.add_handler(
        CommandHandler(
            "myid",
            myid_command,
        )
    )

    # =====================================================
    # 命令
    # =====================================================

    application.add_handler(
        CommandHandler(
            "start",
            start,
        )
    )

    application.add_handler(
        CommandHandler(
            "help",
            help_command,
        )
    )

    # =====================================================
    # Inline Keyboard
    # =====================================================

    application.add_handler(
        CallbackQueryHandler(
            button_callback,
        )
    )

    # =====================================================
    # 普通消息
    # =====================================================

    application.add_handler(
        MessageHandler(
            filters.ALL & ~filters.COMMAND,
            handle_message,
        )
    )

    # =====================================================
    # 错误处理
    # =====================================================

    application.add_error_handler(
        error_handler
    )

    # =====================================================
    # 启动
    # =====================================================

    logger.info(
        "Starting polling..."
    )

    application.run_polling(
        drop_pending_updates=True
    )


# =========================================================
# 程序入口
# =========================================================

if __name__ == "__main__":
    main()
