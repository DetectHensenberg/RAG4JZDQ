---
name: qa-tester
description: "Fully autonomous QA testing agent for Modular RAG MCP Server. Reads test cases from QA_TEST_PLAN.md, executes ALL test types automatically without human intervention — CLI commands, Dashboard UI via Streamlit AppTest headless rendering, MCP protocol via subprocess JSON-RPC, provider switches, and data lifecycle checks. Diagnoses failures, applies fixes with up to 3 retry rounds, and records results in QA_TEST_PROGRESS.md. Use when user says 'run QA', 'QA test', 'QA 测试', '执行测试', '跑测试', 'test and fix', or wants to execute QA test plan."
---

# QA Tester

All test types (CLI / Dashboard UI / MCP protocol) are **fully automated** — zero human intervention.

Optional modifiers: append section letter (`run QA G`) or test ID (`run QA G-01`).

---

> ## ⛔ IRON RULES
>
> ### Rule 1: STRICTLY SERIAL
> Pick ONE test → Run ONE command → Wait for output → Record ONE row in `QA_TEST_PROGRESS.md` → THEN pick next.
> NEVER run two tests in one command. NEVER record two rows in one file edit. NEVER use parallel tool calls. NEVER plan the next test before recording the current one.
>
> ### Rule 2: PASS = TERMINAL OUTPUT EVIDENCE
> ✅ means you ran a command **in THIS session** and the Note contains **concrete values** copied from that output.
> No terminal output for THIS test → mark ⬜. NEVER ✅.
>
> ### Rule 3: ZERO CROSS-REFERENCING
> NEVER write "Verified via X-YZ", "Already verified in C-02", "Same as…", "Similar to…".
> Even if G-05 tests the same flag as C-02, run G-05 independently and paste its own output.
>
> ### Rule 4: ZERO INFERENCE
> **BANNED Note patterns** (caught by validator):
> "Code uses…" / "Dataclass validates…" / "auto-creates…" → Reading code ≠ testing.
> "Should work…" / "Would raise…" / "Expected behavior…" → Speculation ≠ testing.
> "Parameter accepted" / "Config controls behavior" → Vague. No output = no pass.
> If you didn't run a command and see output for THIS test, mark ⬜.
>
> ### Rule 5: ADVERSARIAL MINDSET
> Find bugs, not confirmations. 10+ passes with zero bugs → re-examine your rigor.
>
> ### Rule 6: SECTION-END VALIDATION
> After completing a section, run `python .github/skills/qa-tester/scripts/qa_validate_notes.py`.
> Re-execute any flagged test before moving to next section.

---

## Pipeline (strictly serial)

```
1. Pick ONE pending test (by ID order)
2. Set system state if needed
3. Run ONE command — WAIT for output
4. Verify ALL assertions from Expected Result vs ACTUAL output
5. Fix if needed (≤3 rounds)
6. ⛔ GATE: Edit QA_TEST_PROGRESS.md (row + counters) — ONE row per edit
7. Only NOW return to step 1
```

> Activate `.venv` before any `python` command: `.\.venv\Scripts\Activate.ps1`

---

## Step 1: Pick Target

1. Read `QA_TEST_PLAN.md` for test steps and expected results.
2. Read `QA_TEST_PROGRESS.md` for current status.
3. User-specified section/ID → scope to that. Otherwise → first ⬜ pending test.
4. If any 🔧 tests exist, re-test those first.
5. Execute in section order (A→O), within section in ID order.

### Test Categories

| Sections | Type | Execution Method |
|----------|------|-----------------|
| A–F | Dashboard UI | AppTest headless — see [references/test_patterns.md](references/test_patterns.md) |
| G, H, I | CLI | Terminal commands, check exit code + stdout |
| J | MCP Protocol | JSON-RPC subprocess — see [references/test_patterns.md](references/test_patterns.md) |
| K, L | Provider Switch | `qa_config.py apply <profile>` → run CLI/Dashboard |
| M | Config & Fault Tolerance | Modify settings → run CLI → verify error handling |
| N, O | Data Lifecycle | Use `qa_multistep.py <TEST_ID>` |

