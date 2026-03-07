---
name: package
description: "Clean and package the project for distribution. Removes __pycache__, .venv, build artifacts, data caches, logs, IDE files, coverage reports, and sanitizes API keys in config. Produces a minimal, ready-to-share codebase. Use when user says 'package', 'clean project', 'clean up', '打包', '清理项目', '清理缓存', 'prepare for distribution', 'remove caches', or wants to deliver a clean copy of the code."
---

# Package

One command cleans the project for distribution: remove caches, secrets, and artifacts.

---

## Pipeline

```
Dry-run → Confirm → Execute → Verify
```

> **⚠️ Activate `.venv` before running scripts.**
> - **Windows**: `.\.venv\Scripts\Activate.ps1`
> - **macOS/Linux**: `source .venv/bin/activate`

---

## Step 1: Dry Run

Show what will be removed without deleting anything:

```powershell
python .github/skills/package/scripts/clean.py
```

Review the output with the user. The script lists:
- 📁 Directories to remove (with sizes)
- 📄 Files to remove (with sizes)
- 🔐 Config values to sanitize (API keys → placeholders)

## Step 2: Confirm with User

Before executing, summarize what will be deleted and ask the user to confirm. Offer options:
- `--keep-data` — preserve `data/` and `logs/` (useful if user wants to keep ingested documents)
- `--no-sanitize` — skip API key replacement in `config/settings.yaml`

## Step 3: Execute

```powershell
# Full clean (removes everything including data)
python .github/skills/package/scripts/clean.py --execute

# Keep data and logs
python .github/skills/package/scripts/clean.py --execute --keep-data

# Skip secret sanitization
python .github/skills/package/scripts/clean.py --execute --no-sanitize
```

## Step 4: Verify

After cleanup, verify the workspace is clean:

```powershell
# Check no __pycache__ remains
python -c "import pathlib; found=list(pathlib.Path('.').rglob('__pycache__')); print(f'{len(found)} __pycache__ dirs remaining') if found else print('Clean')"

# Check no .venv remains
python -c "import pathlib; print('.venv still exists') if pathlib.Path('.venv').exists() else print('Clean')"

# Check settings.yaml has no real API keys
python -c "
import re, pathlib
text = pathlib.Path('config/settings.yaml').read_text()
keys = re.findall(r'api_key:\s*\"([^\"]+)\"', text)
real = [k for k in keys if k not in ('YOUR_API_KEY_HERE', '')]
print(f'{len(real)} real API key(s) found') if real else print('API keys sanitized')
"
```

Report results to user.

---

## What Gets Removed

| Category | Patterns |
|----------|----------|
| Python caches | `__pycache__/`, `*.pyc`, `*.pyo`, `.pytest_cache/`, `.mypy_cache/`, `.ruff_cache/` |
| Virtual envs | `.venv/`, `venv/`, `env/` |
| Build artifacts | `build/`, `dist/`, `*.egg-info/`, `.eggs/`, `wheels/` |
| IDE files | `.idea/`, `.vscode/`, `*.swp`, `*.swo` |
| Coverage | `htmlcov/`, `.coverage`, `coverage.xml`, `.tox/`, `.nox/` |
| Data & logs | `data/`, `logs/`, `cache/` (skip with `--keep-data`) |
| Secrets | `.env`, `.env.local`, `secrets.yaml`, `test_credentials.yaml` |
| Stale artifacts | `nonexistent_traces.jsonl/` |
| Config backups | `settings.yaml.bak`, `settings.yaml.qa_backup` |
| Test artifacts | `.claude/skills/test-skill/`, `test_data/chroma/` |
| Skill caches | `.github/skills/auto-coder/.spec_hash`, `.claude/skills/auto-coder/.spec_hash` |

## What Gets Sanitized (not removed)

- `config/settings.yaml`: `api_key` → `"YOUR_API_KEY_HERE"`, `azure_endpoint` → placeholder
