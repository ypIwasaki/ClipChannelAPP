import tempfile
import unittest
from pathlib import Path

from clipchannel.storage import DataFolder
from clipchannel.word_counts import count_words


class WordCountsTest(unittest.TestCase):
    def test_registered_word_counts_distinct_utterances_and_keeps_versions(self):
        with tempfile.TemporaryDirectory() as temporary:
            data = DataFolder()
            data.select(temporary)
            video = Path(temporary) / "sample.mp4"
            video.write_bytes(b"video")
            data.save_shared("registered-words", [{"word": "ゲーム"}, {"word": "ゲーム大会"}])
            data.save_result(video, "transcripts", [
                {"start_ms": "0", "end_ms": "1000", "text": "ゲーム大会、ゲーム大会。", "speaker_id": "target"},
                {"start_ms": "1000", "end_ms": "2000", "text": "ゲーム大会。", "speaker_id": "target"},
                {"start_ms": "2000", "end_ms": "3000", "text": "ゲーム大会", "speaker_id": "unknown"},
            ])
            first = count_words(data, video, 1)
            rows = data.load_result(video, "word-counts", 1)
            matches = [row for row in rows if row["word"] == "ゲーム大会"]
            self.assertEqual(first.name, "sample_v1.csv")
            self.assertEqual([(row["occurrences"], row["utterances"], row["start_ms"])
                              for row in matches], [("3", "2", "0"), ("3", "2", "1000")])
            self.assertFalse(any(row["word"] == "ゲーム" for row in rows))
            data.save_shared("excluded-words", [{"word": "ゲーム大会"}])
            second = count_words(data, video, 1)
            self.assertEqual(second.name, "sample_v2.csv")
            self.assertFalse(data.load_result(video, "word-counts", 2))
            self.assertEqual(data.load_result(video, "word-counts", 1), rows)

    def test_verbs_are_optional_and_inflections_share_dictionary_form(self):
        with tempfile.TemporaryDirectory() as temporary:
            data = DataFolder()
            data.select(temporary)
            video = Path(temporary) / "sample.mp4"
            video.write_bytes(b"video")
            data.save_result(video, "transcripts", [
                {"start_ms": "0", "end_ms": "1000", "text": "走った。走る。", "speaker_id": "target"},
            ])
            count_words(data, video, 1)
            self.assertFalse(any(row["word"] == "走る" for row in data.load_result(video, "word-counts", 1)))
            count_words(data, video, 1, include_verbs=True)
            running = [row for row in data.load_result(video, "word-counts", 2) if row["word"] == "走る"]
            self.assertEqual([(row["occurrences"], row["utterances"]) for row in running], [("2", "1")])


if __name__ == "__main__":
    unittest.main()