---

## Step 2: Set System State

```
Empty          → python .github/skills/qa-tester/scripts/qa_bootstrap.py clear
Baseline       → python .github/skills/qa-tester/scripts/qa_bootstrap.py baseline
DeepSeek       → python .github/skills/qa-tester/scripts/qa_config.py apply deepseek
Rerank_LLM     → python .github/skills/qa-tester/scripts/qa_config.py apply rerank_llm
NoVision       → python .github/skills/qa-tester/scripts/qa_config.py apply no_vision
InvalidKey     → python .github/skills/qa-tester/scripts/qa_config.py apply invalid_llm_key
InvalidEmbedKey→ python .github/skills/qa-tester/scripts/qa_config.py apply invalid_embed_key
Any            → no state change needed
```

After config-profile tests → `python .github/skills/qa-tester/scripts/qa_config.py restore`
Check state → `python .github/skills/qa-tester/scripts/qa_bootstrap.py status`

---

## Step 3: Execute & Verify

### CLI Tests (G, H, I, parts of K/L/M)

1. Read the test's **Steps** column from `QA_TEST_PLAN.md`.
2. Run the exact command in terminal.
3. Compare output against **Expected Result**:
   - **Ingest**: exit=0, output has stage names (load/split/transform/embed/upsert)
   - **Query**: exit=0, results have source_file and score
   - **Error**: exit≠0, stderr has descriptive error (not raw stack trace)
   - **Idempotency**: second run shows "skipped", no duplicates

### Dashboard Tests (A–F)

Read [references/test_patterns.md](references/test_patterns.md) for AppTest templates, interaction patterns, and file upload workarounds.

Key points:
- Write one inline Python script per test, render via `AppTest.from_function`
- Print specific element values (metric labels, selectbox options, expander labels)
- For file uploads: ingest via CLI first, verify via AppTest
- For data mutations: call `DataService` directly, verify via AppTest/CLI

#### ⚠️ AppTest `st.tabs()` Limitation — MUST READ before testing any tab content

AppTest renders **all tab contents simultaneously** into a flat element list. There is **no spatial isolation** between tabs — you cannot determine which element belongs to which tab from `at.info`, `at.metric`, `at.markdown` etc.

**Consequence:** If a test step says "click tab X → see content Y inside tab X", AppTest **cannot confirm the spatial relationship**. Even if content Y exists in the output, it may come from a different region (e.g., a diagnostics area above the tabs, or a different tab).

**Mandatory check for ALL tab-content tests:**

1. **First verify the tab label exists:** Print `[t.label for t in at.tabs]` (if `at.tabs` is available) OR check the page source for the tab label string. If the expected tab label is **absent** → mark ❌ immediately — the tab does not exist.
2. **Then verify the content element exists** in the AppTest output.
3. **Acknowledge the limitation in the Note:** Append `[AppTest: tab isolation unverifiable]` to the Note.

**Example — tab does NOT exist:**
```python
# For a test expecting "🟪 Rerank" tab with "skipped" message:
tab_labels = [el.value for el in at.markdown if '🟪' in el.value or 'Rerank' in el.value]
print('Rerank tab label found:', tab_labels)
# If empty → tab absent → mark ❌ with note "Rerank tab not rendered (stage absent)"
```

**BANNED pattern:** Finding a content element (e.g., "Rerank skipped" info) and concluding the tab test PASSED — the element may be from a diagnostics region, not from inside the tab.

### MCP Tests (J)

Read [references/test_patterns.md](references/test_patterns.md) for JSON-RPC script template and assertion matrix.

Primary method: `pytest tests/e2e/test_mcp_client.py -v` covers most J-* cases.

### Multi-Step Tests (N, O, M config, L-07)

Tests with 3+ sequential steps **MUST** use the runner script:

