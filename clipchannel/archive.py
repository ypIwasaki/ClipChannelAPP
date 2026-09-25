"""Lossless video archives with verified, separate outputs."""

import hashlib
import json
import os
import re
import stat
import tempfile
import uuid
import zipfile
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .process_control import check_cancelled
from .storage import DataFolder, StorageError, VIDEO_EXTENSIONS, _name, _publish_new


@dataclass(frozen=True)
class ArchiveResult:
    archive: Path
    output: Path
    original_size: int
    archive_size: int
    sha256: str

    @property
    def reduced(self) -> bool:
        return self.archive_size < self.original_size

    @property
    def summary(self) -> str:
        sizes = f"元動画: {self.original_size:,} バイト / 保管物: {self.archive_size:,} バイト"
        result = (f"{self.original_size - self.archive_size:,} バイト削減しました"
                  if self.reduced else "容量は削減できなかった")
        return f"{sizes}\n{result}。元動画と保管物は保持します。"



def _copy_stream(source, output=None, *, stop_requested=None):
    digest = hashlib.sha256()
    size = 0
    for chunk in iter(lambda: source.read(1024 * 1024), b""):
        check_cancelled(stop_requested)
        digest.update(chunk)
        size += len(chunk)
        if output is not None:
            output.write(chunk)
    check_cancelled(stop_requested)
    return size, digest.hexdigest()


def _read_video(archive, output=None, *, stop_requested=None):
    try:
        entries = archive.infolist()
        if (len(entries) != 2 or len({entry.filename for entry in entries}) != 2
                or any(entry.is_dir() or stat.S_IFMT(entry.external_attr >> 16) not in (0, stat.S_IFREG)
                       for entry in entries)):
            raise StorageError("保管物のファイル構成が不正です")
        manifest = archive.getinfo("manifest.json")
        if manifest.file_size > 65536:
            raise StorageError("保管物の情報が大きすぎます")
        metadata = json.loads(archive.read(manifest).decode("utf-8"))
        if (not isinstance(metadata, dict) or type(metadata.get("schema_version")) is not int
                or metadata["schema_version"] != 1):
            raise StorageError("保管物の形式または版が不明です")
        if (not isinstance(metadata.get("name"), str) or type(metadata.get("size")) is not int
                or metadata["size"] < 0 or not isinstance(metadata.get("sha256"), str)
                or not re.fullmatch(r"[0-9a-f]{64}", metadata["sha256"])):
            raise StorageError("保管物の動画情報が不正です")
        name = _name(metadata["name"])
        reserved = {"CON", "PRN", "AUX", "NUL", *(f"COM{n}" for n in range(1, 10)),
                    *(f"LPT{n}" for n in range(1, 10))}
        if (Path(name).suffix.lower() not in VIDEO_EXTENSIONS
                or name.split(".", 1)[0].rstrip(" ").upper() in reserved):
            raise StorageError("保管物の動画名が不正です")
        video = archive.getinfo(name)
        if video.file_size != metadata["size"]:
            raise StorageError("保管物のサイズが一致しません")
        with archive.open(video) as source:
            size, digest = _copy_stream(source, output, stop_requested=stop_requested)
        if size != metadata["size"] or digest != metadata["sha256"]:
            raise StorageError("保管物のサイズまたはSHA256が一致しません")
        return name, size, digest
    except StorageError:
        raise
    except (KeyError, ValueError, UnicodeError, zipfile.BadZipFile, RuntimeError, NotImplementedError, zlib.error) as error:
        raise StorageError("保管物を読み取れません。形式または破損を確認してください") from error



def archive_video(data: DataFolder, source, *, stop_requested: Callable[[], bool] | None = None) -> ArchiveResult:
    """Keep the source and publish a verified ZIP64 archive as a new file."""
    check_cancelled(stop_requested)
    source = Path(source).expanduser().resolve()
    if not source.is_file() or source.suffix.lower() not in VIDEO_EXTENSIONS:
        raise StorageError("対応する動画ファイルを選んでください")
    _name(source.name)
    root = data._root()
    destination = root / "archives" / f"{source.stem[:48]}-{uuid.uuid4().hex}.zip"
    with tempfile.TemporaryDirectory(dir=root / "work", prefix="archive-") as temporary:
        staged = Path(temporary) / "video.zip"
        with zipfile.ZipFile(staged, "x", compression=zipfile.ZIP_DEFLATED, allowZip64=True) as archive:
            with source.open("rb") as original, archive.open(source.name, "w", force_zip64=True) as stored:
                size, digest = _copy_stream(original, stored, stop_requested=stop_requested)
            archive.writestr("manifest.json", json.dumps(
                {"schema_version": 1, "name": source.name, "size": size, "sha256": digest},
                ensure_ascii=False).encode("utf-8"))
        with zipfile.ZipFile(staged) as archive:
            _read_video(archive, stop_requested=stop_requested)
        with source.open("rb") as original:
            if _copy_stream(original, stop_requested=stop_requested) != (size, digest):
                raise StorageError("保管中に元動画が変わりました。再試行してください")
        with staged.open("rb") as stream:
            os.fsync(stream.fileno())
        check_cancelled(stop_requested)
        archive_size = staged.stat().st_size
        _publish_new(staged, destination)
    return ArchiveResult(destination, destination, size, archive_size, digest)


def restore_archive(data: DataFolder, archive, *, stop_requested: Callable[[], bool] | None = None) -> ArchiveResult:
    """Verify an archive and extract into a new folder, retaining the archive."""
    check_cancelled(stop_requested)
    archive = Path(archive).expanduser().resolve()
    root = data._root()
    with tempfile.TemporaryDirectory(dir=root / "work", prefix="restore-") as temporary:
        staged = Path(temporary) / "video"
        try:
            with zipfile.ZipFile(archive) as stored, staged.open("xb") as output:
                name, size, digest = _read_video(stored, output, stop_requested=stop_requested)
                output.flush()
                os.fsync(output.fileno())
        except zipfile.BadZipFile as error:
            raise StorageError("保管物を読み取れません。ZIP形式または破損を確認してください") from error

        check_cancelled(stop_requested)
        destination = root / "media" / "restored" / uuid.uuid4().hex / name
        destination.parent.mkdir(parents=True)
        _publish_new(staged, destination)
    return ArchiveResult(archive, destination, size, archive.stat().st_size, digest)
