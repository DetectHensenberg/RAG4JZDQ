"""Pydantic models for API request/response."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class ApiResponse(BaseModel):
    """Standard API response wrapper."""
    ok: bool = True
    message: str = ""
    data: Any = None


class ErrorResponse(BaseModel):
    """Error response."""
    ok: bool = False
    message: str


class ChatRequest(BaseModel):
    """Chat/QA request."""
    question: str
    collection: str = "default"
    top_k: int = 5
    max_tokens: int = 4096
    uploaded_text: str = ""


class IngestRequest(BaseModel):
    """Knowledge base ingestion request."""
    folder_path: str
    collection: str = "default"
    file_types: List[str] = [".pdf", ".pptx", ".docx", ".md", ".txt"]


class ConfigUpdateRequest(BaseModel):
    """System config update request."""
    config: Dict[str, Any]


class ConfigTestRequest(BaseModel):
    """API key test request."""
    api_key: str
    base_url: str
    model: str


class ExportRequest(BaseModel):
    """Document export request."""
    content: str
    format: str = "markdown"
    filename: str = "document"


class EvalRequest(BaseModel):
    """Evaluation run request."""
    queries: List[str]
    collection: str = "default"
    metrics: List[str] = ["hit_rate", "mrr"]


class DocumentDeleteRequest(BaseModel):
    """Document delete request."""
    source_path: str
    collection: str = "default"
    source_hash: Optional[str] = None
