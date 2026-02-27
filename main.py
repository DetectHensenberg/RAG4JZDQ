"""
Modular RAG MCP Server - Main Entry Point

This is the entry point for the MCP Server. It initializes the configuration,
sets up logging, and starts the server.
"""

import sys
from pathlib import Path

from src.core.settings import SettingsError, load_settings
from src.observability.logger import get_logger


def main() -> int:
    """
    Main entry point for the MCP Server.
    
    Returns:
        int: Exit code (0 for success, non-zero for failure)
    """
    print("Modular RAG MCP Server - Starting...")

    settings_path = Path("config/settings.yaml")
    try:
        settings = load_settings(settings_path)
    except SettingsError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 1

    logger = get_logger(log_level=settings.observability.log_level)
    logger.info("Settings loaded successfully.")
    logger.info("MCP Server will be implemented in Phase E.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
