#!/bin/bash
# Continuous Learning v2 - Observation Hook
#
# Captures tool use events for pattern analysis.
# Claude Code passes hook data via stdin as JSON.
#
# v2.1: Project-scoped observations — detects current project context
#       and writes observations to project-specific directory.
#
# Registered via plugin hooks/hooks.json (auto-loaded when plugin is enabled).
# Can also be registered manually in ~/.claude/settings.json.

set -e

# Hook phase from CLI argument: "pre" (PreToolUse) or "post" (PostToolUse)
HOOK_PHASE="${1:-post}"

# ─────────────────────────────────────────────
# Read stdin first (before project detection)
# ─────────────────────────────────────────────

# Read JSON from stdin (Claude Code hook format)
INPUT_JSON=$(cat)

# Exit if no input
if [ -z "$INPUT_JSON" ]; then
  exit 0
fi

resolve_python_cmd() {
  if [ -n "${CLV2_PYTHON_CMD:-}" ] && command -v "$CLV2_PYTHON_CMD" >/dev/null 2>&1; then
    printf '%s\n' "$CLV2_PYTHON_CMD"
    return 0
  fi

  # FIX: Windows Git Bash — probe Python install paths directly because
  # `command -v python` can hit the Microsoft Store alias instead.
  for win_py in /c/Users/"$USER"/AppData/Local/Programs/Python/Python3*/python; do
    if [ -x "$win_py" ]; then
      printf '%s\n' "$win_py"
      return 0
    fi
  done

  if command -v python3 >/dev/null 2>&1; then
    printf '%s\n' python3
    return 0
  fi

  if command -v python >/dev/null 2>&1; then
    printf '%s\n' python
    return 0
  fi

  return 1
}

PYTHON_CMD="$(resolve_python_cmd 2>/dev/null || true)"
if [ -z "$PYTHON_CMD" ]; then
  echo "[observe] No python interpreter found, skipping observation" >&2
  exit 0
fi

# ─────────────────────────────────────────────
# Extract cwd from stdin for project detection
# ─────────────────────────────────────────────

# Extract cwd from the hook JSON to use for project detection.
# This avoids spawning a separate git subprocess when cwd is available.
STDIN_CWD=$(echo "$INPUT_JSON" | "$PYTHON_CMD" -c '
import json, sys
try:
    data = json.load(sys.stdin)
    cwd = data.get("cwd", "")
    print(cwd)
except(KeyError, TypeError, ValueError):
    print("")
' 2>/dev/null || echo "")

# If cwd was provided in stdin, use it for project detection
if [ -n "$STDIN_CWD" ] && [ -d "$STDIN_CWD" ]; then
  export CLAUDE_PROJECT_DIR="$STDIN_CWD"
fi

# ─────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────

CONFIG_DIR="${HOME}/.claude/homunculus"
MAX_FILE_SIZE_MB=10

# Skip if disabled globally
if [ -f "$CONFIG_DIR/disabled" ]; then
  exit 0
fi

# ─────────────────────────────────────────────
# Automated session guards
# Prevents observe.sh from firing on non-human sessions to avoid:
#   - ECC observing its own Haiku observer sessions (self-loop)
#   - ECC observing other tools' automated sessions (e.g. claude-mem)
#   - All-night Haiku usage with no human activity
# Run these before project detection so skipped sessions cannot mutate
# project-scoped observer state.
# ─────────────────────────────────────────────

# Env-var checks first (cheapest — no subprocess spawning):

# Layer 1: CLAUDE_CODE_ENTRYPOINT — set by Claude Code itself to indicate how
# it was invoked. Only interactive terminal sessions should continue; treat any
# explicit non-cli entrypoint as automated so future entrypoint types fail closed
# without requiring updates here.
case "${CLAUDE_CODE_ENTRYPOINT:-cli}" in
  cli) ;;
  *) exit 0 ;;
esac

# Layer 2: Respect ECC_HOOK_PROFILE=minimal — suppresses non-essential hooks
[ "${ECC_HOOK_PROFILE:-standard}" = "minimal" ] && exit 0

# Layer 3: Cooperative skip env var — tools like claude-mem can set this
# (export ECC_SKIP_OBSERVE=1) before spawning their automated sessions
[ "${ECC_SKIP_OBSERVE:-0}" = "1" ] && exit 0

# Layer 4: Skip subagent sessions — agent_id is only present when a hook fires
# inside a subagent (automated by definition, never a human interactive session).
# Placed after env-var checks to avoid a Python subprocess on sessions that
# already exit via Layers 1-3.
_ECC_AGENT_ID=$(echo "$INPUT_JSON" | "$PYTHON_CMD" -c "import json,sys; print(json.load(sys.stdin).get('agent_id',''))" 2>/dev/null || true)
[ -n "$_ECC_AGENT_ID" ] && exit 0

