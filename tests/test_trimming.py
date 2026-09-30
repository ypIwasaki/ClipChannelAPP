import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from clipchannel.media import _probe
from clipchannel.storage import DataFolder, VideoNameConflict
from clipchannel.trimming import boundaries, destination, history, trim_video


class Control:
    def __init__(self, cancel=False):
        self.cancel = cancel

    def cancelled(self):
        return self.cancel

    def report(self, _message):
        pass


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "ffmpeg required")
class TrimmingTests(unittest.TestCase):
    def test_video_audio_history_and_conflict(self):
        with tempfile.TemporaryDirectory() as root:
            data = DataFolder()
            data.select(root)
            source = Path(root) / "source.mp4"
            subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i",
                            "testsrc2=size=64x64:rate=10:duration=3", "-f", "lavfi", "-i",
                            "sine=frequency=440:duration=3", "-c:v", "libx264", "-c:a", "aac",
                            "-shortest", str(source)], check=True)
            original = data.register_video(source)
            start, end = boundaries(data, original, 0.9, 2.1)
            self.assertEqual((start, end), (900, 2100))
            first = trim_video(Control(), data, original, "first.mp4", start, end)
            self.assertTrue(first in data.list_videos())
            self.assertAlmostEqual(float(_probe(first).duration), 1.2, delta=0.15)
            self.assertIsNotNone(_probe(first).audio)
            with self.assertRaises(VideoNameConflict):
                destination(data, "first.mp4")
            second = trim_video(Control(), data, first, "second.mp4", *boundaries(data, first, .2, .8))
            self.assertEqual([row["parent"] for row in history(data, second)], ["first.mp4", "source.mp4"])

    def test_silent_video_and_cancel_do_not_register(self):
        with tempfile.TemporaryDirectory() as root:
            data = DataFolder()
            data.select(root)
            source = Path(root) / "silent.mp4"
            subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i",
                            "testsrc2=size=64x64:rate=10:duration=2", "-c:v", "libx264",
                            str(source)], check=True)
            original = data.register_video(source)
            start, end = boundaries(data, original, .2, 1.2)
            with self.assertRaises(Exception):
                trim_video(Control(True), data, original, "cancelled.mp4", start, end)
            self.assertNotIn("cancelled.mp4", [path.name for path in data.list_videos()])
            result = trim_video(Control(), data, original, "silent_trim.mp4", start, end)
            self.assertIsNone(_probe(result).audio)
