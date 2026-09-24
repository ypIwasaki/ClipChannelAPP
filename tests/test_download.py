import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from clipchannel.download import DownloadError, DownloadSession
from clipchannel.storage import DataFolder


class FakeYoutubeDL:
    def __init__(self, options):
        self.options = options

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass

    def extract_info(self, url, download, process=True):
        if not download:
            return {"entries": [{"webpage_url": "https://example.test/a", "title": "A"},
                                {"webpage_url": "https://example.test/b", "title": "B"}]}
        if url.endswith("/b"):
            raise RuntimeError("source URL or secret must not be shown")
        Path(self.options["outtmpl"].replace("%(id)s", "a").replace("%(ext)s", "mp4")).write_bytes(b"video")
        return {"vcodec": "h264"}


class DownloadTests(unittest.TestCase):
    def test_success_remains_registered_when_another_entry_fails(self):
        with tempfile.TemporaryDirectory() as temporary:
            data = DataFolder()
            data.select(temporary)
            session = DownloadSession(data, "https://example.test/list")
            with patch.dict(sys.modules, {"yt_dlp": types.SimpleNamespace(YoutubeDL=FakeYoutubeDL)}):
                items = session.run()
            self.assertEqual([item.state for item in items], ["成功", "失敗"])
            self.assertEqual(len(data.list_videos()), 1)
            self.assertNotIn("secret", items[1].error)
            self.assertFalse(data.running)

    def test_protected_options_and_credential_urls_stop_before_execution(self):
        with tempfile.TemporaryDirectory() as temporary:
            data = DataFolder()
            data.select(temporary)
            for extra in ("--output elsewhere", "--exec echo", "--cookies secret.txt", "--unknown value"):
                with self.assertRaises(DownloadError):
                    DownloadSession(data, "https://example.test/a", extra=extra)
            with self.assertRaises(DownloadError):
                DownloadSession(data, "https://user:secret@example.test/a")

    def test_conversion_failure_keeps_acquired_source(self):
        class WebmYoutubeDL(FakeYoutubeDL):
            def extract_info(self, url, download, process=True):
                if not download:
                    return {"title": "A", "webpage_url": url}
                Path(self.options["outtmpl"].replace("%(id)s", "a").replace("%(ext)s", "webm")).write_bytes(b"video")
                return {"vcodec": "vp9"}

        with tempfile.TemporaryDirectory() as temporary:
            data = DataFolder()
            data.select(temporary)
            session = DownloadSession(data, "https://example.test/a")
            with patch.dict(sys.modules, {"yt_dlp": types.SimpleNamespace(YoutubeDL=WebmYoutubeDL)}), \
                 patch("clipchannel.download.shutil.which", return_value=None):
                item = session.run()[0]
            self.assertEqual(item.state, "失敗")
            self.assertTrue(item.source_path.is_file())
            self.assertEqual(data.list_videos(), [])

    def test_info_only_stop_confirms_stopped_item(self):
        with tempfile.TemporaryDirectory() as temporary:
            data = DataFolder()
            data.select(temporary)
            session = DownloadSession(data, "https://example.test/list", info_only=True)

            class StopOnInfo(FakeYoutubeDL):
                def extract_info(self, url, download, process=True):
                    if process:
                        session.stop()
                        return {"duration": 12, "formats": []}
                    return super().extract_info(url, download, process)

            with patch.dict(sys.modules, {"yt_dlp": types.SimpleNamespace(YoutubeDL=StopOnInfo)}):
                items = session.run()
            self.assertEqual(items[0].state, "中止")
            self.assertEqual(items[1].state, "未着手")
            self.assertEqual(session.state, "停止完了")


if __name__ == "__main__":
    unittest.main()
