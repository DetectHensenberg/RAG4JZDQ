#!/usr/bin/env python3
"""QA Config — Switch settings.yaml profiles for testing different configurations.

Usage:
    python .github/skills/qa-tester/scripts/qa_config.py show          # List profiles
    python .github/skills/qa-tester/scripts/qa_config.py check         # Verify credentials
    python .github/skills/qa-tester/scripts/qa_config.py apply <name>  # Apply a profile
    python .github/skills/qa-tester/scripts/qa_config.py restore       # Restore backup

Profiles:
    deepseek         LLM → DeepSeek + Vision disabled (needs test_credentials.yaml)
    rerank_llm       Rerank → LLM-based
    no_vision        Vision LLM disabled
    invalid_llm_key  LLM API key set to invalid
    invalid_embed_key  Embedding API key set to invalid
"""

import argparse
import shutil
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML is required. Install with: pip install pyyaml")
    sys.exit(2)

REPO_ROOT = Path(__file__).resolve().parents[4]
SETTINGS_FILE = REPO_ROOT / "config" / "settings.yaml"
SETTINGS_BACKUP = REPO_ROOT / "config" / "settings.yaml.bak"
CREDENTIALS_FILE = REPO_ROOT / "config" / "test_credentials.yaml"


def _load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _save_yaml(path: Path, data: dict) -> None:
    # Preserve comments by doing targeted edits — but for simplicity,
    # we use dump with default_flow_style=False
    path.write_text(yaml.dump(data, default_flow_style=False, allow_unicode=True), encoding="utf-8")


def _backup() -> None:
    """Create backup if not already backed up."""
    if not SETTINGS_BACKUP.exists():
        shutil.copy2(SETTINGS_FILE, SETTINGS_BACKUP)
        print(f"   📋 Backup created: {SETTINGS_BACKUP.name}")
    else:
        print(f"   📋 Backup already exists")


def _load_credentials() -> dict | None:
    """Load test_credentials.yaml."""
    if not CREDENTIALS_FILE.exists():
        return None
    return _load_yaml(CREDENTIALS_FILE)


def apply_deepseek(settings: dict) -> dict:
    """Switch LLM to DeepSeek, disable Vision."""
    creds = _load_credentials()
    if not creds or "deepseek" not in creds:
        print("   ❌ DeepSeek credentials not found in test_credentials.yaml")
        sys.exit(1)

    ds = creds["deepseek"]
    api_key = ds.get("api_key", "")
    if not api_key or api_key.startswith("<"):
        print("   ❌ DeepSeek API key is not configured (still placeholder)")
        sys.exit(1)

    settings["llm"]["provider"] = "deepseek"
    settings["llm"]["model"] = ds.get("model", "deepseek-chat")
    settings["llm"]["api_key"] = api_key
    if "base_url" in ds:
        settings["llm"]["base_url"] = ds["base_url"]
    # Remove Azure-specific fields
    for key in ["deployment_name", "azure_endpoint", "api_version"]:
        settings["llm"].pop(key, None)

    # Disable Vision LLM (DeepSeek has no Vision API)
    settings["vision_llm"]["enabled"] = False

    print("   LLM -> deepseek / " + ds.get("model", "deepseek-chat"))
    print("   Vision -> disabled")
    return settings


def apply_rerank_llm(settings: dict) -> dict:
    """Enable LLM-based reranking."""
    settings["rerank"]["enabled"] = True
    settings["rerank"]["provider"] = "llm"
    settings["rerank"]["top_k"] = 5
    print("   Rerank -> llm (top_k=5)")
    return settings


def apply_no_vision(settings: dict) -> dict:
    """Disable Vision LLM."""
    settings["vision_llm"]["enabled"] = False
    print("   Vision -> disabled")
    return settings


def apply_invalid_llm_key(settings: dict) -> dict:
    """Set LLM API key to invalid value."""
    settings["llm"]["api_key"] = "invalid_key_12345"
    print("   LLM api_key -> invalid_key_12345")
    return settings


def apply_invalid_embed_key(settings: dict) -> dict:
    """Set Embedding API key to invalid value."""
    settings["embedding"]["api_key"] = "invalid_key_12345"
    print("   Embedding api_key -> invalid_key_12345")
    return settings


PROFILES = {
    "deepseek": apply_deepseek,
    "rerank_llm": apply_rerank_llm,
    "no_vision": apply_no_vision,
    "invalid_llm_key": apply_invalid_llm_key,
    "invalid_embed_key": apply_invalid_embed_key,
}


def cmd_show() -> None:
    """Show available profiles."""
    print("📋 Available Configuration Profiles")
    print("=" * 50)
    for name, fn in PROFILES.items():
        doc = fn.__doc__ or ""
        print(f"   {name:25s} {doc.strip()}")
    print()
    print(f"Current settings: {SETTINGS_FILE}")
    print(f"Backup exists: {SETTINGS_BACKUP.exists()}")


def cmd_check() -> None:
    """Check credentials file."""
    print("🔑 Credential Check")
    print("=" * 50)
    if not CREDENTIALS_FILE.exists():
        print(f"   ❌ {CREDENTIALS_FILE} not found")
        print(f"   → Copy from {CREDENTIALS_FILE.with_suffix('.yaml.example')}")
        return

    creds = _load_credentials()
    if creds and "deepseek" in creds:
        key = creds["deepseek"].get("api_key", "")
        if key and not key.startswith("<"):
            print(f"   ✅ DeepSeek API key: configured ({key[:8]}...)")
        else:
            print(f"   ⚠️  DeepSeek API key: placeholder (not configured)")
    else:
        print(f"   ⚠️  DeepSeek section: missing")


def cmd_apply(profile_name: str) -> None:
    """Apply a configuration profile."""
    if profile_name not in PROFILES:
        print(f"❌ Unknown profile: {profile_name}")
        print(f"   Available: {', '.join(PROFILES.keys())}")
        sys.exit(1)

    print(f"🔄 Applying profile: {profile_name}")
    _backup()

    settings = _load_yaml(SETTINGS_FILE)
    settings = PROFILES[profile_name](settings)
    _save_yaml(SETTINGS_FILE, settings)
    print(f"   ✅ settings.yaml updated")


def cmd_restore() -> None:
    """Restore settings.yaml from backup."""
    if not SETTINGS_BACKUP.exists():
        print("❌ No backup found. Nothing to restore.")
        return

    shutil.copy2(SETTINGS_BACKUP, SETTINGS_FILE)
    SETTINGS_BACKUP.unlink()
    print("✅ settings.yaml restored from backup")


def main() -> None:
    parser = argparse.ArgumentParser(description="QA Config — manage settings profiles")
    parser.add_argument(
        "command",
        choices=["show", "check", "apply", "restore"],
        help="Command to execute",
    )
    parser.add_argument(
        "profile",
        nargs="?",
        help="Profile name (for 'apply' command)",
    )
    args = parser.parse_args()

    if args.command == "show":
        cmd_show()
    elif args.command == "check":
        cmd_check()
    elif args.command == "apply":
        if not args.profile:
            print("❌ Profile name required. Usage: qa_config.py apply <profile>")
            sys.exit(1)
        cmd_apply(args.profile)
    elif args.command == "restore":
        cmd_restore()


if __name__ == "__main__":
    main()
