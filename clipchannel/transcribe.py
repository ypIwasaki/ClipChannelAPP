"""Conservative, offline speaker review and target-only transcription.

Similarity scores are review aids, never identity labels. A user must confirm a
window as the target before its audio is sent to ASR or its text is saved.
"""

import math
import json
import os
import shutil
import tempfile
import wave
from dataclasses import dataclass
from pathlib import Path

from .people import _model_fingerprint, target_for_video
from .storage import StorageError
from .process_control import ProcessCancelled, run_process


class TranscriptionError(StorageError):
    pass


class Cancelled(TranscriptionError):
    pass


@dataclass(frozen=True)
class Interval:
    start_ms: int
    end_ms: int
    state: str  # target, non-target, unknown
    score: float | None = None
    text: str = ""


def _check_stop(stop):
    if stop and stop():
        raise Cancelled("文字起こしを中止しました")


def validate_intervals(intervals):
    previous = 0
    for row in intervals:
        if row.state not in {"target", "non-target", "unknown"}:
            raise TranscriptionError("区間の判定が不正です")
        if row.start_ms < previous or row.end_ms <= row.start_ms:
            raise TranscriptionError("区間の時刻が重複または逆転しています")
        if row.state != "target" and row.text:
            raise TranscriptionError("対象話者以外の本文は保存できません")
        previous = row.end_ms


def save_intervals(data, video, intervals, *, stop=None, source_version=None):
    """Persist a reviewed snapshot, including unknowns.

    Pass source_version when editing/re-recognizing a saved version so its
    person references survive changes to the video's currently selected target.
    """
    _check_stop(stop)
    if target_for_video(data, video) is None:
        raise TranscriptionError("この動画の対象話者を選んでください")
    validate_intervals(intervals)
    return data.save_result(video, "transcripts", [
        {"start_ms": str(row.start_ms), "end_ms": str(row.end_ms),
         "text": row.text, "speaker_id": row.state}
        for row in intervals], stop_requested=stop, source_version=source_version)


def load_intervals(data, video, version):
    rows = data.load_result(video, "transcripts", version)
    result = [Interval(int(row["start_ms"]), int(row["end_ms"]),
                       row["speaker_id"], text=row["text"]) for row in rows]
    validate_intervals(result)
    return result


def _pcm(video, destination, stop):
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise TranscriptionError("音声解析に ffmpeg が必要です")
    try:
        result = run_process([ffmpeg, "-v", "error", "-i", str(video),
                              "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le",
                              str(destination)], stop=stop, ffmpeg=True)
    except ProcessCancelled as error:
        raise Cancelled("音声解析を中止しました") from error
    if result.returncode or not destination.is_file():
        raise TranscriptionError("動画の音声を読み取れません。音声トラックを確認してください")


def propose_intervals(data, video, model_dir, *, stop=None, progress=None):
    """Return bounded review windows. Unverified identity remains unknown."""
    _check_stop(stop)
    video = Path(video).resolve()
    if video not in data.list_videos():
        raise TranscriptionError("登録済み動画を選んでください")
    person = target_for_video(data, video)
    if person is None:
        raise TranscriptionError("この動画の対象話者を選んでください")
    if not person.reference_audio.is_file() or not person.feature_file.is_file():
        raise TranscriptionError("参照音声または人物特徴が見つかりません")
    _check_stop(stop)
    model_dir = Path(model_dir).expanduser().resolve()
    if _model_fingerprint(model_dir) != person.model_fingerprint:
        raise TranscriptionError("人物登録時と同じ ECAPA モデル一式を選んでください")
    try:
        import numpy as np
        import torch
        from speechbrain.inference.classifiers import EncoderClassifier
        from speechbrain.utils.fetching import FetchConfig, LocalStrategy
    except ImportError as error:
        raise TranscriptionError("話者照合に Torch・SpeechBrain・numpy が必要です") from error
    _check_stop(stop)
    metadata = json.loads(person.feature_file.read_text(encoding="utf-8"))
    reference = torch.tensor(metadata["features"], dtype=torch.float32)
    if reference.shape != (192,) or not torch.isfinite(reference).all():
        raise TranscriptionError("人物特徴が不正です")
    with tempfile.TemporaryDirectory(dir=data._root() / "work", prefix="transcribe-") as temporary:
        audio = Path(temporary) / "input.wav"
        if progress:
            progress("音声を準備中")
        _pcm(video, audio, stop)
        with wave.open(str(audio), "rb") as stream:
            if stream.getframerate() != 16000 or stream.getnchannels() != 1:
                raise TranscriptionError("音声形式を読み取れません")
            duration = stream.getnframes() / 16000
        if progress:
            progress("試聴区間を作成中")
        _check_stop(stop)
        previous_offline = os.environ.get("HF_HUB_OFFLINE")
        os.environ["HF_HUB_OFFLINE"] = "1"
        try:
            model = EncoderClassifier.from_hparams(
                source=str(model_dir), savedir=str(Path(temporary) / "model"),
                overrides={"pretrained_path": model_dir.as_posix()},
                run_opts={"device": "cpu"}, local_strategy=LocalStrategy.COPY,
                fetch_config=FetchConfig(allow_network=False))
        finally:
            if previous_offline is None:
                os.environ.pop("HF_HUB_OFFLINE", None)
            else:
                os.environ["HF_HUB_OFFLINE"] = previous_offline
        _check_stop(stop)
        # A reference alone does not calibrate the non-target distribution.
        # Scores help choose what to listen to; all identity labels remain unknown.
        rows = []
        with wave.open(str(audio), "rb") as stream:
            for start in range(0, math.ceil(duration * 1000), 5000):
                _check_stop(stop)
                end = min(start + 5000, round(duration * 1000))
                stream.setpos(round(start * 16))
                signal = np.frombuffer(stream.readframes(min(round((end - start) * 16),
                                                             stream.getnframes() - stream.tell())),
                                       dtype="<i2").astype(np.float32) / 32768
                score = None
                if len(signal) >= 16000:
                    with torch.inference_mode():
                        feature = model.encode_batch(torch.from_numpy(signal).unsqueeze(0),
                                                     normalize=False).reshape(-1)
                    _check_stop(stop)
                    if feature.shape == (192,) and torch.isfinite(feature).all():
                        score = float(torch.nn.functional.cosine_similarity(reference, feature, dim=0))
                rows.append(Interval(start, end, "unknown", score))
                if progress:
                    progress(f"話者照合 {len(rows)}/{math.ceil(duration / 5)}")
        _check_stop(stop)
        return rows


