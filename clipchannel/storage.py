"""Versioned, UTF-8 CSV storage in a user selected data folder.

Times are integer milliseconds on the source video timeline. Every CSV has a
``schema_version`` column so a future reader can reject unknown layouts.
"""

import csv
import hashlib
import os
import re
import shutil
import tempfile
from pathlib import Path


class StorageError(ValueError):
    """A folder or CSV cannot be used without risking existing data."""


class FolderBusy(StorageError):
    """A running operation or unsaved input prevents switching folders."""


class VideoNameConflict(StorageError):
    """A different video already owns the result-saving name."""


ROOT_DIRS = ("catalog", "media", "people", "projects", "exports", "archives", "work", "recovery", "logs")
SCHEMAS = {
    "result-references": ("schema_version", "kind", "key"),
    "list-state": ("schema_version", "kind", "key", "state"),
    "transcripts": ("schema_version", "start_ms", "end_ms", "text", "speaker_id"),
    "segments": ("schema_version", "start_ms", "end_ms", "kind", "selected"),
    "word-counts": ("schema_version", "word", "occurrences", "utterances", "start_ms", "end_ms", "text", "transcript_version", "include_verbs", "include_adjectives"),
    "people": ("schema_version", "person_id", "name", "reference_audio", "feature_file"),
    "targets": ("schema_version", "video_name", "person_id"),
    "registered-words": ("schema_version", "word"),
    "excluded-words": ("schema_version", "word"),
}
RESULT_KINDS = ("transcripts", "segments", "word-counts")
VIDEO_EXTENSIONS = {".mp4", ".mkv", ".mov", ".avi", ".webm", ".m4v", ".ts", ".mts", ".m2ts"}
SHARED_KINDS = ("people", "targets", "registered-words", "excluded-words")
SAFE_NAME = re.compile(r"^[^<>:\"/\\|?*\x00-\x1f.][^<>:\"/\\|?*\x00-\x1f]*$")


def _name(value):
    if not value or value in (".", "..") or value.endswith((" ", ".")) or not SAFE_NAME.fullmatch(value):
        raise StorageError(f"利用できない名前です: {value!r}")
    return value


def result_relative_path(source_name, kind, version):
    """One naming rule for saved results and references to a particular version."""
    if kind not in RESULT_KINDS or not isinstance(version, int) or version < 1:
        raise StorageError("結果の種類または版が不正です")
    stem = _name(Path(source_name).stem)
    return f"catalog/{stem}/{kind}/{stem}_v{version}.csv"


def _check_stop(stop):
    if stop and stop():
        raise StorageError("通常中止しました")


def _publish_new(staged, destination):
    """Publish a complete file without replacing an existing result."""
    if os.name == "nt":
        # Windows rename is atomic and refuses an existing destination.
        os.rename(staged, destination)
    else:
        os.link(staged, destination)
        staged.unlink()


def _same_file_contents(left, right, stop_requested=None):
    _check_stop(stop_requested)
    if left.samefile(right):
        return True
    if left.stat().st_size != right.stat().st_size:
        return False

    def digest(path):
        checksum = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                _check_stop(stop_requested)
                checksum.update(chunk)
        return checksum.digest()
    return digest(left) == digest(right)


