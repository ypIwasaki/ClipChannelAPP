"""Versioned, UTF-8 CSV storage in a user selected data folder.

Times are integer milliseconds on the source video timeline. Every CSV has a
``schema_version`` column so a future reader can reject unknown layouts.
"""

import csv
import os
import re
import tempfile
from pathlib import Path


class StorageError(ValueError):
    """A folder or CSV cannot be used without risking existing data."""


class FolderBusy(StorageError):
    """A running operation or unsaved input prevents switching folders."""


ROOT_DIRS = ("catalog", "media", "people", "projects", "exports", "archives", "work", "recovery", "logs")
SCHEMAS = {
    "transcripts": ("schema_version", "start_ms", "end_ms", "text", "speaker_id"),
    "segments": ("schema_version", "start_ms", "end_ms", "kind", "selected"),
    "word-counts": ("schema_version", "word", "occurrences", "utterances"),
    "people": ("schema_version", "person_id", "name", "reference_audio", "feature_file"),
    "registered-words": ("schema_version", "word"),
    "excluded-words": ("schema_version", "word"),
}
RESULT_KINDS = ("transcripts", "segments", "word-counts")
SHARED_KINDS = ("people", "registered-words", "excluded-words")
SAFE_NAME = re.compile(r"^[^<>:\"/\\|?*\x00-\x1f.][^<>:\"/\\|?*\x00-\x1f]*$")


def _name(value):
    if not value or value in (".", "..") or value.endswith((" ", ".")) or not SAFE_NAME.fullmatch(value):
        raise StorageError(f"利用できない名前です: {value!r}")
    return value


def _write_csv(path, kind, rows):
    columns = SCHEMAS[kind]
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="", dir=path.parent,
                                         prefix=f".{path.name}.", suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            writer = csv.DictWriter(stream, fieldnames=columns, lineterminator="\n", quoting=csv.QUOTE_MINIMAL)
            writer.writeheader()
            for row in rows:
                if set(row) != set(columns) - {"schema_version"}:
                    raise StorageError(f"{kind} の列が一致しません")
                if any(not isinstance(value, str) for value in row.values()):
                    raise StorageError("CSVの値は文字列で指定してください")
                if kind in ("transcripts", "segments"):
                    try:
                        start, end = int(row["start_ms"]), int(row["end_ms"])
                    except ValueError as error:
                        raise StorageError("時刻は整数ミリ秒で指定してください") from error
                    if start < 0 or end <= start:
                        raise StorageError("終了時刻は開始時刻より後にしてください")
                writer.writerow({"schema_version": "1", **row})
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _read_csv(path, kind):
    try:
        with path.open("r", encoding="utf-8", newline="") as stream:
            reader = csv.DictReader(stream, strict=True)
            if tuple(reader.fieldnames or ()) != SCHEMAS[kind]:
                raise StorageError(f"{path} の列または版が不明です")
            rows = list(reader)
    except (UnicodeError, csv.Error) as error:
        raise StorageError(f"{path} を読み取れません: {error}") from error
    if any(row.get("schema_version") != "1" or None in row for row in rows):
        raise StorageError(f"{path} の版または行が不正です")
    return [{key: value for key, value in row.items() if key != "schema_version"} for row in rows]


class DataFolder:
    def __init__(self):
        self.path = None
        self.running = False
        self.unsaved = False

    def select(self, path):
        if self.running or self.unsaved:
            reasons = []
            if self.running:
                reasons.append("処理中")
            if self.unsaved:
                reasons.append("未保存入力")
            raise FolderBusy("・".join(reasons) + "のためフォルダを切り替えられません")
        target = Path(path).expanduser().resolve()
        if not target.is_dir():
            raise StorageError("既存のデータ用フォルダを選んでください")
        if os.name == "nt":
            import ctypes
            if str(target).startswith("\\\\") or ctypes.windll.kernel32.GetDriveTypeW(str(target.anchor)) not in (2, 3):
                raise StorageError("直接接続されたドライブを選んでください")
        for name in ROOT_DIRS:
            (target / name).mkdir(exist_ok=True)
        (target / "media" / "edits").mkdir(exist_ok=True)
        self.path = target
        return self.list_saved()

    def _root(self):
        if self.path is None:
            raise StorageError("データ用フォルダを選んでください")
        return self.path

    def list_saved(self):
        root = self._root()
        return sorted(path.relative_to(root).as_posix() for path in root.glob("catalog/*/*/*_v*.csv")
                      if re.fullmatch(re.escape(path.parent.parent.name) + r"_v[1-9][0-9]*\.csv", path.name))

    def save_result(self, source_name, kind, rows):
        if kind not in RESULT_KINDS:
            raise StorageError("不明な結果の種類です")
        stem = _name(Path(source_name).stem)
        directory = self._root() / "catalog" / stem / kind
        directory.mkdir(parents=True, exist_ok=True)
        versions = [int(match.group(1)) for path in directory.glob(f"{stem}_v*.csv")
                    if (match := re.fullmatch(re.escape(stem) + r"_v([1-9][0-9]*)\.csv", path.name))]
        version = max(versions, default=0) + 1
        target = directory / f"{stem}_v{version}.csv"
        # Exclusive reservation prevents another writer from silently replacing this version.
        with target.open("x"):
            pass
        try:
            _write_csv(target, kind, rows)
        except Exception:
            target.unlink(missing_ok=True)
            raise
        return target

    def load_result(self, source_name, kind, version):
        if kind not in RESULT_KINDS or not isinstance(version, int) or version < 1:
            raise StorageError("結果の種類または版が不正です")
        stem = _name(Path(source_name).stem)
        return _read_csv(self._root() / "catalog" / stem / kind / f"{stem}_v{version}.csv", kind)

    def save_shared(self, kind, rows):
        if kind not in SHARED_KINDS:
            raise StorageError("不明な共通設定です")
        target = self._root() / "people" / f"{kind}.csv"
        _write_csv(target, kind, rows)
        return target

    def load_shared(self, kind):
        if kind not in SHARED_KINDS:
            raise StorageError("不明な共通設定です")
        target = self._root() / "people" / f"{kind}.csv"
        return _read_csv(target, kind) if target.exists() else []
