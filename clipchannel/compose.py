"""Build a versioned editing video from source-timeline segments."""

import json
import math
import shutil
import subprocess
import tempfile
import uuid
from fractions import Fraction
from pathlib import Path

from .segments import SegmentError, validate_segments


def probe_frames(source):
    probe = shutil.which("ffprobe")
    if not probe:
        raise SegmentError("ffprobe が必要です")
    result = subprocess.run([probe, "-v", "error", "-select_streams", "v:0",
                             "-show_entries", "stream=avg_frame_rate,r_frame_rate,width,height",
                             "-of", "json", str(source)], capture_output=True, text=True)
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


def nearest_frame(source, requested_ms):
    """Return an actual decoded frame timestamp and its signed offset in ms."""
    probe = shutil.which("ffprobe")
    if not probe or not math.isfinite(requested_ms) or requested_ms < 0:
        raise SegmentError("時刻または ffprobe が不正です")
    start = max(0, requested_ms / 1000 - 2)
    result = subprocess.run([probe, "-v", "error", "-select_streams", "v:0",
                             "-read_intervals", f"{start}%+4", "-show_entries",
                             "frame=best_effort_timestamp_time", "-of", "csv=p=0", str(source)],
                            capture_output=True, text=True)
    if result.returncode:
        raise SegmentError("フレーム境界を読み取れません")
    try:
        stamps = [round(float(line.strip().rstrip(",")) * 1000) for line in result.stdout.splitlines()
                  if line.strip().rstrip(",")]
        closest = min(stamps, key=lambda value: abs(value - requested_ms))
    except ValueError as error:
        raise SegmentError("フレーム境界を読み取れません") from error
    return closest, closest - requested_ms


def compose_video(data, source, segments, order, duration_ms, *, fps=None):
    """Render requested indices in order; repeated indices are intentional."""
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
    _, _, width, height = probe_frames(source)
    # Even dimensions are required by yuv420p and keep the source size where possible.
    width -= width % 2
    height -= height % 2
    from .media import _probe
    info = _probe(source)
    directory = data.path / "media" / "edits" / f"{source.stem}_{uuid.uuid4().hex[:12]}"
    directory.mkdir(parents=True, exist_ok=True)
    name = "_".join(f"S{i + 1}_{segments[i].start_ms}_{segments[i].end_ms}" for i in order)
    # Preserve available source encoding targets rather than ffmpeg defaults.
    probe = subprocess.run([shutil.which("ffprobe"), "-v", "error", "-show_streams", "-of", "json", str(source)],
                           capture_output=True, text=True, check=True)
    streams = json.loads(probe.stdout)["streams"]
    video_stream = next(stream for stream in streams if stream["codec_type"] == "video")
    audio_stream = next((stream for stream in streams if stream["codec_type"] == "audio"), None)
    with tempfile.TemporaryDirectory(dir=data.path / "work", prefix="compose-") as temporary:
        output = Path(temporary) / "editing.mp4"
        filters = []
        for position, index in enumerate(order):
            row = segments[index]
            start_ms, _ = nearest_frame(source, row.start_ms)
            end_ms, _ = nearest_frame(source, row.end_ms)
            if end_ms <= start_ms:
                raise SegmentError("フレーム境界に合わせると区間の長さが0になります")
            start, end = start_ms / 1000, end_ms / 1000
            video_filter = f"[0:v]trim=start={start}:end={end},setpts=PTS-STARTPTS,scale={width}:{height},format=yuv420p"
            if fps is not None:
                video_filter += f",fps={fps}"
            filters.append(video_filter + f"[v{position}]")
            if info.audio:
                filters.append(f"[0:a]atrim=start={start}:end={end},asetpts=PTS-STARTPTS,aresample=async=1:first_pts=0[a{position}]")
        if info.audio:
            inputs = "".join(f"[v{i}][a{i}]" for i in range(len(order)))
            filters.append(f"{inputs}concat=n={len(order)}:v=1:a=1[v][a]")
        else:
            inputs = "".join(f"[v{i}]" for i in range(len(order)))
            filters.append(f"{inputs}concat=n={len(order)}:v=1:a=0[v]")
        command = [ffmpeg, "-nostdin", "-v", "error", "-i", str(source), "-filter_complex", ";".join(filters),
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
        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode or not output.is_file() or not output.stat().st_size:
            raise SegmentError(f"編集用動画を作れません: {result.stderr[-500:]}")
        version = 1
        while True:
            destination = directory / f"{name}_v{version}.mp4"
            try:
                with destination.open("xb") as target, output.open("rb") as rendered:
                    shutil.copyfileobj(rendered, target)
                break
            except FileExistsError:
                version += 1
            except Exception:
                destination.unlink(missing_ok=True)
                raise
    return destination
