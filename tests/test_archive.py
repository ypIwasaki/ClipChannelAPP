import json
import zipfile
import tempfile
import unittest
from pathlib import Path

from clipchannel.archive import archive_video, restore_archive
from clipchannel.process_control import ProcessCancelled
from clipchannel.storage import DataFolder, StorageError


class ArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.folder = self.root / "data"
        self.folder.mkdir()
        self.data = DataFolder()
        self.data.select(self.folder)

    def test_result_shows_sizes_and_whether_capacity_was_reduced(self):
        for payload, reduced in ((b"abc", False), (b"x" * 10000, True)):
            with self.subTest(reduced=reduced):
                source = self.root / "size.mp4"
                source.write_bytes(payload)
                result = archive_video(self.data, source)
                restored = restore_archive(self.data, result.archive)
                for value in (result, restored):
                    self.assertEqual(value.reduced, reduced)
                    self.assertIn(f"{len(payload):,} バイト", value.summary)
                    self.assertIn(f"{value.archive_size:,} バイト", value.summary)
                    self.assertEqual("容量は削減できなかった" in value.summary, not reduced)


    def test_unknown_archive_version_is_rejected_without_publishing_video(self):
        archive = self.root / "future.zip"
        with zipfile.ZipFile(archive, "w") as stored:
            stored.writestr("movie.mp4", b"abc")
            stored.writestr("manifest.json", json.dumps({
                "schema_version": 2, "name": "movie.mp4", "size": 3,
                "sha256": "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
            }))

        with self.assertRaisesRegex(StorageError, "版|形式"):
            restore_archive(self.data, archive)

        self.assertTrue(archive.exists())
        self.assertFalse((self.folder / "media" / "restored").exists())


    def test_malformed_archive_is_rejected_without_extracting_untrusted_entries(self):
        manifest = {"schema_version": 1, "name": "movie.mp4", "size": 3,
                    "sha256": "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"}
        cases = [
            [("movie.mp4", b"abc"), ("manifest.json", b"not json")],
            [("movie.mp4", b"abc"), ("manifest.json", json.dumps({**manifest, "size": True}))],
            [("movie.mp4", b"abc"), ("manifest.json", json.dumps({**manifest, "sha256": "0" * 64}))],
            [("../escape.mp4", b"abc"), ("manifest.json", json.dumps({**manifest, "name": "../escape.mp4"}))],
            [("movie.mp4", b"abc"), ("unexpected.txt", b"x"), ("manifest.json", json.dumps(manifest))],
        ]
        for entries in cases:
            with self.subTest(entries=entries):
                archive = self.root / "invalid.zip"
                with zipfile.ZipFile(archive, "w") as stored:
                    for name, value in entries:
                        stored.writestr(name, value)

                with self.assertRaises(StorageError):
                    restore_archive(self.data, archive)

                self.assertTrue(archive.exists())
                self.assertFalse((self.folder / "media" / "restored").exists())
                self.assertFalse((self.folder / "escape.mp4").exists())
                self.assertEqual(list((self.folder / "work").iterdir()), [])


    def test_broken_zip_is_reported_as_a_storage_error_and_retained(self):
        archive = self.root / "broken.zip"
        archive.write_bytes(b"broken zip")

        with self.assertRaises(StorageError):
            restore_archive(self.data, archive)

        self.assertEqual(archive.read_bytes(), b"broken zip")
        self.assertEqual(list((self.folder / "work").iterdir()), [])


    def test_long_japanese_video_name_can_be_archived_and_restored(self):
        source = self.root / ("あ" * 80 + ".mp4")
        source.write_bytes(b"abc")

        result = archive_video(self.data, source)
        restored = restore_archive(self.data, result.archive)

        self.assertEqual(restored.output.name, source.name)
        self.assertEqual(restored.output.read_bytes(), b"abc")


    def test_normal_cancellation_keeps_completed_files_and_discards_partial_outputs(self):
        source = self.root / "cancel.mp4"
        source.write_bytes(b"x" * (3 * 1024 * 1024))
        archived = archive_video(self.data, source)
        restored = restore_archive(self.data, archived.archive)
        archive_before = archived.archive.read_bytes()
        outputs_before = sorted(path for path in (self.folder / "media" / "restored").rglob("*") if path.is_file())

        for action, input_path in ((archive_video, source), (restore_archive, archived.archive)):
            with self.subTest(action=action.__name__):
                permitted = iter((False, False))
                with self.assertRaises(ProcessCancelled):
                    action(self.data, input_path, stop_requested=lambda: next(permitted, True))

                self.assertEqual(source.stat().st_size, 3 * 1024 * 1024)
                self.assertEqual(archived.archive.read_bytes(), archive_before)
                self.assertEqual(list((self.folder / "archives").iterdir()), [archived.archive])
                self.assertEqual(sorted(path for path in (self.folder / "media" / "restored").rglob("*")
                                        if path.is_file()), outputs_before)
                self.assertEqual(restored.output.read_bytes(), source.read_bytes())
                self.assertEqual(list((self.folder / "work").iterdir()), [])

    def test_repeated_archiving_and_restoration_create_separate_files(self):
        source = self.root / "repeat.mp4"
        source.write_bytes(b"abc")
        registered = self.data.register_video(source)

        first = archive_video(self.data, registered)
        second = archive_video(self.data, registered)
        restored_first = restore_archive(self.data, first.archive)
        restored_second = restore_archive(self.data, first.archive)

        self.assertNotEqual(first.archive, second.archive)
        self.assertTrue(first.archive.is_file())
        self.assertTrue(second.archive.is_file())
        self.assertNotEqual(restored_first.output, restored_second.output)
        self.assertEqual(restored_first.output.read_bytes(), b"abc")
        self.assertEqual(restored_second.output.read_bytes(), b"abc")
        self.assertEqual(registered.read_bytes(), b"abc")
        self.assertEqual(source.read_bytes(), b"abc")


    def test_japanese_video_round_trip_preserves_source_archive_and_bytes(self):
        source = self.root / "日本語の動画.mp4"
        source.write_bytes(b"abc")

        archived = archive_video(self.data, source)
        restored = restore_archive(self.data, archived.archive)

        self.assertEqual(source.read_bytes(), b"abc")
        self.assertTrue(archived.archive.is_file())
        self.assertEqual(archived.output, archived.archive)
        self.assertEqual(restored.output.name, source.name)
        self.assertEqual(restored.output.read_bytes(), b"abc")
        self.assertNotEqual(restored.output, source)
        self.assertEqual(restored.archive, archived.archive)
        self.assertEqual(restored.original_size, 3)
        self.assertEqual(restored.archive_size, archived.archive.stat().st_size)
        self.assertEqual(restored.sha256, "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad")
        self.assertEqual(archived.sha256, restored.sha256)


if __name__ == "__main__":
    unittest.main()
