"""System config API router — read/write settings.yaml and .env."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict

import yaml
from fastapi import APIRouter

from api.crypto import decrypt, encrypt
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
    """Load DASHSCOPE_API_KEY (main LLM key) from .env."""
    return _load_env_var("DASHSCOPE_API_KEY")


def _load_emb_key() -> str:
    """Load EMBEDDING_API_KEY from .env, fall back to DASHSCOPE_API_KEY."""
    key = _load_env_var("EMBEDDING_API_KEY")
    return key or _load_env_var("DASHSCOPE_API_KEY")


def _load_env_var(var_name: str) -> str:
    """Load a specific env var from .env file."""
    if _ENV_PATH.exists():
        for line in _ENV_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                if key.strip() == var_name:
                    raw = value.strip()
                    if raw.startswith("enc:"):
                        try:
                            return decrypt(raw[4:])
                        except ValueError:
                            return raw
                    return raw
    return ""


def _save_env_key(api_key: str) -> None:
    """Save DASHSCOPE_API_KEY to .env."""
    _save_env_var("DASHSCOPE_API_KEY", api_key)
    os.environ["DASHSCOPE_API_KEY"] = api_key


def _save_emb_key(api_key: str) -> None:
    """Save EMBEDDING_API_KEY to .env."""
    _save_env_var("EMBEDDING_API_KEY", api_key)
    os.environ["EMBEDDING_API_KEY"] = api_key


def _save_env_var(var_name: str, value: str) -> None:
    """Write an env var to .env file, creating or updating the line."""
    encrypted_value = f"enc:{encrypt(value)}"
    lines = []
    found = False
    if _ENV_PATH.exists():
        for line in _ENV_PATH.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and stripped.startswith(f"{var_name}="):
                lines.append(f"{var_name}={encrypted_value}")
                found = True
            else:
                lines.append(line)
    if not found:
        if not lines or lines[-1].strip():
            lines.append("")
        lines.append(f"{var_name}={encrypted_value}")
    _ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _mask_key(key: str) -> str:
    if not key or len(key) < 12:
        return "***"
    return key[:6] + "..." + key[-4:]


@router.get("")
async def get_config():
    """Return current configuration (API keys masked)."""
    cfg = _load_yaml()
    llm_key = _load_env_key()
    emb_key = _load_env_var("EMBEDDING_API_KEY")
    return {
        "ok": True,
        "data": {
            "config": cfg,
            "api_key_masked": _mask_key(llm_key),   # 兼容旧字段
            "llm_key_masked": _mask_key(llm_key),
            "emb_key_masked": _mask_key(emb_key),
            "has_api_key": bool(llm_key),
        },
    }


@router.put("")
async def update_config(body: Dict[str, Any]):
    """Update settings.yaml and optionally .env API keys."""
    api_key = body.pop("api_key", None)
    if api_key and api_key.strip():
        _save_env_key(api_key.strip())

    embedding_api_key = body.pop("embedding_api_key", None)
    if embedding_api_key and embedding_api_key.strip():
        _save_emb_key(embedding_api_key.strip())

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
    """Test API key + base_url + model connectivity.
    
    Supports two modes:
    - Default: Chat completions test (LLM/Vision keys)
    - test_embedding=True: Embeddings test (Embedding key)
    """
    api_key = body.get("api_key", "").strip()
    base_url = body.get("base_url", "")
    model = body.get("model", "")
    test_embedding = body.get("test_embedding", False)

    # Fall back to env keys if no key provided
    if not api_key:
        api_key = _load_emb_key() if test_embedding else _load_env_key()

    if not api_key:
        return {"ok": False, "message": "未提供 API Key"}
    if not base_url:
        return {"ok": False, "message": "未提供 Base URL"}

    try:
        import httpx
        if test_embedding:
            # Test embedding endpoint
            resp = httpx.post(
                f"{base_url.rstrip('/')}/embeddings",
                json={"model": model or "text-embedding-v3", "input": ["test"]},
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                timeout=15.0,
            )
        else:
            # Test chat completions endpoint
            resp = httpx.post(
                f"{base_url.rstrip('/')}/chat/completions",
                json={"model": model, "messages": [{"role": "user", "content": "hi"}], "max_tokens": 5},
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                timeout=15.0,
            )
        if resp.status_code == 200:
            key_type = "Embedding" if test_embedding else "模型"
            return {"ok": True, "message": f"{key_type} Key 连接成功"}
        else:
            return {"ok": False, "message": f"HTTP {resp.status_code}: {resp.text[:200]}"}
    except Exception as e:
        return {"ok": False, "message": f"连接失败: {e}"}
