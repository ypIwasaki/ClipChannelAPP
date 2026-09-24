import tempfile
import unittest
from pathlib import Path

from clipchannel import DataFolder, StorageError, VideoNameConflict


class VideoRegistrationTests(unittest.TestCase):
    def test_copy_reselect_and_reject_different_video_with_same_result_name(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            folder = root / "data"
            folder.mkdir()
            first = root / "first" / "movie.mp4"
            first.parent.mkdir()
            first.write_bytes(b"first video")
            second = root / "second" / "movie.mkv"
            second.parent.mkdir()
            second.write_bytes(b"different video")
            data = DataFolder()
            data.select(folder)

            registered = data.register_video(first)
            self.assertEqual(first.read_bytes(), b"first video")
            self.assertEqual(registered.read_bytes(), b"first video")
            self.assertEqual(data.register_video(first), registered)
            self.assertEqual([path.name for path in data.list_videos()], ["movie.mp4"])
            with self.assertRaises(VideoNameConflict):
                data.register_video(second)
            self.assertEqual([path.name for path in data.list_videos()], ["movie.mp4"])

            reopened = DataFolder()
            reopened.select(folder)
            self.assertEqual(reopened.list_videos(), [registered])

    def test_non_video_is_rejected_and_directories_are_not_listed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            data = DataFolder()
            data.select(root)
            document = root / "notes.txt"
            document.write_text("not a video")
            with self.assertRaises(StorageError):
                data.register_video(document)
            (root / "media" / "originals" / "folder.mp4").mkdir(parents=True)
            self.assertEqual(data.list_videos(), [])


if __name__ == "__main__":
    unittest.main()
