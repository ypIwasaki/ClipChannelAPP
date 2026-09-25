"""Build a versioned editing video from source-timeline segments."""

import json
import math
import os
import shutil
import tempfile
import uuid
from bisect import bisect_left
from fractions import Fraction
from pathlib import Path

from .segments import SegmentError, validate_segments
from .edit_project import write_edit_project
from .process_control import check_cancelled, run_process


def probe_frames(source, *, stop_requested=None):
    probe = shutil.which("ffprobe")
    if not probe:
        raise SegmentError("ffprobe が必要です")
    result = run_process([probe, "-v", "error", "-select_streams", "v:0",
                             "-show_entries", "stream=avg_frame_rate,r_frame_rate,width,height",
                             "-of", "json", str(source)], stop=stop_requested)
    if result.returncode:
        raise SegmentError("フレーム情報を読み取れません")
    try:
        stream = json.loads(result.stdout)["streams"][0]
        average = Fraction(stream["avg_frame_rate"])
        nominal = Fraction(stream["r_frame_rate"])
        if average <= 0 or nominal <= 0:
            raise ValueError()
        return average, nominal, int(stream["width"]), int(stream["height"])
    except (KeyError, IndexError, ValueError, ZeroDivisionError) as error:
        raise SegmentError("フレーム情報が不正です") from error


