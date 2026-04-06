"""资料助手 — 知识星球 (ZSXQ) 适配器。

通过知识星球 REST API (api.zsxq.com) 获取星球内容和附件。
参考开源项目 ZsxqCrawler 的 API 调用逻辑。

认证方式:
    知识星球不支持用户名密码登录 API，需要用户提供浏览器 Cookie。
    用户在前端配置 Cookie 后保存到 .env，后续请求携带此 Cookie。

API 基础:
    - 基础域名: https://api.zsxq.com/v2
    - 认证: 通过 Cookie 中的 zsxq_access_token
    - 内容类型: JSON
"""

from __future__ import annotations

import asyncio
import logging
import re
from pathlib import Path
from typing import Any, Optional

import httpx

from src.material.base_adapter import (
    DownloadResult,
    DownloadStatus,
    OnProgressCallback,
    Platform,
    SearchResult,
)

logger = logging.getLogger(__name__)

# ── 常量 ──────────────────────────────────────────────────────────
ZSXQ_API_BASE = "https://api.zsxq.com/v2"
ZSXQ_FILE_BASE = "https://api.zsxq.com/v2/files"

# 默认请求头（模拟浏览器）
DEFAULT_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Origin": "https://wx.zsxq.com",
    "Referer": "https://wx.zsxq.com/",
}

# 每页请求条数
PAGE_SIZE = 20
# 请求间隔（秒），避免触发限流
REQUEST_DELAY = 1.5


