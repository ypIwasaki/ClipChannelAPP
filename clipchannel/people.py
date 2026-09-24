"""Register reusable reference voices within one data folder.

Heavy inference imports are deliberately local to enrollment. Saved people stay
readable even when ffmpeg, Torch, or SpeechBrain is unavailable.
"""

import hashlib
import json
import math
import os
import shutil
import subprocess
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path

from .storage import StorageError


class PersonError(StorageError):
    pass


MODEL = "speechbrain/spkrec-ecapa-voxceleb"
SPLITS = {"whole-reference", "five-second-windows"}
AUDIO_EXTENSIONS = {".wav", ".mp3", ".m4a", ".flac", ".ogg", ".aac", ".opus"}


@dataclass(frozen=True)
class Person:
    person_id: str
    name: str
    reference_audio: Path
    feature_file: Path
    model: str
    model_fingerprint: str
    threshold: float
    split: str


def _inside(root, relative):
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise PersonError("人物ファイルがデータ用フォルダの外を参照しています")
    return path


def _model_fingerprint(model_dir):
    if not (model_dir / "hyperparams.yaml").is_file():
        raise PersonError("ローカルの ECAPA モデル一式を選んでください")
    digest = hashlib.sha256()
    files = sorted(path for path in model_dir.rglob("*") if path.is_file())
    for path in files:
        digest.update(path.relative_to(model_dir).as_posix().encode())
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    return digest.hexdigest()


