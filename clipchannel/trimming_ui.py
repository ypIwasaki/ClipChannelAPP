"""Embedded trimming preview and controls."""

import shutil
import subprocess
import threading
import time
import tkinter as tk
import uuid
from tkinter import ttk

from .dialogs import messagebox
from .media import _probe
from .process_launch import hidden_console_kwargs
from .storage import StorageError
from .trimming import boundaries, cleanup_staged, destination, history, trim_video, video_duration


class TrimmingPanel(ttk.Frame):
    def __init__(self, parent, data, process_panel, refresh_videos):
        super().__init__(parent, padding=8)
        self.data, self.process_panel, self.refresh_videos = data, process_panel, refresh_videos
        self.source = tk.StringVar()
        self.name = tk.StringVar()
        self.start = tk.StringVar(value="0.000")
        self.end = tk.StringVar(value="0.000")
        self.position = tk.DoubleVar(value=0)
        self.details = tk.StringVar()
        self.boundary_text = tk.StringVar()
        self.duration = 0.0
        self.adopted = None
        self.playing = False
        self.audio = None
        self.video_process = None
        self.generation = 0
        self.image = None
        self._preview_condition = threading.Condition()
        self._preview_request = None
        self._preview_stop = False
        self._preview_process = None
        threading.Thread(target=self._preview_worker, daemon=True).start()
        self._clock = None
        self._base = 0.0
        self._play_start = 0.0
        self._play_end = 0.0
        self._tick_id = None
        self._updating_position = False
        self.columnconfigure(0, weight=1)
        line = ttk.Frame(self)
        line.grid(row=0, column=0, sticky="ew")
        ttk.Label(line, text="登録済み動画").pack(side="left")
        self.sources = ttk.Combobox(line, textvariable=self.source, state="readonly", width=35)
        self.sources.pack(side="left", padx=6)
        self.sources.bind("<<ComboboxSelected>>", self._select)
        ttk.Button(line, text="一覧を更新", command=self.refresh).pack(side="left")
        ttk.Button(line, text="履歴を表示", command=self.show_history).pack(side="left", padx=6)
        self.screen = tk.Canvas(self, width=640, height=360, background="black", highlightthickness=0)
        self.screen.grid(row=1, column=0, sticky="nsew", pady=6)
        self.screen.create_text(320, 180, text="動画を選んでください", fill="white", tags="placeholder")
        self._resize_id = None
        self.screen.bind("<Configure>", self._resize_preview)
        self.rowconfigure(1, weight=1)
        scale = ttk.Scale(self, from_=0, to=1, variable=self.position, command=self._seek_drag)
        scale.grid(row=2, column=0, sticky="ew")
        self.scale = scale
        self.scale.bind("<ButtonRelease-1>", self._seek_release)
        actions = ttk.Frame(self)
        actions.grid(row=3, column=0, sticky="w", pady=5)
        ttk.Button(actions, text="再生／一時停止", command=self.toggle).pack(side="left")
        ttk.Button(actions, text="現在位置を開始に", command=lambda: self.start.set(f"{self.position.get():.3f}")).pack(side="left", padx=4)
        ttk.Button(actions, text="現在位置を終了に", command=lambda: self.end.set(f"{self.position.get():.3f}")).pack(side="left")
        ttk.Button(actions, text="選択範囲を再生", command=self.play_range).pack(side="left", padx=4)
        fields = ttk.Frame(self)
        fields.grid(row=4, column=0, sticky="w")
        for label, var in (("開始 秒", self.start), ("終了 秒", self.end), ("保存名", self.name)):
            ttk.Label(fields, text=label).pack(side="left", padx=(8, 2))
            ttk.Entry(fields, textvariable=var, width=24 if label == "保存名" else 10).pack(side="left")
        ttk.Button(fields, text="境界を確認", command=self.confirm).pack(side="left", padx=6)
        ttk.Button(fields, text="MP4を書き出す", command=self.export).pack(side="left")
        ttk.Label(self, textvariable=self.details, wraplength=800).grid(row=5, column=0, sticky="ew")
        ttk.Label(self, textvariable=self.boundary_text, wraplength=800).grid(row=6, column=0, sticky="ew")
        for var in (self.start, self.end, self.name):
            var.trace_add("write", self._invalidate)
        self.bind("<Destroy>", self._destroy, add="+")

    def _path(self):
        return self.data._root() / "media" / "originals" / self.source.get()

    def refresh(self):
        names = [path.name for path in self.data.list_videos()] if self.data.path else []
        self.sources.configure(values=names)
        if self.source.get() not in names:
            self.source.set(names[0] if names else "")
            if names:
                self._select()

    def _select(self, _event=None):
        self.pause()
        try:
            info = _probe(self._path())
            self.duration = video_duration(self._path())
            self.scale.configure(to=self.duration)
            self.position.set(0)
            self.start.set("0.000")
            self.end.set(f"{self.duration:.3f}")
            self.name.set(self._path().stem + "_trim.mp4")
            self.details.set(f"長さ {self.duration:.3f} 秒 / 音声 {'あり' if info.audio else 'なし'}")
            self._frame(0)
        except (OSError, StorageError, ValueError) as error:
            self.details.set(str(error))

    def _invalidate(self, *_args):
        self.adopted = None
        self.boundary_text.set("境界を確認してください")

    def _seek_drag(self, _value):
        if self.playing and not self._updating_position:
            self.pause()

    def _set_position(self, seconds):
        self._updating_position = True
        try:
            self.position.set(seconds)
        finally:
            self._updating_position = False

    def _seek_release(self, _event):
        self._frame(self.position.get())

    def _viewport(self):
        width, height = self.screen.winfo_width(), self.screen.winfo_height()
        if width < 32 or height < 32:
            width, height = 640, 360
        return min(width, 1280), min(height, 900)

    def _resize_preview(self, event):
        self.screen.coords("video", event.width // 2, event.height // 2)
        self.screen.coords("placeholder", event.width // 2, event.height // 2)
        if self._resize_id is not None:
            self.after_cancel(self._resize_id)
        if self.source.get() and not self.playing:
            self._resize_id = self.after(120, lambda: self._frame(self.position.get()))

    def _display_image(self, data):
        self.image = tk.PhotoImage(data=data)
        self.screen.delete("placeholder")
        self.screen.delete("video")
        self.screen.create_image(self.screen.winfo_width() // 2, self.screen.winfo_height() // 2,
                                 image=self.image, tags="video")

    def _frame(self, seconds):
        if not self.source.get():
            return
        self.generation += 1
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            self.details.set("プレビューに ffmpeg が必要です")
            return
        with self._preview_condition:
            self._preview_request = (self.generation, ffmpeg, self._path(), seconds, self._viewport())
            if self._preview_process is not None and self._preview_process.poll() is None:
                self._preview_process.terminate()
            self._preview_condition.notify()

    def _preview_worker(self):
        while True:
            with self._preview_condition:
                while self._preview_request is None and not self._preview_stop:
                    self._preview_condition.wait()
                if self._preview_stop:
                    return
                generation, ffmpeg, path, seconds, (width, height) = self._preview_request
                self._preview_request = None
            fit = f"scale={width}:{height}:force_original_aspect_ratio=decrease"
            process = subprocess.Popen([ffmpeg, "-v", "error", "-ss", str(max(0, seconds)), "-i", str(path),
                                        "-frames:v", "1", "-vf", fit, "-f", "image2pipe",
                                        "-vcodec", "png", "pipe:1"], stdout=subprocess.PIPE,
                                       stderr=subprocess.DEVNULL, **hidden_console_kwargs())
            with self._preview_condition:
                self._preview_process = process
                if self._preview_stop or generation != self.generation:
                    process.terminate()
            image_bytes, _ = process.communicate()
            with self._preview_condition:
                if self._preview_process is process:
                    self._preview_process = None
            if process.returncode == 0 and image_bytes:
                def display():
                    if generation == self.generation and self.winfo_exists():
                        import base64
                        self._display_image(base64.b64encode(image_bytes).decode("ascii"))
                try:
                    self.after(0, display)
                except RuntimeError:
                    pass

    def pause(self):
        if self._tick_id is not None:
            self.after_cancel(self._tick_id)
            self._tick_id = None
        if self.playing:
            self._set_position(min(self._play_end, self._base + time.monotonic() - self._clock))
        self.playing = False
        if self.audio is not None and self.audio.poll() is None:
            self.audio.terminate()
            try:
                self.audio.wait(timeout=.5)
            except subprocess.TimeoutExpired:
                self.audio.kill()
                self.audio.wait()
        self.audio = None
        if self.video_process is not None and self.video_process.poll() is None:
            self.video_process.terminate()
            try:
                self.video_process.wait(timeout=.5)
            except subprocess.TimeoutExpired:
                self.video_process.kill()
                self.video_process.wait()
        self.video_process = None
        self.generation += 1

    def toggle(self):
        if self.playing:
            self.pause()
        else:
            self._play(self.position.get(), self.duration)

    def play_range(self):
        try:
            start, end = float(self.start.get()), float(self.end.get())
            if not 0 <= start < end <= self.duration:
                raise ValueError()
            self._play(start, end)
        except ValueError:
            messagebox.showerror("再生できません", "有効な開始・終了秒を入力してください")

    def _play(self, start, end):
        self.pause()
        self._base, self._play_end, self._clock = start, end, time.monotonic()
        self._set_position(start)
        self.playing = True
        ffplay = shutil.which("ffplay")
        if ffplay:
            self.audio = subprocess.Popen([ffplay, "-nodisp", "-autoexit", "-loglevel", "error",
                                          "-ss", str(start), "-t", str(end - start), str(self._path())],
                                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                          **hidden_console_kwargs())
        self._start_video_stream(start, end)
        self._tick()

    def _start_video_stream(self, start, end):
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            return
        generation = self.generation
        width, height = self._viewport()
        fit = f"fps=10,scale={width}:{height}:force_original_aspect_ratio=decrease"
        process = subprocess.Popen([ffmpeg, "-v", "error", "-ss", str(start), "-i", str(self._path()),
                                    "-t", str(end - start), "-an", "-vf", fit,
                                    "-f", "image2pipe", "-vcodec", "png", "pipe:1"],
                                   stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                   **hidden_console_kwargs())
        self.video_process = process

        def read_exact(length):
            chunks = bytearray()
            while len(chunks) < length:
                part = process.stdout.read(length - len(chunks))
                if not part:
                    return None
                chunks.extend(part)
            return bytes(chunks)

        def reader():
            import base64
            signature = b"\x89PNG\r\n\x1a\n"
            frame_number = 0
            try:
                while self.playing and generation == self.generation:
                    header = read_exact(8)
                    if header != signature:
                        break
                    frame = bytearray(header)
                    while True:
                        chunk = read_exact(8)
                        if chunk is None:
                            return
                        length = int.from_bytes(chunk[:4], "big")
                        if length > 4_000_000:
                            return
                        payload = read_exact(length + 4)
                        if payload is None:
                            return
                        frame.extend(chunk)
                        frame.extend(payload)
                        if chunk[4:] == b"IEND":
                            break
                    encoded = base64.b64encode(frame).decode("ascii")
                    until = self._clock + frame_number / 10
                    if until > time.monotonic():
                        time.sleep(until - time.monotonic())
                    frame_number += 1
                    def display(image_data=encoded):
                        if self.playing and generation == self.generation and self.winfo_exists():
                            self._display_image(image_data)
                    try:
                        self.after(0, display)
                    except RuntimeError:
                        return
            finally:
                if process.poll() is None:
                    process.terminate()
                process.stdout.close()
        threading.Thread(target=reader, daemon=True).start()

    def _tick(self):
        self._tick_id = None
        if not self.playing or not self.winfo_exists():
            return
        now = min(self._play_end, self._base + time.monotonic() - self._clock)
        self._set_position(now)
        if now >= self._play_end:
            self.pause()
        else:
            self._tick_id = self.after(200, self._tick)

    def confirm(self):
        self.pause()
        try:
            destination(self.data, self.name.get())
            first, last = boundaries(self.data, self._path(), self.start.get(), self.end.get())
            self.adopted = (self.source.get(), self.name.get(), self.start.get(), self.end.get(), first, last)
            self.boundary_text.set(f"指定: {self.start.get()}–{self.end.get()} 秒 / 採用: {first / 1000:.3f}–{last / 1000:.3f} 秒")
        except (OSError, StorageError, ValueError) as error:
            self.boundary_text.set(str(error))

    def export(self):
        if self.adopted is None:
            self.confirm()
            return
        _, name, _, _, first, last = self.adopted
        work_name = f"trim-{uuid.uuid4().hex}"
        def finished(_operation):
            try:
                cleanup_staged(self.data, work_name)
            except (OSError, StorageError) as error:
                messagebox.showerror("一時ファイルを整理できません", str(error))
            self.refresh()
        self.process_panel.start("動画のトリミング", trim_video,
                                 (self.data, self._path(), name, first, last, work_name),
                                 on_result=lambda _result: self.refresh_videos(),
                                 on_finished=finished)

    def show_history(self):
        try:
            rows = history(self.data, self._path())
            text = "\n".join(f"{row['parent']}: {row['start_ms'] / 1000:.3f}–{row['end_ms'] / 1000:.3f} 秒" for row in rows)
            messagebox.showinfo("トリミング履歴", text or "この動画は元動画です")
        except (OSError, StorageError, ValueError, KeyError) as error:
            messagebox.showerror("履歴を表示できません", str(error))

    def _destroy(self, event):
        if event.widget is self:
            if self._resize_id is not None:
                self.after_cancel(self._resize_id)
            self.pause()
            with self._preview_condition:
                self._preview_stop = True
                if self._preview_process is not None and self._preview_process.poll() is None:
                    self._preview_process.terminate()
                self._preview_condition.notify()
