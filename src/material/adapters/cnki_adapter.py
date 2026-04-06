"""资料助手 — 知网 (CNKI) 适配器。

通过 wytsg.com (无忧图书馆) 认证后跳转知网进行搜索和下载。
使用 Playwright 进行浏览器自动化操作。

登录流程:
    1. 打开 http://www.wytsg.com → 填写用户名/密码
    2. 弹出浏览器窗口让用户手动输入图形验证码
    3. 登录成功后点击知网跳转按钮
    4. 在知网上按关键词搜索并下载 PDF

关键选择器 (wytsg.com 登录页):
    - 用户名: input#userid
    - 密码:   input#password
    - 验证码: input.mark1.mark
    - 验证码图片: a.mark2 img
    - 登录按钮: input.btn-success
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from pathlib import Path
from typing import Optional

from src.material.base_adapter import (
    DownloadResult,
    DownloadStatus,
    OnProgressCallback,
    Platform,
    SearchResult,
)

logger = logging.getLogger(__name__)

# ── 常量 ──────────────────────────────────────────────────────────
WYTSG_LOGIN_URL = "http://www.wytsg.com/e/member/login/"
WYTSG_HOME_URL = "http://www.wytsg.com"
CNKI_SEARCH_URL = "https://kns.cnki.net/kns8s/search"

# 等待用户填验证码的最长时间（秒）
CAPTCHA_TIMEOUT = 120
# 下载单个文件的超时（秒）
DOWNLOAD_TIMEOUT = 60


class CnkiAdapter:
    """知网适配器。

    通过 Playwright 控制浏览器，先登录 wytsg.com 再跳转知网进行搜索下载。

    Attributes:
        browser: Playwright 浏览器实例。
        page: 当前页面。
        _logged_in: 是否已登录。
    """

    platform = Platform.CNKI

    def __init__(self) -> None:
        """初始化适配器（浏览器在 login 时创建）。"""
        self._playwright: Optional[object] = None
        self._browser: Optional[object] = None
        self._context: Optional[object] = None
        self.page: Optional[object] = None
        self._logged_in: bool = False

    async def login(self, credentials: dict[str, str]) -> bool:
        """登录 wytsg.com 并跳转到知网。

        流程:
            1. 启动 Playwright 浏览器 (非 headless，用户需看到验证码)
            2. 打开 wytsg.com 登录页
            3. 自动填写用户名和密码
            4. 等待用户手动输入验证码并点击登录
            5. 检测登录成功后，查找并点击知网跳转按钮

        Args:
            credentials: 包含 'username' 和 'password' 的字典。

        Returns:
            是否登录成功。
        """
        username = credentials.get("username", "")
        password = credentials.get("password", "")

        if not username or not password:
            logger.error("CNKI adapter: username or password is empty")
            return False

        try:
            from playwright.async_api import async_playwright

            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(
                headless=False,  # 必须非 headless，让用户填验证码
                args=["--start-maximized"],
            )
            self._context = await self._browser.new_context(
                accept_downloads=True,
                viewport={"width": 1280, "height": 900},
            )
            self.page = await self._context.new_page()

            # Step 1: 打开登录页
            logger.info("CNKI: Navigating to wytsg.com login page...")
            await self.page.goto(WYTSG_LOGIN_URL, wait_until="domcontentloaded")
            await self.page.wait_for_timeout(1000)

            # Step 2: 填写用户名和密码
            logger.info("CNKI: Filling username and password...")
            await self.page.fill("input#userid", username)
            await self.page.fill("input#password", password)

            # Step 3: 等待用户手动输入验证码
            logger.info(
                "CNKI: Waiting for user to input captcha and click login "
                f"(timeout: {CAPTCHA_TIMEOUT}s)..."
            )

            # 等待页面跳转（表示登录成功），或超时
            try:
                await self.page.wait_for_url(
                    lambda url: "login" not in url.lower(),
                    timeout=CAPTCHA_TIMEOUT * 1000,
                )
                logger.info("CNKI: Login successful! Redirected to member area.")
            except Exception:
                logger.error("CNKI: Login timeout or failed.")
                return False

            # Step 4: 在登录后页面查找知网链接并点击
            await self.page.wait_for_timeout(2000)
            cnki_clicked = await self._find_and_click_cnki_link()

            if cnki_clicked:
                self._logged_in = True
                logger.info("CNKI: Successfully jumped to CNKI!")
                return True

            logger.warning("CNKI: Could not find CNKI jump link.")
            # 即使找不到跳转链接也标记为登录成功，后续可以手动操作
            self._logged_in = True
            return True

        except ImportError:
            logger.error(
                "Playwright is not installed. "
                "Run: pip install playwright && playwright install chromium"
            )
            return False
        except Exception as e:
            logger.error(f"CNKI login failed: {e}", exc_info=True)
            return False

    async def _find_and_click_cnki_link(self) -> bool:
        """在 wytsg.com 登录后页面查找知网跳转链接并点击。

        Returns:
            是否成功找到并点击了知网链接。
        """
        try:
            # 根据用户指定，优先点击“知网推荐4”
            selectors = [
                "a:has-text('知网推荐4')",
                "div:has-text('知网推荐4')",
                "a:has-text('知网')",
                "a:has-text('CNKI')",
                "a[href*='cnki']",
            ]

            for selector in selectors:
                try:
                    link = self.page.locator(selector).first
                    if await link.count() > 0:
                        logger.info(f"CNKI: Found link with selector: {selector}")

                        # 可能在新标签页打开，需要监听
                        async with self._context.expect_page() as new_page_info:
                            await link.click(timeout=5000)

                        new_page = await new_page_info.value
                        await new_page.wait_for_load_state("domcontentloaded")
                        self.page = new_page
                        return True
                except Exception:
                    continue

            # 如果是在同一页面跳转
            for selector in selectors:
                try:
                    link = self.page.locator(selector).first
                    if await link.count() > 0:
                        await link.click(timeout=5000)
                        await self.page.wait_for_timeout(3000)
                        return True
                except Exception:
                    continue

            return False

        except Exception as e:
            logger.warning(f"Failed to find CNKI link: {e}")
            return False

    async def search(
        self,
        keywords: list[str],
        max_results: int = 30,
    ) -> list[SearchResult]:
        """在知网上搜索论文。

        Args:
            keywords: 搜索关键词列表（会用空格连接）。
            max_results: 最大返回结果数。

        Returns:
            搜索结果列表。
        """
        if not self._logged_in or not self.page:
            logger.error("CNKI: Not logged in. Call login() first.")
            return []

        query = " ".join(keywords)
        logger.info(f"CNKI: Searching for '{query}', max_results={max_results}...")

        results: list[SearchResult] = []

        try:
            # 导航到知网搜索页
            await self.page.goto(
                CNKI_SEARCH_URL, wait_until="domcontentloaded", timeout=30000
            )
            await self.page.wait_for_timeout(2000)

            # 在搜索框中输入关键词
            search_input = self.page.locator(
                "input.search-input, input[name='txt_1_value1'], "
                "input#txt_SearchText"
            ).first
            await search_input.fill(query)
            await self.page.wait_for_timeout(500)

            # 点击搜索按钮
            search_btn = self.page.locator(
                "input.search-btn, button.search-btn, "
                "input[onclick*='search'], .btn-search"
            ).first
            await search_btn.click()

            # 等待搜索结果加载
            await self.page.wait_for_timeout(3000)
            await self.page.wait_for_selector(
                ".result-table-list, #gridTable, .s-main",
                timeout=15000,
            )

            # 解析搜索结果
            results = await self._parse_search_results(max_results)
            logger.info(f"CNKI: Found {len(results)} results for '{query}'")

        except Exception as e:
            logger.error(f"CNKI search failed: {e}", exc_info=True)

        return results

    async def _parse_search_results(
        self, max_results: int
    ) -> list[SearchResult]:
        """从知网搜索结果页面解析论文信息。

        Args:
            max_results: 最大解析数量。

        Returns:
            搜索结果列表。
        """
        results: list[SearchResult] = []

        try:
            # 知网搜索结果通常在表格中
            rows = self.page.locator(
                "table.result-table-list tbody tr, "
                "#gridTable tr.GTContentRow, "
                ".s-main .result-table-list tr"
            )

            count = await rows.count()
            parse_count = min(count, max_results)

            for i in range(parse_count):
                try:
                    row = rows.nth(i)

                    # 提取标题和链接
                    title_link = row.locator("td.name a, td.title a, a.fz14").first
                    title = (await title_link.text_content() or "").strip()
                    url = await title_link.get_attribute("href") or ""
                    if url and not url.startswith("http"):
                        url = f"https://kns.cnki.net{url}"

                    # 提取作者
                    author_el = row.locator("td.author, td:nth-child(2)").first
                    authors = (await author_el.text_content() or "").strip()

                    # 提取来源
                    source_el = row.locator("td.source a, td:nth-child(3) a").first
                    source = (await source_el.text_content() or "").strip()

                    # 提取发布日期
                    date_el = row.locator("td.date, td:nth-child(4)").first
                    publish_date = (await date_el.text_content() or "").strip()

                    if title:
                        results.append(
                            SearchResult(
                                title=title,
                                url=url,
                                authors=authors,
                                source=source,
                                publish_date=publish_date,
                                file_type="pdf",
                                platform=Platform.CNKI,
                            )
                        )

                except Exception as e:
                    logger.debug(f"Failed to parse result row {i}: {e}")
                    continue

        except Exception as e:
            logger.error(f"Failed to parse CNKI search results: {e}")

        return results

    async def download(
        self,
        items: list[SearchResult],
        dest_dir: Path,
        on_progress: OnProgressCallback | None = None,
    ) -> list[DownloadResult]:
        """下载论文到本地目录。

        Args:
            items: 待下载的搜索结果列表。
            dest_dir: 目标目录。
            on_progress: 进度回调。

        Returns:
            下载结果列表。
        """
        if not self._logged_in or not self.page:
            logger.error("CNKI: Not logged in.")
            return [
                DownloadResult(
                    item=item,
                    status=DownloadStatus.FAILED,
                    error="Not logged in",
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

            result = await self._download_single(item, dest_dir)
            results.append(result)

            # 添加随机延迟以避免被封
            await asyncio.sleep(2 + (idx % 3))

        if on_progress:
            await on_progress(f"下载完成: {len(results)} 个文件", 100.0)

        return results

    async def _download_single(
        self,
        item: SearchResult,
        dest_dir: Path,
    ) -> DownloadResult:
        """下载单个论文。

        Args:
            item: 搜索结果。
            dest_dir: 目标目录。

        Returns:
            下载结果。
        """
        try:
            # 打开论文详情页
            await self.page.goto(item.url, wait_until="domcontentloaded", timeout=15000)
            await self.page.wait_for_timeout(2000)

            # 查找下载按钮（PDF 优先，CAJ 次之）
            download_btn = None
            for selector in [
                "a#pdfDown, a.btn-dlpdf",
                "a[href*='PDF'], a:has-text('PDF 下载')",
                "a#cajDown, a.btn-dlcaj",
                "a[href*='CAJ'], a:has-text('CAJ 下载')",
                "a.btn-dl",
            ]:
                btn = self.page.locator(selector).first
                if await btn.count() > 0:
                    download_btn = btn
                    break

            if download_btn is None:
                return DownloadResult(
                    item=item,
                    status=DownloadStatus.FAILED,
                    error="No download button found",
                )

            # 生成安全的文件名
            safe_title = re.sub(r'[\\/:*?"<>|]', "_", item.title)[:80]
            file_ext = ".pdf" if "pdf" in (item.file_type or "pdf").lower() else ".caj"

            # 使用 Playwright 的 download 事件
            async with self.page.expect_download(
                timeout=DOWNLOAD_TIMEOUT * 1000
            ) as download_info:
                await download_btn.click()

            download = await download_info.value
            dest_file = dest_dir / f"{safe_title}{file_ext}"
            await download.save_as(str(dest_file))

            file_size = dest_file.stat().st_size
            logger.info(f"CNKI: Downloaded '{item.title}' → {dest_file} ({file_size} bytes)")

            return DownloadResult(
                item=item,
                status=DownloadStatus.SUCCESS,
                local_path=str(dest_file),
                file_size=file_size,
            )

        except Exception as e:
            logger.warning(f"CNKI: Failed to download '{item.title}': {e}")
            return DownloadResult(
                item=item,
                status=DownloadStatus.FAILED,
                error=str(e),
            )

    async def close(self) -> None:
        """关闭浏览器释放资源。"""
        try:
            if self._browser:
                await self._browser.close()
            if self._playwright:
                await self._playwright.stop()
            logger.info("CNKI: Browser closed.")
        except Exception as e:
            logger.warning(f"CNKI: Error closing browser: {e}")
        finally:
            self._browser = None
            self._playwright = None
            self.page = None
            self._logged_in = False
