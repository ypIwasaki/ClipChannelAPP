import unittest
from unittest.mock import patch

from clipchannel.process_control import run_process


class HiddenProcessTests(unittest.TestCase):
    def test_managed_ffmpeg_does_not_open_windows_console(self):
        with patch("os.name", "nt"), patch(
                "clipchannel.process_control.subprocess.Popen") as launch:
            process = launch.return_value
            process.poll.return_value = 0
            process.returncode = 0
            process.stdin = None
            run_process(["ffmpeg.exe", "-version"], ffmpeg=True)
        self.assertEqual(launch.call_args.kwargs.get("creationflags"), 0x08000000)