def is_variable_fps(source, *, stop_requested=None):
    """Inspect actual presentation intervals; stream averages alone can hide VFR."""
    probe = shutil.which("ffprobe")
    if not probe:
        raise SegmentError("ffprobe が必要です")
    result = run_process([probe, "-v", "error", "-select_streams", "v:0",
                             "-show_entries", "frame=best_effort_timestamp_time", "-of", "csv=p=0",
                             str(source)], stop=stop_requested)
    if result.returncode:
        raise SegmentError("フレーム時刻を読み取れません")
    try:
        stamps = [float(line.strip().rstrip(",")) for line in result.stdout.splitlines()
                  if line.strip().rstrip(",")]
    except ValueError as error:
        raise SegmentError("フレーム時刻が不正です") from error
    if len(stamps) < 3:
        return False
    intervals = [right - left for left, right in zip(stamps, stamps[1:])]
    if any(interval <= 0 for interval in intervals):
        raise SegmentError("フレーム時刻が不正です")
    reference = sorted(intervals)[len(intervals) // 2]
    return any(abs(interval - reference) > max(0.001, reference * 0.02) for interval in intervals)


def _nearby_frames(source, requested_ms, *, stop_requested=None):
    probe = shutil.which("ffprobe")
    if not probe or not math.isfinite(requested_ms) or requested_ms < 0:
        raise SegmentError("時刻または ffprobe が不正です")
    result = run_process([probe, "-v", "error", "-select_streams", "v:0",
                             "-show_entries",
                             "frame=best_effort_timestamp_time", "-of", "csv=p=0", str(source)],
                            stop=stop_requested)
    if result.returncode:
        raise SegmentError("フレーム境界を読み取れません")
    try:
        stamps = sorted({round(float(line.strip().rstrip(",")) * 1000)
                         for line in result.stdout.splitlines() if line.strip().rstrip(",")})
        if not stamps:
            raise ValueError("フレームがありません")
    except ValueError as error:
        raise SegmentError("フレーム境界を読み取れません") from error
    return stamps


def nearest_frame(source, requested_ms, *, stop_requested=None):
    """Return an actual decoded frame timestamp and its signed offset in ms."""
    closest = _closest(_nearby_frames(source, requested_ms, stop_requested=stop_requested), requested_ms)
    return closest, closest - requested_ms


def _closest(frames, requested_ms):
    position = bisect_left(frames, requested_ms)
    candidates = frames[max(0, position - 1):position + 1]
    return min(candidates, key=lambda value: abs(value - requested_ms))


def adjacent_frame(source, current_ms, direction, *, stop_requested=None):
    """Move to the preceding or following actual presentation timestamp."""
    if direction not in (-1, 1):
        raise SegmentError("フレームの移動方向が不正です")
    frames = _nearby_frames(source, current_ms, stop_requested=stop_requested)
    nearest = _closest(frames, current_ms)
    position = bisect_left(frames, nearest) + direction
    if not 0 <= position < len(frames):
        raise SegmentError("隣のフレームがありません")
    return frames[position]


def compose_video(data, source, segments, order, duration_ms, *, fps=None, short=False, stop_requested=None, progress=None):
    """Render requested indices in order; repeated indices are intentional."""
    check_cancelled(stop_requested)
    if progress:
        progress("元動画とフレーム境界を確認中")
    validate_segments(segments, duration_ms)
    if not order or any(not isinstance(i, int) or i < 0 or i >= len(segments) for i in order):
        raise SegmentError("使用区間の順番が不正です")
    if fps is not None and (not isinstance(fps, (int, float)) or not math.isfinite(fps) or fps <= 0 or fps > 120):
        raise SegmentError("固定fpsは1～120で指定してください")
    source = Path(source).resolve()
    if data.path is None or not source.is_file() or not source.is_relative_to(data.path / "media" / "originals"):
        raise SegmentError("データ用フォルダ内の元動画を選んでください")
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise SegmentError("ffmpeg が必要です")
    if fps is None and is_variable_fps(source, stop_requested=stop_requested):
        raise SegmentError("可変fpsの動画です。固定fpsを指定してください")
    average_fps, _, width, height = probe_frames(source, stop_requested=stop_requested)
    # Even dimensions are required by yuv420p and keep the source size where possible.
    width -= width % 2
    height -= height % 2
    from .media import _probe
    info = _probe(source, stop_requested=stop_requested)
    directory = data.path / "media" / "edits" / f"{source.stem}_{uuid.uuid4().hex[:12]}"
    directory.parent.mkdir(parents=True, exist_ok=True)
    project_directory = data.path / "projects" / directory.name
    project_directory.parent.mkdir(parents=True, exist_ok=True)
    name = "_".join(f"S{i + 1}_{segments[i].start_ms}_{segments[i].end_ms}" for i in order)
    # Preserve available source encoding targets rather than ffmpeg defaults.
    probe = run_process([shutil.which("ffprobe"), "-v", "error", "-show_streams", "-of", "json", str(source)],
                           stop=stop_requested)
    if probe.returncode:
        raise SegmentError("元動画のストリーム情報を読み取れません")
    streams = json.loads(probe.stdout)["streams"]
    video_stream = next(stream for stream in streams if stream["codec_type"] == "video")
    audio_stream = next((stream for stream in streams if stream["codec_type"] == "audio"), None)
    source_frames = _nearby_frames(source, 0, stop_requested=stop_requested)
    spans = []
    frame_counts = []
    rate = Fraction(str(fps)) if fps is not None else average_fps
    with tempfile.TemporaryDirectory(dir=data.path / "work", prefix="compose-") as temporary:
        staged = Path(temporary) / "result"
        staged.mkdir()
        output = staged / f"{name}_v1.mp4"
        filters = []
        for position, index in enumerate(order):
            check_cancelled(stop_requested)
            row = segments[index]
            start_ms = _closest(source_frames, row.start_ms)
            end_ms = _closest(source_frames, row.end_ms)
            if end_ms <= start_ms:
                raise SegmentError("フレーム境界に合わせると区間の長さが0になります")
            spans.append((start_ms, end_ms))
            frames = round(Fraction(end_ms - start_ms, 1000) * rate)
            if frames < 1:
                raise SegmentError("区間が1フレーム未満です")
            frame_counts.append(frames)
            duration = float(Fraction(frames, 1) / rate)
            start, end = start_ms / 1000, end_ms / 1000
            video_filter = f"[0:v]trim=start={start}:end={end},setpts=PTS-STARTPTS,scale={width}:{height},format=yuv420p"
            video_filter += (f",fps={rate.numerator}/{rate.denominator},"
                             f"tpad=stop_mode=clone:stop_duration={duration},"
                             f"trim=end_frame={frames},setpts=PTS-STARTPTS")
            filters.append(video_filter + f"[v{position}]")
            if info.audio:
                filters.append(f"[0:a]atrim=start={start}:end={end},asetpts=PTS-STARTPTS,"
                               f"aresample=async=1:first_pts=0,apad,atrim=duration={duration}[a{position}]")
        if info.audio:
            inputs = "".join(f"[v{i}][a{i}]" for i in range(len(order)))
            filters.append(f"{inputs}concat=n={len(order)}:v=1:a=1[v][a]")
        else:
            inputs = "".join(f"[v{i}]" for i in range(len(order)))
            filters.append(f"{inputs}concat=n={len(order)}:v=1:a=0[v]")
        command = [ffmpeg, "-v", "error", "-i", str(source), "-filter_complex", ";".join(filters),
                   "-map", "[v]"]
        if info.audio:
            command += ["-map", "[a]"]
        command += ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-profile:a", "aac_low",
                    "-movflags", "+faststart"]
        if video_stream.get("bit_rate"):
            command += ["-b:v", video_stream["bit_rate"]]
        if audio_stream and audio_stream.get("sample_rate"):
            command += ["-ar", audio_stream["sample_rate"]]
        command += [str(output)]
        if progress:
            progress("編集用動画を作成中")
        result = run_process(command, stop=stop_requested, ffmpeg=True)
        if result.returncode or not output.is_file() or not output.stat().st_size:
            raise SegmentError(f"編集用動画を作れません: {result.stderr[-500:]}")
        output.with_suffix(".json").write_text(json.dumps({
            "source": str(source), "spans_ms": spans, "fps": str(rate),
            "frame_counts": frame_counts
        }, ensure_ascii=False), encoding="utf-8")
        project = project_directory / output.with_suffix(".aup2").name
        staged_projects = Path(temporary) / "project"
        staged_projects.mkdir()
        write_edit_project(staged_projects / project.name, directory / output.name, project,
                           width=height if short else width, height=width if short else height,
                           fps=rate, frames=sum(frame_counts),
                           audio_rate=int(audio_stream["sample_rate"]) if audio_stream else 48000,
                           has_audio=bool(audio_stream))
        check_cancelled(stop_requested)
        # Reserve both new folders exclusively; never reuse even an empty old folder.
        directory.mkdir()
        try:
            project_directory.mkdir()
        except OSError:
            directory.rmdir()
            raise
        # Each rename publishes complete files. No old edit is touched on failure.
        for artifact in staged.iterdir():
            os.rename(artifact, directory / artifact.name)
        os.rename(staged_projects / project.name, project)
    return directory / output.name
