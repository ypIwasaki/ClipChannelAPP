"""Probe source media and prepare a separate editing compatible copy when needed.

All timestamps are seconds on the source container timeline. The manifest records
the stream starts in both files so downstream work can map a source time to the
corresponding prepared time without assuming that both start at zero.
"""

import json
import os
import shutil
import subprocess
import tempfile
import uuid
from dataclasses import asdict, dataclass
from decimal import Decimal
from pathlib import Path

from .storage import StorageError


class MediaError(StorageError):
    pass


@dataclass(frozen=True)
class MediaStream:
    index: int
    codec: str
    start: str
    profile: str | None


@dataclass(frozen=True)
class MediaInfo:
    path: Path
    format: str
    video: MediaStream
    audio: MediaStream | None
    duration: str | None


@dataclass(frozen=True)
class PreparedMedia:
    source: Path
    editing: Path
    source_info: MediaInfo
    editing_info: MediaInfo
    manifest: Path

    def editing_time(self, source_seconds, kind="video"):
        original = getattr(self.source_info, kind)
        prepared = getattr(self.editing_info, kind)
        if original is None or prepared is None:
            raise MediaError("指定したストリームがありません")
        return Decimal(str(source_seconds)) - Decimal(original.start) + Decimal(prepared.start)


def _probe(path):
    ffprobe = shutil.which("ffprobe")
    if ffprobe is None:
        raise MediaError("媒体の確認に ffprobe が必要です")
    result = subprocess.run([ffprobe, "-v", "error", "-show_format", "-show_streams",
                             "-of", "json", str(path)], capture_output=True, text=True)
    if result.returncode:
        raise MediaError("媒体の映像・音声情報を読み取れません")
    try:
        metadata = json.loads(result.stdout)
        streams = metadata["streams"]
        video = next(stream for stream in streams if stream["codec_type"] == "video")
        if video.get("color_transfer") in ("smpte2084", "arib-std-b67"):
            raise MediaError("HDR動画は初版の媒体準備対象外です")
        audio_streams = [stream for stream in streams if stream["codec_type"] == "audio"]
        if len(audio_streams) > 1:
            raise MediaError("複数音声トラックの選択は初版の媒体準備対象外です")
        audio = audio_streams[0] if audio_streams else None
        start = metadata.get("format", {}).get("start_time") or "0"

        def describe(stream):
            return MediaStream(int(stream["index"]), stream["codec_name"],
                               str(stream.get("start_time") or start), stream.get("profile"))

        duration = metadata.get("format", {}).get("duration")
        return MediaInfo(Path(path), metadata["format"]["format_name"], describe(video),
                         describe(audio) if audio else None, str(duration) if duration else None)
    except MediaError:
        raise
    except (ValueError, KeyError, StopIteration, TypeError) as error:
        raise MediaError("利用できる映像ストリームを確認できません") from error


def _prepared_dir(data, source):
    return data.path / "media" / "prepared" / source.name


def _record(path, source_info, editing_info):
    def serialize(info):
        value = asdict(info)
        value["path"] = str(info.path)
        return value

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent,
                                         prefix=".manifest-", suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            json.dump({"schema_version": 1, "source": serialize(source_info),
                       "editing": serialize(editing_info)}, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def prepare_media(data, source, *, stop_requested=lambda: False):
    """Inspect and prepare an already retained source; safe to retry after failure."""
    source = Path(source).resolve()
    if data.path is None or not source.is_file() or not source.is_relative_to(data.path / "media" / "originals"):
        raise MediaError("データ用フォルダ内の元動画を選んでください")
    source_info = _probe(source)
    compatible = ("mp4" in source_info.format.split(",") and
                  source_info.video.codec == "h264" and
                  (source_info.audio is None or
                   (source_info.audio.codec == "aac" and source_info.audio.profile == "LC")))
    directory = _prepared_dir(data, source)
    if compatible:
        editing = source
        editing_info = source_info
        manifest = directory / "source.json"
    else:
        ffmpeg = shutil.which("ffmpeg")
        if ffmpeg is None:
            raise MediaError("編集互換変換に ffmpeg が必要です。元動画は保持しました")
        directory.mkdir(parents=True, exist_ok=True)
        editing = directory / f"editing-{uuid.uuid4().hex}.mp4"
        manifest = editing.with_suffix(".json")
        with tempfile.TemporaryDirectory(dir=data.path / "work", prefix="prepare-") as temporary:
            output = Path(temporary) / "editing.mp4"
            command = [ffmpeg, "-nostdin", "-v", "error", "-y", "-copyts", "-start_at_zero",
                       "-i", str(source), "-map", f"0:{source_info.video.index}"]
            if source_info.audio:
                command += ["-map", f"0:{source_info.audio.index}"]
            command += ["-c:v", "libx264", "-c:a", "aac", "-movflags", "+faststart", str(output)]
            process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            while process.poll() is None:
                if stop_requested():
                    process.terminate()
                    process.wait()
                    raise MediaError("変換を中止しました。元動画は保持しました")
                try:
                    process.wait(timeout=0.2)
                except subprocess.TimeoutExpired:
                    pass
            if process.returncode or not output.is_file() or not output.stat().st_size:
                raise MediaError("編集互換変換に失敗しました。元動画は保持しました")
            editing_info = _probe(output)
            os.replace(output, editing)
            editing_info = MediaInfo(editing, editing_info.format, editing_info.video,
                                     editing_info.audio, editing_info.duration)
    try:
        _record(manifest, source_info, editing_info)
    except Exception:
        if editing != source:
            editing.unlink(missing_ok=True)
        raise
    return PreparedMedia(source, editing, source_info, editing_info, manifest)
