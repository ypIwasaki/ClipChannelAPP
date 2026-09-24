import tempfile
import unittest
from pathlib import Path

from clipchannel.people import select_target
from clipchannel.storage import DataFolder
from clipchannel.transcribe import (Interval, TranscriptionError, load_intervals,
                                    save_intervals, transcribe_confirmed, validate_intervals)


class TranscriptStorageTest(unittest.TestCase):
    def test_versions_keep_unknown_and_exclude_non_target_text(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            data = DataFolder()
            data.select(root)
            video = root / "input.mp4"
            video.write_bytes(b"video")
            registered = data.register_video(video)
            # The storage contract is independent of the heavyweight model.
            data.save_shared("people", [{"person_id": "p1", "name": "A",
                                         "reference_audio": "people/ref.wav",
                                         "feature_file": "people/feature.json"}])
            select_target(data, registered, "p1")
            first = save_intervals(data, registered, [Interval(0, 1000, "unknown")])
            second = save_intervals(data, registered, [Interval(0, 500, "target", text="こんにちは"),
                                                       Interval(500, 1000, "non-target")])
            self.assertEqual(first.name, "input_v1.csv")
            self.assertEqual(second.name, "input_v2.csv")
            self.assertEqual(load_intervals(data, registered, 1)[0].state, "unknown")
            self.assertEqual(load_intervals(data, registered, 2)[0].text, "こんにちは")
            with self.assertRaises(TranscriptionError):
                save_intervals(data, registered, [Interval(0, 1000, "non-target", text="他者")])
            with self.assertRaises(TranscriptionError):
                transcribe_confirmed(data, registered, [Interval(0, 1000, "target")],
                                     root / "missing-model")
            self.assertEqual(len(data.list_saved()), 4)  # two result versions, people, targets

    def test_overlapping_review_ranges_are_rejected(self):
        with self.assertRaises(TranscriptionError):
            validate_intervals([Interval(0, 1000, "target"),
                                Interval(900, 1200, "unknown")])


if __name__ == "__main__":
    unittest.main()
