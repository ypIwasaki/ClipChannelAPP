import tempfile
import unittest
from pathlib import Path

from clipchannel.storage import DataFolder, StorageError
from clipchannel.registrations import RegistrationManager


class RegistrationTests(unittest.TestCase):
    def test_hidden_registration_can_be_restored_after_reopening_folder(self):
        with tempfile.TemporaryDirectory() as temporary:
            data = DataFolder()
            data.select(temporary)
            data.save_shared("registered-words", [{"word": "ゲーム大会"}])
            manager = RegistrationManager(data)
            manager.set_hidden("registered-words", "ゲーム大会", True)
            reopened = DataFolder()
            reopened.select(temporary)
            manager = RegistrationManager(reopened)
            self.assertEqual(manager.list_entries(), [])
            self.assertTrue(manager.list_entries(include_hidden=True)[0].hidden)
            self.assertEqual(reopened.load_shared("registered-words"), [{"word": "ゲーム大会"}])
            manager.set_hidden("registered-words", "ゲーム大会", False)
            self.assertEqual([entry.key for entry in manager.list_entries()], ["ゲーム大会"])

    def test_saved_transcript_protects_original_person_after_target_changes(self):
        with tempfile.TemporaryDirectory() as temporary:
            data = DataFolder()
            data.select(temporary)
            root = Path(temporary)
            video = root / "sample.mp4"
            video.write_bytes(b"original video")
            audio = root / "people" / "reference.wav"
            audio.write_bytes(b"reference audio")
            people = [{"person_id": key, "name": key, "reference_audio": "people/reference.wav",
                       "feature_file": "people/feature.json"} for key in ("old", "new", "unused")]
            data.save_shared("people", people)
            data.save_shared("targets", [{"video_name": video.name, "person_id": "old"}])
            saved = data.save_result(video, "transcripts", [
                {"start_ms": "0", "end_ms": "1000", "text": "発言", "speaker_id": "target"}])
            data.save_shared("targets", [{"video_name": video.name, "person_id": "new"}])
            manager = RegistrationManager(data)
            manager.set_hidden("results", saved.relative_to(root).as_posix(), True)
            with self.assertRaisesRegex(StorageError, "参照"):
                manager.delete_registration("people", "old")
            manager.delete_registration("people", "unused")
            self.assertEqual([row["person_id"] for row in data.load_shared("people")], ["old", "new"])
            self.assertEqual(audio.read_bytes(), b"reference audio")
            self.assertEqual(data.load_result(video, "transcripts", 1)[0]["text"], "発言")

    def test_empty_word_count_still_protects_dictionary_and_source_version(self):
        from clipchannel.word_counts import count_words
        with tempfile.TemporaryDirectory() as temporary:
            data = DataFolder()
            data.select(temporary)
            video = Path(temporary) / "sample.mp4"
            video.write_bytes(b"original video")
            data.save_shared("registered-words", [{"word": "ゲーム大会"}])
            data.save_shared("excluded-words", [{"word": "ゲーム大会"}])
            transcript = data.save_result(video, "transcripts", [
                {"start_ms": "0", "end_ms": "1000", "text": "ゲーム大会", "speaker_id": "target"}])
            count_words(data, video, 1)
            manager = RegistrationManager(data)
            self.assertEqual(data.load_result(video, "word-counts", 1), [])
            for kind, key in (("registered-words", "ゲーム大会"), ("excluded-words", "ゲーム大会"),
                              ("results", transcript.relative_to(data.path).as_posix())):
                with self.subTest(kind=kind), self.assertRaisesRegex(StorageError, "参照"):
                    manager.delete_registration(kind, key)

    def test_registration_removal_keeps_files_until_separate_confirmed_deletion(self):
        with tempfile.TemporaryDirectory() as temporary:
            data = DataFolder()
            data.select(temporary)
            root = Path(temporary)
            source = root / "sample.mp4"
            source.write_bytes(b"external original")
            registered = data.register_video(source)
            saved = data.save_result(source, "segments", [
                {"start_ms": "0", "end_ms": "1000", "kind": "manual", "selected": "1"}])
            relative = saved.relative_to(root).as_posix()
            manager = RegistrationManager(data)
            manager.delete_registration("results", relative)
            self.assertNotIn(relative, data.list_saved())
            self.assertTrue(saved.is_file())
            with self.assertRaisesRegex(StorageError, "確認"):
                manager.delete_file(relative)
            manager.delete_file(relative, confirmed=True)
            self.assertFalse(saved.exists())
            manager.delete_registration("videos", registered.relative_to(root).as_posix())
            self.assertEqual(data.list_videos(), [])
            self.assertTrue(registered.is_file())
            manager.delete_file(registered.relative_to(root).as_posix(), confirmed=True)
            self.assertEqual(source.read_bytes(), b"external original")

    def test_legacy_results_and_existing_dictionary_edit_cannot_bypass_protection(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            data = DataFolder()
            data.select(root)
            video = root / "sample.mp4"
            video.write_bytes(b"video")
            data.save_shared("registered-words", [{"word": "旧辞書"}])
            result = data.save_result(video, "word-counts", [])
            # Pre-upgrade CSVs have no per-result reference file.
            result.with_suffix(".refs.csv").unlink()
            with self.assertRaisesRegex(StorageError, "参照"):
                data.save_shared("registered-words", [])
            self.assertEqual(data.load_shared("registered-words"), [{"word": "旧辞書"}])
            manager = RegistrationManager(data)
            with self.assertRaisesRegex(StorageError, "参照"):
                manager.delete_file("media/originals/sample.mp4", confirmed=True)
            with self.assertRaises(StorageError):
                manager.delete_file("../external.mp4", confirmed=True)

    def test_unpublished_reference_file_reserves_version_without_blocking_next_save(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            data = DataFolder()
            data.select(root)
            source = root / "sample.mp4"
            source.write_bytes(b"video")
            rows = [{"start_ms": "0", "end_ms": "1000", "kind": "manual", "selected": "1"}]
            first = data.save_result(source, "segments", rows)
            pending = first.with_name("sample_v2.refs.csv")
            pending.write_bytes(first.with_suffix(".refs.csv").read_bytes())
            saved = data.save_result(source, "segments", rows)
            self.assertEqual(saved.name, "sample_v3.csv")
            self.assertEqual(data.load_result(source, "segments", 1), rows)
            self.assertEqual(len(data.list_saved()), 2)


if __name__ == "__main__":
    unittest.main()
