"""Atomic file writes for the publisher.

The hourly score workflow must never leave a half-written status.json behind
(a reader mid-publish would render a broken page), so every publish goes
through a temp file in the same directory followed by os.replace, which is
atomic on POSIX and Windows.
"""

from __future__ import annotations

import contextlib
import json
import os
import tempfile
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any


def atomic_write_text(path: Path, text: str) -> None:
    """Write text to path atomically via temp file + os.replace."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


def append_jsonl_atomic(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    """Append JSONL rows atomically (read + rewrite via temp file + replace).

    Plain appends can interleave with a concurrent reader; the history file is
    small (one row per spot per run), so rewrite is cheap and always consistent.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    lines = [json.dumps(r) for r in rows]
    suffix = "" if not existing or existing.endswith("\n") else "\n"
    atomic_write_text(path, existing + suffix + "".join(line + "\n" for line in lines))
