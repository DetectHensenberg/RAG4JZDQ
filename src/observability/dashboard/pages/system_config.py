"""系统配置页面 — 可视化管理 API Key、LLM、Embedding 等配置。

修改后自动保存到 config/settings.yaml 和 .env，无需手动编辑文件。
"""

from __future__ import annotations

import os
import logging
from pathlib import Path
from typing import Any, Dict

import yaml
import streamlit as st

from src.core.settings import REPO_ROOT, resolve_path

logger = logging.getLogger(__name__)

_SETTINGS_PATH = resolve_path("config/settings.yaml")
_ENV_PATH = REPO_ROOT / ".env"

# ── Preset providers ────────────────────────────────────────────
_LLM_PRESETS = {
    "DashScope (千问)": {
        "provider": "openai",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "models": ["qwen-plus", "qwen-turbo", "qwen-max", "qwen-long"],
    },
    "OpenAI": {
        "provider": "openai",
        "base_url": "https://api.openai.com/v1",
        "models": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo"],
    },
    "DeepSeek": {
        "provider": "deepseek",
        "base_url": "https://api.deepseek.com/v1",
        "models": ["deepseek-chat", "deepseek-reasoner"],
    },
    "Ollama (本地)": {
        "provider": "ollama",
        "base_url": "http://localhost:11434/v1",
        "models": ["llama3", "qwen2", "mistral", "gemma2"],
    },
    "自定义": {
        "provider": "openai",
        "base_url": "",
        "models": [],
    },
}

_EMBEDDING_PRESETS = {
    "DashScope": {
        "provider": "openai",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "models": ["text-embedding-v3", "text-embedding-v2"],
    },
    "OpenAI": {
        "provider": "openai",
        "base_url": "https://api.openai.com/v1",
        "models": ["text-embedding-3-small", "text-embedding-3-large", "text-embedding-ada-002"],
    },
    "Ollama (本地)": {
        "provider": "ollama",
        "base_url": "http://localhost:11434/v1",
        "models": ["nomic-embed-text", "mxbai-embed-large"],
    },
    "自定义": {
        "provider": "openai",
        "base_url": "",
        "models": [],
    },
}


def _load_yaml() -> Dict[str, Any]:
    """Load settings.yaml as raw dict."""
    if _SETTINGS_PATH.exists():
        with open(_SETTINGS_PATH, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


def _save_yaml(data: Dict[str, Any]) -> None:
    """Save dict back to settings.yaml."""
    _SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(_SETTINGS_PATH, "w", encoding="utf-8") as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)


def _load_env_key() -> str:
    """Load DASHSCOPE_API_KEY from .env file."""
    if _ENV_PATH.exists():
        for line in _ENV_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                if key.strip() == "DASHSCOPE_API_KEY":
                    return value.strip()
    return ""


def _save_env_key(api_key: str) -> None:
    """Save DASHSCOPE_API_KEY to .env file."""
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
    """Mask API key for display: sk-02c1...f215"""
    if not key or len(key) < 12:
        return key
    return key[:6] + "..." + key[-4:]