# Layer 5: CWD path exclusions — skip known observer-session directories.
# Add custom paths via ECC_OBSERVE_SKIP_PATHS (comma-separated substrings).
# Whitespace is trimmed from each pattern; empty patterns are skipped to
# prevent an empty-string glob from matching every path.
_ECC_SKIP_PATHS="${ECC_OBSERVE_SKIP_PATHS:-observer-sessions,.claude-mem}"
if [ -n "$STDIN_CWD" ]; then
  IFS=',' read -ra _ECC_SKIP_ARRAY <<< "$_ECC_SKIP_PATHS"
  for _pattern in "${_ECC_SKIP_ARRAY[@]}"; do
    _pattern="${_pattern#"${_pattern%%[![:space:]]*}"}"   # trim leading whitespace
    _pattern="${_pattern%"${_pattern##*[![:space:]]}"}"   # trim trailing whitespace
    [ -z "$_pattern" ] && continue
    case "$STDIN_CWD" in *"$_pattern"*) exit 0 ;; esac
  done
fi

# ─────────────────────────────────────────────
# Project detection
# ─────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SKILL_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Source shared project detection helper
# This sets: PROJECT_ID, PROJECT_NAME, PROJECT_ROOT, PROJECT_DIR
source "${SKILL_ROOT}/scripts/detect-project.sh"
PYTHON_CMD="${CLV2_PYTHON_CMD:-$PYTHON_CMD}"

OBSERVATIONS_FILE="${PROJECT_DIR}/observations.jsonl"

SENTINEL_FILE="${CLV2_OBSERVER_SENTINEL_FILE:-${PROJECT_ROOT:-$PROJECT_DIR}/.observer.lock}"

write_guard_sentinel() {
  printf '%s\n' 'observer paused: confirmation or permission prompt detected; rerun start-observer.sh --reset after reviewing observer.log' > "$SENTINEL_FILE"
}

# Skip if a previous run already aborted due to confirmation/permission prompt.
# This is the circuit-breaker — stops retrying after a non-interactive failure.
if [ -f "$SENTINEL_FILE" ]; then
  echo "[observe] Skipping: previous run aborted due to confirmation/permission prompt. Remove ${SENTINEL_FILE} to re-enable." >&2
  exit 0
fi

# Auto-purge observation files older than 30 days (runs once per session)
PURGE_MARKER="${PROJECT_DIR}/.last-purge"
if [ ! -f "$PURGE_MARKER" ] || [ "$(find "$PURGE_MARKER" -mtime +1 2>/dev/null)" ]; then
  find "${PROJECT_DIR}" -name "observations-*.jsonl" -mtime +30 -delete 2>/dev/null || true
  touch "$PURGE_MARKER" 2>/dev/null || true
fi