def _convert_audio(source, output, start, end):
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise PersonError("参照音声の登録に ffmpeg が必要です")
    command = [ffmpeg, "-nostdin", "-v", "error", "-n"]
    if start is not None:
        command += ["-ss", str(start)]
    command += ["-i", str(source)]
    if end is not None:
        command += ["-t", str(end - start)]
    command += ["-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(output)]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode or not output.is_file() or output.stat().st_size <= 44:
        raise PersonError("参照音声を読み取れません。音声トラックと指定区間を確認してください")


def _encode(audio, model_dir, cache, split):
    try:
        import soundfile as sf
        import torch
        from speechbrain.inference.classifiers import EncoderClassifier
        from speechbrain.utils.fetching import FetchConfig, LocalStrategy
    except ImportError as error:
        raise PersonError("特徴生成に Torch・SpeechBrain・soundfile が必要です") from error
    samples, rate = sf.read(audio, dtype="float32")
    if rate != 16000 or samples.ndim != 1 or len(samples) < rate:
        raise PersonError("参照音声は1秒以上の16kHz単声道で指定してください")
    previous_offline = os.environ.get("HF_HUB_OFFLINE")
    os.environ["HF_HUB_OFFLINE"] = "1"
    try:
        model = EncoderClassifier.from_hparams(
            source=str(model_dir), savedir=str(cache),
            overrides={"pretrained_path": model_dir.as_posix()},
            run_opts={"device": "cpu"}, local_strategy=LocalStrategy.COPY,
            fetch_config=FetchConfig(allow_network=False))
    finally:
        if previous_offline is None:
            os.environ.pop("HF_HUB_OFFLINE", None)
        else:
            os.environ["HF_HUB_OFFLINE"] = previous_offline
    if split == "whole-reference":
        windows = [samples]
    else:
        width = 5 * rate
        windows = [samples[i:i + width] for i in range(0, len(samples), width)
                   if len(samples[i:i + width]) >= rate]
    features = []
    with torch.inference_mode():
        for window in windows:
            feature = model.encode_batch(torch.from_numpy(window).unsqueeze(0), normalize=False).reshape(-1)
            if feature.numel() != 192 or not torch.isfinite(feature).all():
                raise PersonError("人物特徴を生成できません")
            features.append(feature)
    mean = torch.stack(features).mean(dim=0)
    if not torch.isfinite(mean).all() or float(mean.norm()) == 0:
        raise PersonError("人物特徴を生成できません")
    return [float(value) for value in mean]


def list_people(data):
    root = data._root()
    people = []
    for row in data.load_shared("people"):
        audio = _inside(root, row["reference_audio"])
        feature = _inside(root, row["feature_file"])
        metadata = json.loads(feature.read_text(encoding="utf-8")) if feature.is_file() else {}
        people.append(Person(row["person_id"], row["name"], audio, feature,
                             metadata.get("model", ""), metadata.get("model_fingerprint", ""),
                             metadata.get("threshold", float("nan")), metadata.get("split", "")))
    return people


def target_for_video(data, video):
    """Return the saved person for a registered source, if one was chosen."""
    source = Path(video).expanduser().resolve()
    if source not in data.list_videos():
        raise PersonError("登録済み動画を選んでください")
    identity = source.name.casefold()
    rows = [row for row in data.load_shared("targets") if row["video_name"].casefold() == identity]
    if not rows:
        return None
    return next((person for person in list_people(data) if person.person_id == rows[0]["person_id"]), None)


def select_target(data, video, person_id):
    source = Path(video).expanduser().resolve()
    if source not in data.list_videos():
        raise PersonError("登録済み動画を選んでください")
    if person_id not in {person.person_id for person in list_people(data)}:
        raise PersonError("登録済み人物を選んでください")
    rows = [row for row in data.load_shared("targets")
            if row["video_name"].casefold() != source.name.casefold()]
    rows.append({"video_name": source.name, "person_id": person_id})
    data.save_shared("targets", rows)
    return target_for_video(data, source)


def register_person(data, name, source, model_dir, threshold, split, *, video=None,
                    start=None, end=None, encoder=_encode):
    """Store one immutable enrollment; a new enrollment gets a new person ID."""
    root = data._root()
    name = name.strip()
    if not name or any(char in name for char in "\r\n\x00"):
        raise PersonError("人物の名前を入力してください")
    try:
        threshold = float(threshold)
    except (TypeError, ValueError) as error:
        raise PersonError("照合閾値を -1 から 1 の数値で指定してください") from error
    if not math.isfinite(threshold) or not -1 <= threshold <= 1:
        raise PersonError("照合閾値を -1 から 1 の数値で指定してください")
    if split not in SPLITS:
        raise PersonError("分割方法を選んでください")
    model_dir = Path(model_dir).expanduser().resolve()
    fingerprint = _model_fingerprint(model_dir)
    if video is not None:
        registered = data.list_videos()
        source = Path(video).expanduser().resolve()
        if source not in registered:
            raise PersonError("登録済み動画を選んでください")
        try:
            start, end = float(start), float(end)
        except (ValueError, TypeError) as error:
            raise PersonError("開始と終了を秒で指定してください") from error
        if not all(map(math.isfinite, (start, end))) or start < 0 or end <= start:
            raise PersonError("終了は開始より後の時刻にしてください")
    else:
        source = Path(source).expanduser().resolve()
        if not source.is_file() or source.suffix.lower() not in AUDIO_EXTENSIONS:
            raise PersonError("音声ファイルを選んでください")
        start = end = None
    person_id = uuid.uuid4().hex
    directory = root / "people" / person_id
    directory.mkdir(parents=True, exist_ok=False)
    audio = directory / "reference.wav"
    feature = directory / "feature.json"
    try:
        _convert_audio(source, audio, start, end)
        with tempfile.TemporaryDirectory(dir=root / "work", prefix="person-model-") as cache:
            values = encoder(audio, model_dir, Path(cache), split)
        if len(values) != 192 or any(not math.isfinite(value) for value in values):
            raise PersonError("人物特徴を生成できません")
        metadata = {"schema_version": 1, "model": MODEL, "model_fingerprint": fingerprint,
                    "preprocessing": "16kHz mono float32; encode_batch normalize=False; cosine",
                    "threshold": threshold, "split": split, "features": values,
                    "source": "video" if video is not None else "audio-file",
                    "source_name": source.name, "start_seconds": start, "end_seconds": end}
        with feature.open("x", encoding="utf-8") as stream:
            json.dump(metadata, stream, ensure_ascii=False)
            stream.flush()
            os.fsync(stream.fileno())
        rows = data.load_shared("people")
        rows.append({"person_id": person_id, "name": name,
                     "reference_audio": audio.relative_to(root).as_posix(),
                     "feature_file": feature.relative_to(root).as_posix()})
        data.save_shared("people", rows)
    except Exception:
        shutil.rmtree(directory)
        raise
    return list_people(data)[-1]
