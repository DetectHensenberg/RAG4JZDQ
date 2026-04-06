"""资料助手 — 微信公众号文章适配器。

通过搜狗微信搜索获取公众号文章，提取正文内容保存为 Markdown 文件。
参考开源项目 wechat_articles_spider 的搜索逻辑。

搜索入口:
    https://weixin.sogou.com/weixin?type=2&query=<keywords>
    type=2 表示搜索文章（type=1 为搜索公众号）

流程:
    1. 通过搜狗微信搜索关键词 → 获取文章列表
    2. 访问每篇文章原文链接 → 提取正文内容
    3. 将文章内容保存为 Markdown 文件
"""

from __future__ import annotations

import asyncio
import logging
import re
from html import unescape
from pathlib import Path
from typing import Optional
from urllib.parse import quote, urljoin

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
SOGOU_SEARCH_URL = "https://weixin.sogou.com/weixin"
SOGOU_ARTICLE_URL = "https://weixin.sogou.com/weixin?type=2"

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;"
        "q=0.9,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}

# 每页结果数（搜狗固定为10）
PAGE_SIZE = 10
# 请求间隔（秒），搜狗反爬较严格
REQUEST_DELAY = 3.0


class WechatAdapter:
    """微信公众号文章适配器。

    通过搜狗微信搜索获取公众号文章，提取正文保存为 Markdown。

    Attributes:
        _client: httpx 异步客户端。
        _logged_in: 是否已初始化。
    """

    platform = Platform.WECHAT

    def __init__(self) -> None:
        """初始化适配器。"""
        self._client: Optional[httpx.AsyncClient] = None
        self._logged_in: bool = False

    async def login(self, credentials: dict[str, str]) -> bool:
        """初始化 HTTP 客户端。

        微信公众号搜索不需要登录。此方法仅创建 HTTP 客户端。
        如果用户提供了搜狗 Cookie 可以提高搜索成功率。

        Args:
            credentials: 可选的 Cookie 配置。
                - cookie: 搜狗搜索 Cookie（可选，有助于绕过反爬）

        Returns:
            始终返回 True。
        """
        cookie = credentials.get("cookie", "") or credentials.get("password", "")
        headers = {**DEFAULT_HEADERS}
        if cookie:
            headers["Cookie"] = cookie

        try:
            self._client = httpx.AsyncClient(
                headers=headers,
                timeout=httpx.Timeout(30.0),
                follow_redirects=True,
            )
            self._logged_in = True
            logger.info("WeChat: HTTP client initialized.")
            return True

        except Exception as e:
            logger.error(f"WeChat: Failed to initialize client: {e}")
            return False

    async def search(
        self,
        keywords: list[str],
        max_results: int = 30,
    ) -> list[SearchResult]:
        """通过搜狗微信搜索公众号文章。

        Args:
            keywords: 搜索关键词列表。
            max_results: 最大返回结果数。

        Returns:
            搜索结果列表。
        """
        if not self._logged_in or not self._client:
            logger.error("WeChat: Not initialized. Call login() first.")
            return []

        query = " ".join(keywords)
        results: list[SearchResult] = []
        pages_needed = min((max_results + PAGE_SIZE - 1) // PAGE_SIZE, 10)

        for page in range(1, pages_needed + 1):
            try:
                page_results = await self._search_page(query, page)
                results.extend(page_results)

                if len(results) >= max_results:
                    break

                if not page_results:
                    break

                await asyncio.sleep(REQUEST_DELAY)

            except Exception as e:
                logger.warning(f"WeChat: Search page {page} failed: {e}")
                break

        logger.info(f"WeChat: Found {len(results)} results for '{query}'")
        return results[:max_results]

    async def _search_page(
        self, query: str, page: int
    ) -> list[SearchResult]:
        """搜索单页结果。

        Args:
            query: 搜索关键词。
            page: 页码。

        Returns:
            当页搜索结果。
        """
        params = {
            "type": "2",  # 搜索文章
            "query": query,
            "page": str(page),
        }

        try:
            resp = await self._client.get(SOGOU_SEARCH_URL, params=params)
            resp.raise_for_status()
            html = resp.text

            return self._parse_search_page(html)

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 302:
                logger.warning(
                    "WeChat: Redirected (likely anti-bot). "
                    "Try providing a Sogou cookie."
                )
            raise

    def _parse_search_page(self, html: str) -> list[SearchResult]:
        """从搜狗搜索结果页面解析文章信息。

        使用正则表达式解析，避免依赖额外的 HTML 解析库。

        Args:
            html: 搜索结果 HTML 内容。

        Returns:
            搜索结果列表。
        """
        results: list[SearchResult] = []

        # 使用 BeautifulSoup 解析（如已安装）或正则解析
        try:
            from bs4 import BeautifulSoup

            soup = BeautifulSoup(html, "html.parser")
            items = soup.select("div.txt-box, li[id^='sogou_vr']")

            for item in items:
                try:
                    # 提取标题和链接
                    title_el = item.select_one("h3 a, a.tit")
                    if not title_el:
                        continue

                    title = title_el.get_text(strip=True)
                    url = title_el.get("href", "")
                    if url and not url.startswith("http"):
                        url = urljoin("https://weixin.sogou.com", url)

                    # 提取公众号名称
                    account_el = item.select_one(
                        "a.account, span.s-p a, div.s-p a"
                    )
                    source = (
                        account_el.get_text(strip=True)
                        if account_el
                        else ""
                    )

                    # 提取摘要
                    abstract_el = item.select_one("p.txt-info, p.txt-desc")
                    abstract = (
                        abstract_el.get_text(strip=True) if abstract_el else ""
                    )

                    # 提取日期
                    date_text = ""
                    date_el = item.select_one("span.s2, span.date")
                    if date_el:
                        # 搜狗用 timeConvert 函数显示日期
                        date_script = date_el.get("t", "")
                        if date_script:
                            date_text = date_script[:10]

                    if title:
                        results.append(
                            SearchResult(
                                title=title,
                                url=url,
                                authors=source,
                                abstract=unescape(abstract),
                                source=f"微信公众号: {source}",
                                publish_date=date_text,
                                file_type="md",
                                platform=Platform.WECHAT,
                            )
                        )

                except Exception as e:
                    logger.debug(f"Failed to parse search item: {e}")
                    continue

        except ImportError:
            # 回退到正则解析
            results = self._regex_parse(html)

        return results

    def _regex_parse(self, html: str) -> list[SearchResult]:
        """用正则表达式解析搜索结果（BeautifulSoup 不可用时的回退方案）。

        Args:
            html: 搜索结果 HTML。

        Returns:
            搜索结果列表。
        """
        results: list[SearchResult] = []

        # 匹配标题和链接
        pattern = r'<a[^>]*href="([^"]*)"[^>]*>(.+?)</a>'
        for match in re.finditer(pattern, html, flags=re.DOTALL):
            url = match.group(1)
            title = re.sub(r"<[^>]+>", "", match.group(2)).strip()

            if title and len(title) > 5 and "sogou" in url:
                results.append(
                    SearchResult(
                        title=unescape(title),
                        url=urljoin("https://weixin.sogou.com", url),
                        file_type="md",
                        platform=Platform.WECHAT,
                        source="微信公众号",
                    )
                )

        return results

    async def download(
        self,
        items: list[SearchResult],
        dest_dir: Path,
        on_progress: OnProgressCallback | None = None,
    ) -> list[DownloadResult]:
        """下载公众号文章，保存为 Markdown 文件。

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
                    item=item, status=DownloadStatus.FAILED, error="Not initialized"
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

            result = await self._download_article(item, dest_dir)
            results.append(result)

            await asyncio.sleep(REQUEST_DELAY)

        if on_progress:
            await on_progress(f"下载完成: {len(results)} 个文件", 100.0)

        return results

    async def _download_article(
        self, item: SearchResult, dest_dir: Path
    ) -> DownloadResult:
        """下载单篇文章并保存为 Markdown。

        Args:
            item: 搜索结果。
            dest_dir: 目标目录。

        Returns:
            下载结果。
        """
        try:
            # 先通过搜狗链接获取微信文章原文链接
            resp = await self._client.get(item.url)
            resp.raise_for_status()
            html = resp.text

            # 提取正文
            content = self._extract_article_content(html, item.title)

            # 保存为 Markdown
            safe_title = re.sub(r'[\\/:*?"<>|]', "_", item.title)[:80]
            dest_file = dest_dir / f"{safe_title}.md"

            markdown = (
                f"# {item.title}\n\n"
                f"> 来源: {item.source}  \n"
                f"> 作者: {item.authors}  \n"
                f"> 日期: {item.publish_date}\n\n"
                f"---\n\n"
                f"{content}\n"
            )

            dest_file.write_text(markdown, encoding="utf-8")
            file_size = dest_file.stat().st_size

            logger.info(
                f"WeChat: Saved article '{item.title}' ({file_size} bytes)"
            )
            return DownloadResult(
                item=item,
                status=DownloadStatus.SUCCESS,
                local_path=str(dest_file),
                file_size=file_size,
            )

        except Exception as e:
            logger.warning(f"WeChat: Failed to download '{item.title}': {e}")
            return DownloadResult(
                item=item, status=DownloadStatus.FAILED, error=str(e)
            )

    def _extract_article_content(self, html: str, fallback_title: str) -> str:
        """从公众号文章页面提取正文内容。

        优先使用 BeautifulSoup，回退到正则提取。

        Args:
            html: 文章 HTML 内容。
            fallback_title: 回退标题。

        Returns:
            提取的文章正文文本。
        """
        try:
            from bs4 import BeautifulSoup

            soup = BeautifulSoup(html, "html.parser")

            # 微信文章正文容器
            content_el = soup.select_one(
                "#js_content, .rich_media_content, "
                "#img-content, .weui-article__body"
            )

            if content_el:
                # 移除脚本和样式
                for tag in content_el.find_all(["script", "style", "iframe"]):
                    tag.decompose()

                # 提取文本，保留段落结构
                paragraphs: list[str] = []
                for p in content_el.find_all(["p", "section", "h1", "h2", "h3"]):
                    text = p.get_text(strip=True)
                    if text:
                        if p.name and p.name.startswith("h"):
                            level = int(p.name[1])
                            paragraphs.append(f"{'#' * (level + 1)} {text}")
                        else:
                            paragraphs.append(text)

                if paragraphs:
                    return "\n\n".join(paragraphs)

            # 如果正文容器不存在，尝试提取全部可见文本
            text = soup.get_text(separator="\n", strip=True)
            # 只取有意义的内容（超过100字）
            if len(text) > 100:
                return text[:5000]

        except ImportError:
            pass

        # 正则回退：提取 <p> 标签内容
        paragraphs = re.findall(r"<p[^>]*>(.*?)</p>", html, re.DOTALL)
        cleaned = [
            re.sub(r"<[^>]+>", "", p).strip()
            for p in paragraphs
            if len(re.sub(r"<[^>]+>", "", p).strip()) > 10
        ]

        if cleaned:
            return "\n\n".join(cleaned[:50])

        return f"[无法提取正文内容，请访问原文链接查看]"

    async def close(self) -> None:
        """关闭 HTTP 客户端。"""
        try:
            if self._client:
                await self._client.aclose()
                logger.info("WeChat: HTTP client closed.")
        except Exception as e:
            logger.warning(f"WeChat: Error closing client: {e}")
        finally:
            self._client = None
            self._logged_in = False
