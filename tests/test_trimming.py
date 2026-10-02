import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from clipchannel import trimming
from clipchannel.media import _probe
from clipchannel.storage import DataFolder, VideoNameConflict
from clipchannel.trimming import boundaries, destination, history, trim_video, publish_trim, cleanup_staged
from clipchannel.trimming_ui import TrimmingPanel


class Control:
    def __init__(self, cancel=False):
        self.cancel = cancel

    def cancelled(self):
        return self.cancel

    def report(self, _message):
        pass


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "ffmpeg required")
class TrimmingTests(unittest.TestCase):
    def test_portrait_preview_fits_viewer_without_cropping(self):
        import tkinter as tk
        with tempfile.TemporaryDirectory() as root:
            data = DataFolder()
            data.select(root)
            source = Path(root) / "portrait.mp4"
            subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i",
                            "testsrc2=size=180x320:rate=10:duration=1", "-c:v", "libx264",
                            str(source)], check=True)
            data.register_video(source)
            window = tk.Tk()
            window.geometry("900x600")
            try:
                panel = TrimmingPanel(window, data, None, lambda: None)
                panel.pack(fill="both", expand=True)
                panel.refresh()
                window.after(1200, window.quit)
                window.mainloop()
                self.assertIsNotNone(panel.image)
                self.assertLessEqual(panel.image.height(), panel.screen.winfo_height())
                self.assertLessEqual(panel.image.width(), panel.screen.winfo_width())
                self.assertAlmostEqual(panel.image.width() / panel.image.height(), 180 / 320, delta=.02)
                panel._play(0, .8)
                window.after(500, window.quit)
                window.mainloop()
                self.assertLessEqual(panel.image.height(), panel.screen.winfo_height())
                self.assertAlmostEqual(panel.image.width() / panel.image.height(), 180 / 320, delta=.02)
            finally:
                window.destroy()

    def test_embedded_preview_advances_in_app(self):
        import tkinter as tk
        with tempfile.TemporaryDirectory() as root:
            data = DataFolder()
            data.select(root)
            source = Path(root) / "preview.mp4"
            subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i",
                            "testsrc2=size=64x64:rate=10:duration=2", "-c:v", "libx264",
                            str(source)], check=True)
            data.register_video(source)
            window = tk.Tk()
            try:
                panel = TrimmingPanel(window, data, None, lambda: None)
                panel.pack()
                panel.refresh()
                window.after(1200, window.quit)
                window.mainloop()
                self.assertIsNotNone(panel.image, "静止画プレビュー")
                still = panel.image
                panel._play(0, 2)
                window.after(1200, window.quit)
                window.mainloop()
                self.assertIsNotNone(panel.image, f"position={panel.position.get()} playing={panel.playing} process={panel.video_process}")
                self.assertIsNot(panel.image, still)
                self.assertGreater(panel.position.get(), 0)
            finally:
                window.destroy()

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
            staged = trim_video(Control(), data, original, "first.mp4", start, end)
            self.assertNotIn("first.mp4", [path.name for path in data.list_videos()])
            first = publish_trim(data, staged)
            self.assertTrue(first in data.list_videos())
            self.assertAlmostEqual(float(_probe(first).duration), 1.2, delta=0.15)
            self.assertIsNotNone(_probe(first).audio)
            def frame(path, at):
                return subprocess.run(["ffmpeg", "-v", "error", "-ss", str(at), "-i", str(path),
                                       "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"],
                                      capture_output=True, check=True).stdout
            expected = frame(original, .9)
            actual = frame(first, 0)
            self.assertEqual(len(actual), len(expected))
            self.assertLess(sum(abs(a - b) for a, b in zip(actual, expected)) / len(actual), 20)
            with self.assertRaises(VideoNameConflict):
                destination(data, "first.mp4")
            second = publish_trim(data, trim_video(Control(), data, first, "second.mp4",
                                                  *boundaries(data, first, .2, .8)))
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
            staged = trim_video(Control(), data, original, "abandoned.mp4", start, end)
            other = Path(root) / "work" / "trim-other-instance"
            other.mkdir()
            cleanup_staged(data, staged["work"])
            self.assertFalse(Path(staged["work"]).exists())
            self.assertTrue(other.is_dir())
            self.assertNotIn("abandoned.mp4", [path.name for path in data.list_videos()])
            result = publish_trim(data, trim_video(Control(), data, original, "silent_trim.mp4", start, end))
            self.assertIsNone(_probe(result).audio)

    def test_nonzero_video_start_uses_relative_input_seconds(self):
        with tempfile.TemporaryDirectory() as root:
            data = DataFolder()
            data.select(root)
            source = Path(root) / "offset.mp4"
            subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i",
                            "testsrc2=size=64x64:rate=10:duration=2", "-vf", "setpts=PTS+5/TB",
                            "-copyts", "-c:v", "libx264", str(source)], check=True)
            original = data.register_video(source)
            self.assertGreater(float(_probe(original).video.start), 4)
            start, end = boundaries(data, original, .2, 1.2)
            self.assertGreater(start, 5000)
            result = publish_trim(data, trim_video(Control(), data, original, "offset_trim.mp4", start, end))
            self.assertAlmostEqual(float(_probe(result).duration), 1, delta=.15)

    def test_late_audio_retains_silence_before_it_starts(self):
        with tempfile.TemporaryDirectory() as root:
            data = DataFolder()
            data.select(root)
            source = Path(root) / "late_audio.mp4"
            subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i",
                            "testsrc2=size=64x64:rate=10:duration=2", "-itsoffset", "0.5",
                            "-f", "lavfi", "-i", "sine=frequency=440:duration=1.5",
                            "-c:v", "libx264", "-c:a", "aac", str(source)], check=True)
            original = data.register_video(source)
            self.assertGreater(float(_probe(original).audio.start), .4)
            start, end = boundaries(data, original, 0, 1.2)
            result = publish_trim(data, trim_video(Control(), data, original, "late_trim.mp4", start, end))
            self.assertIsNotNone(_probe(result).audio)
            self.assertAlmostEqual(float(_probe(result).duration), 1.2, delta=.15)
            def amplitude(at):
                process = subprocess.run(["ffmpeg", "-v", "error", "-ss", str(at), "-i", str(result),
                                          "-t", "0.2", "-vn", "-c:a", "pcm_s16le", "-f", "s16le", "-ac", "1", "-ar", "16000", "pipe:1"],
                                         capture_output=True)
                self.assertEqual(process.returncode, 0, process.stderr.decode())
                pcm = process.stdout
                from array import array
                samples = array("h")
                samples.frombytes(pcm)
                return sum(abs(sample) for sample in samples) / max(1, len(samples))
            self.assertLess(amplitude(.1), 30)
            self.assertGreater(amplitude(.7), 500)

    def test_variable_frame_rate_preserves_requested_times_without_frame_scan(self):
        with tempfile.TemporaryDirectory() as root:
            data = DataFolder()
            data.select(root)
            source = Path(root) / "variable.mp4"
            subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i",
                            "testsrc2=size=64x64:rate=10:duration=2",
                            "-vf", "setpts=PTS+if(gte(N\\,10)\\,0.3/TB\\,0)",
                            "-fps_mode", "vfr", "-c:v", "libx264", str(source)], check=True)
            original = data.register_video(source)
            start, end = boundaries(data, original, 1.05, 1.55)
            self.assertEqual((start, end), (1050, 1550))
            result = publish_trim(data, trim_video(Control(), data, original, "variable_trim.mp4", start, end))
            self.assertGreater(float(_probe(result).duration), .2)

    def test_export_confirms_and_starts_on_first_click(self):
        import tkinter as tk
        from unittest.mock import Mock
        with tempfile.TemporaryDirectory() as root:
            data = DataFolder()
            data.select(root)
            source = Path(root) / "source.mp4"
            subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i",
                            "testsrc2=size=64x64:rate=10:duration=2", "-c:v", "libx264",
                            str(source)], check=True)
            data.register_video(source)
            window = tk.Tk()
            try:
                process_panel = Mock()
                panel = TrimmingPanel(window, data, process_panel, lambda: None)
                panel.pack()
                panel.refresh()
                panel.start.set("0.200")
                panel.end.set("1.200")
                panel.export()
                process_panel.start.assert_called_once()
            finally:
                window.destroy()

    def test_publish_collision_keeps_other_video(self):
        with tempfile.TemporaryDirectory() as root:
            data = DataFolder()
            data.select(root)
            work = Path(root) / "work" / "trim-owned"
            work.mkdir()
            (work / "result.mp4").write_bytes(b"staged")
            (work / "trim.json").write_text("{}")
            target = Path(root) / "media" / "originals" / "new.mp4"
            target.parent.mkdir()
            original_publish = trimming._publish_new
            def collision(staged, destination):
                if destination == target:
                    target.write_bytes(b"other-instance")
                    raise FileExistsError("collision")
                return original_publish(staged, destination)
            with patch("clipchannel.trimming._publish_new", side_effect=collision):
                with self.assertRaises(FileExistsError):
                    publish_trim(data, {"work": str(work), "name": "new.mp4"})
            self.assertEqual(target.read_bytes(), b"other-instance")
            self.assertFalse((target.parent / ".new.mp4.trim.json").exists())
