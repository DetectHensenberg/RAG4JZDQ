"""Clean project for distribution — remove caches, venv, build artifacts, data, logs.

Usage:
    python .github/skills/package/scripts/clean.py          # dry-run (show what would be deleted)
    python .github/skills/package/scripts/clean.py --execute # actually delete
    python .github/skills/package/scripts/clean.py --execute --keep-data  # keep data/ & logs/
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

# Ensure UTF-8 stdout on Windows
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

REPO_ROOT = Path(__file__).resolve().parents[4]  # .github/skills/package/scripts → repo root

# ── Directories to remove ───────────────────────────────────────────────────
REMOVE_DIRS: list[str] = [
    # Python caches
    "**/__pycache__",
    "**/.pytest_cache",
    "**/.mypy_cache",
    "**/.ruff_cache",
    "**/.hypothesis",
    # Virtual environments
    ".venv",
    "venv",
    "env",
    # Build / dist artifacts
    "build",
    "dist",
    "*.egg-info",
    ".eggs",
    "sdist",
    "wheels",
    # IDE
    ".idea",
    ".vscode",
    # Jupyter
    ".ipynb_checkpoints",
    # Coverage
    "htmlcov",
    ".tox",
    ".nox",
    # Misc caches
    "cache",
    ".cache",
    # Stale artifact
    "nonexistent_traces.jsonl",
    # Test data caches
    "test_data/chroma",
    # Claude skill test artifacts
    ".claude/skills/test-skill",
]

# Directories removed only when --keep-data is NOT set
DATA_DIRS: list[str] = [
    "data",
    "logs",
]

# ── Files to remove ─────────────────────────────────────────────────────────
REMOVE_FILES: list[str] = [
    "**/*.pyc",
    "**/*.pyo",
    "**/*.pyd",
    "**/*.so",
    "**/*.egg",
    "**/*.cover",
    "**/*.py,cover",
    ".coverage",
    ".coverage.*",
    "coverage.xml",
    "nosetests.xml",
    "pip-log.txt",
    "pip-delete-this-directory.txt",
    "*.log",
    # Secrets that should never be shipped
    ".env",
    ".env.local",
    ".env.*.local",
    "secrets.yaml",
    # Skill caches 
    ".github/skills/auto-coder/.spec_hash",
    ".claude/skills/auto-coder/.spec_hash",
    # Config backups
    "config/settings.yaml.bak",
    "config/settings.yaml.qa_backup",
    "config/test_credentials.yaml",
]

# ── Files to sanitize (replace API keys with placeholders) ───────────────────
SANITIZE_FILES: list[str] = [
    "config/settings.yaml",
]


# Directories that are removed whole — skip glob matches inside them
_WHOLE_REMOVE_DIRS = {".venv", "venv", "env", "data", "build", "dist", "cache", ".cache"}


def _glob_resolve(patterns: list[str]) -> list[Path]:
    """Expand glob patterns relative to REPO_ROOT and return existing paths."""
    found: list[Path] = []
    for pat in patterns:
        if "**" in pat or "*" in pat:
            found.extend(REPO_ROOT.glob(pat))
        else:
            p = REPO_ROOT / pat
            if p.exists():
                found.append(p)
    # Deduplicate and filter out paths under whole-remove directories
    result: list[Path] = []
    for p in sorted(set(found)):
        rel = p.relative_to(REPO_ROOT)
        parts = rel.parts
        # Skip if this path is inside a directory that will be removed entirely
        # (e.g. .venv/__pycache__ is redundant if .venv itself is listed)
        if len(parts) > 1 and parts[0] in _WHOLE_REMOVE_DIRS:
            continue
        result.append(p)
    return result


# Directories too large to scan for size (just show "large")
_SKIP_SIZE_SCAN = {".venv", "venv", "env", "data"}


def _is_symlink(p: Path) -> bool:
    try:
        return p.is_symlink()
    except (OSError, PermissionError):
        return True


def _dir_size(d: Path) -> int | None:
    """Return total file size in bytes, or None if too large to scan."""
    if d.name in _SKIP_SIZE_SCAN:
        return None
    try:
        return sum(
            f.stat().st_size
            for f in d.rglob("*")
            if f.is_file() and not _is_symlink(f)
        )
    except (OSError, PermissionError):
        return None


def _sanitize_settings(path: Path, *, dry_run: bool) -> list[str]:
    """Replace real API keys / endpoints in settings.yaml with placeholders."""
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    import re
    actions: list[str] = []

    # Match api_key values (quoted or unquoted)
    def _replace_key(m: re.Match) -> str:
        prefix = m.group(1)
        actions.append(f"  Sanitize api_key in {path.relative_to(REPO_ROOT)}")
        return f'{prefix}"YOUR_API_KEY_HERE"'

    new_text = re.sub(
        r'(api_key:\s*)("[^"]*"|\'[^\']*\'|\S+)',
        _replace_key,
        text,
    )

    # Replace azure_endpoint values
    def _replace_endpoint(m: re.Match) -> str:
        prefix = m.group(1)
        actions.append(f"  Sanitize azure_endpoint in {path.relative_to(REPO_ROOT)}")
        return f'{prefix}"https://YOUR_ENDPOINT.openai.azure.com/"'

    new_text = re.sub(
        r'(azure_endpoint:\s*)("[^"]*"|\'[^\']*\'|\S+)',
        _replace_endpoint,
        new_text,
    )

    if new_text != text and not dry_run:
        path.write_text(new_text, encoding="utf-8")

    return actions


def main() -> None:
    parser = argparse.ArgumentParser(description="Clean project for packaging")
    parser.add_argument("--execute", action="store_true", help="Actually delete (default is dry-run)")
    parser.add_argument("--keep-data", action="store_true", help="Keep data/ and logs/ directories")
    parser.add_argument("--no-sanitize", action="store_true", help="Skip API key sanitization")
    args = parser.parse_args()

    dry_run = not args.execute
    if dry_run:
        print("🔍 DRY RUN — showing what would be removed (use --execute to delete)\n")
    else:
        print("🗑️  EXECUTING cleanup...\n")

    # ── Collect targets ──────────────────────────────────────────────────────
    dir_patterns = list(REMOVE_DIRS)
    if not args.keep_data:
        dir_patterns.extend(DATA_DIRS)

    dirs_to_remove = _glob_resolve(dir_patterns)
    files_to_remove = _glob_resolve(REMOVE_FILES)

    # ── Report & execute: directories ────────────────────────────────────────
    total_size = 0
    if dirs_to_remove:
        print("📁 Directories to remove:")
        for d in dirs_to_remove:
            if d.is_dir():
                size = _dir_size(d)
                size_str = _human_size(size) if size is not None else "large"
                if size is not None:
                    total_size += size
                label = f"  {d.relative_to(REPO_ROOT)}/  ({size_str})"
                print(label)
                if not dry_run:
                    shutil.rmtree(d, ignore_errors=True)
        print()

    # ── Report & execute: files ──────────────────────────────────────────────
    if files_to_remove:
        print("📄 Files to remove:")
        for f in files_to_remove:
            if f.is_file():
                try:
                    size = f.stat().st_size
                except (OSError, PermissionError):
                    size = 0
                total_size += size
                print(f"  {f.relative_to(REPO_ROOT)}  ({_human_size(size)})")
                if not dry_run:
                    f.unlink(missing_ok=True)
        print()

    # ── Sanitize config ──────────────────────────────────────────────────────
    if not args.no_sanitize:
        print("🔐 Sanitize secrets in config files:")
        for pat in SANITIZE_FILES:
            for p in _glob_resolve([pat]):
                actions = _sanitize_settings(p, dry_run=dry_run)
                for a in actions:
                    print(a)
        print()

    # ── Summary ──────────────────────────────────────────────────────────────
    action = "Would free" if dry_run else "Freed"
    print(f"✅ {action} ~{_human_size(total_size)}")
    if dry_run:
        print("\nRe-run with --execute to apply.")


def _human_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if abs(n) < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024  # type: ignore[assignment]
    return f"{n:.1f} TB"


if __name__ == "__main__":
    main()
