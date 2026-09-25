"""Owned background processes with cooperative cancellation and explicit force stop.

Targets must be module-level callables for the spawn multiprocessing context. They
receive a control object before their normal arguments. Polling never reads a
partially received pipe message on the UI thread.
"""

import ctypes
import multiprocessing
import os
import queue
import signal
import threading
import time
from multiprocessing.connection import Connection
from multiprocessing.process import BaseProcess
from typing import Any, Callable


class OperationControl:
    def __init__(self, cancellation: Any, sender: Connection):
        self._cancellation = cancellation
        self._sender = sender

    def cancelled(self) -> bool:
        return self._cancellation.is_set()

    def report(self, value: Any) -> None:
        self._sender.send(("progress", value))


def _run_target(target, args, kwargs, cancellation, sender, gate, abort):
    try:
        # The target cannot launch descendants until containment is established.
        if os.name != "nt":
            os.setsid()
        gate.wait()
        if abort.is_set():
            return
        control = OperationControl(cancellation, sender)
        result = None if control.cancelled() else target(control, *args, **kwargs)
        sender.send(("result", result))
    except BaseException as error:
        try:
            sender.send(("error", str(error) or type(error).__name__))
        except (EOFError, OSError):
            pass
    finally:
        sender.close()


class _WindowsJob:
    """A private job: descendants inherit membership; no name-based process kill."""

    class _Accounting(ctypes.Structure):
        _fields_ = [("user", ctypes.c_longlong), ("kernel", ctypes.c_longlong),
                    ("period_user", ctypes.c_longlong), ("period_kernel", ctypes.c_longlong),
                    ("page_faults", ctypes.c_ulong), ("total", ctypes.c_ulong),
                    ("active", ctypes.c_ulong), ("terminated", ctypes.c_ulong)]

    def __init__(self):
        from ctypes import wintypes

        self._api = getattr(ctypes, "WinDLL")("kernel32", use_last_error=True)
        signatures = {
            "CreateJobObjectW": ([ctypes.c_void_p, wintypes.LPCWSTR], wintypes.HANDLE),
            "OpenProcess": ([wintypes.DWORD, wintypes.BOOL, wintypes.DWORD], wintypes.HANDLE),
            "AssignProcessToJobObject": ([wintypes.HANDLE, wintypes.HANDLE], wintypes.BOOL),
            "QueryInformationJobObject": ([wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p,
                                            wintypes.DWORD, ctypes.c_void_p], wintypes.BOOL),
            "TerminateJobObject": ([wintypes.HANDLE, wintypes.UINT], wintypes.BOOL),
            "CloseHandle": ([wintypes.HANDLE], wintypes.BOOL),
        }
        for name, (arguments, result) in signatures.items():
            function = getattr(self._api, name)
            function.argtypes, function.restype = arguments, result
        self._handle = self._api.CreateJobObjectW(None, None)
        if not self._handle:
            raise getattr(ctypes, "WinError")(getattr(ctypes, "get_last_error")())

    def assign(self, pid: int) -> None:
        process = self._api.OpenProcess(0x0100 | 0x0001, False, pid)
        if not process:
            raise getattr(ctypes, "WinError")(getattr(ctypes, "get_last_error")())
        try:
            if not self._api.AssignProcessToJobObject(self._handle, process):
                raise getattr(ctypes, "WinError")(getattr(ctypes, "get_last_error")())
        finally:
            self._api.CloseHandle(process)

    def active(self) -> bool:
        info = self._Accounting()
        if not self._api.QueryInformationJobObject(
                self._handle, 1, ctypes.byref(info), ctypes.sizeof(info), None):
            raise getattr(ctypes, "WinError")(getattr(ctypes, "get_last_error")())
        return bool(info.active)

    def terminate(self) -> None:
        if not self._api.TerminateJobObject(self._handle, 1):
            raise getattr(ctypes, "WinError")(getattr(ctypes, "get_last_error")())

    def close(self) -> None:
        if self._handle:
            self._api.CloseHandle(self._handle)
            self._handle = None


def _group_active(group: int) -> bool:
    if os.path.isdir("/proc"):
        # Orphan zombies can remain until the OS's reaper runs. They have already
        # stopped and must not prevent the user from resuming editing.
        for entry in os.scandir("/proc"):
            if not entry.name.isdecimal():
                continue
            try:
                with open(f"/proc/{entry.name}/stat", encoding="utf-8") as source:
                    fields = source.read().rsplit(")", 1)[1].split()
                if int(fields[2]) == group and fields[0] not in ("Z", "X"):
                    return True
            except (FileNotFoundError, ProcessLookupError):
                continue
        return False
    try:
        os.killpg(group, 0)
        return True
    except ProcessLookupError:
        return False


