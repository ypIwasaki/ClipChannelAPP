import base64
import json
import tempfile
import time
import unittest
from pathlib import Path
from tkinter import ttk
from unittest.mock import patch

from clipchannel.app import build_app
from clipchannel.supporting_media_ui import SupportingMediaPanel


class SupportingMediaInputTest(unittest.TestCase):
    def test_unapplied_input_blocks_folder_switch_until_explicitly_discarded(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first, second = root / "first", root / "second"
            first.mkdir()
            second.mkdir()
            window = build_app()
            self.addCleanup(window.destroy)

            def descendants(widget):
                for child in widget.winfo_children():
                    yield child
                    yield from descendants(child)

            widgets = list(descendants(window))
            choose = next(w for w in widgets if w.winfo_class() == "Button" and
                          w.cget("text") == "フォルダを選択・切り替え")
            with patch("tkinter.filedialog.askdirectory", return_value=str(first)):
                choose.invoke()
            panel = next(w for w in widgets if isinstance(w, SupportingMediaPanel))
            video = first / "media" / "edits" / "take1" / "edit.mp4"
            video.parent.mkdir(parents=True)
            video.write_bytes(b"video")
            video.with_suffix(".json").write_text(json.dumps(
                {"fps": "10", "frame_counts": [20, 20]}), encoding="utf-8")
            panel.set_video(video)
            source = root / "image.png"
            source.write_bytes(base64.b64decode(
                "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII="))
            add = next(w for w in descendants(panel) if isinstance(w, ttk.Button) and w.cget("text") == "画像を追加")
            with patch("tkinter.filedialog.askopenfilename", return_value=str(source)):
                add.invoke()
            # Run the real Tk event loop, including the worker's completion callback.
            deadline = time.monotonic() + 5
            def attempt_switch():
                if panel.data.running and time.monotonic() < deadline:
                    window.after(20, attempt_switch)
                else:
                    window.quit()
            window.after(20, attempt_switch)
            window.mainloop()
            self.assertFalse(panel.data.running)
            with patch("tkinter.filedialog.askdirectory", return_value=str(second)), patch("tkinter.messagebox.showerror") as error:
                choose.invoke()
            self.assertEqual(panel.data.path, first)
            error.assert_called_once()
            discard = next(w for w in descendants(panel) if isinstance(w, ttk.Button) and
                           w.cget("text") == "未適用入力を破棄")
            discard.invoke()
            with patch("tkinter.filedialog.askdirectory", return_value=str(second)):
                choose.invoke()
            self.assertEqual(panel.data.path, second)
