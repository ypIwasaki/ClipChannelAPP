"""Supporting-media controls for the current editing video."""

import math
import os
import shutil
import subprocess
import threading
import tkinter as tk
from dataclasses import replace
from tkinter import filedialog, messagebox, ttk

from .editor_bridge import apply_supporting_media
from .storage import StorageError
from .supporting_media import MediaPlacement, import_supporting_media, save_supporting_media


class SupportingMediaPanel(ttk.Frame):
    def __init__(self, parent, data, status):
        super().__init__(parent, padding=4)
        self.data = data
        self.status = status
        self.video = None
        self.placements: list[MediaPlacement] = []
        self.preview = None
        self.player = None
        self.video_label = tk.StringVar(value="切り出し区間タブで編集用動画を作成してください")
        ttk.Label(self, textvariable=self.video_label, wraplength=500).pack(anchor="w")
        buttons = ttk.Frame(self)
        buttons.pack(anchor="w", pady=6)
        for label, kind in (("画像を追加", "image"), ("BGMを追加", "bgm"), ("効果音を追加", "sound")):
            ttk.Button(buttons, text=label, command=lambda value=kind: self.add(value)).pack(side="left")
        self.listing = tk.Listbox(self, height=6, exportselection=False)
        self.listing.pack(fill="both", expand=True)
        self.listing.bind("<<ListboxSelect>>", self.select)
        self.fields = {name: tk.StringVar(value=value) for name, value in
                       (("first", "0"), ("length", "1"), ("offset", "0"), ("volume", "100"),
                        ("x", "0"), ("y", "0"), ("scale", "100"), ("preview_frame", "0"))}
        form = ttk.Frame(self)
        form.pack(anchor="w", pady=6)
        for index, (label, name) in enumerate((("開始F (0始まり)", "first"), ("長さF", "length"),
                ("素材の開始秒（音声）", "offset"), ("音量 %", "volume"), ("画像 X", "x"),
                ("画像 Y", "y"), ("画像拡大率 %", "scale"), ("プレビュー開始F", "preview_frame"))):
            ttk.Label(form, text=label).grid(row=index, column=0, sticky="w")
            ttk.Entry(form, textvariable=self.fields[name], width=14).grid(row=index, column=1, sticky="w")
        ttk.Label(self, text="BGMは元の長さで追加します。必要な長さは手動で調整してください。\n"
                  "プレビュー音声は開始Fから最大5秒、映像終端までです。", wraplength=500).pack(anchor="w")
        ttk.Button(self, text="配置をAviUtl2へ適用・プレビュー", command=self.apply).pack(anchor="w", pady=6)
        ttk.Button(self, text="直前のプレビューを開く", command=self.show_preview).pack(anchor="w")

    def set_video(self, video):
        self.stop_audio()
        self.video = video
        self.placements.clear()
        self.preview = None
        self.listing.delete(0, tk.END)
        self.video_label.set(str(video) if video else "切り出し区間タブで編集用動画を作成してください")

    def refresh(self, index):
        self.listing.delete(0, tk.END)
        for item in self.placements:
            self.listing.insert(tk.END, f"{item.asset.name} | {item.kind} | {item.first}Fから {item.length}F")
        self.listing.selection_set(index)
        self.select()

    def select(self, _event=None):
        selected = self.listing.curselection()
        if not selected:
            return
        item = self.placements[selected[0]]
        for name, variable in self.fields.items():
            variable.set(str(item.first if name == "preview_frame" else getattr(item, name)))

    def run(self, work, finish):
        if self.data.running:
            messagebox.showerror("補助素材", "処理完了を待ってください")
            return
        self.data.running = True
        self.status.set("補助素材を処理中です。AviUtl2への適用中は手編集を待ってください")
        def worker():
            try:
                result = work()
            except Exception as error:
                reason = str(error) or type(error).__name__
                self.after(0, lambda: self.failed(reason))
            else:
                def done():
                    self.data.running = False
                    finish(result)
                self.after(0, done)
        threading.Thread(target=worker, daemon=True).start()

    def failed(self, reason):
        self.data.running = False
        self.status.set(reason)
        messagebox.showerror("補助素材を処理できません", reason)

    def add(self, kind):
        if self.video is None or self.data.running:
            messagebox.showerror("補助素材", "編集用動画を作成し、処理完了を待ってください")
            return
        source = filedialog.askopenfilename(title="補助素材を選択（データ用フォルダへコピーします）")
        if not source:
            return
        video = self.video
        def finish(item):
            self.placements.append(item)
            self.refresh(len(self.placements) - 1)
            self.status.set("補助素材をコピーしました。配置を調整してAviUtl2へ適用してください")
        self.run(lambda: import_supporting_media(self.data, video, source, kind), finish)

    def apply(self):
        selected = self.listing.curselection()
        if not selected or self.data.running:
            return
        index = selected[0]
        try:
            values = {name: int(variable.get()) if name in ("first", "length", "preview_frame")
                      else float(variable.get()) for name, variable in self.fields.items()}
            preview_frame = int(values.pop("preview_frame"))
            placement = replace(self.placements[index], **values)
            path = save_supporting_media(self.data, placement, preview_frame=preview_frame)
        except (OSError, ValueError, StorageError) as error:
            messagebox.showerror("配置を適用できません", str(error))
            return
        self.placements[index] = placement
        self.refresh(index)
        self.fields["preview_frame"].set(str(preview_frame))
        self.preview = None
        def finish(result):
            if result == "preview":
                self.preview = path
                self.status.set("補助素材の配置を適用しました。画像と音声を確認してください")
                self.show_preview()
            elif result == "applied":
                self.status.set("配置は適用済みです。プレビュー生成に失敗しました")
                messagebox.showwarning("補助素材", "配置は適用しましたが、プレビューを生成できませんでした")
            else:
                self.status.set("配置を適用できませんでした。対応するAviUtl2プロジェクトを確認してください")
                messagebox.showerror("補助素材", "対応する編集用動画を先頭に置き、projects 内の同名編集フォルダへ\n"
                                     "保存したAviUtl2プロジェクトを開いてください。プラグインの更新も確認してください。")
        self.run(lambda: apply_supporting_media(path), finish)

    def show_preview(self):
        if self.preview is None:
            messagebox.showinfo("プレビュー", "先に配置を適用してください")
            return
        try:
            picture = tk.PhotoImage(file=str(self.preview.with_suffix(".ppm")))
            factor = max(1, math.ceil(picture.width() / 700), math.ceil(picture.height() / 450))
            picture = picture.subsample(factor)
        except (OSError, tk.TclError) as error:
            messagebox.showerror("プレビュー", str(error))
            return
        popup = tk.Toplevel(self)
        popup.title("AviUtl2 補助素材プレビュー")
        label = ttk.Label(popup, image=picture)
        setattr(label, "picture", picture)
        label.pack()
        sound = self.preview.with_suffix(".wav")
        ttk.Button(popup, text="この位置から音声を試聴（最大5秒）", command=lambda: self.play_audio(sound)).pack()
        ttk.Button(popup, text="試聴を停止", command=self.stop_audio).pack()
        popup.protocol("WM_DELETE_WINDOW", lambda: (self.stop_audio(), popup.destroy()))

    def play_audio(self, sound):
        self.stop_audio()
        try:
            if os.name == "nt":
                import winsound
                winsound.PlaySound(str(sound), winsound.SND_FILENAME | winsound.SND_ASYNC)
            else:
                player = shutil.which("ffplay")
                if not player:
                    raise StorageError("試聴には ffplay が必要です")
                self.player = subprocess.Popen([player, "-nodisp", "-autoexit", "-loglevel", "error", str(sound)],
                                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except (OSError, RuntimeError, StorageError) as error:
            messagebox.showerror("試聴できません", str(error))

    def stop_audio(self):
        if os.name == "nt":
            import winsound
            winsound.PlaySound(None, 0)
        elif self.player is not None and self.player.poll() is None:
            self.player.terminate()
