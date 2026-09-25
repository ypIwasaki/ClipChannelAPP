"""Cooperative subprocess cancellation within a managed operation's process tree."""

import subprocess
import tempfile

from .storage import StorageError


class ProcessCancelled(StorageError):
    pass


def check_cancelled(stop):
    if stop and stop():
        raise ProcessCancelled("通常中止しました")


def run_process(command, *, stop=None, ffmpeg=False):
    """Wait for real exit; only an explicit force action may kill a process.

    FFmpeg accepts q on stdin to finish cooperatively. Probes have no graceful
    stop command, so cancellation waits for their exit before discarding results.
    Files drain both output streams while polling, including large frame probes.
    """
    check_cancelled(stop)
    with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
        process = subprocess.Popen(command, stdin=subprocess.PIPE if ffmpeg else subprocess.DEVNULL,
                                   stdout=stdout, stderr=stderr)
        requested = False
        try:
            while process.poll() is None:
                if stop and stop() and not requested:
                    requested = True
                    if ffmpeg and process.stdin is not None:
                        try:
                            process.stdin.write(b"q\n")
                            process.stdin.flush()
                        except (BrokenPipeError, OSError):
                            pass
                try:
                    process.wait(timeout=0.1)
                except subprocess.TimeoutExpired:
                    pass
            if requested:
                raise ProcessCancelled("通常中止しました")
            check_cancelled(stop)
            stdout.seek(0)
            stderr.seek(0)
            return subprocess.CompletedProcess(command, process.returncode,
                                               stdout.read().decode("utf-8", errors="replace"),
                                               stderr.read().decode("utf-8", errors="replace"))
        finally:
            if process.stdin is not None:
                try:
                    process.stdin.close()
                except (BrokenPipeError, OSError):
                    pass
