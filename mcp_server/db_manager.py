from __future__ import annotations

import sys
from pathlib import Path

# Add repo root to path so backend.chroma_client is importable
_repo_root = Path(__file__).resolve().parent.parent
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

from backend.chroma_client import ChromaManager  # noqa: E402

# Re-export for convenience
__all__ = ["ChromaManager"]
