import tempfile
import unittest
from pathlib import Path

from clipchannel.segments import (Segment, candidates_from_transcript, generate_candidates,
                                  load_segments, merge_segments, save_segments, split_segment)
from clipchannel.storage import DataFolder
from clipchannel.transcribe import Interval


class SegmentTest(unittest.TestCase):
    def test_candidates_collapse_windows_but_not_short_gaps_or_padding_overlap(self):
        rows = [Interval(10000, 15000, "target"), Interval(15000, 20000, "target"),
                Interval(22000, 25000, "unknown"), Interval(25000, 30000, "non-target")]
        self.assertEqual(generate_candidates(rows, 60000), [
            Segment(5000, 25000, "target"), Segment(17000, 30000, "unknown"),
            Segment(20000, 35000, "non-target")])
        self.assertEqual(generate_candidates(rows[:1], 60000, 2000, 3000),
                         [Segment(8000, 18000, "target")])

    def test_manual_boundaries_split_and_merge_include_gap_without_new_padding(self):
        rows = [Segment(7000, 23000, "target"), Segment(25000, 30000, "unknown", False)]
        pieces = split_segment(rows, 0, 15000, 60000)
        self.assertEqual(pieces[:2], [Segment(7000, 15000, "target"), Segment(15000, 23000, "target")])
        self.assertEqual(merge_segments(rows, [0, 1], 60000), [Segment(7000, 30000, "mixed")])
        three = [Segment(10000, 20000, "target"), Segment(20000, 25000, "unknown"),
                 Segment(25000, 30000, "target")]
        self.assertEqual(merge_segments(three, [0, 2], 60000), [Segment(10000, 30000, "mixed")])

    def test_versions_keep_old_list_and_selected_state(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data = DataFolder()
            data.select(root)
            source = root / "source.mp4"
            source.write_bytes(b"video")
            video = data.register_video(source)
            first = save_segments(data, video, [Segment(5000, 25000, "target")], 60000)
            second = save_segments(data, video, [Segment(7000, 23000, "target", False)], 60000)
            self.assertEqual((first.name, second.name), ("source_v1.csv", "source_v2.csv"))
            self.assertEqual(load_segments(data, video, 1, 60000), [Segment(5000, 25000, "target")])
            self.assertEqual(load_segments(data, video, 2, 60000), [Segment(7000, 23000, "target", False)])


if __name__ == "__main__":
    unittest.main()
