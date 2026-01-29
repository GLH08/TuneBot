"""
TuneBot - Telegram 音乐下载与归档机器人
主程序入口
"""
import os
import logging
import io
import re
import asyncio
import tempfile
from uuid import uuid4
from pathlib import Path

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InlineQueryResultArticle,
    InputTextMessageContent,
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    InlineQueryHandler,
    ContextTypes,
)
from telegram.constants import ParseMode

from config import (
    BOT_TOKEN,
    ARCHIVE_CHANNEL_ID,
    ALLOWED_USER_IDS,
    DEFAULT_QUALITY,
    VALID_QUALITIES,
    PLATFORMS,
    MAX_FILE_SIZE,
    TELEGRAM_API_ID,
    TELEGRAM_API_HASH,
)
from utils import (
    client,
    init_db,
    format_song_caption,
    format_favorite_item,
    format_history_item,
    format_platform,
    format_file_size,
    make_hashtag,
    make_hashtags,
    add_favorite,
    remove_favorite,
    is_favorite,
    get_favorites,
    get_favorites_count,
    add_history,
    get_history,
    get_history_count,
    find_history_by_song,
    get_history_by_id,
)

# 日志配置
log_level = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=getattr(logging, log_level, logging.INFO)
)
logger = logging.getLogger(__name__)

# Pyrogram 客户端（用于大文件上传）
pyrogram_client = None
PYROGRAM_ENABLED = False

if TELEGRAM_API_ID and TELEGRAM_API_HASH:
    try:
        from pyrogram import Client
        # 设置 Pyrogram 日志级别为 WARNING，避免 DEBUG 输出大量二进制数据
        logging.getLogger("pyrogram").setLevel(logging.WARNING)
        # 确保 workdir 存在
        pyrogram_workdir = Path(tempfile.gettempdir()) / "tunebot_pyrogram"
        pyrogram_workdir.mkdir(parents=True, exist_ok=True)
        pyrogram_client = Client(
            "tunebot_uploader",
            api_id=int(TELEGRAM_API_ID),
            api_hash=TELEGRAM_API_HASH,
            bot_token=BOT_TOKEN,
            workdir=str(pyrogram_workdir)
        )
        PYROGRAM_ENABLED = True
        logger.info("Pyrogram 大文件上传已启用")
    except Exception as e:
        logger.warning(f"Pyrogram 初始化失败: {e}，将使用标准 Bot API（50MB 限制）")

# 用户设置缓存
user_quality: dict[int, str] = {}


# ==================== 工具函数 ====================

def get_file_extension(quality: str) -> str:
    """根据音质获取文件扩展名"""
    if quality in ("flac", "flac24bit"):
        return ".flac"
    return ".mp3"


async def upload_large_audio(
    chat_id: int,
    audio_bytes: bytes,
    filename: str,
    title: str,
    performer: str,
    caption: str,
    cover_bytes: bytes = b""
) -> str:
    """使用 Pyrogram 上传大文件，返回 file_id"""
    if not PYROGRAM_ENABLED or not pyrogram_client:
        raise RuntimeError("Pyrogram 未启用")

    # 创建临时文件
    with tempfile.NamedTemporaryFile(delete=False, suffix=Path(filename).suffix) as audio_file:
        audio_file.write(audio_bytes)
        audio_path = audio_file.name

    thumb_path = None
    if cover_bytes:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as thumb_file:
            thumb_file.write(cover_bytes)
            thumb_path = thumb_file.name

    try:
        async with pyrogram_client:
            msg = await pyrogram_client.send_audio(
                chat_id=chat_id,
                audio=audio_path,
                thumb=thumb_path,
                title=title,
                performer=performer,
                caption=caption,
                file_name=filename
            )
            return msg.audio.file_id if msg.audio else ""
    finally:
        # 清理临时文件
        try:
            os.unlink(audio_path)
            if thumb_path:
                os.unlink(thumb_path)
        except Exception:
            pass


# ==================== 鉴权 ====================

def is_allowed(user_id: int) -> bool:
    """检查用户是否有权限"""
    if not ALLOWED_USER_IDS:
        return True
    return user_id in ALLOWED_USER_IDS


