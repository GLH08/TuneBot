"""TuneBot 数据库模块 - 收藏夹与历史记录"""
import aiosqlite
from pathlib import Path
from datetime import datetime
from typing import Optional

from config import DB_PATH


async def init_db():
    """初始化数据库表"""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS favorites (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT NOT NULL,
                song_id TEXT NOT NULL,
                name TEXT,
                artist TEXT,
                album TEXT,
                added_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(source, song_id)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT NOT NULL,
                song_id TEXT NOT NULL,
                name TEXT,
                artist TEXT,
                album TEXT,
                quality TEXT,
                file_id TEXT,
                downloaded_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_history_downloaded
            ON history(downloaded_at DESC)
        """)
        await db.commit()


# ==================== 收藏夹操作 ====================

async def add_favorite(source: str, song_id: str, name: str, artist: str, album: str = "") -> bool:
    """添加收藏，返回是否成功"""
    async with aiosqlite.connect(DB_PATH) as db:
        try:
            await db.execute(
                "INSERT OR IGNORE INTO favorites (source, song_id, name, artist, album) VALUES (?, ?, ?, ?, ?)",
                (source, song_id, name, artist, album)
            )
            await db.commit()
            return db.total_changes > 0
        except Exception:
            return False


async def remove_favorite(source: str, song_id: str) -> bool:
    """移除收藏"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "DELETE FROM favorites WHERE source = ? AND song_id = ?",
            (source, song_id)
        )
        await db.commit()
        return db.total_changes > 0


async def is_favorite(source: str, song_id: str) -> bool:
    """检查是否已收藏"""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT 1 FROM favorites WHERE source = ? AND song_id = ?",
            (source, song_id)
        )
        return await cursor.fetchone() is not None


async def get_favorites(limit: int = 20, offset: int = 0) -> list[dict]:
    """获取收藏列表"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM favorites ORDER BY added_at DESC LIMIT ? OFFSET ?",
            (limit, offset)
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def get_favorites_count() -> int:
    """获取收藏总数"""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT COUNT(*) FROM favorites")
        row = await cursor.fetchone()
        return row[0] if row else 0


# ==================== 历史记录操作 ====================

async def add_history(
    source: str,
    song_id: str,
    name: str,
    artist: str,
    album: str = "",
    quality: str = "",
    file_id: str = ""
) -> int:
    """添加历史记录，返回记录ID"""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """INSERT INTO history (source, song_id, name, artist, album, quality, file_id)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (source, song_id, name, artist, album, quality, file_id)
        )
        await db.commit()
        return cursor.lastrowid or 0


async def get_history(limit: int = 20, offset: int = 0) -> list[dict]:
    """获取历史记录"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM history ORDER BY downloaded_at DESC LIMIT ? OFFSET ?",
            (limit, offset)
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def get_history_count() -> int:
    """获取历史总数"""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT COUNT(*) FROM history")
        row = await cursor.fetchone()
        return row[0] if row else 0


async def find_history_by_song(source: str, song_id: str) -> Optional[dict]:
    """查找歌曲的历史记录（用于 file_id 复用）"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """SELECT * FROM history
               WHERE source = ? AND song_id = ? AND file_id IS NOT NULL AND file_id != ''
               ORDER BY downloaded_at DESC LIMIT 1""",
            (source, song_id)
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def get_history_by_id(history_id: int) -> Optional[dict]:
    """根据 ID 获取历史记录"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM history WHERE id = ?",
            (history_id,)
        )
        row = await cursor.fetchone()
        return dict(row) if row else None
