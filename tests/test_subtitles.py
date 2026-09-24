import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from clipchannel.storage import DataFolder
from clipchannel.compose import compose_video
from clipchannel.segments import Segment
from clipchannel.subtitles import Subtitle, map_subtitles, prepare_subtitle_import
from clipchannel.transcribe import Interval


class SubtitleImportTest(unittest.TestCase):
    def test_clip_repeat_and_target_only(self):
        spoken = [Interval(100, 600, "target", text="最初"),
                  Interval(900, 1400, "target", text="また"),
                  Interval(200, 350, "non-target"),
                  Interval(1300, 1700, "unknown")]
        result = map_subtitles(spoken, [(0, 500), (1000, 1500), (0, 500)], "10", [5, 5, 5])
        self.assertEqual(result, [Subtitle(1, 4, "最初"), Subtitle(5, 8, "また"),
                                  Subtitle(11, 14, "最初")])

    def test_new_import_keeps_prior_version_and_source_csv(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            data = DataFolder()
            data.select(root)
            source = root / "media" / "originals" / "日本語.mp4"
            source.parent.mkdir()
            source.write_bytes(b"source")
            edit = root / "media" / "edits" / "take1" / "日本語.mp4"
            edit.parent.mkdir()
            edit.write_bytes(b"rendered")
            edit.with_suffix(".json").write_text(json.dumps({
                "source": str(source), "spans_ms": [[0, 1000]], "fps": "10",
                "frame_counts": [10]
            }), encoding="utf-8")
            transcript = data.save_result(source, "transcripts", [{
                "start_ms": "100", "end_ms": "900", "text": "字幕\n二行", "speaker_id": "target"
            }])
            original = transcript.read_bytes()
            first, subtitles = prepare_subtitle_import(data, source, edit, 1)
            second, _ = prepare_subtitle_import(data, source, edit, 1)
            self.assertNotEqual(first, second)
            self.assertEqual(transcript.read_bytes(), original)
            self.assertEqual(subtitles, [Subtitle(1, 8, "字幕\n二行")])
            self.assertIn("e5ad97e5b9950ae4ba8ce8a18c", first.read_text(encoding="ascii"))

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "ffmpeg required")
    def test_composed_video_and_repeated_subtitles_share_frame_timeline(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            data = DataFolder()
            data.select(root)
            source = root / "media" / "originals" / "source.mp4"
            source.parent.mkdir()
            subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-f", "lavfi", "-i",
                            "testsrc2=size=160x90:rate=10:duration=2", "-c:v", "libx264",
                            str(source)], check=True)
            data.save_result(source, "transcripts", [{
                "start_ms": "100", "end_ms": "600", "text": "発言", "speaker_id": "target"
            }])
            segments = [Segment(0, 500, "manual"), Segment(1000, 1500, "manual")]
            edit = compose_video(data, source, segments, [0, 1, 0], 2000, fps=10)
            _, rows = prepare_subtitle_import(data, source, edit, 1)
            self.assertEqual(rows, [Subtitle(1, 4, "発言"), Subtitle(11, 14, "発言")])
            probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                                    "-count_frames", "-show_entries", "stream=nb_read_frames",
                                    "-of", "default=noprint_wrappers=1:nokey=1", str(edit)],
                                   capture_output=True, text=True, check=True)
            self.assertEqual(int(probe.stdout.strip()), 15)
