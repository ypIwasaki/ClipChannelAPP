"""Trim one registered video and publish it only after media validation."""

import json
import math
import os
import shutil
import tempfile
from pathlib import Path

from .media import _probe
from .process_control import check_cancelled, run_process
from .storage import StorageError, VideoNameConflict, _name, _publish_new


def _registered_source(data, source):
    source = Path(source).resolve()
    originals = (data._root() / "media" / "originals").resolve()
    if source.parent != originals or not source.is_file() or source not in data.list_videos():
        raise StorageError("登録済み動画を選んでください")
    return source


def destination(data, name):
    stem = _name(Path(name).stem)
    if Path(name).suffix.lower() != ".mp4" or Path(name).name != name:
        raise StorageError("保存名は .mp4 を付けて指定してください")
    target = data._root() / "media" / "originals" / name
    if any(path.stem.casefold() == stem.casefold() for path in target.parent.iterdir() if path.is_file()):
        raise VideoNameConflict("同じ保存名の動画があります。名前を変更してください")
    if any(path.name.casefold() == stem.casefold() for path in (data._root() / "catalog").iterdir()):
        raise VideoNameConflict("同じ結果保存名があります。名前を変更してください")
    return target


def boundaries(data, source, start_seconds, end_seconds, *, stop_requested=None):
    source = _registered_source(data, source)
    info = _probe(source, stop_requested=stop_requested)
    duration = float(info.duration or 0)
    start, end = float(start_seconds), float(end_seconds)
    if not all(math.isfinite(value) for value in (start, end, duration)) or duration <= 0:
        raise StorageError("動画の長さまたは指定時刻が不正です")
    if start < 0 or end > duration or start >= end:
        raise StorageError("開始・終了を動画内の有効な順序で指定してください")
    video_start = float(info.video.start)
    requested = (round((video_start + start) * 1000), round((video_start + end) * 1000))
    probe = shutil.which("ffprobe")
    if not probe:
        raise StorageError("ffprobe が必要です")
    result = run_process([probe, "-v", "error", "-select_streams", "v:0", "-show_entries",
                          "frame=best_effort_timestamp_time", "-of", "csv=p=0", str(source)],
                         stop=stop_requested)
    if result.returncode:
        raise StorageError("実フレーム時刻を読み取れません")
    try:
        frames = sorted({round(float(line.strip().rstrip(",")) * 1000)
                         for line in result.stdout.splitlines() if line.strip().rstrip(",")})
    except ValueError as error:
        raise StorageError("実フレーム時刻が不正です") from error
    if not frames:
        raise StorageError("映像フレームがありません")
    first, last = (min(frames, key=lambda frame: abs(frame - value)) for value in requested)
    if first >= last:
        raise StorageError("採用フレーム境界で長さが0になります")
    return first, last


def history(data, source):
    """Return direct parent first, up to the earliest original."""
    originals = data._root() / "media" / "originals"
    current = Path(source).name
    seen = set()
    rows = []
    while current not in seen:
        seen.add(current)
        sidecar = originals / f".{current}.trim.json"
        if not sidecar.is_file():
            break
        record = json.loads(sidecar.read_text(encoding="utf-8"))
        if record.get("schema_version") != 1:
            raise StorageError("トリミング履歴の版が不明です")
        rows.append(record)
        current = record["parent"]
    if current in seen and (originals / f".{current}.trim.json").is_file():
        raise StorageError("トリミング履歴が循環しています")
    return rows


def trim_video(control, data, source, name, start_ms, end_ms):
    """Run in a managed worker. Boundaries are already shown in the UI."""
    source = _registered_source(data, source)
    target = destination(data, name)
    info = _probe(source, stop_requested=control.cancelled)
    video_start_ms = round(float(info.video.start) * 1000)
    if not video_start_ms <= start_ms < end_ms <= video_start_ms + round(float(info.duration or 0) * 1000):
        raise StorageError("採用範囲が動画外です")
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise StorageError("ffmpeg が必要です")
    control.report("MP4を書き出しています")
    with tempfile.TemporaryDirectory(dir=data._root() / "work", prefix="trim-") as work:
        output = Path(work) / "result.mp4"
        # Decode from the source timeline. Avoid input seeking so nonzero stream
        # start times and variable frame rates retain their presentation times.
        start, end = start_ms / 1000, end_ms / 1000
        video_filter = f"trim=start={start}:end={end},setpts=PTS-STARTPTS"
        command = [ffmpeg, "-v", "error", "-i", str(source), "-filter_complex",
                   f"[0:v:0]{video_filter}[v]" +
                   (f";[0:a:0]atrim=start={start}:end={end},asetpts=PTS-STARTPTS[a]" if info.audio else ""),
                   "-map", "[v]"]
        if info.audio:
            command += ["-map", "[a]"]
        command += ["-c:v", "libx264", "-c:a", "aac", "-movflags", "+faststart", str(output)]
        result = run_process(command, stop=control.cancelled, ffmpeg=True)
        if result.returncode or not output.is_file() or not output.stat().st_size:
            raise StorageError("MP4を書き出せませんでした: " + result.stderr[-500:])
        control.report("成果物を検証しています")
        actual = _probe(output, stop_requested=control.cancelled)
        if actual.video.codec != "h264" or (info.audio is None) != (actual.audio is None) or (
                actual.audio and actual.audio.codec != "aac"):
            raise StorageError("書き出した映像・音声を検証できません")
        expected = (end_ms - start_ms) / 1000
        if not actual.duration or abs(float(actual.duration) - expected) > max(.25, expected * .02):
            raise StorageError("書き出した動画の長さが採用範囲と一致しません")
        decode = run_process([ffmpeg, "-v", "error", "-xerror", "-i", str(output),
                              "-f", "null", "-"], stop=control.cancelled)
        if decode.returncode:
            raise StorageError("書き出した動画を最後まで再生できません")
        check_cancelled(control.cancelled)
        destination(data, name)
        record = {"schema_version": 1, "parent": source.name,
                  "start_ms": start_ms, "end_ms": end_ms}
        sidecar = target.parent / f".{target.name}.trim.json"
        metadata = Path(work) / "trim.json"
        metadata.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
        _publish_new(output, target)
        try:
            _publish_new(metadata, sidecar)
        except BaseException:
            target.unlink(missing_ok=True)
            raise
    return target