class ZsxqAdapter:
    """知识星球适配器。

    通过 REST API 获取星球内容列表，并下载其中的附件文件。

    Attributes:
        _client: httpx 异步客户端。
        _logged_in: 是否已认证。
        _group_id: 当前星球 ID。
    """

    platform = Platform.ZSXQ

    def __init__(self) -> None:
        """初始化适配器。"""
        self._client: Optional[httpx.AsyncClient] = None
        self._logged_in: bool = False
        self._group_id: str = ""

    async def login(self, credentials: dict[str, str]) -> bool:
        """使用 Cookie 认证。

        知识星球 API 需要有效的 Cookie（包含 zsxq_access_token）。
        用户需要在浏览器中登录知识星球，然后复制 Cookie。

        Args:
            credentials: 包含 'cookie' 和可选 'group_id' 的字典。
                - cookie: 浏览器 Cookie 字符串
                - group_id: 星球 ID（可选，搜索时如不指定则获取用户所有星球）

        Returns:
            认证是否成功。
        """
        cookie = credentials.get("cookie", "") or credentials.get("password", "")
        self._group_id = credentials.get("group_id", "")

        # 尝试使用现有 Cookie 登录
        if cookie:
            if await self._validate_cookie(cookie):
                return True
            logger.warning("ZSXQ: Cookie is invalid or expired. Falling back to browser login.")

        # 如果没有 Cookie 或 Cookie 失效，弹出浏览器让用户登录
        logger.info("ZSXQ: Initiating browser login for Cookie extraction...")
        new_cookie = await self._browser_login()
        if new_cookie:
            # 更新 credentials 字典以便调用方（如路由）可以拿到新 Cookie 并保存
            credentials["cookie"] = new_cookie
            credentials["password"] = new_cookie
            return await self._validate_cookie(new_cookie)

        return False

    async def _validate_cookie(self, cookie: str) -> bool:
        """验证 Cookie 是否有效并初始化客户端。"""
        try:
            headers = {**DEFAULT_HEADERS, "Cookie": cookie}
            self._client = httpx.AsyncClient(
                headers=headers,
                timeout=httpx.Timeout(30.0),
                follow_redirects=True,
            )

            # 验证 Cookie 是否有效：请求用户信息
            resp = await self._client.get(f"{ZSXQ_API_BASE}/users/self")
            data = resp.json()

            if data.get("succeeded"):
                user_name = (
                    data.get("resp_data", {})
                    .get("user", {})
                    .get("name", "Unknown")
                )
                logger.info(f"ZSXQ: Login successful, user: {user_name}")
                self._logged_in = True
                return True

            logger.error(f"ZSXQ: Cookie validation failed: {data}")
            return False

        except Exception as e:
            logger.error(f"ZSXQ: Login failed: {e}", exc_info=True)
            return False

    async def _browser_login(self) -> str:
        """弹出浏览器让用户登录知识星球，并提取 Cookie。

        Returns:
            提取到的 Cookie 字符串。
        """
        try:
            from playwright.async_api import async_playwright

            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=False)
                context = await browser.new_context(
                    viewport={"width": 1280, "height": 800}
                )
                page = await context.new_page()

                logger.info("ZSXQ: Please login in the opened browser (Scan QR code).")
                await page.goto("https://wx.zsxq.com/dweb2/login")

                # 等待登录成功（URL 变化或出现特定元素）
                try:
                    await page.wait_for_url(
                        lambda url: "login" not in url.lower(),
                        timeout=120000, # 给用户 2 分钟时间扫码
                    )
                    # 再等待一下确保状态加载完成
                    await page.wait_for_timeout(3000)
                except Exception:
                    logger.error("ZSXQ: Browser login timeout.")
                    await browser.close()
                    return ""

                # 提取 Cookie
                cookies = await context.cookies()
                cookie_str = "; ".join([f"{c['name']}={c['value']}" for c in cookies])
                
                await browser.close()
                logger.info("ZSXQ: Successfully extracted Cookie from browser.")
                return cookie_str

        except ImportError:
            logger.error("Playwright is not installed. Please install it first.")
            return ""
        except Exception as e:
            logger.error(f"ZSXQ: Browser login failed: {e}")
            return ""

    async def search(
        self,
        keywords: list[str],
        max_results: int = 30,
    ) -> list[SearchResult]:
        """搜索星球内容。

        如果指定了 group_id，则在该星球内搜索；否则搜索用户加入的所有星球。
        优先返回包含附件（文件/PDF）的帖子。

        Args:
            keywords: 搜索关键词列表。
            max_results: 最大返回结果数。

        Returns:
            搜索结果列表。
        """
        if not self._logged_in or not self._client:
            logger.error("ZSXQ: Not logged in. Call login() first.")
            return []

        query = " ".join(keywords)
        results: list[SearchResult] = []

        try:
            if self._group_id:
                # 在指定星球内搜索
                results = await self._search_in_group(
                    self._group_id, query, max_results
                )
            else:
                # 获取用户的星球列表，逐个搜索
                groups = await self._get_user_groups()
                for group in groups[:5]:  # 最多搜5个星球
                    group_results = await self._search_in_group(
                        group["id"], query, max_results - len(results)
                    )
                    results.extend(group_results)
                    if len(results) >= max_results:
                        break
                    await asyncio.sleep(REQUEST_DELAY)

        except Exception as e:
            logger.error(f"ZSXQ: Search failed: {e}", exc_info=True)

        logger.info(f"ZSXQ: Found {len(results)} results for '{query}'")
        return results[:max_results]

    async def _get_user_groups(self) -> list[dict[str, Any]]:
        """获取用户加入的星球列表。

        Returns:
            星球信息列表 [{"id": "...", "name": "..."}]。
        """
        try:
            resp = await self._client.get(f"{ZSXQ_API_BASE}/groups")
            data = resp.json()

            if not data.get("succeeded"):
                return []

            groups = data.get("resp_data", {}).get("groups", [])
            return [
                {
                    "id": str(g.get("group_id", "")),
                    "name": g.get("name", ""),
                }
                for g in groups
            ]

        except Exception as e:
            logger.warning(f"ZSXQ: Failed to get groups: {e}")
            return []

    async def _search_in_group(
        self,
        group_id: str,
        query: str,
        max_results: int,
    ) -> list[SearchResult]:
        """在指定星球内搜索内容。

        Args:
            group_id: 星球 ID。
            query: 搜索关键词。
            max_results: 最大结果数。

        Returns:
            搜索结果列表。
        """
        results: list[SearchResult] = []
        end_time = ""
        page = 0

        while len(results) < max_results and page < 10:
            try:
                params: dict[str, Any] = {"count": PAGE_SIZE}
                if end_time:
                    params["end_time"] = end_time

                # 如果有关键词则搜索，否则获取最新内容
                if query:
                    params["keyword"] = query
                    url = f"{ZSXQ_API_BASE}/groups/{group_id}/search"
                else:
                    url = f"{ZSXQ_API_BASE}/groups/{group_id}/topics"

                resp = await self._client.get(url, params=params)
                data = resp.json()

                if not data.get("succeeded"):
                    break

                topics = data.get("resp_data", {}).get("topics", [])
                if not topics:
                    break

                for topic in topics:
                    result = self._parse_topic(topic, group_id)
                    if result:
                        results.append(result)

                # 获取下一页的时间游标
                last_topic = topics[-1]
                end_time = last_topic.get("create_time", "")

                page += 1
                await asyncio.sleep(REQUEST_DELAY)

            except Exception as e:
                logger.warning(f"ZSXQ: Error fetching page {page}: {e}")
                break

        return results

    def _parse_topic(
        self, topic: dict[str, Any], group_id: str
    ) -> Optional[SearchResult]:
        """解析单个帖子为 SearchResult。

        Args:
            topic: 帖子 API 数据。
            group_id: 星球 ID。

        Returns:
            搜索结果，无附件时返回 None。
        """
        try:
            topic_id = str(topic.get("topic_id", ""))
            talk = topic.get("talk", topic.get("question", {}))

            # 提取文本内容
            text = talk.get("text", "")
            title = text[:80].replace("\n", " ") if text else f"Topic {topic_id}"

            # 提取作者
            owner = talk.get("owner", {})
            author = owner.get("name", "")

            # 提取附件信息
            files = talk.get("files", [])
            images = talk.get("images", [])

            # 确定文件类型
            file_type = "html"  # 默认保存为 HTML/Markdown
            file_url = ""
            extra: dict[str, str] = {"topic_id": topic_id, "group_id": group_id}

            if files:
                # 有附件文件
                first_file = files[0]
                file_url = first_file.get("download_url", "")
                file_name = first_file.get("name", "")
                file_type = Path(file_name).suffix.lstrip(".") or "pdf"
                extra["file_id"] = str(first_file.get("file_id", ""))
                extra["file_name"] = file_name

            publish_date = topic.get("create_time", "")[:10]

            return SearchResult(
                title=title,
                url=file_url or f"https://wx.zsxq.com/topic/{topic_id}",
                authors=author,
                abstract=text[:200] if text else "",
                source=f"知识星球 (Group {group_id})",
                publish_date=publish_date,
                file_type=file_type,
                platform=Platform.ZSXQ,
                extra=extra,
            )

        except Exception as e:
            logger.debug(f"ZSXQ: Failed to parse topic: {e}")
            return None

    async def download(
        self,
        items: list[SearchResult],
        dest_dir: Path,
        on_progress: OnProgressCallback | None = None,
    ) -> list[DownloadResult]:
        """下载星球内容到本地。

        对于有附件的帖子，下载附件文件；
        对于纯文本帖子，保存为 Markdown 文件。

        Args:
            items: 待下载的搜索结果列表。
            dest_dir: 目标目录。
            on_progress: 进度回调。

        Returns:
            下载结果列表。
        """
        if not self._logged_in or not self._client:
            return [
                DownloadResult(
                    item=item, status=DownloadStatus.FAILED, error="Not logged in"
                )
                for item in items
            ]

        dest_dir = Path(dest_dir)
        dest_dir.mkdir(parents=True, exist_ok=True)

        results: list[DownloadResult] = []

        for idx, item in enumerate(items):
            if on_progress:
                percent = (idx / len(items)) * 100
                await on_progress(
                    f"正在下载 ({idx + 1}/{len(items)}): {item.title[:30]}...",
                    percent,
                )

            if item.extra.get("file_id"):
                # 有附件：下载文件
                result = await self._download_file(item, dest_dir)
            else:
                # 纯文本：保存为 Markdown
                result = await self._save_as_markdown(item, dest_dir)

            results.append(result)
            await asyncio.sleep(REQUEST_DELAY)

        if on_progress:
            await on_progress(f"下载完成: {len(results)} 个文件", 100.0)

        return results

    async def _download_file(
        self, item: SearchResult, dest_dir: Path
    ) -> DownloadResult:
        """下载附件文件。

        Args:
            item: 搜索结果（包含文件下载 URL）。
            dest_dir: 目标目录。

        Returns:
            下载结果。
        """
        try:
            file_name = item.extra.get("file_name", "")
            if not file_name:
                safe_title = re.sub(r'[\\/:*?"<>|]', "_", item.title)[:60]
                file_name = f"{safe_title}.{item.file_type}"

            # 安全文件名
            file_name = re.sub(r'[\\/:*?"<>|]', "_", file_name)
            dest_file = dest_dir / file_name

            # 构建下载 URL
            download_url = item.url
            if not download_url or "zsxq.com" not in download_url:
                # 通过 API 获取下载链接
                file_id = item.extra.get("file_id", "")
                group_id = item.extra.get("group_id", "")
                if file_id and group_id:
                    download_url = (
                        f"{ZSXQ_API_BASE}/groups/{group_id}/"
                        f"files/{file_id}/download_url"
                    )
                    resp = await self._client.get(download_url)
                    data = resp.json()
                    download_url = (
                        data.get("resp_data", {}).get("download_url", "")
                    )

            if not download_url:
                return DownloadResult(
                    item=item,
                    status=DownloadStatus.FAILED,
                    error="No download URL available",
                )

            # 下载文件
            resp = await self._client.get(download_url)
            resp.raise_for_status()

            dest_file.write_bytes(resp.content)
            file_size = dest_file.stat().st_size

            logger.info(
                f"ZSXQ: Downloaded '{file_name}' ({file_size} bytes)"
            )
            return DownloadResult(
                item=item,
                status=DownloadStatus.SUCCESS,
                local_path=str(dest_file),
                file_size=file_size,
            )

        except Exception as e:
            logger.warning(f"ZSXQ: Failed to download '{item.title}': {e}")
            return DownloadResult(
                item=item, status=DownloadStatus.FAILED, error=str(e)
            )

    async def _save_as_markdown(
        self, item: SearchResult, dest_dir: Path
    ) -> DownloadResult:
        """将纯文本帖子保存为 Markdown 文件。

        Args:
            item: 搜索结果。
            dest_dir: 目标目录。

        Returns:
            下载结果。
        """
        try:
            safe_title = re.sub(r'[\\/:*?"<>|]', "_", item.title)[:60]
            dest_file = dest_dir / f"{safe_title}.md"

            content = (
                f"# {item.title}\n\n"
                f"> 作者: {item.authors}  \n"
                f"> 日期: {item.publish_date}  \n"
                f"> 来源: {item.source}\n\n"
                f"---\n\n"
                f"{item.abstract}\n"
            )

            dest_file.write_text(content, encoding="utf-8")
            file_size = dest_file.stat().st_size

            return DownloadResult(
                item=item,
                status=DownloadStatus.SUCCESS,
                local_path=str(dest_file),
                file_size=file_size,
            )

        except Exception as e:
            return DownloadResult(
                item=item, status=DownloadStatus.FAILED, error=str(e)
            )

    async def close(self) -> None:
        """关闭 HTTP 客户端。"""
        try:
            if self._client:
                await self._client.aclose()
                logger.info("ZSXQ: HTTP client closed.")
        except Exception as e:
            logger.warning(f"ZSXQ: Error closing client: {e}")
        finally:
            self._client = None
            self._logged_in = False