async def check_permission(update: Update) -> bool:
    """检查权限，无权限则回复提示"""
    if not update.effective_user:
        return False
    user_id = update.effective_user.id
    if not is_allowed(user_id):
        if update.message:
            await update.message.reply_text("⛔ 无权限使用此机器人")
        return False
    return True


# ==================== 命令处理 ====================

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理 /start 命令"""
    if not await check_permission(update):
        return
    await update.message.reply_text(
        "🎵 *TuneBot* - 音乐搜索与归档\n\n"
        "使用方法:\n"
        "• /search <歌名> - 搜索歌曲\n"
        "• /quality - 切换音质\n"
        "• /fav - 查看收藏夹\n"
        "• /history - 下载历史\n"
        "• /top - 查看排行榜\n"
        "• /help - 获取帮助\n\n"
        "💡 在任意聊天中输入 @机器人用户名 歌名 即可快速搜索",
        parse_mode=ParseMode.MARKDOWN
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理 /help 命令"""
    if not await check_permission(update):
        return
    user_id = update.effective_user.id if update.effective_user else 0
    current_quality = user_quality.get(user_id, DEFAULT_QUALITY)
    await update.message.reply_text(
        "📖 *帮助文档*\n\n"
        "*基础命令*\n"
        "• /search <关键词> - 聚合搜索\n"
        "• /quality - 切换下载音质\n\n"
        "*收藏与历史*\n"
        "• /fav - 查看收藏夹\n"
        "• /history - 查看下载历史\n\n"
        "*排行榜*\n"
        "• /top - 查看排行榜列表\n\n"
        "*Inline 模式*\n"
        "在任意聊天中输入:\n"
        "`@机器人用户名 歌名`\n"
        "即可快速搜索并发送\n\n"
        f"当前音质: *{current_quality}*",
        parse_mode=ParseMode.MARKDOWN
    )


async def cmd_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理 /search 命令"""
    if not await check_permission(update):
        return

    if not context.args:
        await update.message.reply_text("用法: /search <歌名>\n例如: /search 七里香")
        return

    keyword = " ".join(context.args)
    msg = await update.message.reply_text(f"🔍 正在搜索: {keyword}...")

    results = await client.aggregate_search(keyword)
    if not results:
        await msg.edit_text("❌ 未找到相关歌曲")
        return

    # 最多显示 10 条
    results = results[:10]
    buttons = []
    for r in results:
        name = r.name[:20]
        artist = r.artist[:15]
        source = r.platform
        song_id = r.id
        btn_text = f"{name} - {artist} [{format_platform(source)}]"
        callback_data = f"dl|{source}|{song_id}"
        buttons.append([InlineKeyboardButton(btn_text, callback_data=callback_data)])

    await msg.edit_text(
        f"🎵 搜索结果: {keyword}\n选择要下载的歌曲:",
        reply_markup=InlineKeyboardMarkup(buttons)
    )


async def cmd_quality(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理 /quality 命令"""
    if not await check_permission(update):
        return

    user_id = update.effective_user.id
    current = user_quality.get(user_id, DEFAULT_QUALITY)

    buttons = []
    for q in ["128k", "320k", "flac", "flac24bit"]:
        label = f"✓ {q}" if q == current else q
        buttons.append(InlineKeyboardButton(label, callback_data=f"quality|{q}"))

    await update.message.reply_text(
        f"🎧 当前音质: *{current}*\n选择新的音质:",
        reply_markup=InlineKeyboardMarkup([buttons]),
        parse_mode=ParseMode.MARKDOWN
    )


