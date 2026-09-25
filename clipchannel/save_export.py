"""Explicit AviUtl2 saving and verified, cancellable finished-video export."""

import configparser
import json
import math
import os
import shutil
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Callable

from .editor_bridge import send_control
from .storage import StorageError


@dataclass(frozen=True)
class ExportSettings:
    width: int
    height: int
    fps: Fraction
    bitrate_mbps: float = 8
    audio_rate: int = 48000

    @classmethod
    def defaults(cls, short: bool, fps: Fraction):
        return cls(1080 if short else 1920, 1920 if short else 1080,
                   Fraction(fps), 12 if fps > 30 else 8)

    def validate(self):
        if any(type(value) is not int or not 2 <= value <= 8192 or value % 2
               for value in (self.width, self.height)):
            raise StorageError("出力の幅・高さは2～8192の偶数で指定してください")
        if not 0 < self.fps <= 120 or self.fps.denominator > 1000000:
            raise StorageError("出力fpsは0より大きく120以下で指定してください")
        if not math.isfinite(self.bitrate_mbps) or not 0.1 <= self.bitrate_mbps <= 200:
            raise StorageError("映像ビットレートは0.1～200 Mbpsで指定してください")
        if self.audio_rate not in (32000, 44100, 48000, 96000):
            raise StorageError("音声サンプルレートは32000・44100・48000・96000から選んでください")

    def short_eligible(self, duration):
        # YouTube Help answer/15424877: square/vertical and at most 3 minutes.
        output_duration = Fraction(math.ceil(duration * self.fps), 1) / self.fps
        return self.width <= self.height and 0 < output_duration <= 180


@dataclass(frozen=True)
class ProjectState:
    project: Path
    width: int
    height: int
    fps: Fraction
    frames: int
    dirty: bool | None
    busy: bool

    @property
    def duration(self):
        return Fraction(self.frames, 1) / self.fps


@dataclass(frozen=True)
class OperationResult:
    state: str
    detail: str
    path: Path

    @property
    def confirmed(self):
        return self.state == "confirmed"


@dataclass(frozen=True)
class FileState:
    modified_ns: int
    size: int

    @classmethod
    def read(cls, path):
        try:
            info = Path(path).stat()
            return cls(info.st_mtime_ns, info.st_size)
        except FileNotFoundError:
            return None


def _windows_path(path):
    path = Path(path).resolve()
    if os.name == "nt":
        return str(path)
    return subprocess.run(["wslpath", "-w", str(path)], check=True,
                          capture_output=True, text=True).stdout.strip()


def _encoder_path():
    """The encoder runs in the Windows host, including when the app runs in WSL."""
    configured = os.environ.get("CLIPCHANNEL_FFMPEG")
    if configured:
        if os.name != "nt" and (configured.startswith("\\\\") or len(configured) > 2 and configured[1] == ":"):
            return configured
        return _windows_path(configured)
    if os.name == "nt":
        executable = shutil.which("ffmpeg")
        if executable:
            return str(Path(executable).resolve())
    else:
        executable = shutil.which("ffmpeg.exe")
        if executable:
            return _windows_path(executable)
        try:
            found = subprocess.run(["powershell.exe", "-NoProfile", "-Command",
                                    "(Get-Command ffmpeg.exe -ErrorAction Stop).Source"],
                                   capture_output=True, text=True, check=True, timeout=15)
            if found.stdout.strip():
                return found.stdout.strip()
        except (OSError, subprocess.SubprocessError):
            pass
    raise StorageError("Windows版 ffmpeg をPATHに置くか、CLIPCHANNEL_FFMPEGに実行ファイルの場所を設定してください")


def _instruction(project, video, action, **fields):
    project, video = Path(project).resolve(), Path(video).resolve()
    if (project.suffix.lower() != ".aup2" or not project.parent.is_dir() or not video.is_file() or
            (action == "export" and not project.is_file())):
        raise StorageError("対応する編集用動画と、AviUtl2で開いている保存先プロジェクトを選んでください")
    path = project.parent / f"control-{uuid.uuid4().hex}.cccontrol"
    values = {"action": action, "video": _windows_path(video).encode("utf-8").hex(),
              "project": _windows_path(project).encode("utf-8").hex(), **fields}
    path.write_text("ClipChannel-Control-1\n" + "".join(f"{key}\t{value}\n" for key, value in values.items()),
                    encoding="ascii", newline="\n")
    return path


