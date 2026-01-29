"""TuneBot API 客户端 - TuneHub V3 API 封装"""
import asyncio
import aiohttp
import logging
import execjs
import re
from typing import Optional
from dataclasses import dataclass

from config import API_BASE_URL, API_KEY, MAX_FILE_SIZE, PLATFORMS

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    """搜索结果"""
    id: str
    name: str
    artist: str
    album: str = ""
    platform: str = ""


@dataclass
class ParseResult:
    """解析结果"""
    success: bool
    song_id: str
    name: str = ""
    artist: str = ""
    album: str = ""
    url: str = ""
    cover: str = ""
    lyrics: str = ""
    duration: int = 0
    file_size: int = 0
    actual_quality: str = ""
    was_downgraded: bool = False
    error: str = ""
    expire: int = 1800


@dataclass
class ToplistItem:
    """排行榜项"""
    id: str
    name: str
    pic: str = ""
    update_frequency: str = ""


class TuneHubClient:
    """TuneHub V3 API 客户端"""

    def __init__(self, base_url: str = API_BASE_URL, api_key: str = API_KEY):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self._session: Optional[aiohttp.ClientSession] = None
        # 缓存方法配置
        self._method_cache: dict[str, dict] = {}

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

    def _get_headers(self) -> dict:
        """获取请求头（包含认证）"""
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["X-API-Key"] = self.api_key
        return headers

    async def _request(self, method: str, url: str, **kwargs) -> dict:
        """发送请求"""
        session = await self._get_session()
        logger.debug(f"API 请求: {method} {url}")
        resp = await session.request(method, url, **kwargs)
        logger.debug(f"API 响应: status={resp.status}")
        data = await resp.json()
        return data

    # ==================== 解析接口（消耗积分）===================

    async def parse_songs(
        self,
        platform: str,
        song_ids: str,
        quality: str = "320k"
    ) -> list[ParseResult]:
        """解析歌曲（POST /v1/parse）

        Args:
            platform: 平台 (netease/kuwo/qq)
            song_ids: 歌曲 ID，支持批量逗号分隔
            quality: 音质

        Returns:
            ParseResult 列表
        """
        try:
            url = f"{self.base_url}/v1/parse"
            payload = {
                "platform": platform,
                "ids": song_ids,
                "quality": quality
            }

            data = await self._request("POST", url, json=payload, headers=self._get_headers())

            if data.get("code") != 0:
                msg = data.get("message", "未知错误")
                logger.warning(f"解析请求失败: {msg}")
                return []

            results = []
            for item in data.get("data", {}).get("data", []):
                if item.get("success"):
                    info = item.get("info", {})
                    results.append(ParseResult(
                        success=True,
                        song_id=item.get("id", ""),
                        name=info.get("name", ""),
                        artist=info.get("artist", ""),
                        album=info.get("album", ""),
                        url=item.get("url", ""),
                        cover=item.get("cover", ""),
                        lyrics=item.get("lyrics", ""),
                        duration=info.get("duration", 0),
                        file_size=item.get("fileSize", 0),
                        actual_quality=item.get("actualQuality", ""),
                        was_downgraded=item.get("wasDowngraded", False),
                        expire=item.get("expire", 1800)
                    ))
                else:
                    results.append(ParseResult(
                        success=False,
                        song_id=item.get("id", ""),
                        error=item.get("error", "解析失败")
                    ))
            return results

        except aiohttp.ClientError as e:
            logger.warning(f"网络请求错误: {e}")
            return []
        except (KeyError, TypeError, ValueError) as e:
            logger.warning(f"数据解析错误: {e}")
            return []
        except Exception as e:
            logger.warning(f"解析失败: {e}", exc_info=True)
            return []

    # ==================== 方法下发模式（不消耗积分）===================

    async def get_method_config(self, platform: str, function: str) -> Optional[dict]:
        """获取方法配置（GET /v1/methods/{platform}/{function}）"""
        cache_key = f"{platform}_{function}"
        if cache_key in self._method_cache:
            return self._method_cache[cache_key]

        try:
            url = f"{self.base_url}/v1/methods/{platform}/{function}"
            logger.debug(f"获取方法配置: {url}")
            data = await self._request("GET", url, headers=self._get_headers())

            if data.get("code") == 0:
                config = data.get("data")
                self._method_cache[cache_key] = config
                return config
            logger.warning(f"获取方法配置失败: code={data.get('code')}, message={data.get('message')}")
            return None

        except Exception as e:
            logger.warning(f"获取方法配置失败: {e}")
            return None

    def _replace_template_vars(self, template: str, variables: dict) -> str:
        """替换模板变量，支持 JS 表达式

        支持的格式：
        - {{key}} - 简单变量替换
        - {{key || default}} - 默认值语法
        - {{(page || 1) - 1}} - 算术表达式
        """
        result = template

        # 第一步：简单变量替换 {{key}} 和 {key}
        for key, value in variables.items():
            result = result.replace(f"{{{{{key}}}}}", str(value))
            result = result.replace(f"{{{key}}}", str(value))

        # 第二步：处理 JS 表达式 {{expr}}
        # 匹配 {{expr}} 模式，使用 execjs 安全地计算表达式
        pattern = r'\{\{([^}]+)\}\}'

        def replace_js_expr(match):
            js_expr = match.group(1).strip()
            if not js_expr:
                return match.group(0)

            try:
                # 安全检查：排除危险操作
                dangerous = ['eval(', 'setTimeout(', 'setInterval(', 'require(', 'import ',
                           'process.', 'child_process', 'fs.', 'http.', 'https.']
                for d in dangerous:
                    if d.lower() in js_expr.lower():
                        logger.warning(f"JS 表达式包含危险内容: {d}")
                        return match.group(0)

                # 构建 JavaScript 代码来计算表达式
                # 创建变量环境
                js_vars = []
                for key, value in variables.items():
                    # JavaScript 变量名只能是字母、数字、下划线、$
                    safe_key = re.sub(r'[^a-zA-Z_$]', '_', key)
                    if isinstance(value, str):
                        js_vars.append(f"var {safe_key} = '{value}';")
                    elif isinstance(value, bool):
                        js_vars.append(f"var {safe_key} = {str(value).lower()};")
                    elif value is None:
                        js_vars.append(f"var {safe_key} = undefined;")
                    else:
                        js_vars.append(f"var {safe_key} = {value};")

                js_code = f"""
                (function() {{
                    {' '.join(js_vars)}
                    return {js_expr};
                }})()
                """

                # 使用 execjs.eval 直接执行
                result_value = execjs.eval(js_code)
                return str(int(result_value) if isinstance(result_value, float) and result_value == int(result_value) else result_value)

            except Exception as e:
                logger.warning(f"计算 JS 表达式失败: {js_expr}, error: {e}")
                return match.group(0)

        result = re.sub(pattern, replace_js_expr, result)
        return result

    def _execute_transform(self, transform_func: str, response_data: dict) -> list:
        """执行 JS transform 函数"""
        # 安全检查：验证 transform 函数不包含危险操作
        dangerous_patterns = [
            'eval(', 'setTimeout(', 'setInterval(',
            'require(', 'import ', 'process.', 'child_process',
            'fs.', 'http.', 'https.'
        ]

        for pattern in dangerous_patterns:
            if pattern.lower() in transform_func.lower():
                logger.warning(f"Transform 函数包含危险内容: {pattern}")
                return []

        try:
            # API 返回的是匿名函数 function(response){...}
            # 需要包装成命名函数才能被 execjs 调用
            if transform_func.strip().startswith('function('):
                # 将 function(response) 改为 function transform(response)
                wrapped_func = 'function transform' + transform_func.strip()[8:]
            elif transform_func.strip().startswith('function '):
                # 已经是命名函数
                wrapped_func = transform_func
            else:
                # 其他情况，尝试包装
                wrapped_func = f"function transform(response) {{ return ({transform_func})(response); }}"

            ctx = execjs.compile(wrapped_func)
            result = ctx.call("transform", response_data)
            logger.debug(f"Transform 执行成功，返回 {len(result) if isinstance(result, list) else 'non-list'} 条")
            return result if isinstance(result, list) else []
        except Exception as e:
            logger.warning(f"执行 transform 失败: {e}")
            return []

    async def execute_method(
        self,
        config: dict,
        variables: dict
    ) -> list:
        """执行方法下发请求

        Args:
            config: get_method_config 返回的配置
            variables: 模板变量值

        Returns:
            转换后的结果列表
        """
        try:
            # 构建 URL（替换模板变量）
            url = config.get("url", "")
            url = self._replace_template_vars(url, variables)
            logger.debug(f"构建 URL: {url}")

            # 构建查询参数
            params = {}
            for key, value in config.get("params", {}).items():
                if isinstance(value, str):
                    processed_value = self._replace_template_vars(value, variables)
                    params[key] = processed_value
                    logger.debug(f"参数 {key}: {value} -> {processed_value}")
                else:
                    params[key] = value

            logger.debug(f"参数处理完成，共 {len(params)} 个参数")

            headers = config.get("headers", {})
            method = config.get("method", "GET")

            logger.debug(f"最终请求: {method} {url} params={params}")

            session = await self._get_session()

            if method == "GET":
                resp = await session.get(url, params=params, headers=headers)
            else:
                # POST 请求
                body = config.get("body", {})
                # 替换 body 中的模板变量
                if isinstance(body, dict):
                    body = {k: self._replace_template_vars(str(v), variables) if isinstance(v, str) else v for k, v in body.items()}
                resp = await session.request(method, url, json=body, params=params, headers=headers)

            # 强制解析 JSON（某些 API 返回 text/plain）
            response_data = await resp.json(content_type=None)
            logger.debug(f"API 原始响应类型: {type(response_data).__name__}, 键: {list(response_data.keys()) if isinstance(response_data, dict) else 'N/A'}")

            # 检查 API 错误响应
            if isinstance(response_data, dict) and response_data.get("code") != 0:
                logger.warning(f"API 返回错误: code={response_data.get('code')}, msg={response_data.get('msg', '未知错误')}")
                return []

            # 执行 transform 转换
            transform_func = config.get("transform", "")
            if transform_func:
                result = self._execute_transform(transform_func, response_data)
                if not result:
                    logger.warning(f"Transform 返回空结果，原始数据前200字符: {str(response_data)[:200]}")
                return result

            return response_data if isinstance(response_data, list) else []

        except Exception as e:
            logger.warning(f"执行方法失败: {e}")
            return []

    # ==================== 搜索功能 ====================

    async def search(
        self,
        platform: str,
        keyword: str,
        page: int = 1,
        limit: int = 20
    ) -> list[SearchResult]:
        """搜索歌曲"""
        logger.debug(f"搜索: platform={platform}, keyword={keyword}")
        config = await self.get_method_config(platform, "search")
        if not config:
            logger.warning(f"未获取到 {platform} 搜索配置")
            return []

        results = await self.execute_method(config, {
            "keyword": keyword,
            "page": page,
            "limit": limit
        })
        logger.debug(f"搜索结果: {platform} 返回 {len(results)} 条")

        # 字段映射
        songs = []
        for r in results:
            songs.append(SearchResult(
                id=str(r.get("id", "")),
                name=r.get("name", ""),
                artist=r.get("artist", ""),
                album=r.get("album", ""),
                platform=platform
            ))
        return songs

    async def aggregate_search(self, keyword: str) -> list[SearchResult]:
        """聚合搜索（并发搜索所有平台）"""
        tasks = []
        platforms = list(PLATFORMS.keys())
        logger.info(f"聚合搜索: keyword={keyword}, platforms={platforms}")
        for platform in platforms:
            tasks.append(self.search(platform, keyword))

        platform_results = await asyncio.gather(*tasks, return_exceptions=True)

        all_results = []
        for platform, results in zip(platforms, platform_results):
            if isinstance(results, Exception):
                logger.warning(f"搜索 {platform} 失败: {results}")
                continue
            for r in results:
                r.platform = platform
                all_results.append(r)

        # 去重（按 platform + id，保留第一个匹配）
        seen = {}
        unique_results = []
        for r in all_results:
            key = (r.platform, r.id)
            if key not in seen:
                seen[key] = True
                unique_results.append(r)

        return unique_results

    # ==================== 排行榜功能 ====================

    async def get_toplists(self, platform: str) -> list[ToplistItem]:
        """获取排行榜列表"""
        config = await self.get_method_config(platform, "toplists")
        if not config:
            return []

        results = await self.execute_method(config, {})

        # 字段名映射：API 返回 camelCase，dataclass 使用 snake_case
        toplists = []
        for r in results:
            toplists.append(ToplistItem(
                id=r.get("id", ""),
                name=r.get("name", ""),
                pic=r.get("pic", ""),
                update_frequency=r.get("updateFrequency", r.get("update_frequency", ""))
            ))
        return toplists

    async def get_toplist_songs(self, platform: str, list_id: str) -> list[SearchResult]:
        """获取榜单歌曲"""
        config = await self.get_method_config(platform, "toplist")
        if not config:
            return []

        # 替换 URL 中的 id 占位符
        url = config.get("url", "")
        url = url.replace("{{id}}", list_id).replace("{id}", list_id)
        config["url"] = url

        results = await self.execute_method(config, {"id": list_id})

        # 字段映射
        songs = []
        for r in results:
            songs.append(SearchResult(
                id=str(r.get("id", "")),
                name=r.get("name", ""),
                artist=r.get("artist", ""),
                album=r.get("album", ""),
                platform=platform
            ))
        return songs

    # ==================== 歌单功能 ====================

    async def get_playlist(self, platform: str, playlist_id: str) -> dict:
        """获取歌单详情"""
        config = await self.get_method_config(platform, "playlist")
        if not config:
            return {}

        # 替换 URL 中的 id 占位符
        url = config.get("url", "")
        url = url.replace("{{id}}", playlist_id).replace("{id}", playlist_id)
        config["url"] = url

        result = await self.execute_method(config, {"id": playlist_id})

        return result if result else {}

    # ==================== 下载功能 ====================

    async def download_bytes(self, url: str) -> bytes:
        """下载通用内容（封面等）"""
        try:
            session = await self._get_session()
            async with session.get(url) as resp:
                if resp.status == 200:
                    return await resp.read()
                return b""
        except Exception as e:
            logger.warning(f"下载失败: {e}")
            return b""

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

                download_timeout = aiohttp.ClientTimeout(total=timeout, connect=30)
                async with aiohttp.ClientSession(timeout=download_timeout) as download_session:
                    async with download_session.get(url, headers=headers) as resp:
                        if resp.status != 200:
                            logger.warning(f"下载失败: HTTP {resp.status}")
                            if attempt < max_retries:
                                await asyncio.sleep(2)
                                continue
                            return b""

                        total = int(resp.headers.get("Content-Length", 0))
                        logger.debug(f"文件大小: {total} bytes")
                        downloaded = 0
                        chunks = []

                        async for chunk in resp.content.iter_chunked(64 * 1024):
                            chunks.append(chunk)
                            downloaded += len(chunk)
                            if progress_callback and total > 0:
                                await progress_callback(downloaded, total)

                        result = b"".join(chunks)
                        logger.debug(f"下载完成: {len(result)} bytes")
                        return result

            except asyncio.TimeoutError:
                logger.warning(f"下载超时 (尝试 {attempt}/{max_retries})")
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

    async def get_file_size(self, url: str) -> int:
        """获取文件大小"""
        try:
            session = await self._get_session()
            async with session.head(url, allow_redirects=True) as resp:
                length = resp.headers.get("Content-Length", "0")
                return int(length)
        except Exception as e:
            logger.warning(f"获取文件大小失败: {e}")
            return 0


# 全局客户端实例
client = TuneHubClient()
