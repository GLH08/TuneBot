"""TuneBot 消息格式化工具"""
import re
from config import PLATFORMS


def format_file_size(size_bytes: int) -> str:
    """格式化文件大小"""
    if size_bytes < 1024:
        return f"{size_bytes}B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f}KB"
    else:
        return f"{size_bytes / (1024 * 1024):.1f}MB"


def format_platform(source: str) -> str:
    """格式化平台名称"""
    return PLATFORMS.get(source, source)


def format_song_caption(
    name: str,
    artist: str,
    album: str = "",
    quality: str = "",
    size_bytes: int = 0,
    source: str = "",
    source_switched: str = ""
) -> str:
    """格式化歌曲消息 caption"""
    lines = [f"🎵 {name} - {artist}"]

    if album:
        lines.append(f"💿 {album}")

    meta_parts = []
    if quality:
        meta_parts.append(f"🎧 {quality}")
    if size_bytes:
        meta_parts.append(f"📦 {format_file_size(size_bytes)}")
    if meta_parts:
        lines.append(" | ".join(meta_parts))

    if source_switched:
        lines.append(f"🔄 {source_switched}")
    elif source:
        lines.append(f"📍 {format_platform(source)}")

    return "\n".join(lines)


def format_search_result(result, index: int) -> str:
    """格式化搜索结果显示"""
    # 支持 SearchResult 对象和字典
    name = getattr(result, 'name', None) or result.get("name", "未知") if hasattr(result, 'get') else "未知"
    artist = getattr(result, 'artist', None) or result.get("artist", "未知") if hasattr(result, 'get') else "未知"
    platform = getattr(result, 'platform', None) or result.get("platform", "") if hasattr(result, 'get') else ""
    return f"{index}. {name} - {artist} [{format_platform(platform)}]"


def format_favorite_item(item: dict, index: int) -> str:
    """格式化收藏项"""
    name = item.get("name", "未知")
    artist = item.get("artist", "未知")
    source = format_platform(item.get("source", ""))
    return f"{index}. {name} - {artist} [{source}]"


def format_history_item(item: dict, index: int) -> str:
    """格式化历史记录项"""
    name = item.get("name", "未知")
    artist = item.get("artist", "未知")
    quality = item.get("quality", "")
    return f"{index}. {name} - {artist} ({quality})"


def format_toplist_item(item: dict, index: int) -> str:
    """格式化排行榜项"""
    # 支持 ToplistItem 对象和字典
    name = getattr(item, 'name', None) or item.get("name", "未知") if hasattr(item, 'get') else "未知"
    update = getattr(item, 'update_frequency', None) or item.get("updateFrequency", "") if hasattr(item, 'get') else ""
    if update:
        return f"{index}. {name} ({update})"
    return f"{index}. {name}"


def escape_markdown(text: str) -> str:
    """转义 Markdown 特殊字符"""
    chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    for char in chars:
        text = text.replace(char, f"\\{char}")
    return text


def make_hashtag(text: str) -> str:
    """生成单个 hashtag（移除空格和特殊字符，保留中文）"""
    def is_cjk(char: str) -> bool:
        """检查是否为 CJK 字符"""
        return '\u4e00' <= char <= '\u9fff'
    tag = "".join(c for c in text if c.isalnum() or is_cjk(c))
    return f"#{tag}" if tag else ""


def make_hashtags(
    name: str = "",
    artist: str = "",
    album: str = "",
    source: str = ""
) -> str:
    """生成多个 hashtag 用于归档搜索

    - 歌曲名：#歌曲名
    - 歌手：每个歌手单独标签（按、/,分隔）
    - 专辑：#专辑名
    - 来源：#netease等
    """
    tags = []

    # 歌曲名标签
    if name:
        name_tag = make_hashtag(name)
        if name_tag and len(name_tag) > 1:
            tags.append(name_tag)

    # 歌手标签（支持多歌手分隔）
    if artist:
        # 按常见分隔符拆分：、/ , & feat. ft.
        artists = re.split(r'[、/,&]|feat\.|ft\.', artist, flags=re.IGNORECASE)
        for a in artists:
            a = a.strip()
            if a:
                artist_tag = make_hashtag(a)
                if artist_tag and len(artist_tag) > 1 and artist_tag not in tags:
                    tags.append(artist_tag)

    # 专辑标签
    if album:
        album_tag = make_hashtag(album)
        if album_tag and len(album_tag) > 1 and album_tag not in tags:
            tags.append(album_tag)

    # 来源标签
    if source:
        tags.append(f"#{source}")

    return " ".join(tags)