def transcribe_confirmed(data, video, intervals, model_dir, *, stop=None, progress=None, source_version=None):
    """ASR only on user-confirmed target ranges; save complete version on success."""
    validate_intervals(intervals)
    _check_stop(stop)
    video = Path(video).resolve()
    if video not in data.list_videos() or target_for_video(data, video) is None:
        raise TranscriptionError("登録済み動画と対象話者を選んでください")
    _check_stop(stop)
    model_dir = Path(model_dir).expanduser().resolve()
    if not model_dir.is_dir() or not (model_dir / "config.json").is_file():
        raise TranscriptionError("ローカルの Whisper モデル一式を選んでください")
    if not shutil.which("ffmpeg"):
        raise TranscriptionError("文字起こしに ffmpeg が必要です")
    try:
        import numpy as np
        from faster_whisper import WhisperModel
    except ImportError as error:
        raise TranscriptionError("文字起こしに faster-whisper と numpy が必要です") from error
    _check_stop(stop)
    with tempfile.TemporaryDirectory(dir=data._root() / "work", prefix="transcribe-") as temporary:
        audio = Path(temporary) / "input.wav"
        if progress:
            progress("音声を準備中")
        _pcm(video, audio, stop)
        _check_stop(stop)
        if progress:
            progress("認識モデルを読み込み中")
        model = WhisperModel(str(model_dir), device="cpu", compute_type="int8", local_files_only=True)
        _check_stop(stop)
        output = []
        with wave.open(str(audio), "rb") as stream:
            for index, row in enumerate(intervals):
                _check_stop(stop)
                if progress:
                    progress(f"文字起こし {index + 1}/{len(intervals)}")
                if row.end_ms > round(stream.getnframes() / 16):
                    raise TranscriptionError("区間が動画の音声範囲を超えています")
                if row.state != "target":
                    output.append(row)
                    continue
                stream.setpos(round(row.start_ms * 16))
                samples = stream.readframes(round(row.end_ms * 16) - stream.tell())
                signal = np.frombuffer(samples, dtype="<i2").astype(np.float32) / 32768
                segments, _ = model.transcribe(signal, language="ja", beam_size=5,
                                                condition_on_previous_text=False, vad_filter=False)
                cursor = row.start_ms
                for segment in segments:
                    _check_stop(stop)
                    start = max(cursor, min(row.end_ms, row.start_ms + round(segment.start * 1000)))
                    end = max(start, min(row.end_ms, row.start_ms + round(segment.end * 1000)))
                    text = segment.text.strip()
                    if end <= start or not text:
                        continue
                    if start > cursor:
                        output.append(Interval(cursor, start, "unknown", row.score))
                    output.append(Interval(start, end, "target", row.score, text))
                    cursor = end
                if cursor < row.end_ms:
                    output.append(Interval(cursor, row.end_ms, "unknown", row.score))
        _check_stop(stop)
        return save_intervals(data, video, output, stop=stop, source_version=source_version), output