async def cmd_fav(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理 /fav 命令"""
    if not await check_permission(update):
        return

    page = 0
    if context.args and context.args[0].isdigit():
        page = int(context.args[0]) - 1

    await show_favorites(update, page)


async def show_favorites(update: Update, page: int = 0):
    """显示收藏夹"""
    limit = 10
    offset = page * limit
    total = await get_favorites_count()
    items = await get_favorites(limit, offset)

    if not items:
        text = "📁 收藏夹为空\n下载歌曲时点击「收藏」按钮添加"
        if update.callback_query:
            await update.callback_query.edit_message_text(text)
        else:
            await update.message.reply_text(text)
        return

    lines = [f"📁 *收藏夹* ({total} 首)\n"]
    buttons = []
    for i, item in enumerate(items, start=offset + 1):
        lines.append(format_favorite_item(item, i))
        source = item['source']
        song_id = item['song_id']
        btn_text = f"{item['name'][:15]} - {item['artist'][:10]}"
        # 每行两个按钮：下载和取消收藏
        buttons.append([
            InlineKeyboardButton(f"📥 {btn_text}", callback_data=f"dl|{source}|{song_id}"),
            InlineKeyboardButton("💔", callback_data=f"delfav_list|{source}|{song_id}|{page}")
        ])

    # 分页按钮
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️ 上一页", callback_data=f"fav|{page - 1}"))
    if (page + 1) * limit < total:
        nav_buttons.append(InlineKeyboardButton("➡️ 下一页", callback_data=f"fav|{page + 1}"))
    if nav_buttons:
        buttons.append(nav_buttons)

    text = "\n".join(lines)
    markup = InlineKeyboardMarkup(buttons)

    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=markup, parse_mode=ParseMode.MARKDOWN)
    else:
        await update.message.reply_text(text, reply_markup=markup, parse_mode=ParseMode.MARKDOWN)


async def cmd_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理 /history 命令"""
    if not await check_permission(update):
        return

    page = 0
    if context.args and context.args[0].isdigit():
        page = int(context.args[0]) - 1

    await show_history(update, page)


async def show_history(update: Update, page: int = 0):
    """显示历史记录"""
    limit = 10
    offset = page * limit
    total = await get_history_count()
    items = await get_history(limit, offset)

    if not items:
        text = "📜 暂无下载历史"
        if update.callback_query:
            await update.callback_query.edit_message_text(text)
        else:
            await update.message.reply_text(text)
        return

    lines = [f"📜 *下载历史* ({total} 首)\n"]
    buttons = []
    for i, item in enumerate(items, start=offset + 1):
        lines.append(format_history_item(item, i))
        # 如果有 file_id，可以快速重发
        if item.get("file_id"):
            callback_data = f"resend|{item['id']}"
        else:
            callback_data = f"dl|{item['source']}|{item['song_id']}"
        btn_text = f"{item['name'][:15]} - {item['artist'][:10]}"
        buttons.append([InlineKeyboardButton(btn_text, callback_data=callback_data)])

    # 分页按钮
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️ 上一页", callback_data=f"history|{page - 1}"))
    if (page + 1) * limit < total:
        nav_buttons.append(InlineKeyboardButton("➡️ 下一页", callback_data=f"history|{page + 1}"))
    if nav_buttons:
        buttons.append(nav_buttons)

    text = "\n".join(lines)
    markup = InlineKeyboardMarkup(buttons)

    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=markup, parse_mode=ParseMode.MARKDOWN)
    else:
        await update.message.reply_text(text, reply_markup=markup, parse_mode=ParseMode.MARKDOWN)


