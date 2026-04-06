"""资料助手 API 路由 — 下载任务管理与进度推送。

提供 REST API 和 SSE 进度流用于:
- 创建/查询/删除下载任务
- 平台账号配置管理
- 实时下载进度推送
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Optional

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter()


# ── 请求/响应模型 ─────────────────────────────────────────────────
class CreateTaskRequest(BaseModel):
    """创建下载任务的请求。"""

    platform: str  # cnki / zsxq / wechat
    keywords: list[str]
    dest_dir: str
    max_results: int = 30


class SaveConfigRequest(BaseModel):
    """保存平台账号配置。"""

    platform: str
    username: str = ""
    password: str = ""
    extra: dict[str, str] = {}


# ── 任务管理接口 ──────────────────────────────────────────────────
@router.post("/task")
async def create_task(req: CreateTaskRequest):
    """创建新的下载任务并立即开始执行。

    Args:
        req: 下载任务参数。

    Returns:
        任务 ID 和初始状态。
    """
    from src.material.task_manager import TaskManager

    manager = TaskManager()
    task = manager.create_task(
        platform=req.platform,
        keywords=req.keywords,
        dest_dir=req.dest_dir,
        max_results=req.max_results,
    )

    # 在后台启动下载流程
    asyncio.create_task(_execute_task(task.id))

    return {"ok": True, "data": task.to_dict()}


@router.get("/task/{task_id}")
async def get_task(task_id: str):
    """获取任务详情。

    Args:
        task_id: 任务 ID。

    Returns:
        任务详情。
    """
    from src.material.task_manager import TaskManager

    manager = TaskManager()
    task = manager.get_task(task_id)
    if not task:
        return {"ok": False, "message": "任务不存在"}
    return {"ok": True, "data": task.to_dict()}


@router.get("/task/{task_id}/progress")
async def task_progress_stream(task_id: str):
    """SSE 进度推送流。

    Args:
        task_id: 任务 ID。

    Returns:
        SSE 事件流。
    """

    async def event_stream():
        from src.material.task_manager import TaskManager, TaskStatus

        manager = TaskManager()
        last_percent = -1.0

        while True:
            task = manager.get_task(task_id)
            if not task:
                yield f"data: {json.dumps({'error': '任务不存在'})}\n\n"
                break

            # 只在进度变化时推送
            if task.progress_percent != last_percent:
                last_percent = task.progress_percent
                yield f"data: {json.dumps(task.to_dict(), ensure_ascii=False)}\n\n"

            # 终止条件
            if task.status in (
                TaskStatus.COMPLETED,
                TaskStatus.FAILED,
                TaskStatus.CANCELLED,
            ):
                break

            await asyncio.sleep(1)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.get("/tasks")
async def list_tasks(limit: int = 50):
    """列出历史任务。

    Args:
        limit: 返回数量上限。

    Returns:
        任务列表。
    """
    from src.material.task_manager import TaskManager

    manager = TaskManager()
    tasks = manager.list_tasks(limit=limit)
    return {"ok": True, "data": [t.to_dict() for t in tasks]}


@router.delete("/task/{task_id}")
async def delete_task(task_id: str):
    """删除任务。

    Args:
        task_id: 任务 ID。

    Returns:
        是否成功删除。
    """
    from src.material.task_manager import TaskManager

    manager = TaskManager()
    deleted = manager.delete_task(task_id)
    return {"ok": deleted, "message": "已删除" if deleted else "删除失败"}


# ── 账号配置接口 ──────────────────────────────────────────────────
@router.post("/config")
async def save_config(req: SaveConfigRequest):
    """保存平台账号配置到 .env 文件。

    Args:
        req: 平台配置信息。

    Returns:
        保存结果。
    """
    try:
        env_path = Path(__file__).resolve().parent.parent.parent / ".env"
        env_content = env_path.read_text(encoding="utf-8") if env_path.exists() else ""

        # 构建环境变量键名
        prefix = f"MATERIAL_{req.platform.upper()}"
        updates = {}
        if req.username:
            updates[f"{prefix}_USERNAME"] = req.username
        if req.password:
            updates[f"{prefix}_PASSWORD"] = req.password
        for key, value in req.extra.items():
            updates[f"{prefix}_{key.upper()}"] = value

        # 更新 .env 文件
        lines = env_content.split("\n")
        for env_key, env_value in updates.items():
            found = False
            for i, line in enumerate(lines):
                if line.startswith(f"{env_key}="):
                    lines[i] = f'{env_key}="{env_value}"'
                    found = True
                    break
            if not found:
                lines.append(f'{env_key}="{env_value}"')

            # 同时设置环境变量（当前进程生效）
            os.environ[env_key] = env_value

        env_path.write_text("\n".join(lines), encoding="utf-8")
        logger.info(f"Saved {len(updates)} config entries for platform '{req.platform}'")

        return {"ok": True, "message": f"已保存 {req.platform} 配置"}

    except Exception as e:
        logger.exception(f"Failed to save config: {e}")
        return {"ok": False, "message": str(e)}


@router.get("/config/{platform}")
async def get_config(platform: str):
    """读取平台账号配置（密码脱敏）。

    Args:
        platform: 平台名称。

    Returns:
        配置信息（密码仅显示是否已配置）。
    """
    prefix = f"MATERIAL_{platform.upper()}"
    username = os.environ.get(f"{prefix}_USERNAME", "")
    password = os.environ.get(f"{prefix}_PASSWORD", "")

    return {
        "ok": True,
        "data": {
            "platform": platform,
            "username": username,
            "has_password": bool(password),
        },
    }


# ── 任务执行逻辑 ──────────────────────────────────────────────────
async def _execute_task(task_id: str) -> None:
    """后台执行下载任务。

    完整流程: 登录 → 搜索 → LLM筛选 → 下载

    Args:
        task_id: 任务 ID。
    """
    from src.material.task_manager import TaskManager, TaskStatus

    manager = TaskManager()
    task = manager.get_task(task_id)

    if not task:
        return

    adapter = None

    try:
        # Step 1: 获取适配器
        adapter = _get_adapter(task.platform)
        if adapter is None:
            task.status = TaskStatus.FAILED
            task.error = f"不支持的平台: {task.platform}"
            manager.update_task(task)
            return

        # Step 2: 登录
        task.status = TaskStatus.LOGGING_IN
        task.progress_percent = 5.0
        task.progress_message = "正在登录..."
        manager.update_task(task)

        credentials = _get_credentials(task.platform)
        login_ok = await adapter.login(credentials)

        if not login_ok:
            task.status = TaskStatus.FAILED
            task.error = "登录失败，请检查账号配置"
            manager.update_task(task)
            return

        # Step 3: 搜索
        task.status = TaskStatus.SEARCHING
        task.progress_percent = 20.0
        task.progress_message = f"正在搜索: {', '.join(task.keywords)}"
        manager.update_task(task)

        search_results = await adapter.search(
            keywords=task.keywords,
            max_results=task.max_results * 2,  # 多搜一些给 LLM 筛选
        )
        task.total_found = len(search_results)
        task.progress_percent = 40.0
        task.progress_message = f"找到 {task.total_found} 个结果，正在筛选..."
        manager.update_task(task)

        # Step 4: LLM 相关性筛选
        task.status = TaskStatus.FILTERING
        manager.update_task(task)

        try:
            from api.deps import get_llm
            from src.material.relevance_filter import RelevanceFilter

            llm = get_llm()
            relevance_filter = RelevanceFilter(llm)
            filtered = await relevance_filter.filter(
                items=search_results,
                keywords=task.keywords,
            )
        except Exception as e:
            logger.warning(f"LLM filter failed, using all results: {e}")
            filtered = search_results

        # 限制到 max_results
        filtered = filtered[: task.max_results]
        task.filtered_count = len(filtered)
        task.progress_percent = 50.0
        task.progress_message = f"筛选后 {task.filtered_count} 个结果，开始下载..."
        manager.update_task(task)

        # Step 5: 下载
        task.status = TaskStatus.DOWNLOADING
        manager.update_task(task)

        # 创建按主题命名的子文件夹
        topic_name = "_".join(task.keywords)[:50]
        dest_dir = Path(task.dest_dir) / topic_name
        dest_dir.mkdir(parents=True, exist_ok=True)

        async def _on_progress(msg: str, percent: float) -> None:
            """下载进度回调。"""
            task.progress_percent = 50.0 + (percent * 0.5)
            task.progress_message = msg
            manager.update_task(task)

        download_results = await adapter.download(
            items=filtered,
            dest_dir=dest_dir,
            on_progress=_on_progress,
        )

        # 统计结果
        from src.material.base_adapter import DownloadStatus

        task.downloaded_count = sum(
            1 for r in download_results if r.status == DownloadStatus.SUCCESS
        )
        task.failed_count = sum(
            1 for r in download_results if r.status == DownloadStatus.FAILED
        )
        task.results = [
            {
                "title": r.item.title,
                "status": r.status.value,
                "path": r.local_path,
                "error": r.error,
                "size": r.file_size,
            }
            for r in download_results
        ]

        task.status = TaskStatus.COMPLETED
        task.progress_percent = 100.0
        task.progress_message = (
            f"完成！成功 {task.downloaded_count}/"
            f"{task.filtered_count} 个文件"
        )
        manager.update_task(task)

        logger.info(
            f"Task {task_id} completed: "
            f"{task.downloaded_count} downloaded, "
            f"{task.failed_count} failed"
        )

    except Exception as e:
        logger.exception(f"Task {task_id} failed: {e}")
        task.status = TaskStatus.FAILED
        task.error = str(e)
        manager.update_task(task)

    finally:
        if adapter:
            await adapter.close()


def _get_adapter(platform: str) -> Optional[object]:
    """根据平台名称获取适配器实例。

    Args:
        platform: 平台名称。

    Returns:
        适配器实例，不支持的平台返回 None。
    """
    if platform == "cnki":
        from src.material.adapters.cnki_adapter import CnkiAdapter

        return CnkiAdapter()
    if platform == "zsxq":
        from src.material.adapters.zsxq_adapter import ZsxqAdapter

        return ZsxqAdapter()
    if platform == "wechat":
        from src.material.adapters.wechat_adapter import WechatAdapter

        return WechatAdapter()
    return None


def _get_credentials(platform: str) -> dict[str, str]:
    """从环境变量读取平台凭证。

    Args:
        platform: 平台名称。

    Returns:
        凭证字典。
    """
    prefix = f"MATERIAL_{platform.upper()}"
    return {
        "username": os.environ.get(f"{prefix}_USERNAME", ""),
        "password": os.environ.get(f"{prefix}_PASSWORD", ""),
        "cookie": os.environ.get(f"{prefix}_COOKIE", ""),
        "group_id": os.environ.get(f"{prefix}_GROUP_ID", ""),
    }
