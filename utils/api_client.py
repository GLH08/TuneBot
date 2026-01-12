"""TuneBot API 客户端 - TuneHub API 封装"""
import asyncio
import aiohttp
import logging
from typing import Optional
from dataclasses import dataclass

from config import API_BASE_URL, MAX_FILE_SIZE

logger = logging.getLogger(__name__)


@dataclass
class SongInfo:
    """歌曲信息"""
    source: str
    song_id: str
    name: str
    artist: str
    album: str = ""
    pic_url: str = ""
    lrc_url: str = ""
    url: str = ""


@dataclass
class AudioResult:
    """音频获取结果"""
    success: bool
    url: str = ""
    size: int = 0
    content: bytes = b""
    source_switched: str = ""  # 换源信息
    error: str = ""
    need_fallback: bool = False  # 是否需要降级
    actual_quality: str = ""  # 实际使用的音质


class TuneHubClient:
    """TuneHub API 客户端"""

    def __init__(self, base_url: str = API_BASE_URL):
        self.base_url = base_url.rstrip("/")
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """获取或创建 aiohttp Session"""
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=60)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session

    async def close(self):
        """关闭 Session"""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    async def _request(
        self,
        params: dict,
        allow_redirects: bool = True
    ) -> aiohttp.ClientResponse:
        """发送请求"""
        session = await self._get_session()
        url = f"{self.base_url}/api/"
        logger.debug(f"API 请求: {url} params={params}")
        resp = await session.get(url, params=params, allow_redirects=allow_redirects)
        logger.debug(f"API 响应: status={resp.status}")
        return resp

    # ==================== 搜索 ====================

    async def aggregate_search(self, keyword: str) -> list[dict]:
        """聚合搜索"""
        try:
            resp = await self._request({
                "type": "aggregateSearch",
                "keyword": keyword
            })
            if resp.status != 200:
                return []
            data = await resp.json()
            if data.get("code") != 200:
                return []
            return data.get("data", {}).get("results", [])
        except Exception as e:
            logger.warning(f"聚合搜索失败: {e}")
            return []

    async def search(self, source: str, keyword: str, limit: int = 20) -> list[dict]:
        """单平台搜索"""
        try:
            resp = await self._request({
                "source": source,
                "type": "search",
                "keyword": keyword,
                "limit": limit
            })
            if resp.status != 200:
                return []
            data = await resp.json()
            if data.get("code") != 200:
                return []
            return data.get("data", {}).get("results", [])
        except Exception as e:
            logger.warning(f"单平台搜索失败: {e}")
            return []

    # ==================== 歌曲信息 ====================

    async def get_song_info(self, source: str, song_id: str) -> Optional[SongInfo]:
        """获取歌曲元数据"""
        try:
            resp = await self._request({
                "source": source,
                "id": song_id,
                "type": "info"
            })
            if resp.status != 200:
                return None
            data = await resp.json()
            if data.get("code") != 200:
                return None
            info = data.get("data", {})
            return SongInfo(
                source=source,
                song_id=song_id,
                name=info.get("name", "未知歌曲"),
                artist=info.get("artist", "未知歌手"),
                album=info.get("album", ""),
                pic_url=info.get("pic", ""),
                lrc_url=info.get("lrc", ""),
                url=info.get("url", "")
            )
        except Exception as e:
            logger.warning(f"获取歌曲信息失败: {e}")
            return None

    # ==================== 资源获取 ====================

    async def resolve_audio_url(
        self,
        source: str,
        song_id: str,
        quality: str = "320k"
    ) -> AudioResult:
        """获取音频真实 URL（处理 302 重定向）"""
        try:
            logger.debug(f"请求音频: source={source}, id={song_id}, quality={quality}")
            resp = await self._request(
                {
                    "source": source,
                    "id": song_id,
                    "type": "url",
                    "br": quality
                },
                allow_redirects=False
            )

            # 检查换源
            source_switched = resp.headers.get("X-Source-Switch", "")
            logger.debug(f"音频响应: status={resp.status}, switched={source_switched}")

            if resp.status == 302:
                location = resp.headers.get("Location", "")
                if location:
                    # 检查文件大小
                    size = await self._get_content_length(location)
                    need_fallback = size > MAX_FILE_SIZE
                    logger.debug(f"音频 URL: {location[:100]}..., size={size}")
                    return AudioResult(
                        success=True,
                        url=location,
                        size=size,
                        source_switched=source_switched,
                        need_fallback=need_fallback
                    )
            elif resp.status == 200:
                # 有些情况可能直接返回 URL
                data = await resp.json()
                url = data.get("data", {}).get("url", "")
                if url:
                    size = await self._get_content_length(url)
                    return AudioResult(
                        success=True,
                        url=url,
                        size=size,
                        source_switched=source_switched,
                        need_fallback=size > MAX_FILE_SIZE
                    )
                else:
                    # API 返回 200 但无 URL，可能该品质不可用
                    error_msg = data.get("msg", "") or data.get("message", "") or "该品质不可用"
                    logger.warning(f"音频解析失败: {error_msg}, data={data}")
                    return AudioResult(success=False, error=error_msg, need_fallback=True)
            else:
                # 非预期状态码
                try:
                    error_data = await resp.text()
                    logger.warning(f"音频请求失败: status={resp.status}, body={error_data[:200]}")
                except Exception:
                    pass
                return AudioResult(success=False, error=f"HTTP {resp.status}", need_fallback=True)

            return AudioResult(success=False, error="无法获取音频链接", need_fallback=True)
        except Exception as e:
            logger.warning(f"获取音频 URL 失败: {e}", exc_info=True)
            return AudioResult(success=False, error=str(e))

    async def get_audio_with_fallback(
        self,
        source: str,
        song_id: str,
        quality: str = "320k",
        skip_size_check: bool = False
    ) -> AudioResult:
        """获取音频，超限或不可用时自动降级

        Args:
            source: 音源平台
            song_id: 歌曲 ID
            quality: 请求的音质
            skip_size_check: 是否跳过文件大小检查（启用大文件上传时使用）
        """
        # 品质降级顺序
        quality_order = ["flac24bit", "flac", "320k", "128k"]

        result = await self.resolve_audio_url(source, song_id, quality)

        # 如果成功但需要降级（文件太大），且未跳过大小检查
        if result.success and result.need_fallback and not skip_size_check:
            try:
                current_idx = quality_order.index(quality)
                if current_idx < len(quality_order) - 1:
                    next_quality = quality_order[current_idx + 1]
                    logger.info(f"文件过大，降级到 {next_quality}")
                    return await self.get_audio_with_fallback(source, song_id, next_quality, skip_size_check)
            except ValueError:
                pass

        # 如果失败且需要降级（品质不可用）
        if not result.success and result.need_fallback:
            try:
                current_idx = quality_order.index(quality)
                if current_idx < len(quality_order) - 1:
                    next_quality = quality_order[current_idx + 1]
                    logger.info(f"品质 {quality} 不可用，降级到 {next_quality}")
                    return await self.get_audio_with_fallback(source, song_id, next_quality, skip_size_check)
            except ValueError:
                pass

        # 设置实际使用的音质
        if result.success:
            result.actual_quality = quality

        return result

    async def download_audio(
        self,
        url: str,
        progress_callback=None,
        max_retries: int = 3,
        timeout: int = 180
    ) -> bytes:
        """下载音频内容，支持进度回调和自动重试

        Args:
            url: 音频 URL
            progress_callback: 可选的进度回调函数 async def callback(downloaded, total)
            max_retries: 最大重试次数
            timeout: 下载超时时间（秒）
        """
        # 某些源可能需要特定的 headers
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        if "kuwo" in url.lower():
            headers["Referer"] = "https://www.kuwo.cn/"
        elif "kugou" in url.lower():
            headers["Referer"] = "https://www.kugou.com/"

        for attempt in range(1, max_retries + 1):
            try:
                logger.debug(f"开始下载 (尝试 {attempt}/{max_retries}): {url[:100]}...")

                # 使用独立的超时配置
                download_timeout = aiohttp.ClientTimeout(total=timeout, connect=30)
                async with aiohttp.ClientSession(timeout=download_timeout) as download_session:
                    async with download_session.get(url, headers=headers) as resp:
                        if resp.status != 200:
                            logger.warning(f"下载失败: HTTP {resp.status}, url={url[:100]}")
                            if attempt < max_retries:
                                await asyncio.sleep(2)
                                continue
                            return b""

                        total = int(resp.headers.get("Content-Length", 0))
                        logger.debug(f"文件大小: {total} bytes")
                        downloaded = 0
                        chunks = []

                        async for chunk in resp.content.iter_chunked(64 * 1024):  # 64KB chunks
                            chunks.append(chunk)
                            downloaded += len(chunk)
                            if progress_callback and total > 0:
                                await progress_callback(downloaded, total)

                        result = b"".join(chunks)
                        logger.debug(f"下载完成: {len(result)} bytes")
                        return result

            except asyncio.TimeoutError:
                logger.warning(f"下载超时 (尝试 {attempt}/{max_retries}): {url[:100]}")
                if attempt < max_retries:
                    await asyncio.sleep(2)
                    continue
                return b""
            except Exception as e:
                logger.warning(f"下载失败 (尝试 {attempt}/{max_retries}): {type(e).__name__}: {e}")
                if attempt < max_retries:
                    await asyncio.sleep(2)
                    continue
                return b""

        return b""

    async def get_cover(self, source: str, song_id: str) -> bytes:
        """获取封面图片"""
        try:
            # 先尝试通过 API 获取封面 URL
            resp = await self._request(
                {"source": source, "id": song_id, "type": "pic"},
                allow_redirects=False
            )

            if resp.status == 302:
                # 如果是重定向，获取真实 URL 并下载
                pic_url = resp.headers.get("Location", "")
                if pic_url:
                    logger.debug(f"封面重定向: {pic_url[:80]}...")
                    session = await self._get_session()
                    async with session.get(pic_url) as pic_resp:
                        if pic_resp.status == 200:
                            content_type = pic_resp.headers.get("Content-Type", "")
                            if "image" in content_type:
                                return await pic_resp.read()
                            else:
                                logger.debug(f"封面非图片类型: {content_type}")
                        else:
                            logger.debug(f"封面下载失败: HTTP {pic_resp.status}")
            elif resp.status == 200:
                content_type = resp.headers.get("Content-Type", "")
                if "image" in content_type:
                    return await resp.read()
                else:
                    # 可能是 JSON 响应包含 URL
                    try:
                        data = await resp.json()
                        pic_url = data.get("data", {}).get("url", "") or data.get("data", {}).get("pic", "")
                        if pic_url:
                            logger.debug(f"封面 URL: {pic_url[:80]}...")
                            session = await self._get_session()
                            async with session.get(pic_url) as pic_resp:
                                if pic_resp.status == 200:
                                    return await pic_resp.read()
                    except Exception:
                        pass
            else:
                logger.debug(f"获取封面失败: HTTP {resp.status}")

            return b""
        except Exception as e:
            logger.warning(f"获取封面失败: {e}")
            return b""

    async def get_lyrics(self, source: str, song_id: str) -> str:
        """获取歌词"""
        try:
            resp = await self._request(
                {"source": source, "id": song_id, "type": "lrc"},
                allow_redirects=True
            )
            if resp.status == 200:
                return await resp.text()
            return ""
        except Exception as e:
            logger.warning(f"获取歌词失败: {e}")
            return ""

    async def _get_content_length(self, url: str) -> int:
        """获取文件大小"""
        try:
            session = await self._get_session()
            async with session.head(url, allow_redirects=True) as resp:
                length = resp.headers.get("Content-Length", "0")
                return int(length)
        except Exception as e:
            logger.warning(f"获取文件大小失败: {e}")
            return 0

    # ==================== 排行榜与歌单 ====================

    async def get_toplists(self, source: str) -> list[dict]:
        """获取排行榜列表"""
        try:
            resp = await self._request({
                "source": source,
                "type": "toplists"
            })
            if resp.status != 200:
                return []
            data = await resp.json()
            if data.get("code") != 200:
                return []
            return data.get("data", {}).get("list", [])
        except Exception as e:
            logger.warning(f"获取排行榜失败: {e}")
            return []

    async def get_toplist_songs(self, source: str, list_id: str) -> dict:
        """获取排行榜歌曲"""
        try:
            resp = await self._request({
                "source": source,
                "id": list_id,
                "type": "toplist"
            })
            if resp.status != 200:
                return {}
            data = await resp.json()
            if data.get("code") != 200:
                return {}
            return data.get("data", {})
        except Exception as e:
            logger.warning(f"获取排行榜歌曲失败: {e}")
            return {}

    async def get_playlist(self, source: str, playlist_id: str) -> dict:
        """获取歌单详情"""
        try:
            resp = await self._request({
                "source": source,
                "id": playlist_id,
                "type": "playlist"
            })
            if resp.status != 200:
                return {}
            data = await resp.json()
            if data.get("code") != 200:
                return {}
            return data.get("data", {})
        except Exception as e:
            logger.warning(f"获取歌单失败: {e}")
            return {}


# 全局客户端实例
client = TuneHubClient()
