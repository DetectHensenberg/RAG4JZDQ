"""System config API router — read/write settings.yaml and .env."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict

import yaml
from fastapi import APIRouter

from src.core.settings import REPO_ROOT, resolve_path

logger = logging.getLogger(__name__)
router = APIRouter()

_SETTINGS_PATH = resolve_path("config/settings.yaml")
_ENV_PATH = REPO_ROOT / ".env"


def _load_yaml() -> Dict[str, Any]:
    if _SETTINGS_PATH.exists():
        with open(_SETTINGS_PATH, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


def _save_yaml(data: Dict[str, Any]) -> None:
    _SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(_SETTINGS_PATH, "w", encoding="utf-8") as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)


def _load_env_key() -> str:
    if _ENV_PATH.exists():
        for line in _ENV_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                if key.strip() == "DASHSCOPE_API_KEY":
                    return value.strip()
    return ""


def _save_env_key(api_key: str) -> None:
    lines = []
    found = False
    if _ENV_PATH.exists():
        for line in _ENV_PATH.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and stripped.startswith("DASHSCOPE_API_KEY"):
                lines.append(f"DASHSCOPE_API_KEY={api_key}")
                found = True
            else:
                lines.append(line)
    if not found:
        if not lines or lines[-1].strip():
            lines.append("")
        lines.append(f"DASHSCOPE_API_KEY={api_key}")
    _ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.environ["DASHSCOPE_API_KEY"] = api_key


def _mask_key(key: str) -> str:
    if not key or len(key) < 12:
        return "***"
    return key[:6] + "..." + key[-4:]


@router.get("")
async def get_config():
    """Return current configuration (API keys masked)."""
    cfg = _load_yaml()
    env_key = _load_env_key()
    return {
        "ok": True,
        "data": {
            "config": cfg,
            "api_key_masked": _mask_key(env_key),
            "has_api_key": bool(env_key),
        },
    }


@router.put("")
async def update_config(body: Dict[str, Any]):
    """Update settings.yaml and optionally .env API key."""
    api_key = body.pop("api_key", None)
    if api_key and api_key.strip():
        _save_env_key(api_key.strip())

    cfg = body.get("config", body)
    # Ensure api_key fields in yaml stay empty (loaded from .env)
    for section in ("llm", "embedding", "vision_llm"):
        if section in cfg and isinstance(cfg[section], dict):
            cfg[section]["api_key"] = ""

    _save_yaml(cfg)

    # Clear cached instances
    from api.deps import reset_all
    reset_all()

    logger.info("Configuration updated via API")
    return {"ok": True, "message": "配置已保存"}


@router.post("/test")
async def test_connection(body: Dict[str, Any]):
    """Test API key + base_url + model connectivity."""
    api_key = body.get("api_key", "").strip() or _load_env_key()
    base_url = body.get("base_url", "")
    model = body.get("model", "")

    if not api_key:
        return {"ok": False, "message": "未提供 API Key"}
    if not base_url:
        return {"ok": False, "message": "未提供 Base URL"}

    try:
        import httpx
        resp = httpx.post(
            f"{base_url.rstrip('/')}/chat/completions",
            json={"model": model, "messages": [{"role": "user", "content": "hi"}], "max_tokens": 5},
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            timeout=15.0,
        )
        if resp.status_code == 200:
            return {"ok": True, "message": "连接成功"}
        else:
            return {"ok": False, "message": f"HTTP {resp.status_code}: {resp.text[:200]}"}
    except Exception as e:
        return {"ok": False, "message": f"连接失败: {e}"}
