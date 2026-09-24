import tempfile
import unittest
from pathlib import Path

from clipchannel.layout import Layout, save_layout
from clipchannel.storage import DataFolder, StorageError


class LayoutTest(unittest.TestCase):
    def test_ratio_change_preserves_placements_and_each_save_is_a_new_version(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            data = DataFolder()
            data.select(root)
            video = root / "media" / "edits" / "take1" / "edit.mp4"
            video.parent.mkdir(parents=True)
            video.write_bytes(b"video")
            horizontal = Layout(1920, 1080, x=75, y=-20, subtitle_y=320)
            first = save_layout(data, video, horizontal, 1920, 1080)
            short = Layout(1080, 1920, x=horizontal.x, y=horizontal.y,
                           subtitle_y=horizontal.subtitle_y)
            second = save_layout(data, video, short, 1920, 1080)
            self.assertNotEqual(first, second)
            self.assertIn("width\t1920", first.read_text(encoding="ascii"))
            self.assertIn("width\t1080", second.read_text(encoding="ascii"))
            self.assertIn("x\t75", second.read_text(encoding="ascii"))
            self.assertIn("subtitle_y\t320", second.read_text(encoding="ascii"))

    def test_invalid_crop_is_refused(self):
        with self.assertRaises(StorageError):
            Layout(1080, 1920, crop_left=100, crop_right=100).validate(160, 90)
