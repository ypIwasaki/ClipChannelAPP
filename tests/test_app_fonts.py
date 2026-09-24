import os
import subprocess
import sys
import unittest
from pathlib import Path


@unittest.skipUnless(Path("/mnt/c/Windows/Fonts").is_dir(), "WSL Windows fonts not mounted")
class JapaneseFontTests(unittest.TestCase):
    def test_app_selects_available_japanese_font(self):
        script = """
import os
from pathlib import Path
import tkinter as tk
from tkinter import font
from clipchannel.app import configure_japanese_fonts
os.environ['FONTCONFIG_FILE'] = str(Path('clipchannel/fonts.conf').resolve())
root = tk.Tk()
family = configure_japanese_fonts(root)
assert family in ('Yu Gothic UI', 'Meiryo UI'), family
assert font.nametofont('TkDefaultFont').actual('family') == family
assert font.nametofont('TkTextFont').actual('family') == family
root.destroy()
"""
        env = dict(os.environ)
        env.pop("FONTCONFIG_FILE", None)
        result = subprocess.run([sys.executable, "-c", script], env=env, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_folder_button_is_visible_in_wide_window(self):
        script = """
from clipchannel.app import build_app
window = build_app()
window.update()
def descendants(widget):
    for child in widget.winfo_children():
        yield child
        yield from descendants(child)
button = next(child for child in descendants(window) if child.winfo_class() == 'Button' and child.cget('text') == 'フォルダを選択・切り替え')
assert window.winfo_width() > window.winfo_height()
assert button.winfo_ismapped()
assert button.winfo_rooty() + button.winfo_height() <= window.winfo_rooty() + window.winfo_height()
assert button.winfo_rootx() + button.winfo_width() <= window.winfo_rootx() + window.winfo_width()
window.destroy()
"""
        result = subprocess.run([sys.executable, "-c", script], text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
