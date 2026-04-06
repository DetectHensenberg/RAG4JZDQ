"""资料助手 — 平台适配器抽象基类与数据模型。

定义了所有平台适配器的统一接口 (Protocol) 以及搜索结果、下载结果的数据结构。
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, runtime_checkable


class Platform(str, enum.Enum):
    """支持的资料平台枚举。"""

    CNKI = "cnki"
    ZSXQ = "zsxq"
    WECHAT = "wechat"


@dataclass(frozen=True)
class SearchResult:
    """单条搜索结果。

    Attributes:
        title: 资料标题
        url: 资料链接
        authors: 作者列表
        abstract: 摘要/简介
        source: 来源 (期刊名/星球名/公众号名)
        publish_date: 发布日期 (ISO 格式字符串)
        file_type: 文件类型 (pdf/caj/docx/html/md)
        platform: 平台枚举
        extra: 平台特有的扩展字段
    """

    title: str
    url: str
    authors: str = ""
    abstract: str = ""
    source: str = ""
    publish_date: str = ""
    file_type: str = "pdf"
    platform: Platform = Platform.CNKI
    extra: dict[str, str] = field(default_factory=dict)


class DownloadStatus(str, enum.Enum):
    """下载状态。"""

    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class DownloadResult:
    """单个文件的下载结果。

    Attributes:
        item: 对应的搜索结果
        status: 下载状态
        local_path: 本地保存路径（下载成功时）
        error: 错误信息（下载失败时）
        file_size: 文件大小 (bytes)
    """

    item: SearchResult
    status: DownloadStatus
    local_path: str = ""
    error: str = ""
    file_size: int = 0


@runtime_checkable
class MaterialAdapter(Protocol):
    """资料平台适配器协议。

    所有平台适配器必须实现此协议，提供统一的搜索和下载接口。
    """

    @property
    def platform(self) -> Platform:
        """返回平台枚举值。"""
        ...

    async def login(self, credentials: dict[str, str]) -> bool:
        """登录平台。

        Args:
            credentials: 登录凭证，键值对因平台而异。

        Returns:
            登录是否成功。
        """
        ...

    async def search(
        self,
        keywords: list[str],
        max_results: int = 30,
    ) -> list[SearchResult]:
        """按关键词搜索资料。

        Args:
            keywords: 搜索关键词列表。
            max_results: 最大返回结果数。

        Returns:
            搜索结果列表。
        """
        ...

    async def download(
        self,
        items: list[SearchResult],
        dest_dir: Path,
        on_progress: OnProgressCallback | None = None,
    ) -> list[DownloadResult]:
        """批量下载资料到本地。

        Args:
            items: 待下载的搜索结果列表。
            dest_dir: 目标目录。
            on_progress: 下载进度回调。

        Returns:
            下载结果列表。
        """
        ...

    async def close(self) -> None:
        """释放资源（如关闭浏览器）。"""
        ...


# ── 回调类型 ─────────────────────────────────────────────────────
from typing import Callable, Coroutine, Any

OnProgressCallback = Callable[
    [str, float],  # (message, percent 0-100)
    Coroutine[Any, Any, None],
]
