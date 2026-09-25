"""Copy supporting media and place it on one editing video's timeline."""

import json
import math
import re
import shutil
import subprocess
import uuid
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

from .storage import StorageError


@dataclass(frozen=True)
class MediaPlacement:
    video: Path
    asset: Path
    kind: str
    identity: str
    first: int
    length: int
    source_duration: float | None = None
    offset: float = 0.0
    volume: float = 100.0
    x: float = 0.0
    y: float = 0.0
    scale: float = 100.0


def _timeline(data, video):
    video = Path(video).resolve()
    if not video.is_file() or not video.is_relative_to(data._root() / "media" / "edits"):
        raise StorageError("データ用フォルダ内の編集用動画を選んでください")
    try:
        metadata = json.loads(video.with_suffix(".json").read_text(encoding="utf-8"))
        rate = Fraction(metadata["fps"])
        frames = sum(metadata["frame_counts"])
        if rate <= 0 or type(frames) is not int or frames < 1:
            raise ValueError
    except (OSError, ValueError, KeyError, TypeError, ZeroDivisionError) as error:
        raise StorageError("編集用動画のフレーム情報を読み取れません") from error
    return video, rate, frames


def import_supporting_media(data, video, source, kind):
    """Retain a separate copy; audio starts with its full duration, without looping."""
    video, rate, frames = _timeline(data, video)
    source = Path(source).resolve()
    if kind not in ("image", "bgm", "sound") or not source.is_file():
        raise StorageError("画像・BGM・効果音のファイルを選んでください")
    probe = shutil.which("ffprobe")
    if not probe:
        raise StorageError("補助素材の確認に ffprobe が必要です")
    result = subprocess.run([probe, "-v", "error", "-show_streams", "-show_format",
                             "-of", "json", str(source)], capture_output=True, encoding="utf-8")
    try:
        metadata = json.loads(result.stdout)
        streams = metadata["streams"]
        if result.returncode:
            raise ValueError
        if kind == "image":
            if source.suffix.lower() not in (".png", ".jpg", ".jpeg", ".bmp") or not any(
                    stream["codec_type"] == "video" for stream in streams):
                raise ValueError
            duration, length = None, frames
        else:
            audio = next(stream for stream in streams if stream["codec_type"] == "audio")
            duration = float(audio.get("duration") or metadata["format"]["duration"])
            if not math.isfinite(duration) or duration <= 0:
                raise ValueError
            length = math.ceil(Fraction(str(duration)) * rate)
    except (ValueError, KeyError, TypeError, StopIteration) as error:
        raise StorageError("選択した種類として読み取れない補助素材です（画像はPNG/JPEG/BMP）") from error
    identity = uuid.uuid4().hex
    folder = data._root() / "media" / "supporting" / video.parent.name / identity
    folder.mkdir(parents=True)
    destination = folder / source.name
    try:
        with source.open("rb") as original, destination.open("xb") as retained:
            shutil.copyfileobj(original, retained)
    except Exception:
        destination.unlink(missing_ok=True)
        folder.rmdir()
        raise
    return MediaPlacement(video, destination, kind, identity, 0, length, duration)


def save_supporting_media(data, placement, *, preview_frame=0):
    """Write a versioned upsert instruction for a single retained placement."""
    video, rate, frames = _timeline(data, placement.video)
    if not re.fullmatch(r"[0-9a-f]{32}", placement.identity):
        raise StorageError("補助素材の識別子が不正です")
    asset_folder = data._root() / "media" / "supporting" / video.parent.name / placement.identity
    if not placement.asset.is_file() or placement.asset.resolve().parent != asset_folder.resolve():
        raise StorageError("この編集用動画にコピーした補助素材を選んでください")
    if placement.kind not in ("image", "bgm", "sound"):
        raise StorageError("補助素材の種類が不正です")
    if any(type(value) is not int for value in (placement.first, placement.length, preview_frame)) or not (
            0 <= placement.first < frames and 1 <= placement.length < 2147483647 - placement.first
            and 0 <= preview_frame < frames):
        raise StorageError("開始・長さ・プレビューは編集用動画内のフレームで指定してください")
    if any(not math.isfinite(value) for value in
           (placement.offset, placement.volume, placement.x, placement.y, placement.scale)) or not (
            0 <= placement.volume <= 1000 and 1 <= placement.scale <= 1000 and placement.offset >= 0):
        raise StorageError("素材位置・音量・拡大率が範囲外です")
    if placement.kind != "image":
        duration = placement.source_duration
        if duration is None or not math.isfinite(duration) or not 0 <= placement.offset < duration or (
                placement.length > math.ceil(Fraction(str(duration - placement.offset)) * rate)):
            raise StorageError("音声の開始位置・長さが素材の範囲を超えています")
    folder = data._root() / "projects" / video.parent.name
    folder.mkdir(parents=True, exist_ok=True)
    lines = ["ClipChannel-Media-1", f"video\t{str(video).encode('utf-8').hex()}",
             f"asset\t{str(placement.asset).encode('utf-8').hex()}",
             f"kind\t{placement.kind}", f"identity\t{placement.identity}",
             f"rate\t{rate.numerator}", f"rate_scale\t{rate.denominator}",
             f"video_frames\t{frames}"]
    lines += [f"{name}\t{getattr(placement, name)}" for name in
              ("first", "length", "offset", "volume", "x", "y", "scale")]
    lines.append(f"preview_frame\t{preview_frame}")
    version = 1
    while True:
        path = folder / f"{placement.identity}_media_v{version}.ccmedia"
        try:
            with path.open("x", encoding="ascii", newline="\n") as output:
                output.write("\n".join(lines) + "\n")
            return path
        except FileExistsError:
            version += 1
