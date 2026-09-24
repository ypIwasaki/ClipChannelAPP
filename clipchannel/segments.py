"""Source-timeline clip ranges, independent of transcript review windows."""

from dataclasses import dataclass, replace

from .storage import StorageError
from .transcribe import load_intervals


class SegmentError(StorageError):
    pass


KINDS = {"target", "non-target", "unknown", "mixed", "manual"}


@dataclass(frozen=True)
class Segment:
    start_ms: int
    end_ms: int
    kind: str
    selected: bool = True


def validate_segments(segments, duration_ms):
    if not isinstance(duration_ms, int) or duration_ms <= 0:
        raise SegmentError("動画の長さが不正です")
    for row in segments:
        if (row.kind not in KINDS or not isinstance(row.selected, bool)
                or not 0 <= row.start_ms < row.end_ms <= duration_ms):
            raise SegmentError("切り出し区間が動画の範囲外または不正です")


def generate_candidates(intervals, duration_ms, before_ms=5000, after_ms=5000):
    """Collapse adjacent equal judgements, then pad each run independently."""
    if any(not isinstance(value, int) or value < 0 for value in (before_ms, after_ms)):
        raise SegmentError("前後の余白は0秒以上で指定してください")
    if not isinstance(duration_ms, int) or duration_ms <= 0:
        raise SegmentError("動画の長さが不正です")
    runs = []
    previous_end = 0
    for row in intervals:
        if row.state not in {"target", "non-target", "unknown"} or not previous_end <= row.start_ms < row.end_ms <= duration_ms:
            raise SegmentError("判定区間が重複または動画の範囲外です")
        if runs and runs[-1].kind == row.state and runs[-1].end_ms == row.start_ms:
            runs[-1] = replace(runs[-1], end_ms=row.end_ms)
        else:
            runs.append(Segment(row.start_ms, row.end_ms, row.state))
        previous_end = row.end_ms
    return [Segment(max(0, row.start_ms - before_ms),
                    min(duration_ms, row.end_ms + after_ms), row.kind) for row in runs]


def split_segment(segments, index, boundary_ms, duration_ms):
    validate_segments(segments, duration_ms)
    row = segments[index]
    if not row.start_ms < boundary_ms < row.end_ms:
        raise SegmentError("分割時刻は選択区間の内側にしてください")
    return [*segments[:index], replace(row, end_ms=boundary_ms),
            replace(row, start_ms=boundary_ms), *segments[index + 1:]]


def merge_segments(segments, indices, duration_ms):
    validate_segments(segments, duration_ms)
    indices = sorted(set(indices))
    if len(indices) < 2:
        raise SegmentError("結合する区間を2件以上選んでください")
    # A merge consumes the intervening candidates as well as their video.
    chosen = segments[indices[0]:indices[-1] + 1]
    start, end = min(row.start_ms for row in chosen), max(row.end_ms for row in chosen)
    kind = chosen[0].kind if all(row.kind == chosen[0].kind for row in chosen) else "mixed"
    first = indices[0]
    return [*segments[:first], Segment(start, end, kind), *segments[indices[-1] + 1:]]


def save_segments(data, video, segments, duration_ms):
    validate_segments(segments, duration_ms)
    return data.save_result(video, "segments", [
        {"start_ms": str(row.start_ms), "end_ms": str(row.end_ms),
         "kind": row.kind, "selected": "1" if row.selected else "0"}
        for row in segments])


def load_segments(data, video, version, duration_ms):
    rows = data.load_result(video, "segments", version)
    try:
        if any(row["selected"] not in {"0", "1"} for row in rows):
            raise ValueError("選択値が不正です")
        result = [Segment(int(row["start_ms"]), int(row["end_ms"]), row["kind"],
                          row["selected"] == "1") for row in rows]
        validate_segments(result, duration_ms)
        return result
    except (ValueError, KeyError) as error:
        raise SegmentError("保存済み区間を読み取れません") from error


def candidates_from_transcript(data, video, version, duration_ms, before_ms=5000, after_ms=5000):
    return generate_candidates(load_intervals(data, video, version), duration_ms, before_ms, after_ms)
