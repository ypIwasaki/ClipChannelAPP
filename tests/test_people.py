import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from clipchannel import DataFolder
from clipchannel.people import PersonError, list_people, register_person, select_target, target_for_video


@unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg is needed for reference conversion")
class PersonTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.folder = self.root / "data"
        self.folder.mkdir()
        self.data = DataFolder()
        self.data.select(self.folder)
        self.model = self.root / "model"
        self.model.mkdir()
        (self.model / "hyperparams.yaml").write_text("local model fixture", encoding="utf-8")
        self.audio = self.root / "source.wav"
        subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i",
                        "sine=frequency=440:duration=2", "-y", str(self.audio)], check=True)

    @staticmethod
    def fake_encoder(audio, model_dir, cache, split):
        assert audio.is_file() and model_dir.is_dir() and cache.is_dir()
        return [0.5] * 192

    def test_audio_file_registration_survives_reopen_and_keeps_external_source(self):
        person = register_person(self.data, "話者A", self.audio, self.model, 0.25,
                                 "whole-reference", encoder=self.fake_encoder)
        self.assertEqual(self.audio.read_bytes()[:4], b"RIFF")
        self.assertTrue(person.reference_audio.is_file())
        self.assertEqual(person.feature_file.parent, person.reference_audio.parent)
        self.assertEqual(len(json.loads(person.feature_file.read_text())["features"]), 192)
        reopened = DataFolder()
        reopened.select(self.folder)
        self.assertEqual(list_people(reopened), [person])
        self.assertEqual(reopened.load_shared("people")[0]["name"], "話者A")

    def test_registered_video_interval_and_reject_unregistered_video(self):
        video = self.root / "sample.mp4"
        subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i",
                        "color=c=black:s=32x32:d=2", "-f", "lavfi", "-i",
                        "sine=frequency=440:duration=2", "-shortest", "-y", str(video)], check=True)
        with self.assertRaises(PersonError):
            register_person(self.data, "A", "", self.model, 0.2, "five-second-windows",
                            video=video, start=0, end=1, encoder=self.fake_encoder)
        registered = self.data.register_video(video)
        person = register_person(self.data, "A", "", self.model, 0.2, "five-second-windows",
                                 video=registered, start=0.25, end=1.25, encoder=self.fake_encoder)
        metadata = json.loads(person.feature_file.read_text())
        self.assertEqual((metadata["source"], metadata["start_seconds"], metadata["end_seconds"]),
                         ("video", 0.25, 1.25))
        second = self.root / "another.mp4"
        second.write_bytes(b"another source video")
        second_registered = self.data.register_video(second)
        select_target(self.data, registered, person.person_id)
        select_target(self.data, second_registered, person.person_id)
        reopened = DataFolder()
        reopened.select(self.folder)
        self.assertEqual(target_for_video(reopened, registered).person_id, person.person_id)
        self.assertEqual(target_for_video(reopened, second_registered).person_id, person.person_id)

    def test_failed_feature_generation_leaves_no_person_or_assets(self):
        def fail(*args):
            raise PersonError("failed")
        with self.assertRaises(PersonError):
            register_person(self.data, "A", self.audio, self.model, 0.2,
                            "whole-reference", encoder=fail)
        self.assertEqual(list_people(self.data), [])
        self.assertEqual(list((self.folder / "people").glob("*/reference.wav")), [])

    def test_threshold_and_split_must_be_explicit_and_valid(self):
        for threshold, split in (("", "whole-reference"), (1.1, "whole-reference"),
                                 (0.2, "unknown")):
            with self.subTest(threshold=threshold, split=split), self.assertRaises(PersonError):
                register_person(self.data, "A", self.audio, self.model, threshold, split,
                                encoder=self.fake_encoder)
        self.assertEqual(list_people(self.data), [])


if __name__ == "__main__":
    unittest.main()