```
python .github/skills/qa-tester/scripts/qa_multistep.py <TEST_ID>
```

**Supported:** `N-01`, `N-03`, `N-04`, `N-05`, `N-06`, `O-07`, `M-03`, `M-04`, `M-05`, `M-06`, `M-10`, `M-11`, `L-07`

The script executes every sub-step, prints ACTUAL values at each step, outputs `VERDICT: PASS/FAIL`. Copy the VERDICT and key step values into the Note.

For tests NOT in the script, run commands from QA_TEST_PLAN.md manually and paste output.

---

## Step 4: Fix & Retry (≤3 rounds)

1. **Diagnose**: code bug / config issue / missing data / test plan error?
2. **Fix**: minimal change only. Record file/line in Note.
3. **Retry**: re-run same command.
4. After 3 failed rounds → mark ❌ with detailed notes.
5. If fix touches shared code → re-run previously-passed tests in same section.

---

## Step 5: Record Results

**⛔ GATE — do this BEFORE picking the next test.**

Edit `QA_TEST_PROGRESS.md`: update ONE test row + summary counters. ONE row per file edit.

### ✅ PASS Requirements

All must be true:
1. Ran the command **in this session**
2. Observed actual output **from that command**
3. Verified **every** assertion in Expected Result
4. Note contains **≥2 concrete values** from terminal output

### Note Format

```
<method>: <value_1>, <value_2>[, ...]
```

- **CLI**: `exit=0, stdout: 'Total chunks: 3', source_file=simple.pdf`
- **AppTest**: `at.metric[0].label='Total traces', at.metric[0].value=6`
- **Multi-step**: `Step1: exit=0, chunks=3. Step2: sources=[simple.pdf]. Step3: deleted=1. Step4: sources=[]`
- **Bad** (BANNED): `"Already verified in C-02"`, `"Code uses yaml.safe_load"`, `"Should work because..."`, `"Parameter accepted"`

### Status Icons

| Icon | Meaning |
|------|---------|
| ✅ | Pass — all assertions verified against actual output |
| ❌ | Fail — failed after 3 fix attempts |
| ⏭️ | Skip — missing third-party API key (K-series only) |
| 🔧 | Fix applied — needs re-test |
| ⬜ | Pending — not yet tested |

### Counters

Update in the same edit: `✅ Pass: X | ❌ Fail: Y | ⏭️ Skip: Z | 🔧 Fix: W | ⬜ Pending: P` (must sum to Total).

### Section-End Gate

After each completed section:
```
python .github/skills/qa-tester/scripts/qa_validate_notes.py
```
Re-execute any flagged test. Do NOT proceed until 0 flags.

---

## Key Paths

| File | Purpose |
|------|---------|
| `QA_TEST_PLAN.md` | Test steps and expected results |
| `QA_TEST_PROGRESS.md` | Execution status and notes |
| `config/settings.yaml` | System configuration |
| `scripts/ingest.py` / `query.py` / `evaluate.py` | CLI commands |
| `tests/e2e/test_mcp_client.py` | MCP E2E tests |
| `tests/e2e/test_dashboard_smoke.py` | Dashboard smoke tests |
| `tests/fixtures/sample_documents/` | Test PDFs |
| `tests/fixtures/golden_test_set.json` | Evaluation golden set |

## Test Documents

| File | Language | Pages | Images |
|------|----------|-------|--------|
| `simple.pdf` | EN | 1 | 0 |
| `with_images.pdf` | EN | 1 | 1 |
| `complex_technical_doc.pdf` | EN | ~8 | 3 |
| `chinese_technical_doc.pdf` | ZH | ~8 | 0 |
| `chinese_table_chart_doc.pdf` | ZH | ~6 | 3 |
| `chinese_long_doc.pdf` | ZH | 30+ | 0 |
| `blogger_intro.pdf` | ZH | ~4 | 2 |

All in `tests/fixtures/sample_documents/`.
