"""Embedded trimming preview and controls."""

import shutil
import subprocess
import threading
import time
import tkinter as tk
from tkinter import ttk

from .dialogs import messagebox
from .media import _probe
from .storage import StorageError
from .trimming import boundaries, destination, history, trim_video


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
        self.generation = 0
        self.image = None
        self._clock = None
        self._base = 0.0
        self._play_start = 0.0
        self._play_end = 0.0
        self.columnconfigure(0, weight=1)
        line = ttk.Frame(self)
        line.grid(row=0, column=0, sticky="ew")
        ttk.Label(line, text="登録済み動画").pack(side="left")
        self.sources = ttk.Combobox(line, textvariable=self.source, state="readonly", width=35)
        self.sources.pack(side="left", padx=6)
        self.sources.bind("<<ComboboxSelected>>", self._select)
        ttk.Button(line, text="一覧を更新", command=self.refresh).pack(side="left")
        ttk.Button(line, text="履歴を表示", command=self.show_history).pack(side="left", padx=6)
        self.screen = ttk.Label(self, text="動画を選んでください", anchor="center")
        self.screen.grid(row=1, column=0, sticky="nsew", pady=6)
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
            self.duration = float(info.duration or 0)
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
        if self.playing:
            self.pause()

    def _seek_release(self, _event):
        self._frame(self.position.get())

    def _frame(self, seconds):
        if not self.source.get():
            return
        self.generation += 1
        generation = self.generation
        path = self._path()
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            self.details.set("プレビューに ffmpeg が必要です")
            return
        def worker():
            result = subprocess.run([ffmpeg, "-v", "error", "-ss", str(max(0, seconds)), "-i", str(path),
                                     "-frames:v", "1", "-vf", "scale=640:-2", "-f", "image2pipe",
                                     "-vcodec", "png", "-"], capture_output=True)
            if result.returncode == 0 and result.stdout:
                def display():
                    if generation == self.generation and self.winfo_exists():
                        import base64
                        self.image = tk.PhotoImage(data=base64.b64encode(result.stdout).decode("ascii"))
                        self.screen.configure(image=self.image, text="")
                try:
                    self.after(0, display)
                except RuntimeError:
                    pass
        threading.Thread(target=worker, daemon=True).start()

    def pause(self):
        if self.playing:
            self.position.set(min(self._play_end, self._base + time.monotonic() - self._clock))
        self.playing = False
        if self.audio is not None and self.audio.poll() is None:
            self.audio.terminate()
        self.audio = None

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
        self.position.set(start)
        self.playing = True
        ffplay = shutil.which("ffplay")
        if ffplay:
            self.audio = subprocess.Popen([ffplay, "-nodisp", "-autoexit", "-loglevel", "error",
                                           "-ss", str(start), "-t", str(end - start), str(self._path())],
                                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self._tick()

    def _tick(self):
        if not self.playing or not self.winfo_exists():
            return
        now = min(self._play_end, self._base + time.monotonic() - self._clock)
        self.position.set(now)
        self._frame(now)
        if now >= self._play_end:
            self.pause()
        else:
            self.after(200, self._tick)

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
        if self.adopted is None:
            return
        source, name, _, _, first, last = self.adopted
        self.process_panel.start("動画のトリミング", trim_video,
                                 (self.data, self._path(), name, first, last),
                                 on_result=lambda _result: self.refresh_videos(),
                                 on_finished=lambda _operation: self.refresh())

    def show_history(self):
        try:
            rows = history(self.data, self._path())
            text = "\n".join(f"{row['parent']}: {row['start_ms'] / 1000:.3f}–{row['end_ms'] / 1000:.3f} 秒" for row in rows)
            messagebox.showinfo("トリミング履歴", text or "この動画は元動画です")
        except (OSError, StorageError, ValueError, KeyError) as error:
            messagebox.showerror("履歴を表示できません", str(error))

    def _destroy(self, event):
        if event.widget is self:
            self.pause()
