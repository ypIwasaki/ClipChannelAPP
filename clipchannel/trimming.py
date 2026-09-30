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


def video_duration(source, *, stop_requested=None):
    """Playable video length, independent of the container's starting PTS."""
    probe = shutil.which("ffprobe")
    if not probe:
        raise StorageError("ffprobe が必要です")
    result = run_process([probe, "-v", "error", "-select_streams", "v:0", "-show_entries",
                          "stream=duration,start_time:format=duration", "-of", "json", str(source)],
                         stop=stop_requested)
    if result.returncode:
        raise StorageError("動画の長さを読み取れません")
    try:
        metadata = json.loads(result.stdout)
        stream = metadata["streams"][0]
        length = stream.get("duration")
        if length is None or length == "N/A":
            length = float(metadata["format"]["duration"]) - float(stream.get("start_time") or 0)
        length = float(length)
        if not math.isfinite(length) or length <= 0:
            raise ValueError()
        return length
    except (KeyError, IndexError, ValueError, TypeError) as error:
        raise StorageError("動画の長さを読み取れません") from error


def boundaries(data, source, start_seconds, end_seconds, *, stop_requested=None):
    source = _registered_source(data, source)
    info = _probe(source, stop_requested=stop_requested)
    duration = video_duration(source, stop_requested=stop_requested)
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


def publish_trim(data, staged):
    """Publish only after the managed worker has exited successfully."""
    work = Path(staged["work"]).resolve()
    root = (data._root() / "work").resolve()
    if work.parent != root or not work.name.startswith("trim-"):
        raise StorageError("トリミング一時領域が不正です")
    target = destination(data, staged["name"])
    output, metadata = work / "result.mp4", work / "trim.json"
    if not output.is_file() or not metadata.is_file():
        raise StorageError("検証済みの成果物がありません")
    sidecar = target.parent / f".{target.name}.trim.json"
    metadata_published = False
    video_published = False
    try:
        _publish_new(metadata, sidecar)
        metadata_published = True
        _publish_new(output, target)
        video_published = True
    except BaseException:
        if video_published:
            target.unlink(missing_ok=True)
        if metadata_published:
            sidecar.unlink(missing_ok=True)
        raise
    finally:
        try:
            shutil.rmtree(work)
        except OSError:
            # Registration has already committed or rolled back. A temporary
            # cleanup error must not change the operation's recorded result.
            pass
    return target


def cleanup_staged(data, work_name):
    """Remove only this operation's staging after its worker has fully stopped."""
    root = (data._root() / "work").resolve()
    entry = root / Path(work_name).name
    if not entry.name.startswith("trim-") or entry.resolve().parent != root:
        raise StorageError("トリミング一時領域が不正です")
    if entry.is_dir():
        shutil.rmtree(entry)


def trim_video(control, data, source, name, start_ms, end_ms, work_name=None):
    """Run in a managed worker. Boundaries are already shown in the UI."""
    source = _registered_source(data, source)
    target = destination(data, name)
    info = _probe(source, stop_requested=control.cancelled)
    video_start_ms = round(float(info.video.start) * 1000)
    if not video_start_ms <= start_ms < end_ms <= video_start_ms + round(video_duration(source, stop_requested=control.cancelled) * 1000):
        raise StorageError("採用範囲が動画外です")
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise StorageError("ffmpeg が必要です")
    control.report("MP4を書き出しています")
    if work_name is None:
        work = Path(tempfile.mkdtemp(dir=data._root() / "work", prefix="trim-"))
    else:
        if Path(work_name).name != work_name or not work_name.startswith("trim-"):
            raise StorageError("トリミング一時領域が不正です")
        work = data._root() / "work" / work_name
        work.mkdir()
    try:
        output = work / "result.mp4"
        # Decode from the source timeline. Avoid input seeking so nonzero stream
        # start times and variable frame rates retain their presentation times.
        start, end = start_ms / 1000, end_ms / 1000
        video_filter = f"trim=start={start}:end={end},setpts=PTS-STARTPTS"
        audio_filter = ""
        if info.audio:
            delay = max(0, round((float(info.audio.start) - start) * 1000))
            audio_filter = (f";[0:a:0]atrim=start={start}:end={end},asetpts=PTS-STARTPTS,"
                            f"adelay={delay}:all=1,apad,atrim=duration={end-start}[a]")
        command = [ffmpeg, "-v", "error", "-copyts", "-i", str(source), "-filter_complex",
                   f"[0:v:0]{video_filter}[v]" + audio_filter,
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
        if actual.audio:
            audio_length = run_process([shutil.which("ffprobe"), "-v", "error", "-select_streams", "a:0",
                                        "-show_entries", "stream=duration", "-of", "default=nw=1:nk=1",
                                        str(output)], stop=control.cancelled)
            try:
                if audio_length.returncode or abs(float(audio_length.stdout.strip()) - expected) > .3:
                    raise ValueError()
            except ValueError as error:
                raise StorageError("書き出した音声の長さが採用範囲と一致しません") from error
        decode = run_process([ffmpeg, "-v", "error", "-xerror", "-i", str(output),
                              "-f", "null", "-"], stop=control.cancelled)
        if decode.returncode:
            raise StorageError("書き出した動画を最後まで再生できません")
        check_cancelled(control.cancelled)
        destination(data, name)
        record = {"schema_version": 1, "parent": source.name,
                  "start_ms": start_ms, "end_ms": end_ms}
        metadata = work / "trim.json"
        metadata.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
        check_cancelled(control.cancelled)
        return {"work": str(work), "name": target.name}
    except BaseException:
        shutil.rmtree(work)
        raise