def render() -> None:
    st.header("⚙️ 系统配置")
    st.markdown("在此页面管理 API Key、模型配置和系统参数。修改后点击 **保存配置** 即可生效。")

    cfg = _load_yaml()
    env_key = _load_env_key()

    # ── API Key ─────────────────────────────────────────────────
    st.markdown("### 🔑 API Key 配置")

    current_key = env_key or cfg.get("llm", {}).get("api_key", "")
    if current_key:
        st.success(f"当前 API Key: `{_mask_key(current_key)}`")
    else:
        st.warning("未配置 API Key，请在下方输入")

    col_key, col_btn = st.columns([4, 1])
    with col_key:
        new_key = st.text_input(
            "API Key",
            value="",
            type="password",
            placeholder="输入新的 API Key（留空则保持不变）",
            key="cfg_api_key",
        )
    with col_btn:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("🔄 测试连接", key="cfg_test_key"):
            test_key = new_key.strip() or current_key
            if test_key:
                with st.spinner("测试中..."):
                    try:
                        import httpx
                        base_url = cfg.get("llm", {}).get("base_url", "https://dashscope.aliyuncs.com/compatible-mode/v1")
                        model = cfg.get("llm", {}).get("model", "qwen-plus")
                        resp = httpx.post(
                            f"{base_url.rstrip('/')}/chat/completions",
                            json={"model": model, "messages": [{"role": "user", "content": "hi"}], "max_tokens": 5},
                            headers={"Authorization": f"Bearer {test_key}", "Content-Type": "application/json"},
                            timeout=15.0,
                        )
                        if resp.status_code == 200:
                            st.success("✅ 连接成功！")
                        else:
                            st.error(f"❌ 连接失败 (HTTP {resp.status_code}): {resp.text[:200]}")
                    except Exception as e:
                        st.error(f"❌ 连接失败: {e}")
            else:
                st.warning("请先输入 API Key")

    st.divider()

    # ── LLM 配置 ───────────────────────────────────────────────
    st.markdown("### 🤖 LLM 配置")

    llm_cfg = cfg.get("llm", {})
    preset_names = list(_LLM_PRESETS.keys())

    # Detect current preset
    current_base = llm_cfg.get("base_url", "")
    current_preset = "自定义"
    for name, preset in _LLM_PRESETS.items():
        if preset["base_url"] and preset["base_url"] in current_base:
            current_preset = name
            break

    col1, col2 = st.columns(2)
    with col1:
        llm_preset = st.selectbox(
            "Provider 预设", preset_names,
            index=preset_names.index(current_preset),
            key="cfg_llm_preset",
        )
    preset = _LLM_PRESETS[llm_preset]

    with col2:
        model_options = preset["models"]
        current_model = llm_cfg.get("model", "")
        if current_model and current_model not in model_options:
            model_options = [current_model] + model_options
        if model_options:
            llm_model = st.selectbox(
                "模型", model_options,
                index=model_options.index(current_model) if current_model in model_options else 0,
                key="cfg_llm_model",
            )
        else:
            llm_model = st.text_input("模型名称", value=current_model, key="cfg_llm_model_custom")

    col3, col4 = st.columns(2)
    with col3:
        llm_base_url = st.text_input(
            "Base URL", value=preset["base_url"] or llm_cfg.get("base_url", ""),
            key="cfg_llm_base_url",
        )
    with col4:
        llm_temp = st.slider(
            "Temperature", 0.0, 2.0, float(llm_cfg.get("temperature", 0.0)),
            step=0.1, key="cfg_llm_temp",
        )

    llm_max_tokens = st.number_input(
        "Max Tokens", value=int(llm_cfg.get("max_tokens", 4096)),
        min_value=256, max_value=32768, step=256, key="cfg_llm_max_tokens",
    )

    st.divider()

    # ── Embedding 配置 ──────────────────────────────────────────
    st.markdown("### 📐 Embedding 配置")

    emb_cfg = cfg.get("embedding", {})
    emb_preset_names = list(_EMBEDDING_PRESETS.keys())

    current_emb_base = emb_cfg.get("base_url", "")
    current_emb_preset = "自定义"
    for name, preset_e in _EMBEDDING_PRESETS.items():
        if preset_e["base_url"] and preset_e["base_url"] in current_emb_base:
            current_emb_preset = name
            break

    col5, col6 = st.columns(2)
    with col5:
        emb_preset = st.selectbox(
            "Provider 预设", emb_preset_names,
            index=emb_preset_names.index(current_emb_preset),
            key="cfg_emb_preset",
        )
    emb_p = _EMBEDDING_PRESETS[emb_preset]

    with col6:
        emb_model_options = emb_p["models"]
        current_emb_model = emb_cfg.get("model", "")
        if current_emb_model and current_emb_model not in emb_model_options:
            emb_model_options = [current_emb_model] + emb_model_options
        if emb_model_options:
            emb_model = st.selectbox(
                "模型", emb_model_options,
                index=emb_model_options.index(current_emb_model) if current_emb_model in emb_model_options else 0,
                key="cfg_emb_model",
            )
        else:
            emb_model = st.text_input("模型名称", value=current_emb_model, key="cfg_emb_model_custom")

    col7, col8 = st.columns(2)
    with col7:
        emb_base_url = st.text_input(
            "Base URL", value=emb_p["base_url"] or emb_cfg.get("base_url", ""),
            key="cfg_emb_base_url",
        )
    with col8:
        emb_dimensions = st.number_input(
            "向量维度", value=int(emb_cfg.get("dimensions", 1024)),
            min_value=128, max_value=4096, step=128, key="cfg_emb_dim",
        )

    st.divider()

    # ── Ingestion 配置 ──────────────────────────────────────────
    st.markdown("### 📥 摄取管道配置")

    ing_cfg = cfg.get("ingestion", {})
    col9, col10, col11 = st.columns(3)
    with col9:
        chunk_size = st.number_input(
            "分块大小 (字符)", value=int(ing_cfg.get("chunk_size", 1000)),
            min_value=200, max_value=5000, step=100, key="cfg_chunk_size",
        )
    with col10:
        chunk_overlap = st.number_input(
            "分块重叠 (字符)", value=int(ing_cfg.get("chunk_overlap", 200)),
            min_value=0, max_value=1000, step=50, key="cfg_chunk_overlap",
        )
    with col11:
        use_llm_refine = st.checkbox(
            "LLM Chunk 精炼",
            value=ing_cfg.get("chunk_refiner", {}).get("use_llm", False) if ing_cfg.get("chunk_refiner") else False,
            key="cfg_use_llm_refine",
            help="启用后使用 LLM 精炼分块内容（消耗更多 API 配额）",
        )

    st.divider()

    # ── Retrieval 配置 ──────────────────────────────────────────
    st.markdown("### 🔍 检索配置")

    ret_cfg = cfg.get("retrieval", {})
    col12, col13, col14 = st.columns(3)
    with col12:
        dense_top_k = st.number_input(
            "Dense Top-K", value=int(ret_cfg.get("dense_top_k", 20)),
            min_value=1, max_value=100, key="cfg_dense_topk",
        )
    with col13:
        sparse_top_k = st.number_input(
            "Sparse Top-K", value=int(ret_cfg.get("sparse_top_k", 20)),
            min_value=1, max_value=100, key="cfg_sparse_topk",
        )
    with col14:
        fusion_top_k = st.number_input(
            "Fusion Top-K", value=int(ret_cfg.get("fusion_top_k", 10)),
            min_value=1, max_value=50, key="cfg_fusion_topk",
        )

    st.divider()

    # ── 保存按钮 ────────────────────────────────────────────────
    col_save, col_reset = st.columns([1, 1])
    with col_save:
        if st.button("💾 保存配置", type="primary", use_container_width=True):
            # Save API Key to .env
            if new_key.strip():
                _save_env_key(new_key.strip())

            # Update settings.yaml
            cfg["llm"] = {
                "provider": preset["provider"] if llm_preset != "自定义" else llm_cfg.get("provider", "openai"),
                "model": llm_model,
                "base_url": llm_base_url,
                "api_key": "",
                "temperature": llm_temp,
                "max_tokens": int(llm_max_tokens),
                "proxy": llm_cfg.get("proxy", ""),
            }
            cfg["embedding"] = {
                "provider": emb_p["provider"] if emb_preset != "自定义" else emb_cfg.get("provider", "openai"),
                "model": emb_model,
                "dimensions": int(emb_dimensions),
                "base_url": emb_base_url,
                "api_key": "",
            }
            cfg.setdefault("ingestion", {})
            cfg["ingestion"]["chunk_size"] = int(chunk_size)
            cfg["ingestion"]["chunk_overlap"] = int(chunk_overlap)
            cfg["ingestion"].setdefault("chunk_refiner", {})
            cfg["ingestion"]["chunk_refiner"]["use_llm"] = use_llm_refine
            cfg.setdefault("retrieval", {})
            cfg["retrieval"]["dense_top_k"] = int(dense_top_k)
            cfg["retrieval"]["sparse_top_k"] = int(sparse_top_k)
            cfg["retrieval"]["fusion_top_k"] = int(fusion_top_k)

            _save_yaml(cfg)

            # Clear cached settings and LLM instances
            for k in list(st.session_state.keys()):
                if k.startswith("_qa_"):
                    del st.session_state[k]

            st.success("✅ 配置已保存！重新进入其他页面后生效。")
            logger.info("System configuration updated via Dashboard")

    with col_reset:
        if st.button("🔄 重置为默认", use_container_width=True):
            example_path = resolve_path("config/settings.yaml.example")
            if example_path.exists():
                import shutil
                shutil.copy(str(example_path), str(_SETTINGS_PATH))
                st.success("✅ 已重置为默认配置")
                st.rerun()
            else:
                st.error("找不到 settings.yaml.example 模板文件")
