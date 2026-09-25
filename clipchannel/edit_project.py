"""Create a fresh AviUtl2 project for one newly composed editing video."""

import subprocess
from fractions import Fraction
from pathlib import Path

from .editor_bridge import windows_path
from .storage import StorageError


def _project_reference(path):
    if any(character in str(path) for character in "\r\n\0"):
        raise StorageError("AviUtl2用のファイル名に改行などの制御文字は使用できません")
    try:
        value = windows_path(path)
    except (OSError, subprocess.SubprocessError) as error:
        raise StorageError("AviUtl2用のファイル参照を作れませんでした") from error
    if not value or any(character in value for character in "\r\n\0"):
        raise StorageError("AviUtl2用のファイル名に改行などの制御文字は使用できません")
    return value


def write_edit_project(destination, video, project, *, width, height, fps, frames,
                       audio_rate=48000, has_audio=True) -> Path:
    """Write only the new video; references point to final, not staged paths.

    The caller owns staging and publication of the video/project pair. No old
    project or placement data is read, and an existing destination is never
    overwritten.
    """
    try:
        rate = Fraction(fps)
    except (TypeError, ValueError, ZeroDivisionError, OverflowError) as error:
        raise StorageError("編集用動画のfpsが不正です") from error
    if (isinstance(fps, bool) or rate <= 0 or
            any(type(value) is not int or not 0 < value <= 2147483647
                for value in (width, height, frames, audio_rate, rate.numerator, rate.denominator)) or
            type(has_audio) is not bool):
        raise StorageError("編集用動画の画面設定・長さ・音声設定が不正です")
    destination, project = Path(destination), Path(project)
    if destination.suffix.lower() != ".aup2" or project.suffix.lower() != ".aup2":
        raise StorageError("AviUtl2プロジェクトの拡張子は .aup2 を指定してください")
    video_reference = _project_reference(video)
    project_reference = _project_reference(project)
    duration = float(Fraction(frames, 1) / rate)
    content = (
        "[project]\nversion=2010900\n"
        f"file={project_reference}\ndisplay.scene=0\npreview.scene=0\n"
        "[scene.0]\nscene=0\nname=Root\n"
        f"video.width={width}\nvideo.height={height}\n"
        f"video.rate={rate.numerator}\nvideo.scale={rate.denominator}\n"
        f"audio.rate={audio_rate}\n"
        f"[0]\nlayer=0\nframe=0,{frames - 1}\n"
        "[0.0]\neffect.name=動画ファイル\n"
        f"ファイル={video_reference}\n再生位置=0.000,{duration:.9f},再生範囲,0\n"
        f"再生速度=100.00\n音声付き={int(has_audio)}\n"
        "[0.1]\neffect.name=映像再生\n拡大率=100.000\n音量=100.00\n"
    )
    with destination.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(content)
    return destination
