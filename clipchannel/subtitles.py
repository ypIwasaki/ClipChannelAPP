"""Map reviewed source utterances onto an immutable editing video's timeline."""

import json
import math
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

from .storage import StorageError
from .transcribe import load_intervals


@dataclass(frozen=True)
class Subtitle:
    start_frame: int
    end_frame: int  # inclusive, as used by AviUtl2
    text: str


def map_subtitles(intervals, spans_ms, fps):
    """Clip target speech to each rendered span, including repeated spans."""
    rate = Fraction(fps)
    if rate <= 0 or not math.isfinite(float(rate)):
        raise StorageError("編集用動画のfpsが不正です")
    result = []
    offset = 0
    for start, end in spans_ms:
        if start < 0 or end <= start:
            raise StorageError("編集用動画の区間が不正です")
        frame_count = round(Fraction(end - start, 1000) * rate)
        if frame_count < 1:
            raise StorageError("字幕の区間が1フレーム未満です")
        for row in intervals:
            if row.state != "target" or not row.text:
                continue
            left, right = max(start, row.start_ms), min(end, row.end_ms)
            if left >= right:
                continue
            first = max(0, int(Fraction(left - start, 1000) * rate))
            last = min(frame_count - 1, math.ceil(Fraction(right - start, 1000) * rate) - 1)
            if last >= first:
                result.append(Subtitle(offset + first, offset + last, row.text))
        offset += frame_count
    return result


def prepare_subtitle_import(data, source, edit_video, transcript_version):
    """Save a new import version beside the matching AviUtl2 project directory."""
    root = data._root()
    edit_video = Path(edit_video).resolve()
    source = Path(source).resolve()
    if not edit_video.is_file() or not edit_video.is_relative_to(root / "media" / "edits"):
        raise StorageError("データ用フォルダ内の編集用動画を選んでください")
    metadata = edit_video.with_suffix(".json")
    try:
        details = json.loads(metadata.read_text(encoding="utf-8"))
        if Path(details["source"]).resolve() != source:
            raise StorageError("編集用動画と文字起こしの元動画が異なります")
        spans, fps = details["spans_ms"], details["fps"]
    except (OSError, KeyError, ValueError, TypeError) as error:
        raise StorageError("編集用動画の区間情報を読み取れません") from error
    subtitles = map_subtitles(load_intervals(data, source, transcript_version), spans, fps)
    project_dir = root / "projects" / edit_video.parent.name
    project_dir.mkdir(parents=True, exist_ok=True)
    number = 1
    while (project_dir / f"{edit_video.stem}_subtitles_v{number}.ccsub").exists():
        number += 1
    destination = project_dir / f"{edit_video.stem}_subtitles_v{number}.ccsub"
    # UTF-8 is encoded as hex so arbitrary body text cannot change record boundaries.
    lines = ["ClipChannel-Subtitles-1", f"video\t{edit_video.name}", f"count\t{len(subtitles)}"]
    lines += [f"{item.start_frame}\t{item.end_frame}\t{item.text.encode('utf-8').hex()}"
              for item in subtitles]
    with destination.open("x", encoding="ascii", newline="\n") as output:
        output.write("\n".join(lines) + "\n")
    return destination, subtitles
