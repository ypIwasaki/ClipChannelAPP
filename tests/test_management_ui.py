import tempfile
import time
import tkinter as tk
import unittest
from pathlib import Path
from unittest.mock import patch

from clipchannel.app import build_app
from clipchannel.storage import DataFolder
from clipchannel.management_ui import ManagementPanel


def descendants(widget):
    for child in widget.winfo_children():
        yield child
        yield from descendants(child)


class ManagementUiTests(unittest.TestCase):
    def test_hide_restore_and_registration_removal_are_available_from_app(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            data = DataFolder()
            data.select(root)
            video = root / "sample.mp4"
            video.write_bytes(b"original")
            registered = data.register_video(video)
            window = build_app()
            self.addCleanup(window.destroy)
            widgets = list(descendants(window))
            choose = next(w for w in widgets if w.winfo_class() == "Button"
                          and w.cget("text") == "フォルダを選択・切り替え")
            with patch("tkinter.filedialog.askdirectory", return_value=str(root)):
                choose.invoke()
            panel = next(w for w in widgets if isinstance(w, ManagementPanel))
            panel.listing.selection_set(0)
            button = lambda name: next(w for w in descendants(panel) if w.winfo_class() == "TButton"
                                       and w.cget("text") == name)
            button("非表示").invoke()
            self.assertEqual(panel.data.list_videos(), [])
            panel.show_hidden.set(True)
            panel.refresh()
            panel.listing.selection_set(0)
            button("再表示").invoke()
            self.assertEqual(panel.data.list_videos(), [registered])
            panel.listing.selection_set(0)
            with patch("tkinter.messagebox.askyesno", return_value=True):
                button("登録情報を削除…").invoke()
            self.assertEqual(panel.data.list_videos(), [])
            self.assertTrue(registered.is_file())
            with patch("tkinter.filedialog.askopenfilename", return_value=str(registered)), \
                    patch("tkinter.messagebox.askyesno", return_value=False):
                button("実ファイルを選んで削除…").invoke()
            self.assertTrue(registered.is_file())

    def test_app_archives_and_restores_through_managed_process_and_records_logs(self):
        from clipchannel.managed_process_ui import ProcessPanel
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "小さい動画.mp4"
            source.write_bytes(b"abc")
            window = build_app()
            self.addCleanup(window.destroy)
            widgets = list(descendants(window))
            choose = next(w for w in widgets if w.winfo_class() == "Button"
                          and w.cget("text") == "フォルダを選択・切り替え")
            with patch("tkinter.filedialog.askdirectory", return_value=str(root)):
                choose.invoke()
            panel = next(w for w in widgets if isinstance(w, ManagementPanel))
            processes = next(w for w in widgets if isinstance(w, ProcessPanel))

            def wait_for_completion():
                deadline = time.monotonic() + 15
                def tick():
                    if processes.active and time.monotonic() < deadline:
                        window.after(25, tick)
                    else:
                        window.quit()
                window.after(25, tick)
                window.mainloop()
                self.assertFalse(processes.active)
                self.assertEqual(processes.operation.state, "完了")

            with patch("tkinter.filedialog.askopenfilename", return_value=str(source)):
                panel.archive()
            wait_for_completion()
            archive = processes.operation.result.archive
            self.assertIn("容量は削減できなかった", panel.result_text.get())
            self.assertIn("3 バイト", panel.result_text.get())
            with patch("tkinter.filedialog.askopenfilename", return_value=str(archive)):
                panel.restore()
            wait_for_completion()
            self.assertEqual(processes.operation.result.output.read_bytes(), b"abc")
            self.assertEqual(source.read_bytes(), b"abc")
            self.assertTrue(archive.is_file())
            self.assertEqual(len(list((root / "logs").glob("*.log"))), 2)


if __name__ == "__main__":
    unittest.main()
