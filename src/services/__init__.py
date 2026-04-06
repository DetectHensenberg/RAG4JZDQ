"""Services layer — reusable business logic extracted from routers.

This package contains service classes that encapsulate domain logic,
making it independently testable and reusable across different
entry points (API, CLI, MCP).
"""

__all__ = ["ChatService", "CacheService", "cache_service", "chat_service"]
