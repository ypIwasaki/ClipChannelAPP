"""Small operation summaries and conservative retention in the data folder."""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from .storage import DataFolder, StorageError


def record_operation(data: DataFolder, label: str, state: str, elapsed: float) -> Path:
    """Record fixed operation metadata; callers never pass errors or arguments."""
    if data.path is None:
        raise StorageError("データ用フォルダを選んでください")
    now = datetime.now(timezone.utc)
    directory = data.path / "logs"
    if directory.is_symlink() or directory.resolve() != directory:
        raise StorageError("データ用フォルダ外へのログ保存はできません")
    directory.mkdir(exist_ok=True)
    destination = directory / f"operation-{now:%Y%m%dT%H%M%S%fZ}-{uuid4().hex}.log"
    summary = {"time": now.isoformat(), "label": label, "state": state, "elapsed": elapsed}
    with destination.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(summary, ensure_ascii=False) + "\n")
    return destination


def cleanup_logs(data: DataFolder, *, now: datetime | None = None) -> list[Path]:
    """Keep all logs if recovery information cannot be associated with a log.

    This application has no recovery index. Any entry in recovery/ therefore
    protects every log, and no recovery files are changed here. Only regular
    .log files directly in logs/ are candidates; symlinks are never followed.
    """
    if data.path is None:
        raise StorageError("データ用フォルダを選んでください")
    directory = data.path / "logs"
    recovery = data.path / "recovery"
    if directory.is_symlink() or directory.resolve() != directory:
        return []
    if recovery.is_symlink() or (recovery.exists() and any(recovery.iterdir())):
        return []
    current = now if now is not None else datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    cutoff = (current.astimezone(timezone.utc) - timedelta(days=30)).timestamp()
    removed = []
    for path in sorted(directory.glob("*.log")):
        if path.is_symlink() or not path.is_file() or path.resolve().parent != directory:
            continue
        if path.stat().st_mtime <= cutoff:
            path.unlink()
            removed.append(path)
    return removed