async def cmd_top(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理 /top 命令"""
    if not await check_permission(update):
        return

    # 显示平台选择
    buttons = []
    for source, name in PLATFORMS.items():
        buttons.append([InlineKeyboardButton(name, callback_data=f"toplists|{source}")])

    await update.message.reply_text(
        "📊 选择平台查看排行榜:",
        reply_markup=InlineKeyboardMarkup(buttons)
    )


# ==================== 回调处理 ====================

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理按钮回调"""
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    if not is_allowed(user_id):
        await query.edit_message_text("⛔ 无权限")
        return

    data = query.data
    if not data:
        return

    parts = data.split("|")
    action = parts[0]

    try:
        if action == "dl":
            if len(parts) >= 3:
                await handle_download(update, context, parts[1], parts[2])
        elif action == "quality":
            if len(parts) >= 2:
                await handle_quality_change(update, context, parts[1])
        elif action == "fav":
            if len(parts) >= 2:
                await show_favorites(update, int(parts[1]))
        elif action == "history":
            if len(parts) >= 2:
                await show_history(update, int(parts[1]))
        elif action == "addfav":
            if len(parts) >= 3:
                await handle_add_favorite(update, context, parts[1], parts[2])
        elif action == "delfav":
            if len(parts) >= 3:
                await handle_del_favorite(update, context, parts[1], parts[2])
        elif action == "delfav_list":
            # 从收藏列表删除，删除后刷新列表
            if len(parts) >= 4:
                await handle_del_favorite_from_list(update, context, parts[1], parts[2], int(parts[3]))
        elif action == "toplists":
            if len(parts) >= 2:
                await handle_toplists(update, context, parts[1])
        elif action == "toplist":
            if len(parts) >= 3:
                await handle_toplist_songs(update, context, parts[1], parts[2])
        elif action == "resend":
            if len(parts) >= 2:
                await handle_resend(update, context, int(parts[1]))
        elif action == "back_toplists":
            await handle_back_toplists(update, context)
    except (IndexError, ValueError) as e:
        logger.warning(f"回调数据解析失败: {data}, 错误: {e}")
        await query.edit_message_text("❌ 操作无效，请重试")


async def handle_download(update: Update, context: ContextTypes.DEFAULT_TYPE, source: str, song_id: str):
    """处理下载"""
    query = update.callback_query
    user_id = query.from_user.id
    quality = user_quality.get(user_id, DEFAULT_QUALITY)

    await query.edit_message_text("⏳ 正在解析歌曲...")

    # 检查历史记录是否有 file_id 可复用
    history = await find_history_by_song(source, song_id)
    if history and history.get("file_id"):
        await query.edit_message_text("📤 发送中 (从缓存)...")
        try:
            # 获取封面用于缩略图（需要先解析获取封面 URL）
            parse_result = await client.parse_songs(source, song_id, quality)
            cover_bytes = b""
            if parse_result and parse_result[0].cover:
                cover_bytes = await client.download_bytes(parse_result[0].cover)
            sent_msg = await context.bot.send_audio(
                chat_id=query.message.chat_id,
                audio=history["file_id"],
                thumbnail=io.BytesIO(cover_bytes) if cover_bytes else None,
                caption=format_song_caption(
                    history["name"],
                    history["artist"],
                    history.get("album", ""),
                    history.get("quality", ""),
                    source=source
                )
            )
            await archive_to_channel(context, sent_msg, source)
            await query.delete_message()
            return
        except Exception as e:
            logger.warning(f"file_id 复用失败: {e}")

    # 使用 V3 API 解析歌曲
    parse_results = await client.parse_songs(source, song_id, quality)
    if not parse_results or not parse_results[0].success:
        error_msg = parse_results[0].error if parse_results else "解析失败"
        await query.edit_message_text(f"❌ 解析失败: {error_msg}")
        return

    result = parse_results[0]
    await query.edit_message_text(f"⏳ 正在下载: {result.name} - {result.artist}...")

    # 检查文件大小
    if not PYROGRAM_ENABLED and result.file_size > MAX_FILE_SIZE:
        await query.edit_message_text(
            f"📎 文件过大 ({format_file_size(result.file_size)})，请直接下载:\n{result.url}\n\n"
            f"💡 提示：配置 TELEGRAM_API_ID 和 TELEGRAM_API_HASH 可解除 50MB 限制"
        )
        return

    # 下载音频内容（带进度显示）
    last_progress_update = [0]  # 用列表以便在闭包中修改

    async def progress_callback(downloaded: int, total: int):
        """下载进度回调"""
        percent = int(downloaded * 100 / total)
        # 每10%更新一次，避免频繁编辑消息
        if percent >= last_progress_update[0] + 10:
            last_progress_update[0] = percent
            progress_bar = "▓" * (percent // 10) + "░" * (10 - percent // 10)
            try:
                await query.edit_message_text(
                    f"⏳ 下载中: {result.name}\n"
                    f"{progress_bar} {percent}%\n"
                    f"📦 {format_file_size(downloaded)} / {format_file_size(total)}"
                )
            except Exception:
                pass  # 忽略编辑失败（如消息内容相同）

    await query.edit_message_text(f"⏳ 开始下载: {result.name}...")
    audio_bytes = await client.download_audio(result.url, progress_callback)
    if not audio_bytes:
        await query.edit_message_text("❌ 下载音频失败")
        return

    # 获取封面
    cover_bytes = await client.download_bytes(result.cover) if result.cover else b""

    await query.edit_message_text("📤 发送中...")

    # 构建换源提示
    source_switched = ""
    if result.was_downgraded:
        source_switched = f"🔄 音质已从 {quality} 降级到 {result.actual_quality}"

    # 发送音频
    caption = format_song_caption(
        result.name,
        result.artist,
        result.album,
        result.actual_quality,
        len(audio_bytes),
        source,
        source_switched
    )

    # 根据实际音质确定文件扩展名
    ext = get_file_extension(result.actual_quality)
    filename = f"{result.name} - {result.artist}{ext}"

    file_id = ""
    try:
        # 根据文件大小选择上传方式
        if len(audio_bytes) > MAX_FILE_SIZE and PYROGRAM_ENABLED:
            # 大文件使用 Pyrogram 上传
            await query.edit_message_text(f"📤 上传大文件中 ({format_file_size(len(audio_bytes))})...")
            file_id = await upload_large_audio(
                chat_id=query.message.chat_id,
                audio_bytes=audio_bytes,
                filename=filename,
                title=result.name,
                performer=result.artist,
                caption=caption,
                cover_bytes=cover_bytes
            )
            sent_msg = None  # Pyrogram 发送的消息，归档需要单独处理
        else:
            # 普通文件使用 python-telegram-bot
            sent_msg = await context.bot.send_audio(
                chat_id=query.message.chat_id,
                audio=io.BytesIO(audio_bytes),
                thumbnail=io.BytesIO(cover_bytes) if cover_bytes else None,
                title=result.name,
                performer=result.artist,
                caption=caption,
                filename=filename
            )
            file_id = sent_msg.audio.file_id if sent_msg and sent_msg.audio else ""
    except Exception as e:
        logger.error(f"发送音频失败: {e}")
        await query.edit_message_text(f"❌ 发送失败: {e}")
        return

    # 保存历史记录
    await add_history(source, song_id, result.name, result.artist, result.album, result.actual_quality, file_id)

    # 归档到频道
    if sent_msg:
        await archive_to_channel(context, sent_msg, source)
    elif file_id and ARCHIVE_CHANNEL_ID:
        # Pyrogram 上传后需要单独归档
        try:
            archive_hashtags = make_hashtags(result.name, result.artist, result.album, source)
            archive_caption = caption + "\n\n" + archive_hashtags if archive_hashtags else caption
            await context.bot.send_audio(
                chat_id=ARCHIVE_CHANNEL_ID,
                audio=file_id,
                caption=archive_caption
            )
            logger.info(f"归档成功: {result.name}")
        except Exception as e:
            logger.warning(f"归档失败: {e}")

    # 更新消息，显示收藏按钮
    is_fav = await is_favorite(source, song_id)
    if is_fav:
        fav_btn = InlineKeyboardButton("💔 取消收藏", callback_data=f"delfav|{source}|{song_id}")
    else:
        fav_btn = InlineKeyboardButton("❤️ 收藏", callback_data=f"addfav|{source}|{song_id}")

    await query.edit_message_text(
        f"✅ 下载完成: {result.name} - {result.artist}\n📊 音质: {result.actual_quality}",
        reply_markup=InlineKeyboardMarkup([[fav_btn]])
    )


async def handle_quality_change(update: Update, context: ContextTypes.DEFAULT_TYPE, quality: str):
    """处理音质切换"""
    query = update.callback_query
    user_id = query.from_user.id

    if quality not in VALID_QUALITIES:
        await query.edit_message_text("❌ 无效的音质选项")
        return

    user_quality[user_id] = quality
    await query.edit_message_text(f"✅ 音质已切换为: *{quality}*", parse_mode=ParseMode.MARKDOWN)


async def handle_add_favorite(update: Update, context: ContextTypes.DEFAULT_TYPE, source: str, song_id: str):
    """添加收藏"""
    query = update.callback_query
    # 使用 V3 API 解析获取歌曲信息
    parse_results = await client.parse_songs(source, song_id, "320k")
    if parse_results and parse_results[0].success:
        result = parse_results[0]
        await add_favorite(source, song_id, result.name, result.artist, result.album)
        await query.edit_message_text(
            f"❤️ 已收藏: {result.name} - {result.artist}",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("💔 取消收藏", callback_data=f"delfav|{source}|{song_id}")
            ]])
        )
    else:
        await query.edit_message_text("❌ 收藏失败")


