import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from clipchannel.app import build_app
from clipchannel.segments import Segment, save_segments
from clipchannel.storage import DataFolder, StorageError


def descendants(widget):
    for child in widget.winfo_children():
        yield child
        yield from descendants(child)


class SegmentReopenUiTests(unittest.TestCase):
    def test_save_retry_before_loading_does_not_block_saved_segments(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            data = DataFolder()
            data.select(root)
            source = root / 'sample.mp4'
            source.write_bytes(b'video')
            video = data.register_video(source)
            saved = save_segments(data, video, [Segment(0, 10000, 'target')], 30000)
            real_tk = tk.Tk

            def hidden_window():
                window = real_tk()
                window.withdraw()
                return window

            with patch('clipchannel.app.tk.Tk', side_effect=hidden_window):
                window = build_app()
            self.addCleanup(window.destroy)
            widgets = list(descendants(window))

            def button(caption):
                return next(w for w in widgets if w.winfo_class() in ('Button', 'TButton')
                            and w.cget('text') == caption)

            with patch('tkinter.filedialog.askdirectory', return_value=str(root)):
                button('フォルダを選択・切り替え').invoke()
            listing = next(w for w in widgets if w.winfo_class() == 'Listbox'
                           and saved.relative_to(root).as_posix() in w.get(0, tk.END))
            segments_tab = button('選択した保存版を使用').master
            retry = next(w for w in descendants(segments_tab) if w.winfo_class() == 'TButton'
                         and w.cget('text') == '保存を再試行')
            with patch('tkinter.messagebox.showerror') as errors:
                retry.invoke()
                errors.reset_mock()
                listing.selection_set(listing.get(0, tk.END).index(saved.relative_to(root).as_posix()))
                with patch('clipchannel.app._probe', return_value=SimpleNamespace(duration=30)):
                    button('選択した保存版を使用').invoke()
                errors.assert_not_called()
            self.assertTrue(any(w.winfo_class() == 'Listbox'
                                and any('0.000–10.000' in row for row in w.get(0, tk.END))
                                for w in widgets))
            with patch('clipchannel.app.save_segments', side_effect=StorageError('disk failure')), \
                    patch('tkinter.messagebox.showerror') as errors:
                retry.invoke()
                errors.reset_mock()
                button('選択した保存版を使用').invoke()
                self.assertIn('未保存の変更', errors.call_args.args[1])
