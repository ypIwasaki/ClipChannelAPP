import json
import shutil
import subprocess
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from clipchannel.media import MediaError, prepare_media
from clipchannel.storage import DataFolder


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg tools required")
class MediaTests(unittest.TestCase):
    def test_preserves_source_and_records_stream_timing_across_conversion(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.mkv"
            subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=64x64:rate=10:duration=2",
                            "-itsoffset", "0.4", "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
                            "-map", "0:v", "-map", "1:a", "-c:v", "mpeg4", "-c:a", "pcm_s16le",
                            str(source)], check=True)
            data = DataFolder()
            data.select(root)
            registered = data.register_video(source)
            before = registered.read_bytes()
            result = prepare_media(data, registered)
            self.assertNotEqual(result.editing, registered)
            self.assertEqual(registered.read_bytes(), before)
            self.assertEqual(result.editing_info.video.codec, "h264")
            self.assertEqual(result.editing_info.audio.codec, "aac")
            self.assertGreater(Decimal(result.source_info.audio.start), Decimal(result.source_info.video.start))
            source_gap = Decimal(result.source_info.audio.start) - Decimal(result.source_info.video.start)
            editing_gap = Decimal(result.editing_info.audio.start) - Decimal(result.editing_info.video.start)
            self.assertLess(abs(source_gap - editing_gap), Decimal("0.05"))
            self.assertAlmostEqual(float(result.editing_time(result.source_info.audio.start, "audio")),
                                   float(result.editing_info.audio.start), places=3)
            self.assertEqual(json.loads(result.manifest.read_text(encoding="utf-8"))["source"]["path"],
                             str(registered))

    def test_failed_conversion_keeps_original_and_can_retry(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.mkv"
            subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=64x64:rate=10:duration=1",
                            "-c:v", "mpeg4", str(source)], check=True)
            data = DataFolder()
            data.select(root)
            registered = data.register_video(source)
            ffprobe = shutil.which("ffprobe")
            with patch("clipchannel.media.shutil.which", side_effect=lambda name: None if name == "ffmpeg" else ffprobe):
                with self.assertRaises(MediaError):
                    prepare_media(data, registered)
            self.assertTrue(registered.exists())
            self.assertEqual(list((root / "media" / "prepared" / registered.name).glob("editing-*.mp4")), [])
            self.assertTrue(prepare_media(data, registered).editing.exists())


if __name__ == "__main__":
    unittest.main()
