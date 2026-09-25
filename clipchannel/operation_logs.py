"""Small operation summaries and conservative retention in the data folder."""

import json
import re
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


def _finished_export_logs(root: Path) -> list[Path]:
    """Match only this app's export logs and keep uncertain/active requests."""
    projects = root / "projects"
    if projects.is_symlink() or projects.resolve() != projects or not projects.is_dir():
        return []
    logs = []
    for directory in sorted(projects.iterdir()):
        if directory.is_symlink() or directory.resolve() != directory or not directory.is_dir():
            continue
        for path in sorted(directory.glob("control-*.log")):
            if not re.fullmatch(r"control-[0-9a-f]{32}\.log", path.name):
                continue
            sidecars = [path.with_suffix(suffix) for suffix in
                        (".cccontrol", ".json", ".cancel", ".force", ".f32le")]
            if any(sidecar.is_symlink() or sidecar.resolve() != sidecar for sidecar in sidecars):
                continue
            response = path.with_suffix(".json")
            if response.exists():
                try:
                    status = json.loads(response.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    continue
                if not isinstance(status, dict) or status.get("state") not in ("completed", "cancelled", "failed"):
                    continue
            elif any(sidecar.exists() for sidecar in sidecars):
                continue
            # The plugin creates the log only after a .cccontrol request exists.
            # export_video removes request/response/stop sidecars only after
            # confirmed termination; normal completion leaves the .log alone.
            # Any surviving request or temporary audio without a terminal
            # response is uncertain and was excluded above.
            logs.append(path)
    return logs

def cleanup_logs(data: DataFolder, *, now: datetime | None = None) -> list[Path]:
    """Keep all logs if recovery information cannot be associated with a log.

    This application has no recovery index. Any entry in recovery/ therefore
    protects every log, and no recovery files are changed here. Only regular
    .log files directly in logs/ and stopped control-<UUID>.log exports under
    projects/<edit>/ are candidates; symlinks are never followed.
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
    candidates = sorted(directory.glob("*.log")) + _finished_export_logs(data.path)
    for path in candidates:
        if path.is_symlink() or not path.is_file() or path.resolve() != path:
            continue
        if path.stat().st_mtime <= cutoff:
            path.unlink()
            removed.append(path)
    return removed
