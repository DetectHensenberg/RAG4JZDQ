"""Integration tests for MCP server stdio entrypoint."""

from __future__ import annotations

import json
import subprocess
import sys
import time
from typing import Any, Dict, List, Optional

import pytest


def send_and_receive(
    proc: subprocess.Popen,
    requests: List[Dict[str, Any]],
    timeout: float = 5.0,
    expected_responses: int = 0,
) -> List[str]:
    """Send requests to proc stdin and collect stdout lines.

    Args:
        proc: Subprocess with stdin/stdout pipes.
        requests: List of JSON-RPC requests/notifications to send.
        timeout: Max time to wait for responses.
        expected_responses: Number of responses to wait for (0 = wait until timeout/EOF).

    Returns:
        List of lines read from stdout.
    """
    assert proc.stdin is not None
    assert proc.stdout is not None

    # Send all requests
    for req in requests:
        proc.stdin.write(json.dumps(req) + "\n")
        proc.stdin.flush()

    # Read stdout with timeout
    lines = []
    start = time.time()
    response_count = 0
    
    # Count expected responses (requests with 'id' field, excluding notifications)
    if expected_responses == 0:
        expected_responses = sum(1 for req in requests if 'id' in req)
    
    while time.time() - start < timeout:
        # Check if we got enough responses
        if expected_responses > 0 and response_count >= expected_responses:
            break
            
        line = proc.stdout.readline()
        if not line:
            # Give a bit more time for slow responses
            time.sleep(0.1)
            continue
        stripped = line.strip()
        if stripped:
            lines.append(stripped)
            # Count JSON-RPC responses (have 'id' and 'result' or 'error')
            try:
                data = json.loads(stripped)
                if 'id' in data and ('result' in data or 'error' in data):
                    response_count += 1
            except json.JSONDecodeError:
                pass

    return lines


def find_response(lines: List[str], request_id: int) -> Optional[Dict[str, Any]]:
    """Find JSON-RPC response with given id in lines."""
    for line in lines:
        if not line.startswith('{"jsonrpc"'):
            continue
        try:
            data = json.loads(line)
            if data.get("id") == request_id:
                return data
        except json.JSONDecodeError:
            continue
    return None


@pytest.mark.integration
def test_mcp_server_initialize_stdio() -> None:
    """Ensure initialize works and stdout is clean JSON-RPC output."""

    proc = subprocess.Popen(
        [sys.executable, "-m", "src.mcp_server.server"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-06-18",
            "clientInfo": {"name": "pytest", "version": "0.0.0"},
            "capabilities": {},
        },
    }

    try:
        lines = send_and_receive(proc, [request], timeout=5.0)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()

    assert len(lines) > 0, "No stdout lines received."

    response = find_response(lines, 1)
    assert response is not None, f"No initialize response found in: {lines}"

    assert response["jsonrpc"] == "2.0"
    assert response["id"] == 1
    assert "result" in response
    assert "serverInfo" in response["result"]
    assert "capabilities" in response["result"]


@pytest.mark.integration
def test_mcp_server_tools_list_stdio() -> None:
    """Ensure tools/list works and returns empty tools array."""

    proc = subprocess.Popen(
        [sys.executable, "-m", "src.mcp_server.server"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    requests = [
        # Initialize request
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "clientInfo": {"name": "pytest", "version": "0.0.0"},
                "capabilities": {},
            },
        },
        # Initialized notification (required by MCP protocol)
        {
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
        },
        # Tools list request
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/list",
            "params": {},
        },
    ]

    try:
        lines = send_and_receive(proc, requests, timeout=10.0)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()

    assert len(lines) > 0, "No stdout lines received."

    # Verify initialize response
    init_response = find_response(lines, 1)
    assert init_response is not None, f"No initialize response found in: {lines}"
    assert "result" in init_response

    # Verify tools/list response
    tools_response = find_response(lines, 2)
    assert tools_response is not None, f"No tools/list response found in: {lines}"

    assert tools_response["jsonrpc"] == "2.0"
    assert tools_response["id"] == 2
    assert "result" in tools_response
    assert "tools" in tools_response["result"]
    # Should have at least query_knowledge_hub and list_collections tools registered
    assert isinstance(tools_response["result"]["tools"], list)
    assert len(tools_response["result"]["tools"]) >= 2
    
    # Verify registered tools are present
    tool_names = [t["name"] for t in tools_response["result"]["tools"]]
    assert "query_knowledge_hub" in tool_names
    assert "list_collections" in tool_names


# =============================================================================
# Multimodal Response Tests (E6)
# =============================================================================


@pytest.mark.integration
@pytest.mark.image
def test_multimodal_assembler_image_content_structure() -> None:
    """Test that MultimodalAssembler produces correct MCP ImageContent structure.
    
    Verifies:
    - ImageContent blocks have type="image"
    - mimeType is correctly set (e.g., "image/png")
    - data field contains valid base64 string
    """
    import base64
    import tempfile
    from pathlib import Path
    
    from mcp import types
    
    from src.core.response.multimodal_assembler import MultimodalAssembler
    from src.core.types import RetrievalResult
    
    # Create test image (minimal valid PNG)
    png_data = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
    
    with tempfile.TemporaryDirectory() as tmpdir:
        img_path = Path(tmpdir) / "test_img.png"
        img_path.write_bytes(png_data)
        
        assembler = MultimodalAssembler()
        
        result = RetrievalResult(
            chunk_id="test_chunk",
            score=0.95,
            text="Content with [IMAGE: test_img]",
            metadata={
                "source_path": "test.pdf",
                "images": [{"id": "test_img", "path": str(img_path)}],
            },
        )
        
        blocks = assembler.assemble_for_result(result)
        
        # Find ImageContent blocks
        image_blocks = [b for b in blocks if isinstance(b, types.ImageContent)]
        assert len(image_blocks) >= 1, "Should produce at least one ImageContent block"
        
        img_block = image_blocks[0]
        assert img_block.type == "image", "ImageContent type should be 'image'"
        assert img_block.mimeType == "image/png", "MIME type should be 'image/png'"
        assert img_block.data, "data should not be empty"
        
        # Verify base64 is valid
        decoded = base64.b64decode(img_block.data)
        assert decoded.startswith(b"\x89PNG"), "Decoded data should be valid PNG"


