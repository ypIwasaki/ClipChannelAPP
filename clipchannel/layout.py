"""Versioned screen and subtitle settings for one editing video."""

import math
from dataclasses import dataclass
from pathlib import Path

from .storage import StorageError


@dataclass(frozen=True)
class Layout:
    width: int
    height: int
    scale: float = 100.0
    x: float = 0.0
    y: float = 0.0
    crop_left: int = 0
    crop_top: int = 0
    crop_right: int = 0
    crop_bottom: int = 0
    subtitle_x: float = 0.0
    subtitle_y: float = 350.0
    subtitle_size: int = 40
    preview_frame: int = 0

    def validate(self, video_width, video_height):
        numbers = (self.scale, self.x, self.y, self.subtitle_x, self.subtitle_y)
        if any(not math.isfinite(value) for value in numbers):
            raise StorageError("画面設定には有限の数値を入力してください")
        if not (1 <= self.width <= 8192 and 1 <= self.height <= 8192):
            raise StorageError("画面の幅・高さが範囲外です")
        if not (1 <= self.scale <= 1000) or not (1 <= self.subtitle_size <= 300):
            raise StorageError("拡大率または字幕サイズが範囲外です")
        if self.preview_frame < 0:
            raise StorageError("プレビューフレームが不正です")
        crops = (self.crop_left, self.crop_top, self.crop_right, self.crop_bottom)
        if any(value < 0 for value in crops) or self.crop_left + self.crop_right >= video_width or self.crop_top + self.crop_bottom >= video_height:
            raise StorageError("切り取り量が動画の大きさを超えています")


def save_layout(data, edit_video, layout, video_width, video_height):
    """Create a new instruction version; never replace a previous layout."""
    edit_video = Path(edit_video).resolve()
    root = data._root()
    if not edit_video.is_file() or not edit_video.is_relative_to(root / "media" / "edits"):
        raise StorageError("データ用フォルダ内の編集用動画を選んでください")
    layout.validate(video_width, video_height)
    folder = root / "projects" / edit_video.parent.name
    folder.mkdir(parents=True, exist_ok=True)
    number = 1
    while (folder / f"{edit_video.stem}_layout_v{number}.cclayout").exists():
        number += 1
    path = folder / f"{edit_video.stem}_layout_v{number}.cclayout"
    fields = ("width", "height", "scale", "x", "y", "crop_left", "crop_top",
              "crop_right", "crop_bottom", "subtitle_x", "subtitle_y", "subtitle_size",
              "preview_frame")
    lines = ["ClipChannel-Layout-1", f"video\t{str(edit_video).encode('utf-8').hex()}"]
    lines += [f"{name}\t{getattr(layout, name)}" for name in fields]
    with path.open("x", encoding="ascii", newline="\n") as output:
        output.write("\n".join(lines) + "\n")
    return path