class ManagedOperation:
    """Track one owned worker and its children until every process has stopped.

    request_cancel sets a cooperative flag. After three seconds without
    completion, can_force only enables the caller's explicit confirmation UI;
    no timer ever terminates a process. force_stop requires that flag.
    """

    FORCE_GRACE_SECONDS = 3.0

    def __init__(self, label: str, target: Callable, args=(), kwargs=None):
        self.label = label
        self.state = "未着手"
        self.result: Any = None
        self.error = ""
        self.progress: Any = None
        self._target, self._args, self._kwargs = target, args, kwargs or {}
        self._context = multiprocessing.get_context("spawn")
        self._cancellation = self._context.Event()
        self._gate = self._context.Event()
        self._abort = self._context.Event()
        self._process: BaseProcess | None = None
        self._job: _WindowsJob | None = None
        self._messages: queue.SimpleQueue[tuple[str, Any]] = queue.SimpleQueue()
        self._reader_done = threading.Event()
        self._active = False
        self._started_at: float | None = None
        self._ended_at: float | None = None
        self._cancelled_at: float | None = None
        self._forced = False
        self._received_result = False
        self._received_error = False
        self._startup_error = False

    @property
    def active(self) -> bool:
        return self._active

    @property
    def elapsed(self) -> float:
        if self._started_at is None:
            return 0.0
        end = self._ended_at if self._ended_at is not None else time.monotonic()
        return end - self._started_at

    @property
    def can_force(self) -> bool:
        return (self.active and not self._forced and self._cancelled_at is not None
                and time.monotonic() - self._cancelled_at >= self.FORCE_GRACE_SECONDS)

    def start(self) -> None:
        if self._started_at is not None:
            raise RuntimeError("同じ処理を再開することはできません")
        if os.name == "nt":
            self._job = _WindowsJob()
        receiver, sender = self._context.Pipe(duplex=False)
        self._process = self._context.Process(
            target=_run_target,
            args=(self._target, self._args, self._kwargs, self._cancellation,
                  sender, self._gate, self._abort),
            name=f"ClipChannel-{self.label}",
        )
        self._started_at = time.monotonic()
        try:
            self._process.start()
        except BaseException:
            receiver.close()
            sender.close()
            if self._job:
                self._job.close()
            self._ended_at = time.monotonic()
            self.state = "失敗"
            raise
        sender.close()
        self._active = True
        self.state = "実行中"
        threading.Thread(target=self._read_messages, args=(receiver,), daemon=True).start()
        try:
            if self._job:
                assert self._process.pid is not None
                self._job.assign(self._process.pid)
        except OSError as error:
            # Release the bootstrap without executing user work. Do not force
            # terminate a task merely because setup or monitoring failed.
            self.error = f"処理の管理を開始できませんでした: {error}"
            self._startup_error = True
            self._abort.set()
            self.state = "停止待ち"
        finally:
            self._gate.set()

    def _read_messages(self, receiver: Connection) -> None:
        try:
            while True:
                self._messages.put(receiver.recv())
        except (EOFError, OSError):
            pass
        finally:
            receiver.close()
            self._reader_done.set()

    def _drain_messages(self) -> None:
        while True:
            try:
                kind, value = self._messages.get_nowait()
            except queue.Empty:
                return
            if kind == "progress":
                self.progress = value
            elif kind == "result":
                self.result = value
                self._received_result = True
            elif kind == "error":
                self.error = value
                self._received_error = True

    def poll(self) -> None:
        self._drain_messages()
        if not self.active:
            return
        process = self._process
        assert process is not None and process.pid is not None
        if process.is_alive():
            return
        try:
            descendants_active = (self._job.active() if self._job
                                  else _group_active(process.pid))
        except OSError as error:
            self.error = f"関連処理の停止を確認できません: {error}"
            return
        if descendants_active:
            if self._cancelled_at is None:
                self.state = "関連処理の終了待ち"
            return
        if not self._reader_done.is_set():
            return
        # The reader may have enqueued the final result since the first drain.
        self._drain_messages()
        process.join(timeout=0)
        exitcode = process.exitcode
        process.close()
        if self._job:
            self._job.close()
        self._ended_at = time.monotonic()
        self._active = False
        if self._startup_error:
            self.state = "失敗"
        elif self._forced:
            self.state = "強制停止"
        elif self._cancelled_at is not None:
            self.state = "中止"
        elif self._received_error:
            self.state = "失敗"
        elif exitcode != 0 or not self._received_result:
            self.state = "失敗"
            self.error = "処理が結果を返さずに終了しました"
        else:
            self.state = "完了"

    def request_cancel(self) -> None:
        self.poll()
        if not self.active or self._cancelled_at is not None:
            return
        self._cancelled_at = time.monotonic()
        self._cancellation.set()
        self.state = "停止待ち"

    def force_stop(self) -> bool:
        self.poll()
        if not self.can_force:
            return False
        try:
            if self._job:
                self._job.terminate()
            else:
                assert self._process is not None and self._process.pid is not None
                os.killpg(self._process.pid, signal.SIGKILL)
        except ProcessLookupError:
            self.poll()
            return False
        self._forced = True
        self.state = "強制停止待ち"
        return True
