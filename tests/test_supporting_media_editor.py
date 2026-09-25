"""Opt-in integration test against an isolated AviUtl2 with the built plugin.

Set CLIPCHANNEL_TEST_AVIUTL to that installation's aviutl2.exe on Windows.
The test creates its own data/project and stops only its own host process.
"""

import array
import json
import math
import os
import subprocess
import tempfile
import time
import unittest
from dataclasses import replace
from pathlib import Path

from clipchannel.editor_bridge import apply_supporting_media
from clipchannel.storage import DataFolder
from clipchannel.supporting_media import import_supporting_media, save_supporting_media


@unittest.skipUnless(os.name == "nt" and os.environ.get("CLIPCHANNEL_TEST_AVIUTL"),
                     "requires a dedicated Windows AviUtl2 installation with the built plugin")
class SupportingMediaEditorTest(unittest.TestCase):
    def test_image_placement_and_mixed_audio_can_be_adjusted_without_duplicate_objects(self):
        with tempfile.TemporaryDirectory(prefix="clipchannel-media-test-") as temporary:
            root = Path(temporary)
            data = DataFolder()
            data.select(root)
            video = root / "media" / "edits" / "take1" / "A1_B2.mp4"
            video.parent.mkdir(parents=True)
            subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i",
                            "color=black:size=160x90:rate=10:duration=4", "-c:v", "libx264",
                            "-pix_fmt", "yuv420p", str(video)], check=True)
            video.with_suffix(".json").write_text(json.dumps(
                {"fps": "10", "frame_counts": [20, 20]}), encoding="utf-8")
            project = root / "projects" / "take1" / "edit.aup2"
            project.parent.mkdir(parents=True)
            project.write_text(
                "[project]\nversion=2010900\nfile=" + str(project) +
                "\ndisplay.scene=0\npreview.scene=0\n[scene.0]\nscene=0\nname=Root\n"
                "video.width=160\nvideo.height=90\nvideo.rate=10\nvideo.scale=1\naudio.rate=48000\n"
                "[0]\nlayer=0\nframe=0,39\n[0.0]\neffect.name=動画ファイル\nファイル=" + str(video) +
                "\n再生位置=0.000,4.000,再生範囲,0\n再生速度=100.00\n音声付き=0\n"
                "[0.1]\neffect.name=映像再生\n拡大率=100.000\n", encoding="utf-8")
            startup = subprocess.STARTUPINFO()
            startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startup.wShowWindow = 0
            host = subprocess.Popen([os.environ["CLIPCHANNEL_TEST_AVIUTL"], str(project)], startupinfo=startup)
            try:
                source = root / "画像.png"
                subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=red:size=20x20",
                                "-frames:v", "1", str(source)], check=True)
                image = import_supporting_media(data, video, source, "image")
                path = save_supporting_media(data, image)
                deadline = time.monotonic() + 30
                while time.monotonic() < deadline:
                    result = apply_supporting_media(path)
                    if result:
                        break
                    time.sleep(0.5)
                self.assertEqual(result, "preview", "AviUtl2 bridge did not apply the image")

                def pixels(instruction):
                    raw = instruction.with_suffix(".ppm").read_bytes().split(b"\n", 3)
                    self.assertEqual(raw[1], b"160 90")
                    return raw[3]

                def red_at(picture, x, y):
                    offset = (y * 160 + x) * 3
                    red, green, blue = picture[offset:offset + 3]
                    return red > 180 and green < 50 and blue < 50

                self.assertTrue(red_at(pixels(path), 80, 45))
                moved = save_supporting_media(data, replace(image, x=40, scale=50))
                self.assertEqual(apply_supporting_media(moved), "preview")
                self.assertFalse(red_at(pixels(moved), 80, 45))
                self.assertTrue(red_at(pixels(moved), 120, 45))

                audio = root / "BGM.wav"
                subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i",
                                "sine=frequency=440:sample_rate=48000:duration=6", str(audio)], check=True)
                bgm = import_supporting_media(data, video, audio, "bgm")
                self.assertEqual(bgm.length, 60)
                path = save_supporting_media(data, replace(bgm, first=10))
                self.assertEqual(apply_supporting_media(path), "preview")

                def samples(instruction):
                    rendered = subprocess.run(["ffmpeg", "-v", "error", "-i",
                        str(instruction.with_suffix(".wav")), "-f", "f32le", "-ac", "1", "-"],
                        capture_output=True, check=True)
                    values = array.array("f")
                    values.frombytes(rendered.stdout)
                    self.assertEqual(len(values), 192000)  # Ends with the four-second video.
                    return values

                def rms(values, start, end):
                    part = values[int(start * 48000):int(end * 48000)]
                    return math.sqrt(sum(value * value for value in part) / len(part))

                first = samples(path)
                self.assertLess(rms(first, 0, 0.9), 0.0001)
                for start, end in ((1.1, 1.9), (2.1, 2.9), (3.1, 3.9)):
                    self.assertGreater(rms(first, start, end), 0.06)
                adjusted = save_supporting_media(data, replace(bgm, first=20, length=40, offset=2, volume=25))
                self.assertEqual(apply_supporting_media(adjusted), "preview")
                second = samples(adjusted)
                self.assertLess(rms(second, 1.1, 1.9), 0.0001)
                self.assertAlmostEqual(rms(second, 2.1, 2.9) / rms(first, 2.1, 2.9), 0.25, delta=0.02)

                # A sound effect is a distinct placement, added to the scene's BGM mix.
                effect = import_supporting_media(data, video, audio, "sound")
                sound = save_supporting_media(data, replace(effect, first=30, length=10, volume=25))
                self.assertEqual(apply_supporting_media(sound), "preview")
                mixed = samples(sound)
                self.assertAlmostEqual(rms(mixed, 3.1, 3.9) / rms(first, 3.1, 3.9), 0.5, delta=0.02)
            finally:
                host.terminate()
                host.wait(timeout=10)