@pytest.mark.integration
@pytest.mark.image
def test_response_builder_multimodal_integration() -> None:
    """Test that ResponseBuilder correctly integrates multimodal content.
    
    Verifies:
    - ResponseBuilder produces MCPToolResponse with image_contents
    - to_mcp_content() returns ImageContent blocks when images present
    - metadata includes has_images and image_count
    """
    import tempfile
    from pathlib import Path
    
    from mcp import types
    
    from src.core.response.multimodal_assembler import MultimodalAssembler
    from src.core.response.response_builder import ResponseBuilder
    from src.core.types import RetrievalResult
    
    # Create test image
    png_data = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
    
    with tempfile.TemporaryDirectory() as tmpdir:
        img_path = Path(tmpdir) / "builder_test_img.png"
        img_path.write_bytes(png_data)
        
        assembler = MultimodalAssembler()
        builder = ResponseBuilder(
            multimodal_assembler=assembler,
            enable_multimodal=True,
        )
        
        results = [
            RetrievalResult(
                chunk_id="chunk_001",
                score=0.92,
                text="Result with image content",
                metadata={
                    "source_path": "docs/guide.pdf",
                    "images": [{"id": "builder_test_img", "path": str(img_path)}],
                },
            ),
        ]
        
        response = builder.build(results, query="test query")
        
        # Check MCPToolResponse has images
        assert response.has_images, "Response should have images"
        assert len(response.image_contents) >= 1, "Should have at least one ImageContent"
        
        # Check metadata
        assert response.metadata.get("has_images") is True
        assert response.metadata.get("image_count", 0) >= 1
        
        # Check to_mcp_content() output
        mcp_blocks = response.to_mcp_content()
        image_blocks = [b for b in mcp_blocks if isinstance(b, types.ImageContent)]
        assert len(image_blocks) >= 1, "MCP content should include ImageContent blocks"


@pytest.mark.integration
@pytest.mark.image
def test_mcp_tool_response_image_content_format() -> None:
    """Test MCPToolResponse.to_mcp_content() returns correct format for images.
    
    Verifies the exact structure expected by MCP protocol:
    - ImageContent blocks have correct type, mimeType, data fields
    - Multiple content types (text + image) can coexist
    """
    from mcp import types
    
    from src.core.response.citation_generator import Citation
    from src.core.response.response_builder import MCPToolResponse
    
    # Create response with mock image content
    mock_image = types.ImageContent(
        type="image",
        data="iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==",
        mimeType="image/png",
    )
    
    response = MCPToolResponse(
        content="# Test Result\n\nContent with image reference.",
        citations=[
            Citation(
                index=1,
                chunk_id="chunk_001",
                source="test.pdf",
                page=1,
                score=0.95,
                text_snippet="Sample text snippet from the document...",
            )
        ],
        metadata={"query": "test", "result_count": 1},
        image_contents=[mock_image],
    )
    
    # Get MCP content blocks
    blocks = response.to_mcp_content()
    
    # Should have text blocks and image blocks
    text_blocks = [b for b in blocks if isinstance(b, types.TextContent)]
    image_blocks = [b for b in blocks if isinstance(b, types.ImageContent)]
    
    assert len(text_blocks) >= 1, "Should have at least one TextContent"
    assert len(image_blocks) == 1, "Should have exactly one ImageContent"
    
    # Verify image block structure
    img = image_blocks[0]
    assert img.type == "image"
    assert img.mimeType == "image/png"
    assert img.data.startswith("iVBORw0KGgo")  # Base64 PNG header


@pytest.mark.integration
@pytest.mark.image
def test_multimodal_mime_type_detection() -> None:
    """Test correct MIME type detection for different image formats.
    
    Verifies:
    - PNG files get image/png
    - JPEG files get image/jpeg
    - Detection works from both extension and magic bytes
    """
    import tempfile
    from pathlib import Path
    
    from src.core.response.multimodal_assembler import MultimodalAssembler
    
    assembler = MultimodalAssembler()
    
    test_cases = [
        # (filename, data_bytes, expected_mime)
        ("test.png", b"\x89PNG\r\n\x1a\n" + b"\x00" * 50, "image/png"),
        ("test.jpg", b"\xff\xd8\xff\xe0" + b"\x00" * 50, "image/jpeg"),
        ("test.gif", b"GIF89a" + b"\x00" * 50, "image/gif"),
    ]
    
    with tempfile.TemporaryDirectory() as tmpdir:
        for filename, data, expected_mime in test_cases:
            img_path = Path(tmpdir) / filename
            img_path.write_bytes(data)
            
            content = assembler.load_image(str(img_path))
            
            assert content is not None, f"Failed to load {filename}"
            assert content.mime_type == expected_mime, (
                f"MIME type mismatch for {filename}: "
                f"expected {expected_mime}, got {content.mime_type}"
            )