#!/usr/bin/env python3
"""QA Note Validator — Detect inference-based notes in QA_TEST_PROGRESS.md.

Scans all ✅ test entries and flags those whose Note column contains
cross-referencing, inference, or missing execution evidence.

Usage:
    python .github/skills/qa-tester/scripts/qa_validate_notes.py

Exit code:
    0 — All notes pass validation
    1 — One or more notes flagged as potentially inferred
"""

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
PROGRESS_FILE = REPO_ROOT / "QA_TEST_PROGRESS.md"

# ── Patterns that indicate INFERRED rather than EXECUTED results ──

INFERENCE_PATTERNS = [
    # Cross-referencing another test
    (r"(?i)\bverified\s+(in|via|across|through)\s+[A-Z]-\d", "Cross-references another test ID"),
    (r"(?i)\balready\s+verified\b", "Claims 'already verified' elsewhere"),
    (r"(?i)\bsame\s+(as|code\s+path|pattern)\b", "Infers from 'same code path'"),
    (r"(?i)\bwill\s+be\s+tested\b", "Defers to future test"),
    (r"(?i)\bverified\s+(via|through)\s+[A-Z]-\d", "Cross-references test ID"),

    # Structural / code-reading inference
    (r"(?i)\bcode\s+uses\b", "Infers from reading code, not execution"),
    (r"(?i)\bdataclass\s+validates\b", "Infers from code structure"),
    (r"(?i)\bauto-creates\b", "Infers behavior, not observed"),
    (r"(?i)\bwould\s+(raise|fail|crash|similarly)\b", "Speculative 'would' language"),
    (r"(?i)\bshould\s+(work|succeed|fail)\b", "Speculative 'should' language"),
    (r"(?i)\b(expected|expect)\b(?!.*\bactual\b)", "Says 'expected' without 'actual'"),

    # Too vague — no concrete values
    (r"(?i)\bparameter\s+accepted\b$", "Vague: 'parameter accepted' without observed result"),
    (r"(?i)\bconfig\s+.*\bcontrols\s+behavior\b", "Vague: 'controls behavior' without evidence"),
    (r"(?i)\bsimilar\s+to\s+[A-Z]-\d", "Cross-references another test ID"),

    # Missing execution evidence keywords
    # A valid ✅ note should contain at least one of: exit=, stdout, AppTest:, output, returned, =
]

# A valid PASS note MUST contain at least one of these evidence markers
EVIDENCE_MARKERS = [
    r"exit[_=]",
    r"stdout",
    r"AppTest:",
    r"output",
    r"returned",
    r"score[=s]",
    r"\d+\s*(chunks|results|items|ms|chars|files)",
    r"exit_code",
    r"PASS",
    r"FAIL",
    r"VERDICT",
    r"source_path",
    r"source_file",
]


def validate():
    content = PROGRESS_FILE.read_text(encoding="utf-8")
    lines = content.splitlines()

    issues = []
    total_pass = 0

    for lineno, line in enumerate(lines, 1):
        # Match ✅ rows: | ✅ | ID | Title | Note |
        m = re.match(r"\|\s*✅\s*\|\s*(\S+)\s*\|[^|]*\|\s*(.*?)\s*\|$", line)
        if not m:
            continue

        test_id = m.group(1)
        note = m.group(2).strip()
        total_pass += 1

        # Check for inference patterns
        for pattern, reason in INFERENCE_PATTERNS:
            if re.search(pattern, note):
                issues.append((test_id, lineno, reason, note[:80]))

        # Check for evidence markers (at least one required)
        has_evidence = any(re.search(p, note, re.IGNORECASE) for p in EVIDENCE_MARKERS)
        if not has_evidence and note:
            issues.append((test_id, lineno, "No execution evidence (missing exit=, stdout, score, etc.)", note[:80]))

    # Print report
    print("QA Note Validation Report")
    print(f"   Total PASS entries: {total_pass}")
    print(f"   Flagged entries:    {len(issues)}")
    print()

    if issues:
        print("FLAGGED ENTRIES (likely inferred, not executed):")
        print("-" * 70)
        for test_id, lineno, reason, note_preview in issues:
            print(f"  [{test_id}] Line {lineno}")
            print(f"    Reason: {reason}")
            print(f"    Note:   {note_preview}...")
            print()
        print(f"FAIL: {len(issues)} notes need re-execution or re-writing with actual evidence.")
    else:
        print("PASS: All notes contain execution evidence. No inference detected.")

    return len(issues) == 0


if __name__ == "__main__":
    ok = validate()
    sys.exit(0 if ok else 1)
