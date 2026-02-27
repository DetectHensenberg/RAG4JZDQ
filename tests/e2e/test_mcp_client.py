"""E2E tests simulating an MCP client against the real server over stdio.

Launches ``src.mcp_server.server`` as a subprocess and drives the full
JSON-RPC / MCP lifecycle:

    initialize → notifications/initialized → tools/list → tools/call

Each test validates the **wire-level** JSON-RPC contract so that any
breaking change in the server, protocol handler, or registered tools
is caught by CI.

Usage::

    pytest tests/e2e/test_mcp_client.py -v
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

PROJECT_ROOT = Path(__file__).parent.parent.parent

# ── Helpers ───────────────────────────────────────────────────────────


def _start_server() -> subprocess.Popen:
    """Start the MCP server subprocess with stdio transport.

    Returns:
        Running subprocess with stdin/stdout/stderr pipes.
    """
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    return subprocess.Popen(
        [sys.executable, "-m", "src.mcp_server.server"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(PROJECT_ROOT),
        env=env,
    )


def _send_jsonrpc(
    proc: subprocess.Popen,
    messages: List[Dict[str, Any]],
    expected_responses: int,
    timeout: float = 15.0,
) -> List[Dict[str, Any]]:
    """Send JSON-RPC messages and collect the expected number of responses.

    Uses a background thread to read stdout so that the ``timeout`` is
    always respected even when ``readline()`` blocks.

    Args:
        proc: Subprocess with stdin/stdout pipes.
        messages: List of JSON-RPC requests / notifications.
        expected_responses: How many JSON-RPC *responses* (with ``id``) to wait for.
        timeout: Max seconds to wait.

    Returns:
        Parsed JSON-RPC response dicts (only entries with ``id``).
    """
    assert proc.stdin is not None
    assert proc.stdout is not None

    for msg in messages:
        proc.stdin.write(json.dumps(msg) + "\n")
        proc.stdin.flush()

    responses: List[Dict[str, Any]] = []
    stop_event = threading.Event()

    def _reader() -> None:
        """Read stdout lines in a daemon thread so timeout can interrupt."""
        while not stop_event.is_set():
            line = proc.stdout.readline()  # type: ignore[union-attr]
            if not line:
                break
            stripped = line.strip()
            if not stripped:
                continue
            try:
                data = json.loads(stripped)
            except json.JSONDecodeError:
                continue
            if "id" in data and ("result" in data or "error" in data):
                responses.append(data)

    reader_thread = threading.Thread(target=_reader, daemon=True)
    reader_thread.start()

    # Wait until we have enough responses *or* timeout expires
    deadline = time.time() + timeout
    while len(responses) < expected_responses and time.time() < deadline:
        time.sleep(0.1)

    stop_event.set()
    return responses


def _find(responses: List[Dict[str, Any]], req_id: int) -> Optional[Dict[str, Any]]:
    """Find a response by request id."""
    for r in responses:
        if r.get("id") == req_id:
            return r
    return None


def _terminate(proc: subprocess.Popen) -> None:
    """Terminate the server subprocess gracefully."""
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()


# ── Fixtures ──────────────────────────────────────────────────────────

INIT_REQUEST: Dict[str, Any] = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-06-18",
        "clientInfo": {"name": "e2e-pytest-client", "version": "1.0.0"},
        "capabilities": {},
    },
}

INITIALIZED_NOTIFICATION: Dict[str, Any] = {
    "jsonrpc": "2.0",
    "method": "notifications/initialized",
}


@pytest.fixture()
def mcp_server():
    """Yield a running MCP server subprocess; tear down after test."""
    proc = _start_server()
    yield proc
    _terminate(proc)


# ── Tests ─────────────────────────────────────────────────────────────


class TestMCPClientE2E:
    """E2E test suite simulating a complete MCP client session."""

    # ------------------------------------------------------------------
    # 1. Lifecycle: initialize → tools/list
    # ------------------------------------------------------------------

    @pytest.mark.e2e
    def test_initialize_and_tools_list(self, mcp_server: subprocess.Popen) -> None:
        """Server responds to initialize and tools/list with all 3 registered tools."""
        messages = [
            INIT_REQUEST,
            INITIALIZED_NOTIFICATION,
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/list",
                "params": {},
            },
        ]

        responses = _send_jsonrpc(mcp_server, messages, expected_responses=2)

        # -- initialize ------------------------------------------------
        init_resp = _find(responses, 1)
        assert init_resp is not None, f"Missing initialize response. Got: {responses}"
        assert "result" in init_resp
        assert "serverInfo" in init_resp["result"]
        assert "capabilities" in init_resp["result"]
        assert init_resp["result"]["capabilities"].get("tools") is not None

        # -- tools/list ------------------------------------------------
        tools_resp = _find(responses, 2)
        assert tools_resp is not None, f"Missing tools/list response. Got: {responses}"
        assert "result" in tools_resp
        tools = tools_resp["result"]["tools"]
        assert isinstance(tools, list)

        tool_names = {t["name"] for t in tools}
        assert "query_knowledge_hub" in tool_names
        assert "list_collections" in tool_names
        assert "get_document_summary" in tool_names

        # Each tool must declare a valid inputSchema
        for tool in tools:
            assert "name" in tool
            assert "description" in tool
            assert "inputSchema" in tool
            schema = tool["inputSchema"]
            assert schema.get("type") == "object"
            assert "properties" in schema

    # ------------------------------------------------------------------
    # 2. tools/call – query_knowledge_hub (protocol round-trip)
    # ------------------------------------------------------------------

    @pytest.mark.e2e
    def test_tools_call_query_knowledge_hub(
        self, mcp_server: subprocess.Popen
    ) -> None:
        """tools/call for query_knowledge_hub returns well-formed CallToolResult.

        Even when there is no indexed data, the tool should return a valid
        (possibly empty) result or a graceful error — never a protocol-level
        failure.
        """
        messages = [
            INIT_REQUEST,
            INITIALIZED_NOTIFICATION,
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": "query_knowledge_hub",
                    "arguments": {
                        "query": "What is Azure OpenAI?",
                        "top_k": 3,
                    },
                },
            },
        ]

        responses = _send_jsonrpc(mcp_server, messages, expected_responses=2, timeout=60.0)

        init_resp = _find(responses, 1)
        assert init_resp is not None, "Missing initialize response"

        call_resp = _find(responses, 2)
        assert call_resp is not None, f"Missing tools/call response. Got: {responses}"
        assert "result" in call_resp, f"Expected result in response: {call_resp}"

        result = call_resp["result"]
        # MCP CallToolResult must have a ``content`` list
        assert "content" in result
        assert isinstance(result["content"], list)
        assert len(result["content"]) >= 1

        # Each content block must have ``type`` and ``text`` (or ``data`` for images)
        for block in result["content"]:
            assert "type" in block
            assert block["type"] in ("text", "image", "resource")

        # If ``isError`` is present, it must be a boolean
        if "isError" in result:
            assert isinstance(result["isError"], bool)

    # ------------------------------------------------------------------
    # 3. tools/call – list_collections
    # ------------------------------------------------------------------

    @pytest.mark.e2e
    def test_tools_call_list_collections(
        self, mcp_server: subprocess.Popen
    ) -> None:
        """tools/call for list_collections returns a valid collection listing."""
        messages = [
            INIT_REQUEST,
            INITIALIZED_NOTIFICATION,
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": "list_collections",
                    "arguments": {"include_stats": True},
                },
            },
        ]

        responses = _send_jsonrpc(mcp_server, messages, expected_responses=2, timeout=15.0)

        call_resp = _find(responses, 2)
        assert call_resp is not None, f"Missing tools/call response. Got: {responses}"
        assert "result" in call_resp

        result = call_resp["result"]
        assert "content" in result
        assert isinstance(result["content"], list)
        assert len(result["content"]) >= 1

        # First content block should be text with collection info (or empty message)
        first = result["content"][0]
        assert first["type"] == "text"
        assert isinstance(first.get("text", ""), str)

    # ------------------------------------------------------------------
    # 4. tools/call – get_document_summary (non-existent doc → graceful)
    # ------------------------------------------------------------------

    @pytest.mark.e2e
    def test_tools_call_get_document_summary_missing(
        self, mcp_server: subprocess.Popen
    ) -> None:
        """get_document_summary with invalid doc_id returns a well-formed error."""
        messages = [
            INIT_REQUEST,
            INITIALIZED_NOTIFICATION,
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": "get_document_summary",
                    "arguments": {
                        "doc_id": "nonexistent_doc_id_12345",
                    },
                },
            },
        ]

        responses = _send_jsonrpc(mcp_server, messages, expected_responses=2, timeout=15.0)

        call_resp = _find(responses, 2)
        assert call_resp is not None, f"Missing tools/call response. Got: {responses}"
        assert "result" in call_resp

        result = call_resp["result"]
        assert "content" in result
        assert isinstance(result["content"], list)
        assert len(result["content"]) >= 1

        # Tool should signal an error through isError or error text
        first_text = result["content"][0].get("text", "")
        is_error = result.get("isError", False)
        # Either isError flag is set OR the text contains an error message
        assert is_error or "not found" in first_text.lower() or "error" in first_text.lower(), (
            f"Expected an error indication for missing doc. Got isError={is_error}, text={first_text!r}"
        )

    # ------------------------------------------------------------------
    # 5. tools/call – unknown tool returns error
    # ------------------------------------------------------------------

    @pytest.mark.e2e
    def test_tools_call_unknown_tool(
        self, mcp_server: subprocess.Popen
    ) -> None:
        """Calling a non-existent tool returns an error response, not a crash."""
        messages = [
            INIT_REQUEST,
            INITIALIZED_NOTIFICATION,
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": "nonexistent_tool",
                    "arguments": {},
                },
            },
        ]

        responses = _send_jsonrpc(mcp_server, messages, expected_responses=2, timeout=15.0)

        call_resp = _find(responses, 2)
        assert call_resp is not None, f"Missing tools/call response. Got: {responses}"
        assert "result" in call_resp

        result = call_resp["result"]
        assert "content" in result
        assert result.get("isError") is True or "error" in result["content"][0].get("text", "").lower()

    # ------------------------------------------------------------------
    # 6. Full session: list tools → call query → verify citations format
    # ------------------------------------------------------------------

    @pytest.mark.e2e
    def test_full_session_query_with_citations_format(
        self, mcp_server: subprocess.Popen
    ) -> None:
        """Complete client session: init → list → query, validating citations structure.

        The response text from query_knowledge_hub should either:
        - Contain citation markers (e.g. [1], [2]) when results exist, OR
        - Return a "no results" message when no data is indexed.
        Either way the protocol contract must be satisfied.
        """
        messages = [
            INIT_REQUEST,
            INITIALIZED_NOTIFICATION,
            # Step 1: discover tools
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/list",
                "params": {},
            },
            # Step 2: call query_knowledge_hub
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": "query_knowledge_hub",
                    "arguments": {
                        "query": "RAG pipeline architecture",
                        "top_k": 5,
                    },
                },
            },
        ]

        responses = _send_jsonrpc(mcp_server, messages, expected_responses=3, timeout=60.0)

        # Validate tools/list
        tools_resp = _find(responses, 2)
        assert tools_resp is not None, "Missing tools/list response"
        tool_names = {t["name"] for t in tools_resp["result"]["tools"]}
        assert "query_knowledge_hub" in tool_names

        # Validate query response
        query_resp = _find(responses, 3)
        assert query_resp is not None, f"Missing query response. Got: {responses}"
        assert "result" in query_resp

        result = query_resp["result"]
        assert "content" in result
        assert isinstance(result["content"], list)
        assert len(result["content"]) >= 1

        # Collect all text content
        all_text = " ".join(
            block.get("text", "")
            for block in result["content"]
            if block.get("type") == "text"
        )
        assert len(all_text) > 0, "Response should contain non-empty text content"

        # The response should either have citation markers or indicate no results
        has_citations = "[1]" in all_text or "**Sources**" in all_text or "citation" in all_text.lower()
        has_no_results = (
            "no results" in all_text.lower()
            or "no relevant" in all_text.lower()
            or "no documents" in all_text.lower()
            or "not found" in all_text.lower()
            or "0 result" in all_text.lower()
            or result.get("isError") is True
        )
        assert has_citations or has_no_results, (
            f"Expected citations or 'no results' indication in response text: {all_text[:300]}"
        )

    # ------------------------------------------------------------------
    # 7. Multiple sequential calls in the same session
    # ------------------------------------------------------------------

    @pytest.mark.e2e
    def test_multiple_tool_calls_same_session(
        self, mcp_server: subprocess.Popen
    ) -> None:
        """Server handles multiple tools/call invocations in one session."""
        messages = [
            INIT_REQUEST,
            INITIALIZED_NOTIFICATION,
            # Call 1: list_collections
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": "list_collections",
                    "arguments": {"include_stats": False},
                },
            },
            # Call 2: query_knowledge_hub
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": "query_knowledge_hub",
                    "arguments": {"query": "test query", "top_k": 2},
                },
            },
            # Call 3: get_document_summary (expect graceful error)
            {
                "jsonrpc": "2.0",
                "id": 4,
                "method": "tools/call",
                "params": {
                    "name": "get_document_summary",
                    "arguments": {"doc_id": "does_not_exist"},
                },
            },
        ]

        responses = _send_jsonrpc(mcp_server, messages, expected_responses=4, timeout=60.0)

        # All four responses (init + 3 tool calls) should arrive
        for req_id in (1, 2, 3, 4):
            resp = _find(responses, req_id)
            assert resp is not None, f"Missing response for id={req_id}. Got: {responses}"
            assert "result" in resp, f"Response id={req_id} missing 'result': {resp}"

        # Each tool call result should have valid content
        for req_id in (2, 3, 4):
            resp = _find(responses, req_id)
            assert resp is not None
            content = resp["result"]["content"]
            assert isinstance(content, list)
            assert len(content) >= 1
            assert all("type" in block for block in content)
