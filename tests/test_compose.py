import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from clipchannel.compose import compose_video, nearest_frame
from clipchannel.media import _probe
from clipchannel.segments import Segment


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "ffmpeg required")
class ComposeTest(unittest.TestCase):
    def test_repeat_order_and_versioned_output(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            original = root / "media" / "originals"
            original.mkdir(parents=True)
            (root / "work").mkdir()
            source = original / "sample.mp4"
            subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-f", "lavfi", "-i",
                            "testsrc2=size=160x90:rate=10:duration=2", "-f", "lavfi", "-i",
                            "sine=frequency=440:duration=2", "-c:v", "libx264", "-c:a", "aac",
                            str(source)], check=True)
            data = SimpleNamespace(path=root)
            rows = [Segment(0, 500, "manual"), Segment(1000, 1500, "manual")]
            first = compose_video(data, source, rows, [1, 0, 1], 2000, fps=10)
            second = compose_video(data, source, rows, [1, 0, 1], 2000, fps=10)
            self.assertNotEqual(first, second)
            self.assertTrue(first.exists())
            self.assertEqual(_probe(first).video.codec, "h264")
            self.assertEqual(_probe(first).audio.codec, "aac")
            self.assertAlmostEqual(float(_probe(first).duration), 1.5, delta=0.15)
            frame, difference = nearest_frame(source, 1020)
            self.assertAlmostEqual(frame, 1000, delta=2)
            self.assertEqual(difference, frame - 1020)
