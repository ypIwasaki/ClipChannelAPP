import tempfile
import tkinter as tk
import unittest
from pathlib import Path

from clipchannel.app import build_app
from clipchannel.save_export_ui import choose_action
from clipchannel.storage import DataFolder
from clipchannel.window_preferences import DisplayArea
from tests.test_responsive_ui import button, descendants


class ResponsiveDialogTests(unittest.TestCase):
    def test_short_confirmation_keeps_message_visible_with_three_actions(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = build_app(data=DataFolder(), preferences=Path(temporary) / 'ui.json',
                             display=DisplayArea(0, 0, 1280, 680))
            self.addCleanup(root.destroy)
            observed = []
            def close():
                dialog = next(w for w in descendants(root) if isinstance(w, tk.Toplevel))
                text = next(w for w in descendants(dialog) if isinstance(w, tk.Text))
                action = button(dialog, '戻る')
                observed.append((text.winfo_height(), text.dlineinfo('1.0'),
                                 action.winfo_rooty() + action.winfo_height(),
                                 dialog.winfo_rooty() + dialog.winfo_height()))
                button(dialog, '戻る').invoke()
            root.after(150, close)
            choose_action(root, '未保存の編集', '未保存の編集があります、または保存状態を確認できません。',
                          (('保存する', 'save'), ('破棄する', 'discard'), ('戻る', None)))
            self.assertIsNotNone(observed[0][1], 'The confirmation message must be visible')
            self.assertGreaterEqual(observed[0][0], 30)
            self.assertLessEqual(observed[0][2], observed[0][3], 'Action must fit inside the dialog')

    def test_error_dialog_is_bounded_and_can_be_dismissed_with_long_detail(self):
        from clipchannel.dialogs import messagebox
        with tempfile.TemporaryDirectory() as temporary:
            root = build_app(data=DataFolder(), preferences=Path(temporary) / 'ui.json',
                             display=DisplayArea(0, 0, 1280, 680))
            self.addCleanup(root.destroy)
            sizes = []
            def close():
                dialog = next(w for w in descendants(root) if isinstance(w, tk.Toplevel))
                sizes.append(dialog.winfo_height())
                button(dialog, '閉じる').invoke()
            root.after(100, close)
            result = messagebox.showerror('処理失敗', '長い例外と入力パス。' * 1000, parent=root)
            self.assertEqual(result, 'ok')
            self.assertLessEqual(sizes[0], 680)

    def test_long_confirmation_keeps_actual_actions_in_available_area(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = build_app(data=DataFolder(), preferences=Path(temporary) / 'ui.json',
                             display=DisplayArea(0, 0, 1280, 680))
            self.addCleanup(root.destroy)
            observed = []
            def choose():
                dialog = next(w for w in descendants(root) if isinstance(w, tk.Toplevel))
                action = button(dialog, '戻る')
                observed.append((dialog.winfo_width(), dialog.winfo_height(),
                                 action.winfo_rooty() + action.winfo_height()))
                action.invoke()
            root.after(100, choose)
            result = choose_action(root, '長い確認', '長い状態文とパス。' * 1000,
                                   (('保存する', 'save'), ('戻る', None)))
            self.assertIsNone(result)
            self.assertLessEqual(observed[0][0], 1280)
            self.assertLessEqual(observed[0][1], 680)
            self.assertLessEqual(observed[0][2], 680)

    def test_supporting_preview_shows_whole_image_and_reachable_close_action(self):
        from clipchannel.supporting_media_ui import SupportingMediaPanel
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            root = build_app(data=DataFolder(), preferences=directory / 'ui.json',
                             display=DisplayArea(0, 0, 1280, 680))
            self.addCleanup(root.destroy)
            picture = tk.PhotoImage(master=root, width=1200, height=1800)
            picture.put('#ff0000', to=(0, 0, 1200, 900))
            picture.put('#00ff00', to=(0, 900, 1200, 1800))
            path = directory / 'preview.ppm'
            picture.write(path, format='ppm')
            panel = next(w for w in descendants(root) if isinstance(w, SupportingMediaPanel))
            panel.preview = path
            panel.show_preview()
            root.update()
            dialog = next(w for w in descendants(root) if isinstance(w, tk.Toplevel))
            close = button(dialog, '閉じる')
            self.assertLessEqual(close.winfo_rooty() + close.winfo_height(), 680)
            label = next(w for w in descendants(dialog) if hasattr(w, 'picture'))
            self.assertEqual(label.picture.get(0, 0), (255, 0, 0))
            self.assertEqual(label.picture.get(0, label.picture.height() - 1), (0, 255, 0))
            self.assertLessEqual(label.picture.width(), label.winfo_width())
            self.assertLessEqual(label.picture.height(), label.winfo_height())
            close.invoke()