async def handle_del_favorite(update: Update, context: ContextTypes.DEFAULT_TYPE, source: str, song_id: str):
    """取消收藏"""
    query = update.callback_query
    await remove_favorite(source, song_id)
    await query.edit_message_text(
        "💔 已取消收藏",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("❤️ 重新收藏", callback_data=f"addfav|{source}|{song_id}")
        ]])
    )


async def handle_del_favorite_from_list(update: Update, context: ContextTypes.DEFAULT_TYPE, source: str, song_id: str, page: int):
    """从收藏列表取消收藏，然后刷新列表"""
    await remove_favorite(source, song_id)
    # 刷新收藏列表
    await show_favorites(update, page)


async def handle_toplists(update: Update, context: ContextTypes.DEFAULT_TYPE, source: str):
    """显示排行榜列表"""
    query = update.callback_query
    await query.edit_message_text(f"⏳ 获取 {format_platform(source)} 排行榜...")

    toplists = await client.get_toplists(source)
    if not toplists:
        await query.edit_message_text("❌ 获取排行榜失败")
        return

    buttons = []
    for item in toplists[:15]:
        list_id = item.id
        name = item.name[:25]
        buttons.append([InlineKeyboardButton(name, callback_data=f"toplist|{source}|{list_id}")])

    # 返回按钮
    buttons.append([InlineKeyboardButton("🔙 返回", callback_data="back_toplists")])

    await query.edit_message_text(
        f"📊 *{format_platform(source)} 排行榜*",
        reply_markup=InlineKeyboardMarkup(buttons),
        parse_mode=ParseMode.MARKDOWN
    )


