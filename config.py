"""TuneBot 配置模块"""
import os
from pathlib import Path

# 项目根目录
BASE_DIR = Path(__file__).parent

# Telegram Bot Token
BOT_TOKEN = os.getenv("BOT_TOKEN", "")

# Telegram API (用于大文件上传，从 https://my.telegram.org 获取)
TELEGRAM_API_ID = os.getenv("TELEGRAM_API_ID", "")
TELEGRAM_API_HASH = os.getenv("TELEGRAM_API_HASH", "")

# 归档频道 ID
_archive_id = os.getenv("ARCHIVE_CHANNEL_ID", "")
ARCHIVE_CHANNEL_ID = None
if _archive_id.strip():
    try:
        ARCHIVE_CHANNEL_ID = int(_archive_id.strip())
    except ValueError:
        pass

# 允许使用的用户 ID (自用)
_allowed_ids = os.getenv("ALLOWED_USER_IDS", "")
ALLOWED_USER_IDS: set[int] = set()
if _allowed_ids.strip():
    ALLOWED_USER_IDS = set(int(uid.strip()) for uid in _allowed_ids.split(",") if uid.strip())

# 默认音质
DEFAULT_QUALITY = os.getenv("DEFAULT_QUALITY", "320k")
VALID_QUALITIES = {"128k", "320k", "flac", "flac24bit"}

# TuneHub API V3
API_BASE_URL = os.getenv("API_BASE_URL", "https://tunehub.sayqz.com/api")
API_KEY = os.getenv("API_KEY", "")

# 数据库路径
DB_PATH = BASE_DIR / "data" / "tunebot.db"

# Telegram 文件大小限制 (50MB)
MAX_FILE_SIZE = 50 * 1024 * 1024

# 平台代码
PLATFORMS = {
    "netease": "网易云",
    "kuwo": "酷我",
    "qq": "QQ音乐",
}