# Parse using Python via stdin pipe (safe for all JSON payloads)
# Pass HOOK_PHASE via env var since Claude Code does not include hook type in stdin JSON
PARSED=$(echo "$INPUT_JSON" | HOOK_PHASE="$HOOK_PHASE" "$PYTHON_CMD" -c '
import json
import sys
import os

try:
    data = json.load(sys.stdin)

    # Determine event type from CLI argument passed via env var.
    # Claude Code does NOT include a "hook_type" field in the stdin JSON,
    # so we rely on the shell argument ("pre" or "post") instead.
    hook_phase = os.environ.get("HOOK_PHASE", "post")
    event = "tool_start" if hook_phase == "pre" else "tool_complete"

    # Extract fields - Claude Code hook format
    tool_name = data.get("tool_name", data.get("tool", "unknown"))
    tool_input = data.get("tool_input", data.get("input", {}))
    tool_output = data.get("tool_response")
    if tool_output is None:
        tool_output = data.get("tool_output", data.get("output", ""))
    session_id = data.get("session_id", "unknown")
    tool_use_id = data.get("tool_use_id", "")
    cwd = data.get("cwd", "")

    # Truncate large inputs/outputs
    if isinstance(tool_input, dict):
        tool_input_str = json.dumps(tool_input)[:5000]
    else:
        tool_input_str = str(tool_input)[:5000]

    if isinstance(tool_output, dict):
        tool_response_str = json.dumps(tool_output)[:5000]
    else:
        tool_response_str = str(tool_output)[:5000]

    print(json.dumps({
        "parsed": True,
        "event": event,
        "tool": tool_name,
        "input": tool_input_str if event == "tool_start" else None,
        "output": tool_response_str if event == "tool_complete" else None,
        "session": session_id,
        "tool_use_id": tool_use_id,
        "cwd": cwd
    }))
except Exception as e:
    print(json.dumps({"parsed": False, "error": str(e)}))
')

# Check if parsing succeeded
PARSED_OK=$(echo "$PARSED" | "$PYTHON_CMD" -c "import json,sys; print(json.load(sys.stdin).get('parsed', False))" 2>/dev/null || echo "False")

if [ "$PARSED_OK" != "True" ]; then
  # Fallback: log raw input for debugging (scrub secrets before persisting)
  timestamp=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
  export TIMESTAMP="$timestamp"
  echo "$INPUT_JSON" | "$PYTHON_CMD" -c '
import json, sys, os, re

_SECRET_RE = re.compile(
    r"(?i)(api[_-]?key|token|secret|password|authorization|credentials?|auth)"
    r"""(["'"'"'\s:=]+)"""
    r"([A-Za-z]+\s+)?"
    r"([A-Za-z0-9_\-/.+=]{8,})"
)

raw = sys.stdin.read()[:2000]
raw = _SECRET_RE.sub(lambda m: m.group(1) + m.group(2) + (m.group(3) or "") + "[REDACTED]", raw)
print(json.dumps({"timestamp": os.environ["TIMESTAMP"], "event": "parse_error", "raw": raw}))
' >> "$OBSERVATIONS_FILE"
  exit 0
fi

# Archive if file too large (atomic: rename with unique suffix to avoid race)
if [ -f "$OBSERVATIONS_FILE" ]; then
  file_size_mb=$(du -m "$OBSERVATIONS_FILE" 2>/dev/null | cut -f1)
  if [ "${file_size_mb:-0}" -ge "$MAX_FILE_SIZE_MB" ]; then
    archive_dir="${PROJECT_DIR}/observations.archive"
    mkdir -p "$archive_dir"
    mv "$OBSERVATIONS_FILE" "$archive_dir/observations-$(date +%Y%m%d-%H%M%S)-$$.jsonl" 2>/dev/null || true
  fi
fi

# Detect confirmation/permission prompts in observer output and fail closed.
# A non-interactive background observer must never ask for user confirmation.
if echo "$PARSED" | grep -E -i -q "$CLV2_OBSERVER_PROMPT_PATTERN"; then
  echo "[observe] OBSERVER_ABORT: Confirmation or permission prompt detected in observer output. This observer run is non-actionable." >&2
  echo "[observe] Writing sentinel to suppress retries: ${SENTINEL_FILE}" >&2
  write_guard_sentinel
  exit 2
fi

# Build and write observation (now includes project context)
timestamp=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
export PROJECT_ID_ENV="$PROJECT_ID"
export PROJECT_NAME_ENV="$PROJECT_NAME"
export TIMESTAMP="$timestamp"
echo "$PARSED" | "$PYTHON_CMD" -c '
import json, sys, os, re
parsed = json.load(sys.stdin)
observation = {
  "timestamp": os.environ["TIMESTAMP"],
  "event": parsed["event"],
  "tool": parsed["tool"],
  "session": parsed["session"],
  "project_id": os.environ.get("PROJECT_ID_ENV", "global"),
  "project_name": os.environ.get("PROJECT_NAME_ENV", "global")
}
# Scrub secrets: match common key=value, key: value, and key"value patterns
_SECRET_RE = re.compile(
  r"(?i)(api[_-]?key|token|secret|password|authorization|credentials?|auth)"
  r"""(["'"'"'\s:=]+)"""
  r"([A-Za-z]+\s+)?"
  r"([A-Za-z0-9_\-/.+=]{8,})"
)
def scrub(val):
  if val is None:
    return None
  return _SECRET_RE.sub(lambda m: m.group(1) + m.group(2) + (m.group(3) or "") + "[REDACTED]", str(val))
if parsed["input"]:
  observation["input"] = scrub(parsed["input"])
if parsed["output"] is not None:
  observation["output"] = scrub(parsed["output"])
print(json.dumps(observation))
' >> "$OBSERVATIONS_FILE"

# Signal observer if running (check both project-scoped and global observer)
for pid_file in "${PROJECT_DIR}/.observer.pid" "${CONFIG_DIR}/.observer.pid"; do
  if [ -f "$pid_file" ]; then
    observer_pid=$(cat "$pid_file")
    if kill -0 "$observer_pid" 2>/dev/null; then
      kill -USR1 "$observer_pid" 2>/dev/null || true
    fi
  fi
done

exit 0
