import json
import shutil
import subprocess
import tempfile
import unittest
import wave
from array import array
from pathlib import Path
from types import SimpleNamespace

from clipchannel.compose import adjacent_frame, compose_video, is_variable_fps, nearest_frame, probe_frames
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
            source_streams = subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-of", "json",
                                             str(source)], capture_output=True, text=True, check=True)
            output_streams = subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-of", "json",
                                             str(first)], capture_output=True, text=True, check=True)
            source_info = json.loads(source_streams.stdout)["streams"]
            output_info = json.loads(output_streams.stdout)["streams"]
            self.assertEqual((output_info[0]["width"], output_info[0]["height"]),
                             (source_info[0]["width"], source_info[0]["height"]))
            self.assertEqual(output_info[1]["sample_rate"], source_info[1]["sample_rate"])
            self.assertAlmostEqual(float(_probe(first).duration), 1.5, delta=0.15)
            frames = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                                     "-show_entries", "frame=best_effort_timestamp_time", "-of", "csv=p=0",
                                     str(first)], capture_output=True, text=True, check=True)
            timestamps = [float(line.strip().rstrip(",")) for line in frames.stdout.splitlines()
                          if line.strip().rstrip(",")]
            self.assertEqual(len(timestamps), 15)
            for seam in (5, 10):
                self.assertAlmostEqual(timestamps[seam] - timestamps[seam - 1], 0.1, delta=0.002)
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
            self.assertEqual(adjacent_frame(source, 200, 1), 400)
            with self.assertRaisesRegex(ValueError, "固定fps"):
                compose_video(SimpleNamespace(path=root), source,
                              [Segment(0, 1500, "manual")], [0], 2000)
            output = compose_video(SimpleNamespace(path=root), source,
                                   [Segment(0, 1500, "manual")], [0], 2000, fps=10)
            self.assertFalse(is_variable_fps(output))

    def test_nearest_frame_with_long_keyframe_interval(self):
        with tempfile.TemporaryDirectory() as root:
            source = Path(root) / "long-gop.mp4"
            subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-f", "lavfi", "-i",
                            "testsrc2=size=64x64:rate=10:duration=20", "-c:v", "libx264",
                            "-g", "100", "-keyint_min", "100", "-sc_threshold", "0", str(source)], check=True)
            frame, difference = nearest_frame(source, 18220)
            self.assertEqual(frame, 18200)
            self.assertEqual(difference, -20)
