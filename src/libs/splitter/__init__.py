"""
Splitter Module.

This package contains text splitter abstractions and implementations:
- Base splitter class
- Splitter factory
- Implementations (Recursive, Semantic, FixedLength)
"""

from src.libs.splitter.base_splitter import BaseSplitter
from src.libs.splitter.splitter_factory import SplitterFactory

# Import concrete implementations (they auto-register with factory)
try:
    from src.libs.splitter.recursive_splitter import RecursiveSplitter
except ImportError:
    RecursiveSplitter = None  # type: ignore[assignment, misc]

__all__ = [
    "BaseSplitter",
    "SplitterFactory",
    "RecursiveSplitter",
]
