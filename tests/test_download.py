import sys
import os
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from clipchannel.download import DownloadError, DownloadSession
from clipchannel.operation_tasks import download as run_download_task
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
    def test_retry_can_use_updated_format_without_losing_items(self):
        with tempfile.TemporaryDirectory() as temporary:
            data = DataFolder()
            data.select(temporary)
            session = DownloadSession(data, "https://example.test/list")
            item = object()
            session.items.append(item)
            session.configure_retry(format="best", retries=2, extra="")
            self.assertEqual(session.options["format"], "best")
            self.assertEqual(session.options["retries"], 2)
            self.assertIs(session.items[0], item)

    def test_configured_ffmpeg_is_passed_to_yt_dlp(self):
        seen = []

        class RecordingYoutubeDL(FakeYoutubeDL):
            def __init__(self, options):
                seen.append(options)
                super().__init__(options)

        with tempfile.TemporaryDirectory() as temporary:
            data = DataFolder()
            data.select(temporary)
            session = DownloadSession(data, "https://example.test/list")
            with patch.dict(os.environ, {"CLIPCHANNEL_FFMPEG": str(Path(temporary) / "ffmpeg.exe")}), \
                 patch.dict(sys.modules, {"yt_dlp": types.SimpleNamespace(YoutubeDL=RecordingYoutubeDL)}), \
                 patch("clipchannel.download.prepare_media") as prepare:
                prepare.side_effect = lambda _data, source, **_kwargs: types.SimpleNamespace(editing=source)
                session.run()
        self.assertEqual(seen[1]["ffmpeg_location"], str(Path(temporary) / "ffmpeg.exe"))

    def test_managed_download_preserves_missing_dependency_message(self):
        class Control:
            def cancelled(self):
                return False

            def report(self, _snapshot):
                pass

        with tempfile.TemporaryDirectory() as temporary:
            data = DataFolder()
            data.select(temporary)
            session = DownloadSession(data, "https://example.test/video")
            with patch.dict(sys.modules, {"yt_dlp": None}):
                with self.assertRaisesRegex(DownloadError, "yt-dlp が必要です"):
                    run_download_task(Control(), session)

    def test_success_remains_registered_when_another_entry_fails(self):
        with tempfile.TemporaryDirectory() as temporary:
            data = DataFolder()
            data.select(temporary)
            session = DownloadSession(data, "https://example.test/list")
            with patch.dict(sys.modules, {"yt_dlp": types.SimpleNamespace(YoutubeDL=FakeYoutubeDL)}), \
                 patch("clipchannel.download.prepare_media") as prepare:
                prepare.side_effect = lambda _data, source, **_kwargs: types.SimpleNamespace(editing=source)
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
                 patch("clipchannel.download.prepare_media", side_effect=DownloadError("変換失敗")):
                item = session.run()[0]
            self.assertEqual(item.state, "失敗")
            self.assertTrue(item.source_path.is_file())
            self.assertEqual([path.name for path in data.list_videos()], ["a.webm"])

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