def _write_csv(path, kind, rows, *, stop_requested=None):
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
                _check_stop(stop_requested)
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
        _check_stop(stop_requested)
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
        self.log_cleanup_error = ''

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
        from .operation_logs import cleanup_logs
        self.log_cleanup_error = ""
        try:
            cleanup_logs(self)
        except (OSError, StorageError) as error:
            self.log_cleanup_error = str(error)
        return self.list_saved()

    def _root(self):
        if self.path is None:
            raise StorageError("データ用フォルダを選んでください")
        return self.path

    def list_saved(self, *, include_hidden=False):
        root = self._root()
        results = [path.relative_to(root).as_posix() for path in root.glob("catalog/*/*/*_v*.csv")
                   if re.fullmatch(re.escape(path.parent.parent.name) + r"_v[1-9][0-9]*\.csv", path.name)]
        shared = [path.relative_to(root).as_posix() for kind in SHARED_KINDS
                  if (path := root / "people" / f"{kind}.csv").is_file()]
        if not include_hidden:
            from .registrations import RegistrationManager
            manager = RegistrationManager(self)
            results = [relative for relative in results if not manager.is_hidden("results", relative)]
        return sorted(results + shared)

    def list_videos(self, *, include_hidden=False):
        from .registrations import RegistrationManager
        manager = RegistrationManager(self)
        return sorted((path for path in (self._root() / "media" / "originals").glob("*")
                       if path.is_file() and path.suffix.lower() in VIDEO_EXTENSIONS
                       and (include_hidden or not manager.is_hidden("videos", path.relative_to(self._root()).as_posix()))),
                      key=lambda path: path.name)

    def register_video(self, source, *, stop_requested=None):
        _check_stop(stop_requested)
        source = Path(source).expanduser().resolve()
        if not source.is_file():
            raise StorageError("動画ファイルを選んでください")
        if source.suffix.lower() not in VIDEO_EXTENSIONS:
            raise StorageError("対応する動画ファイルを選んでください")
        stem = _name(source.stem)
        _name(source.name)
        originals = self._root() / "media" / "originals"
        originals.mkdir(parents=True, exist_ok=True)
        existing = [path for path in originals.iterdir() if path.is_file() and path.stem.casefold() == stem.casefold()]
        if existing:
            registered = existing[0]
            if _same_file_contents(source, registered, stop_requested):
                from .registrations import RegistrationManager
                RegistrationManager(self).restore_deleted("videos", registered.relative_to(self._root()).as_posix())
                return registered
            raise VideoNameConflict("同じ保存名の別動画があります。元動画の名前を変更してください")
        if any(path.name.casefold() == stem.casefold() for path in (self._root() / "catalog").iterdir()):
            raise VideoNameConflict("同じ結果保存名が既にあります。元動画の名前を変更してください")
        target = originals / source.name
        with tempfile.TemporaryDirectory(dir=self._root() / "work", prefix="register-") as temporary:
            staged = Path(temporary) / source.name
            with staged.open("xb") as output, source.open("rb") as input_file:
                for chunk in iter(lambda: input_file.read(1024 * 1024), b""):
                    _check_stop(stop_requested)
                    output.write(chunk)
                output.flush()
                os.fsync(output.fileno())
            if not _same_file_contents(source, staged, stop_requested):
                raise StorageError("コピー中に動画の内容が変わりました。登録をやり直してください")
            _check_stop(stop_requested)
            _publish_new(staged, target)
        from .registrations import RegistrationManager
        RegistrationManager(self).restore_deleted("videos", target.relative_to(self._root()).as_posix())
        return target

    def save_result(self, source_name, kind, rows, *, stop_requested=None, references=(), source_version=None):
        if kind not in RESULT_KINDS:
            raise StorageError("不明な結果の種類です")
        _check_stop(stop_requested)
        rows = list(rows)
        source = self.register_video(source_name, stop_requested=stop_requested)
        from .registrations import snapshot_references
        references = snapshot_references(self, source, kind, rows, references, source_version)
        stem = _name(source.stem)
        _name(source.name)
        identity = self._root() / "catalog" / stem / "source.sha256"
        digest = hashlib.sha256()
        with source.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                _check_stop(stop_requested)
                digest.update(chunk)
        fingerprint = f"{source.name}\n{digest.hexdigest()}\n"
        if identity.exists() and identity.read_text(encoding="utf-8") != fingerprint:
            raise VideoNameConflict("同じ保存名の別動画があります。元動画の名前を変更してください")
        if not identity.exists() and any((self._root() / "catalog" / stem).glob("*/*_v*.csv")):
            raise VideoNameConflict("元動画を識別できない既存結果があります。保存を中止しました")
        directory = self._root() / "catalog" / stem / kind
        directory.mkdir(parents=True, exist_ok=True)
        if not identity.exists():
            with tempfile.TemporaryDirectory(dir=self._root() / "work", prefix="identity-") as temporary:
                staged_identity = Path(temporary) / "source.sha256"
                with staged_identity.open("w", encoding="utf-8") as identity_stream:
                    identity_stream.write(fingerprint)
                    identity_stream.flush()
                    os.fsync(identity_stream.fileno())
                _check_stop(stop_requested)
                _publish_new(staged_identity, identity)
        versions = [int(match.group(1)) for path in directory.glob(f"{stem}_v*.csv")
                    if (match := re.fullmatch(re.escape(stem) + r"_v([1-9][0-9]*)(?:\.refs)?\.csv", path.name))]
        version = max(versions, default=0) + 1
        target = self._root() / result_relative_path(source.name, kind, version)
        with tempfile.TemporaryDirectory(dir=self._root() / "work", prefix="save-") as temporary:
            staged = Path(temporary) / target.name
            _write_csv(staged, kind, rows, stop_requested=stop_requested)
            _check_stop(stop_requested)
            staged_references = Path(temporary) / "references.csv"
            _write_csv(staged_references, "result-references", references, stop_requested=stop_requested)
            reference_path = target.with_suffix(".refs.csv")
            _publish_new(staged_references, reference_path)
            try:
                _check_stop(stop_requested)
                _publish_new(staged, target)
            except BaseException:
                reference_path.unlink(missing_ok=True)
                raise
        return target

    def load_result(self, source_name, kind, version):
        return _read_csv(self._root() / result_relative_path(source_name, kind, version), kind)

    def save_shared(self, kind, rows):
        if kind not in SHARED_KINDS:
            raise StorageError("不明な共通設定です")
        rows = list(rows)
        from .registrations import RegistrationManager, SHARED_KEYS
        if kind in SHARED_KEYS:
            column = SHARED_KEYS[kind]
            previous = {row[column] for row in self.load_shared(kind)}
            current = {row[column] for row in rows}
            manager = RegistrationManager(self)
            for key in previous - current:
                manager.ensure_deletable(kind, key)
        target = self._root() / "people" / f"{kind}.csv"
        _write_csv(target, kind, rows)
        return target

    def load_shared(self, kind):
        if kind not in SHARED_KINDS:
            raise StorageError("不明な共通設定です")
        target = self._root() / "people" / f"{kind}.csv"
        return _read_csv(target, kind) if target.exists() else []
