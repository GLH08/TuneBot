"""TuneBot utils 模块"""
from utils.api_client import (
    client,
    TuneHubClient,
    SearchResult,
    ParseResult,
    ToplistItem,
)
from utils.formatters import (
    format_file_size,
    format_platform,
    format_song_caption,
    format_search_result,
    format_favorite_item,
    format_history_item,
    format_toplist_item,
    escape_markdown,
    make_hashtag,
    make_hashtags,
)
from utils.db import (
    init_db,
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

__all__ = [
    # API 客户端
    "client",
    "TuneHubClient",
    "SearchResult",
    "ParseResult",
    "ToplistItem",
    # 格式化
    "format_file_size",
    "format_platform",
    "format_song_caption",
    "format_search_result",
    "format_favorite_item",
    "format_history_item",
    "format_toplist_item",
    "escape_markdown",
    "make_hashtag",
    "make_hashtags",
    # 数据库
    "init_db",
    "add_favorite",
    "remove_favorite",
    "is_favorite",
    "get_favorites",
    "get_favorites_count",
    "add_history",
    "get_history",
    "get_history_count",
    "find_history_by_song",
    "get_history_by_id",
]
