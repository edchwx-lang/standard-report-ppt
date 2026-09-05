from __future__ import annotations

import hashlib
from pathlib import Path


_TEXT_SUFFIXES = frozenset({".json", ".lock", ".md", ".py", ".txt"})


def frozen_sha256(path: str | Path) -> str:
    """Hash repository text independently of checkout line-ending policy."""

    source = Path(path)
    payload = source.read_bytes()
    if source.suffix.lower() in _TEXT_SUFFIXES:
        payload = payload.replace(b"\r\n", b"\n")
    return hashlib.sha256(payload).hexdigest()
