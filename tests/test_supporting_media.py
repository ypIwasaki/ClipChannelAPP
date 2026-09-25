import json
import base64
import tempfile
import unittest
import wave
from dataclasses import replace
from pathlib import Path

from clipchannel.storage import DataFolder, StorageError
from clipchannel.supporting_media import import_supporting_media, save_supporting_media


class SupportingMediaTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.data = DataFolder()
        self.data.select(self.root)
        self.video = self.root / "media" / "edits" / "take1" / "A1_B2.mp4"
        self.video.parent.mkdir(parents=True)
        self.video.write_bytes(b"video")
        self.video.with_suffix(".json").write_text(json.dumps(
            {"fps": "10", "frame_counts": [20, 20]}), encoding="utf-8")

    def audio(self, name="music.wav"):
        source = self.root / name
        with wave.open(str(source), "wb") as stream:
            stream.setnchannels(1)
            stream.setsampwidth(2)
            stream.setframerate(8000)
            stream.writeframes(b"\x10\x00" * 48000)
        return source

    def test_bgm_is_copied_and_keeps_full_length_across_join_and_video_end(self):
        source = self.audio()
        original = source.read_bytes()
        placement = import_supporting_media(self.data, self.video, source, "bgm")
        self.assertTrue(placement.asset.is_relative_to(self.root / "media" / "supporting"))
        self.assertEqual(placement.asset.read_bytes(), original)
        self.assertEqual(source.read_bytes(), original)
        self.assertEqual(placement.video, self.video)
        self.assertEqual(placement.length, 60)  # Six seconds; the video is four seconds.
        self.assertEqual(placement.first, 0)

    def test_adjustment_keeps_identity_and_versions_without_trimming_at_join(self):
        placement = import_supporting_media(self.data, self.video, self.audio(), "bgm")
        first = save_supporting_media(self.data, placement, preview_frame=10)
        changed = replace(placement, first=10, length=50, offset=1, volume=25)
        second = save_supporting_media(self.data, changed, preview_frame=25)
        self.assertNotEqual(first, second)
        self.assertIn("length\t60\n", first.read_text(encoding="ascii"))
        instruction = second.read_text(encoding="ascii")
        self.assertIn("identity\t" + placement.identity + "\n", instruction)
        self.assertIn("first\t10\nlength\t50\n", instruction)
        self.assertIn("offset\t1\nvolume\t25\n", instruction)
        self.assertEqual(second.parent, self.root / "projects" / "take1")
        self.assertIn("video\t" + str(self.video).encode("utf-8").hex(), instruction)

    def test_invalid_adjustments_and_cross_edit_assets_are_rejected_before_writing(self):
        placement = import_supporting_media(self.data, self.video, self.audio(), "sound")
        for changes in ({"first": -1}, {"length": 0}, {"first": 40},
                        {"volume": float("nan")}, {"offset": 7}, {"scale": 0},
                        {"length": 61}, {"identity": "../escape"}):
            with self.subTest(changes=changes), self.assertRaises(StorageError):
                save_supporting_media(self.data, replace(placement, **changes))
        other = self.video.parent.parent / "take2" / "B2_A1.mp4"
        other.parent.mkdir()
        other.write_bytes(b"other edit")
        other.with_suffix(".json").write_bytes(self.video.with_suffix(".json").read_bytes())
        with self.assertRaises(StorageError):
            save_supporting_media(self.data, replace(placement, video=other))
        self.assertEqual(list((self.root / "projects").rglob("*.ccmedia")), [])

    def test_same_named_images_and_new_edits_keep_separate_copies_and_placements(self):
        source = self.root / "画像.png"
        source.write_bytes(base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII="))
        first = import_supporting_media(self.data, self.video, source, "image")
        old = save_supporting_media(self.data, replace(first, x=12, y=-8, scale=50))
        old_contents = old.read_bytes()
        second = import_supporting_media(self.data, self.video, source, "image")
        other_video = self.video.parent.parent / "take2" / "B2_A1.mp4"
        other_video.parent.mkdir()
        other_video.write_bytes(b"new video")
        other_video.with_suffix(".json").write_bytes(self.video.with_suffix(".json").read_bytes())
        third = import_supporting_media(self.data, other_video, source, "image")
        self.assertEqual(len({first.asset, second.asset, third.asset}), 3)
        self.assertEqual((third.first, third.x, third.y, third.scale), (0, 0, 0, 100))
        self.assertEqual(first.asset.read_bytes(), source.read_bytes())
        self.assertEqual(old.read_bytes(), old_contents)
