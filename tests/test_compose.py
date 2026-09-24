import shutil
import subprocess
import tempfile
import unittest
import wave
from array import array
from pathlib import Path
from types import SimpleNamespace

from clipchannel.compose import compose_video, is_variable_fps, nearest_frame, probe_frames
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
            self.assertFalse(is_variable_fps(source))
            pcm = root / "audio.wav"
            subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-i", str(first),
                            "-vn", "-ac", "1", "-c:a", "pcm_s16le", str(pcm)], check=True)
            with wave.open(str(pcm)) as audio:
                samples = array("h", audio.readframes(audio.getnframes()))
                rate = audio.getframerate()
            # Both sides of each concat seam contain audible source signal.
            for seam in (0.5, 1.0):
                for offset in (-0.025, 0.025):
                    center = round((seam + offset) * rate)
                    self.assertGreater(max(abs(value) for value in samples[center - 100:center + 100]), 100)

    def test_variable_rate_source_requires_explicit_fixed_rate_in_ui(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            original = root / "media" / "originals"
            original.mkdir(parents=True)
            (root / "work").mkdir()
            source = original / "vfr.mp4"
            subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-f", "lavfi", "-i",
                            "testsrc2=size=160x90:rate=10:duration=2", "-vf",
                            "select='not(eq(mod(n,3),0))'", "-fps_mode", "vfr", "-c:v", "libx264",
                            str(source)], check=True)
            average, nominal, _, _ = probe_frames(source)
            self.assertNotEqual(average, nominal)
            self.assertTrue(is_variable_fps(source))
            output = compose_video(SimpleNamespace(path=root), source,
                                   [Segment(0, 1500, "manual")], [0], 2000, fps=10)
            self.assertFalse(is_variable_fps(output))
