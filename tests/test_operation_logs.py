import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from clipchannel import DataFolder
from clipchannel.operation_logs import cleanup_logs, record_operation


class OperationLogTests(unittest.TestCase):
    def test_finished_operation_records_only_its_summary(self):
        with tempfile.TemporaryDirectory() as temporary:
            data = DataFolder()
            data.select(temporary)
            before = datetime.now(timezone.utc)

            path = record_operation(data, "可逆保管", "完了", 1.25)

            record = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(path.parent, Path(temporary) / "logs")
            self.assertEqual(path.suffix, ".log")
            self.assertEqual(set(record), {"time", "label", "state", "elapsed"})
            self.assertEqual(record["label"], "可逆保管")
            self.assertEqual(record["state"], "完了")
            self.assertEqual(record["elapsed"], 1.25)
            self.assertGreaterEqual(datetime.fromisoformat(record["time"]), before)
            self.assertLessEqual(datetime.fromisoformat(record["time"]), datetime.now(timezone.utc))


    def test_only_normal_logs_at_least_thirty_days_old_are_removed(self):
        with tempfile.TemporaryDirectory() as temporary:
            data = DataFolder()
            data.select(temporary)
            expired = record_operation(data, "可逆保管", "完了", 1.25)
            recent = record_operation(data, "展開", "完了", 0.5)
            unrelated = Path(temporary) / "logs" / "notes.txt"
            unrelated.write_text("keep", encoding="utf-8")
            old_time = datetime(2026, 10, 1, tzinfo=timezone.utc).timestamp()
            os.utime(expired, (old_time, old_time))
            os.utime(unrelated, (old_time, old_time))
            os.utime(recent, (old_time + 1, old_time + 1))

            removed = cleanup_logs(data, now=datetime(2026, 10, 31, tzinfo=timezone.utc))

            self.assertEqual(removed, [expired])
            self.assertFalse(expired.exists())
            self.assertTrue(recent.exists())
            self.assertEqual(unrelated.read_text(encoding="utf-8"), "keep")

    def test_log_directory_link_never_writes_or_removes_external_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            folder, outside = root / "data", root / "outside"
            folder.mkdir()
            outside.mkdir()
            data = DataFolder()
            data.select(folder)
            (folder / "logs").rmdir()
            try:
                (folder / "logs").symlink_to(outside, target_is_directory=True)
            except OSError:
                self.skipTest("Symbolic links are unavailable")
            original = outside / "external.log"
            original.write_text("outside", encoding="utf-8")
            old_time = datetime(2026, 10, 1, tzinfo=timezone.utc).timestamp()
            os.utime(original, (old_time, old_time))

            with self.assertRaises(ValueError):
                record_operation(data, "可逆保管", "完了", 1.25)
            self.assertEqual(cleanup_logs(data, now=datetime(2026, 10, 31, tzinfo=timezone.utc)), [])
            self.assertEqual(list(outside.iterdir()), [original])
            self.assertEqual(original.read_text(encoding="utf-8"), "outside")

    def test_recovery_information_protects_old_logs_until_cleared(self):
        with tempfile.TemporaryDirectory() as temporary:
            data = DataFolder()
            data.select(temporary)
            expired = record_operation(data, "解析", "失敗", 4.5)
            old_time = datetime(2026, 10, 1, tzinfo=timezone.utc).timestamp()
            os.utime(expired, (old_time, old_time))
            recovery = Path(temporary) / "recovery" / "pending.json"
            recovery.write_text('{"state": "waiting"}', encoding="utf-8")
            current = datetime(2026, 10, 31, tzinfo=timezone.utc)

            self.assertEqual(cleanup_logs(data, now=current), [])
            self.assertTrue(expired.exists())
            self.assertTrue(recovery.exists())
            recovery.unlink()
            self.assertEqual(cleanup_logs(data, now=current), [expired])
            self.assertFalse(expired.exists())

    def test_retention_uses_elapsed_utc_days_across_daylight_saving(self):
        try:
            local = ZoneInfo("America/New_York")
        except ZoneInfoNotFoundError:
            self.skipTest("Timezone data is unavailable")
        with tempfile.TemporaryDirectory() as temporary:
            data = DataFolder()
            data.select(temporary)
            expired = record_operation(data, "可逆保管", "完了", 1.25)
            old_time = datetime(2026, 10, 3, 4, 30, tzinfo=timezone.utc).timestamp()
            os.utime(expired, (old_time, old_time))

            removed = cleanup_logs(data, now=datetime(2026, 11, 2, tzinfo=local))

            self.assertEqual(removed, [expired])
            self.assertFalse(expired.exists())

    def test_expired_link_inside_logs_is_preserved_without_following_it(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            folder = root / "data"
            folder.mkdir()
            data = DataFolder()
            data.select(folder)
            external = root / "external.log"
            external.write_text("outside", encoding="utf-8")
            old_time = datetime(2026, 10, 1, tzinfo=timezone.utc).timestamp()
            os.utime(external, (old_time, old_time))
            linked = folder / "logs" / "linked.log"
            try:
                linked.symlink_to(external)
            except OSError:
                self.skipTest("Symbolic links are unavailable")

            self.assertEqual(cleanup_logs(data, now=datetime(2026, 10, 31, tzinfo=timezone.utc)), [])
            self.assertTrue(linked.is_symlink())
            self.assertEqual(external.read_text(encoding="utf-8"), "outside")

    def test_finished_export_logs_expire_but_pending_and_unrelated_files_remain(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            data = DataFolder()
            data.select(root)
            project = root / "projects" / "edit-one"
            project.mkdir()
            old_time = datetime(2026, 10, 1, tzinfo=timezone.utc).timestamp()
            finished, pending = [], []
            for number, state in enumerate((None, "completed", "cancelled", "failed", "running", "waiting", "unknown")):
                log = project / f"control-{number:032x}.log"
                log.write_text("encoder output", encoding="utf-8")
                os.utime(log, (old_time, old_time))
                if state is not None:
                    log.with_suffix(".json").write_text(json.dumps({"state": state}), encoding="utf-8")
                    log.with_suffix(".cccontrol").write_text("ClipChannel-Control-1\n", encoding="ascii")
                (finished if state in (None, "completed", "cancelled", "failed") else pending).append(log)
            unrelated = project / "notes.log"
            unrelated.write_text("keep", encoding="utf-8")
            os.utime(unrelated, (old_time, old_time))

            removed = cleanup_logs(data, now=datetime(2026, 10, 31, tzinfo=timezone.utc))

            self.assertEqual(removed, finished)
            self.assertTrue(all(not log.exists() for log in finished))
            self.assertTrue(all(log.is_file() for log in pending))
            self.assertEqual(unrelated.read_text(encoding="utf-8"), "keep")
            self.assertTrue(finished[1].with_suffix(".json").exists())

    def test_recovery_and_uncertain_export_requests_keep_old_logs(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            data = DataFolder()
            data.select(root)
            project = root / "projects" / "edit-one"
            project.mkdir()
            old_time = datetime(2026, 10, 1, tzinfo=timezone.utc).timestamp()
            logs = []
            for number, sidecar in enumerate((None, ".cccontrol", ".cancel", ".force", ".f32le", ".json")):
                log = project / f"control-{number:032x}.log"
                log.write_text("encoder output", encoding="utf-8")
                os.utime(log, (old_time, old_time))
                if sidecar:
                    log.with_suffix(sidecar).write_text("unfinished", encoding="utf-8")
                logs.append(log)
            recovery = root / "recovery" / "pending.json"
            recovery.write_text("pending", encoding="utf-8")
            current = datetime(2026, 10, 31, tzinfo=timezone.utc)

            self.assertEqual(cleanup_logs(data, now=current), [])
            self.assertTrue(all(log.exists() for log in logs))
            recovery.unlink()
            self.assertEqual(cleanup_logs(data, now=current), [logs[0]])
            self.assertTrue(all(log.exists() for log in logs[1:]))

    def test_export_log_cleanup_never_follows_project_or_state_links(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            folder, outside = root / "data", root / "outside"
            folder.mkdir()
            outside.mkdir()
            data = DataFolder()
            data.select(folder)
            project = folder / "projects" / "edit-one"
            project.mkdir()
            external = outside / ("control-" + "a" * 32 + ".log")
            external.write_text("outside", encoding="utf-8")
            protected = project / ("control-" + "b" * 32 + ".log")
            protected.write_text("unknown state", encoding="utf-8")
            response = outside / "terminal.json"
            response.write_text('{"state":"completed"}', encoding="utf-8")
            old_time = datetime(2026, 10, 1, tzinfo=timezone.utc).timestamp()
            for path in (external, protected):
                os.utime(path, (old_time, old_time))
            try:
                (folder / "projects" / "linked-edit").symlink_to(outside, target_is_directory=True)
                (project / external.name).symlink_to(external)
                protected.with_suffix(".json").symlink_to(response)
            except OSError:
                self.skipTest("Symbolic links are unavailable")

            self.assertEqual(cleanup_logs(data, now=datetime(2026, 10, 31, tzinfo=timezone.utc)), [])
            self.assertEqual(external.read_text(encoding="utf-8"), "outside")
            self.assertEqual(protected.read_text(encoding="utf-8"), "unknown state")
            self.assertTrue((project / external.name).is_symlink())
            self.assertTrue(protected.with_suffix(".json").is_symlink())

if __name__ == "__main__":
    unittest.main()