def _host_alive(process_id):
    """Return None when liveness is unknown, never release editing on uncertainty."""
    if type(process_id) is not int or process_id <= 0:
        return None
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
        kernel.WaitForSingleObject.restype = wintypes.DWORD
        kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
        process = kernel.OpenProcess(0x00100000, False, process_id)
        if not process:
            return False if ctypes.get_last_error() == 87 else None
        try:
            outcome = kernel.WaitForSingleObject(process, 0)
            return False if outcome == 0 else True if outcome == 258 else None
        finally:
            kernel.CloseHandle(process)
    try:
        query = subprocess.run(["powershell.exe", "-NoProfile", "-Command",
                                f"if (Get-Process -Id {process_id} -ErrorAction SilentlyContinue) {{ exit 0 }} else {{ exit 1 }}"],
                               capture_output=True, timeout=10)
        return query.returncode == 0 if query.returncode in (0, 1) else None
    except (OSError, subprocess.SubprocessError):
        return None


def _response(instruction):
    try:
        value = json.loads(instruction.with_suffix(".json").read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def _cleanup(instruction):
    for path in (instruction, instruction.with_suffix(".json"), instruction.with_suffix(".cancel")):
        path.unlink(missing_ok=True)


def _project_state(project, response):
    try:
        state = ProjectState(Path(project), int(response["width"]), int(response["height"]),
                             Fraction(int(response["rate"]), int(response["scale"])),
                             int(response["frames"]), response.get("dirty"), bool(response["busy"]))
        if min(state.width, state.height, state.frames, state.fps) <= 0:
            raise ValueError()
        if state.dirty is not None and type(state.dirty) is not bool:
            raise ValueError()
        return state
    except (KeyError, TypeError, ValueError, ZeroDivisionError) as error:
        raise StorageError("AviUtl2の編集状態を確認できませんでした") from error


def _failure_detail(response):
    code = response.get("detail", "")
    messages = {
        "initial-save-target-already-exists": "初回保存先には既存ファイルを指定できません。新しいプロジェクト名を選んでください",
        "initial-save-dialog-not-identified": "AviUtl2の名前を付けて保存する画面を確認できませんでした。編集内容は保持しています",
        "host-is-not-editable": "AviUtl2で実行中の処理の完了を待ってください",
        "editing-is-blocked-until-export-stops": "先の書き出しの停止完了まで編集を待ってください",
        "save-menu-not-identified": "AviUtl2の保存操作を確認できませんでした。対応版とプラグインを確認してください",
        "save-project-before-export": "編集プロジェクトを保存してから書き出してください",
        "audio-temporary-file-unavailable": "作業用音声を書き込めません。保存先の空き容量・書込み権限を確認してください",
        "host-audio-render-rejected": "AviUtl2で音声の描画を開始できませんでした",
        "host-audio-render-incomplete": "AviUtl2の音声を最後まで読み取れませんでした",
        "host-video-render-rejected": "AviUtl2で映像の描画を開始できませんでした",
        "host-video-render-incomplete": "AviUtl2の映像を最後まで読み取れませんでした",
        "encoder-start-failed": "Windows版FFmpegを起動できませんでした。設定した実行ファイルを確認してください",
        "encoder-output-incomplete-see-log": "完成動画の出力に失敗しました。保存先・空き容量とプロジェクトフォルダの出力ログを確認してください",
        "encoder-log-unavailable": "出力ログを書き込めません。プロジェクトフォルダの書込み権限を確認してください",
        "encoder-pipe-unavailable": "エンコーダーとの接続を開始できませんでした",
        "export-worker-unavailable": "書き出し処理を開始できませんでした",
    }
    return messages.get(code, "AviUtl2の処理を完了できませんでした。編集内容を保持しています")


def inspect_project(project, video):
    """Query the matching open editor, including manual edits, without saving."""
    instruction = _instruction(project, video, "status")
    try:
        send_control(instruction)
        response = _response(instruction)
        if response.get("state") not in ("ready", "running"):
            raise StorageError(response.get("detail") or "対応するAviUtl2プロジェクトを開き、プラグインを確認してください")
        return _project_state(project, response)
    finally:
        _cleanup(instruction)


def _read_project(path, expected_video):
    parser = configparser.ConfigParser(interpolation=None, strict=False, delimiters=("=",))
    parser.read_string(path.read_text(encoding="utf-8-sig"))
    scene = parser[f"scene.{parser['project'].get('display.scene', '0')}"]
    if int(parser["project"]["version"]) <= 0:
        raise ValueError("プロジェクト形式を読み取れません")
    for field in ("video.width", "video.height", "video.rate", "video.scale", "audio.rate"):
        if int(scene[field]) <= 0:
            raise ValueError("プロジェクトの画面設定が不正です")
    objects = [name for name in parser.sections() if name.isdigit()]
    if not objects:
        raise ValueError("編集オブジェクトを読み取れません")
    for name in objects:
        frames = [int(value) for value in parser[name]["frame"].split(",")]
        if (len(frames) != 2 or frames[0] < 0 or frames[1] < frames[0] or
                int(parser[name]["layer"]) < 0 or not parser[f"{name}.0"]["effect.name"]):
            raise ValueError("編集オブジェクトの内容が不完全です")
    normalized = expected_video.replace("\\", "/").casefold()
    if not any(parser[section].get("effect.name") == "動画ファイル" and
               parser[section].get("ファイル", "").replace("\\", "/").casefold() == normalized
               for section in parser.sections()):
        raise ValueError("保存内容から対応する編集用動画を読み取れません")


def _confirm_file(path, before, read_contents, *, timeout=10.0, interval=0.25):
    """Require an update, three stable observations and a successful content read."""
    deadline = time.monotonic() + timeout
    previous = None
    stable = 0
    detail = "ファイルの新規作成・更新を確認できませんでした"
    while time.monotonic() < deadline:
        try:
            current = FileState.read(path)
            if current is not None and current != before and current.size > 0:
                stable = stable + 1 if current == previous else 1
                previous = current
                if stable >= 3:
                    read_contents(path)
                    if FileState.read(path) == current:
                        return True, "更新・安定・内容の読取りを確認しました"
                    stable = 0
                detail = "ファイルの安定と内容の読取りを確認できませんでした"
        except (OSError, ValueError, KeyError, configparser.Error, subprocess.SubprocessError) as error:
            detail = str(error)
        time.sleep(interval)
    return False, detail


def save_project(project, video):
    """Issue save once. An uncertain result never becomes a successful save."""
    project = Path(project)
    before = FileState.read(project)
    instruction = _instruction(project, video, "save")
    try:
        send_control(instruction)
        response = _response(instruction)
        if response.get("state") == "failed":
            return OperationResult("failed", _failure_detail(response), project)
        if response.get("state") not in ("requested", "saved"):
            return OperationResult("unconfirmed", "保存を確認できませんでした。編集内容を保持しています", project)
        expected_video = _windows_path(video)
        confirmed, detail = _confirm_file(project, before, lambda path: _read_project(path, expected_video))
        if not confirmed and _response(instruction).get("state") == "failed":
            detail = _failure_detail(_response(instruction))
        return OperationResult("confirmed" if confirmed else "unconfirmed",
                               "保存しました（簡易確認）" if confirmed else f"保存を確認できませんでした: {detail}", project)
    finally:
        _cleanup(instruction)


def _check_video(path, state, settings):
    probe = shutil.which("ffprobe")
    if not probe:
        raise StorageError("出力確認には ffprobe が必要です")
    result = subprocess.run([probe, "-v", "error", "-count_frames", "-show_streams", "-show_format",
                             "-of", "json", str(path)], capture_output=True, text=True, check=True)
    if result.stderr.strip():
        raise StorageError("完成動画の読取りでエラーを検出しました")
    info = json.loads(result.stdout)
    video = next(stream for stream in info["streams"] if stream["codec_type"] == "video")
    audio = next(stream for stream in info["streams"] if stream["codec_type"] == "audio")
    expected = math.ceil(state.duration * settings.fps)
    duration = Fraction(expected, 1) / settings.fps
    if int(video["nb_read_frames"]) != expected:
        raise StorageError("予定したフレーム数まで出力されたことを確認できませんでした")
    if (int(video["width"]), int(video["height"])) != (settings.width, settings.height):
        raise StorageError("出力解像度が設定と一致しません")
    if Fraction(video["avg_frame_rate"]) != settings.fps:
        raise StorageError("出力fpsが設定と一致しません")
    tolerance = max(0.05, float(1 / settings.fps))
    if any(abs(float(value) - float(duration)) > tolerance for value in
           (video["duration"], audio["duration"], info["format"]["duration"])):
        raise StorageError("予定した映像・音声の長さを確認できませんでした")
    if (video["codec_name"] != "h264" or video.get("pix_fmt") != "yuv420p" or
            video.get("color_transfer") != "bt709" or audio["codec_name"] != "aac" or
            audio.get("profile") != "LC" or int(audio["sample_rate"]) != settings.audio_rate):
        raise StorageError("H.264・SDR・AAC-LC・音声サンプルレートが設定と一致しません")


def export_video(project, video, destination, settings, *, cancel: threading.Event,
                 on_progress: Callable[[dict], None] | None = None):
    """Wait for actual host termination before returning or releasing editing."""
    settings.validate()
    destination = Path(destination).resolve()
    if destination.suffix.lower() != ".mp4":
        raise StorageError("完成動画の拡張子は .mp4 を指定してください")
    if destination.exists():
        raise StorageError("既存の完成動画は上書きしません。別の保存名を指定してください")
    ffmpeg = _encoder_path()
    if not shutil.which("ffprobe"):
        raise StorageError("書き出しと確認には ffmpeg・ffprobe が必要です")
    state = inspect_project(project, video)
    if state.busy:
        raise StorageError("AviUtl2で実行中の処理の完了を待ってください")
    if state.dirty is not False:
        raise StorageError("編集プロジェクトを保存してから書き出してください")
    if cancel.is_set():
        return OperationResult("cancelled", "書き出しを中止しました", destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    instruction = _instruction(project, video, "export", output=_windows_path(destination).encode("utf-8").hex(),
                               ffmpeg=ffmpeg.encode("utf-8").hex(), width=settings.width,
                               height=settings.height, rate=settings.fps.numerator, scale=settings.fps.denominator,
                               bitrate=round(settings.bitrate_mbps * 1000000), audio_rate=settings.audio_rate)
    before = FileState.read(destination)
    terminal = False
    try:
        delivery = send_control(instruction)
        response = _response(instruction)
        if not response and delivery != 3:
            terminal = True
            return OperationResult("unconfirmed", "AviUtl2へ書き出しを依頼できませんでした", destination)
        if not response:
            # A timed-out native message may still be running. Keep the operation
            # pending until its terminal response; cancellation remains available.
            if on_progress:
                on_progress({"state": "waiting", "detail": "AviUtl2の応答を確認中です。編集は停止完了まで待ってください"})
        checked_alive = 0.0
        while True:
            if cancel.is_set():
                instruction.with_suffix(".cancel").touch(exist_ok=True)
            response = _response(instruction)
            status = response.get("state")
            if on_progress:
                on_progress(response)
            if status in ("completed", "cancelled", "failed"):
                terminal = True
                break
            if time.monotonic() - checked_alive >= 2:
                checked_alive = time.monotonic()
                if _host_alive(response.get("process_id")) is False:
                    terminal = True
                    return OperationResult("failed", "書き出し中にAviUtl2が終了しました。完成を確認できませんでした", destination)
            time.sleep(0.2)
        if status == "cancelled" or cancel.is_set():
            return OperationResult("cancelled", "書き出しを中止しました。残ったファイルは完成動画として扱いません", destination)
        if status == "failed":
            return OperationResult("failed", _failure_detail(response), destination)
        # Compare against the actual source timeline captured when the host locked.
        state = _project_state(project, response)
        try:
            confirmed, detail = _confirm_file(destination, before,
                lambda path: _check_video(path, state, settings))
        except (StopIteration, TypeError) as error:
            confirmed, detail = False, str(error) or "映像・音声情報が不足しています"
        return OperationResult("confirmed" if confirmed else "unconfirmed",
                               "完成動画を書き出しました（簡易確認）" if confirmed else f"出力を確認できませんでした: {detail}", destination)
    finally:
        if terminal:
            _cleanup(instruction)
