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