async def handle_toplist_songs(update: Update, context: ContextTypes.DEFAULT_TYPE, source: str, list_id: str):
    """显示排行榜歌曲"""
    query = update.callback_query
    await query.edit_message_text("⏳ 获取榜单歌曲...")

    songs = await client.get_toplist_songs(source, list_id)
    if not songs:
        await query.edit_message_text("❌ 获取榜单歌曲失败")
        return

    # 最多显示 20 首
    songs = songs[:20]
    buttons = []
    for song in songs:
        song_id = song.id
        name = song.name[:20]
        artist = song.artist[:10] if song.artist else ""
        btn_text = f"{name} - {artist}" if artist else name
        buttons.append([InlineKeyboardButton(btn_text, callback_data=f"dl|{source}|{song_id}")])

    # 返回按钮
    buttons.append([InlineKeyboardButton("🔙 返回", callback_data=f"toplists|{source}")])

    await query.edit_message_text(
        "📊 选择要下载的歌曲:",
        reply_markup=InlineKeyboardMarkup(buttons)
    )


async def handle_back_toplists(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """返回排行榜平台选择"""
    query = update.callback_query
    buttons = []
    for source, name in PLATFORMS.items():
        buttons.append([InlineKeyboardButton(name, callback_data=f"toplists|{source}")])

    await query.edit_message_text(
        "📊 选择平台查看排行榜:",
        reply_markup=InlineKeyboardMarkup(buttons)
    )


async def handle_resend(update: Update, context: ContextTypes.DEFAULT_TYPE, history_id: int):
    """重发历史记录中的歌曲"""
    query = update.callback_query

    # 根据 history_id 查找记录
    history = await get_history_by_id(history_id)
    if not history:
        await query.edit_message_text("❌ 未找到历史记录")
        return

    file_id = history.get("file_id")
    if not file_id:
        # 没有 file_id，回退到重新下载
        await handle_download(update, context, history["source"], history["song_id"])
        return

    await query.edit_message_text("📤 发送中 (从缓存)...")

    try:
        # 获取封面用于缩略图
        cover_bytes = b""
        parse_results = await client.parse_songs(history["source"], history["song_id"], "320k")
        if parse_results and parse_results[0].cover:
            cover_bytes = await client.download_bytes(parse_results[0].cover)
        sent_msg = await context.bot.send_audio(
            chat_id=query.message.chat_id,
            audio=file_id,
            thumbnail=io.BytesIO(cover_bytes) if cover_bytes else None,
            caption=format_song_caption(
                history["name"],
                history["artist"],
                history.get("album", ""),
                history.get("quality", ""),
                source=history["source"]
            )
        )
        await archive_to_channel(context, sent_msg, history["source"])
        await query.delete_message()
    except Exception as e:
        logger.warning(f"重发失败: {e}")
        # 回退到重新下载
        await handle_download(update, context, history["source"], history["song_id"])


async def archive_to_channel(context: ContextTypes.DEFAULT_TYPE, sent_msg, source: str):
    """归档到私人频道"""
    if not ARCHIVE_CHANNEL_ID:
        return
    if not sent_msg.audio:
        return

    try:
        title = sent_msg.audio.title or ""
        artist = sent_msg.audio.performer or ""

        # 生成多个标签便于搜索
        hashtags = make_hashtags(
            name=title,
            artist=artist,
            source=source
        )

        caption = sent_msg.caption or ""
        if hashtags:
            caption += f"\n\n{hashtags}"

        await context.bot.send_audio(
            chat_id=ARCHIVE_CHANNEL_ID,
            audio=sent_msg.audio.file_id,
            caption=caption,
            title=title,
            performer=artist,
            thumbnail=sent_msg.audio.thumbnail.file_id if sent_msg.audio.thumbnail else None
        )
    except Exception as e:
        logger.error(f"归档失败: {e}")


# ==================== Inline 模式 ====================

async def inline_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理 Inline 查询"""
    query = update.inline_query
    user_id = query.from_user.id

    if not is_allowed(user_id):
        return

    keyword = query.query.strip()
    if not keyword or len(keyword) < 2:
        return

    results = await client.aggregate_search(keyword)
    if not results:
        # 返回空结果提示
        await query.answer(
            results=[
                InlineQueryResultArticle(
                    id=str(uuid4()),
                    title="未找到结果",
                    description=f"搜索: {keyword}",
                    input_message_content=InputTextMessageContent(f"❌ 未找到: {keyword}")
                )
            ],
            cache_time=60
        )
        return

    # 构建结果列表
    inline_results = []
    for r in results[:10]:
        song_id = r.id
        source = r.platform
        name = r.name
        artist = r.artist

        # 使用 Article 类型，点击后发送下载指令
        inline_results.append(
            InlineQueryResultArticle(
                id=f"{source}|{song_id}",
                title=name,
                description=f"{artist} [{format_platform(source)}]",
                input_message_content=InputTextMessageContent(
                    f"🎵 {name} - {artist}\n📍 {format_platform(source)}\n\n"
                    f"请使用 /search {name} 在机器人中下载"
                )
            )
        )

    await query.answer(results=inline_results, cache_time=300)


# ==================== 错误处理 ====================

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    """全局错误处理"""
    logger.error(f"异常发生: {context.error}", exc_info=context.error)

    # 尝试通知用户
    if isinstance(update, Update):
        try:
            if update.callback_query:
                await update.callback_query.edit_message_text("❌ 发生错误，请稍后重试")
            elif update.message:
                await update.message.reply_text("❌ 发生错误，请稍后重试")
        except Exception:
            pass


# ==================== 应用初始化 ====================

async def post_init(application: Application):
    """应用启动后初始化"""
    # 初始化数据库
    await init_db()

    # 注册命令
    await application.bot.set_my_commands([
        ("start", "开始使用"),
        ("search", "搜索歌曲"),
        ("quality", "切换音质"),
        ("fav", "查看收藏夹"),
        ("history", "下载历史"),
        ("top", "查看排行榜"),
        ("help", "获取帮助"),
    ])

    logger.info("TuneBot 启动完成")


def main():
    """主函数"""
    if not BOT_TOKEN:
        logger.error("请设置 BOT_TOKEN 环境变量")
        return

    # 创建应用
    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()

    # 注册处理器
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("search", cmd_search))
    app.add_handler(CommandHandler("quality", cmd_quality))
    app.add_handler(CommandHandler("fav", cmd_fav))
    app.add_handler(CommandHandler("history", cmd_history))
    app.add_handler(CommandHandler("top", cmd_top))

    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(InlineQueryHandler(inline_handler))

    # 注册全局错误处理器
    app.add_error_handler(error_handler)

    # 启动轮询
    logger.info("TuneBot 正在启动...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
