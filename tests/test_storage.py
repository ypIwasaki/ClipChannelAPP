import tempfile
import unittest
from pathlib import Path

from clipchannel import DataFolder, FolderBusy, StorageError


class DataFolderTests(unittest.TestCase):
    def test_switch_and_read_versions_with_multiline_csv(self):
        with tempfile.TemporaryDirectory() as temporary:
            first, second = Path(temporary) / "F1", Path(temporary) / "F2"
            first.mkdir()
            second.mkdir()
            data = DataFolder()
            data.select(first)
            row = {"start_ms": "1250", "end_ms": "2700", "text": '一行目,"引用"\n二行目', "speaker_id": "p1"}
            data.save_result("動画.mp4", "transcripts", [row])
            data.save_result("動画.mp4", "transcripts", [{**row, "text": "再解析"}])
            self.assertEqual(data.load_result("動画.mp4", "transcripts", 1), [row])
            self.assertEqual(len(data.list_saved()), 2)
            data.select(second)
            self.assertEqual(data.list_saved(), [])
            data.select(first)
            self.assertEqual(data.load_result("動画.mp4", "transcripts", 2)[0]["text"], "再解析")

    def test_busy_switch_does_not_change_folder(self):
        with tempfile.TemporaryDirectory() as temporary:
            first, second = Path(temporary) / "F1", Path(temporary) / "F2"
            first.mkdir()
            second.mkdir()
            data = DataFolder()
            data.select(first)
            data.unsaved = True
            with self.assertRaisesRegex(FolderBusy, "未保存入力"):
                data.select(second)
            self.assertEqual(data.path, first)
            data.unsaved = False
            data.running = True
            with self.assertRaisesRegex(FolderBusy, "処理中"):
                data.select(second)

    def test_shared_data_and_unknown_schema(self):
        with tempfile.TemporaryDirectory() as temporary:
            data = DataFolder()
            data.select(temporary)
            data.save_shared("registered-words", [{"word": "固有名詞"}])
            self.assertEqual(data.load_shared("registered-words"), [{"word": "固有名詞"}])
            path = data.save_result("sample.mp4", "segments", [{"start_ms": "0", "end_ms": "10", "kind": "speech", "selected": "1"}])
            path.write_text(path.read_text(encoding="utf-8").replace("schema_version", "unknown_version"), encoding="utf-8")
            with self.assertRaises(StorageError):
                data.load_result("sample.mp4", "segments", 1)


if __name__ == "__main__":
    unittest.main()
