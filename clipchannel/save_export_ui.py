"""Explicit project save and verified movie export controls."""

import json
import threading
import time
import tkinter as tk
from fractions import Fraction
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .save_export import ExportSettings, export_video, inspect_project, save_project
from .storage import StorageError



class WidgetLock:
    """Temporarily disable editor controls and restore their previous states."""

    def __init__(self, roots, *, excluded=()):
        self.roots = tuple(roots)
        self.excluded = tuple(excluded)
        self.previous = None

    def set_locked(self, locked):
        if not locked:
            if self.previous is not None:
                for widget, state in self.previous:
                    widget.configure(state=state)
                self.previous = None
            return
        if self.previous is not None:
            return
        def descendants(widget):
            for child in widget.winfo_children():
                yield child
                yield from descendants(child)
        self.previous = []
        for root in self.roots:
            for widget in descendants(root):
                if widget not in self.excluded and isinstance(widget, (
                        ttk.Button, ttk.Entry, ttk.Combobox, ttk.Checkbutton, tk.Button, tk.Entry,
                        tk.Checkbutton, tk.Listbox, tk.Text)):
                    self.previous.append((widget, widget.cget("state")))
                    widget.configure(state="disabled")


def choose_action(parent, title, message, choices):
    """Show the actual action names; closing a prompt always means returning."""
    dialog = tk.Toplevel(parent)
    dialog.title(title)
    dialog.transient(parent.winfo_toplevel())
    result = [None]
    ttk.Label(dialog, text=message, wraplength=520, padding=16).pack(fill="x")
    buttons = ttk.Frame(dialog, padding=12)
    buttons.pack(fill="x")
    def selected(value):
        result[0] = value
        dialog.destroy()
    for label, value in choices:
        ttk.Button(buttons, text=label, command=lambda item=value: selected(item)).pack(side="left", padx=4)
    dialog.protocol("WM_DELETE_WINDOW", lambda: selected(None))
    dialog.grab_set()
    dialog.wait_window()
    return result[0]


class SaveExportPanel(ttk.Frame):
    def __init__(self, parent, data, status, *, has_drafts, prepare_drafts, lock_editing):
        super().__init__(parent, padding=8)
        self.data = data
        self.status = status
        self.has_drafts = has_drafts
        self.prepare_drafts = prepare_drafts
        self.lock_editing = lock_editing
        self.video = None
        self.project = None
        self.busy = False
        self.cancel = threading.Event()
        self.force = threading.Event()
        self._started_at = None
        self._finished_at = None
        self._operation_state = "待機中"
        self._can_force = False
        self._force_scope = "host"
        self._timer_id = None
        self._bitrate_default = "8"
        self.video_label = tk.StringVar(value="切り出し区間タブで編集用動画を作成してください")
        self.project_label = tk.StringVar(value="保存するAviUtl2プロジェクト: 未選択")
        self.kind = tk.StringVar(value="横")
        self.fields = {name: tk.StringVar(value=value) for name, value in
                       (("width", "1920"), ("height", "1080"), ("fps", "30"),
                        ("bitrate_mbps", "8"), ("audio_rate", "48000"))}
        self.fields["fps"].trace_add("write", self._fps_changed)
        ttk.Label(self, textvariable=self.video_label, wraplength=520).pack(anchor="w")
        ttk.Label(self, textvariable=self.project_label, wraplength=520).pack(anchor="w", pady=6)
        ttk.Button(self, text="対応するAviUtl2プロジェクトを選ぶ", command=self.choose_project).pack(anchor="w")
        ttk.Label(self, text="AviUtl2で開いている同じ編集のプロジェクトを保存します。\n"
                  "未適用の画面・字幕・補助素材の入力は「保存」で先に適用します。",
                  wraplength=520).pack(anchor="w", pady=8)
        profile = ttk.Frame(self)
        profile.pack(anchor="w")
        ttk.Label(profile, text="完成動画の用途").pack(side="left")
        ttk.Combobox(profile, textvariable=self.kind, values=("横", "ショート"),
                     state="readonly", width=12).pack(side="left")
        ttk.Button(profile, text="用途の初期値を設定", command=self.reset_defaults).pack(side="left", padx=8)
        for caption, name in (("出力幅 px", "width"), ("出力高さ px", "height"),
                              ("固定fps（分数も可）", "fps"), ("映像 Mbps", "bitrate_mbps"),
                              ("音声 Hz", "audio_rate")):
            line = ttk.Frame(self)
            line.pack(anchor="w", pady=3)
            ttk.Label(line, text=caption, width=24).pack(side="left")
            ttk.Entry(line, textvariable=self.fields[name], width=16).pack(side="left")
        ttk.Label(self, text="MP4 / H.264 / AAC-LC / SDR。映像の終了までを出力します。\n"
                  "出力中はAviUtl2と本アプリで同じ編集の操作を待ってください。",
                  wraplength=520).pack(anchor="w", pady=10)
        actions = ttk.Frame(self)
        actions.pack(anchor="w")
        ttk.Button(actions, text="保存", command=self.save).pack(side="left", padx=4)
        ttk.Button(actions, text="完成動画を書き出す", command=self.export).pack(side="left", padx=4)
        self.cancel_button = ttk.Button(actions, text="書き出しを中止", command=self.stop, state="disabled")
        self.cancel_button.pack(side="left", padx=4)
        self.force_button = ttk.Button(actions, text="強制停止…", command=self.force_stop, state="disabled")
        self.force_button.pack(side="left", padx=4)
        self.widget_lock = WidgetLock((self,), excluded=(self.cancel_button, self.force_button))
        self.process_summary = tk.StringVar(value="待機中 / 処理時間 0.0秒")
        ttk.Label(self, textvariable=self.process_summary).pack(anchor="w", pady=6)
        self.message = tk.StringVar()
        ttk.Label(self, textvariable=self.message, wraplength=520).pack(anchor="w", pady=10)

    def _fps_changed(self, *_args):
        try:
            value = "12" if Fraction(self.fields["fps"].get()) > 30 else "8"
        except (ValueError, ZeroDivisionError):
            return
        if self.fields["bitrate_mbps"].get() == self._bitrate_default:
            self.fields["bitrate_mbps"].set(value)
        self._bitrate_default = value

    def set_video(self, video, *, short=False):
        self.video = Path(video) if video is not None else None
        self.project = None
        self.project_label.set("保存するAviUtl2プロジェクト: 未選択")
        if self.video is not None:
            self.project_label.set("「保存」で、同じ編集用動画を開いているAviUtl2プロジェクトに名前を付けて保存します:\n" +
                                   str(self.data._root() / "projects" / self.video.parent.name))
        self.video_label.set(str(video) if video else "切り出し区間タブで編集用動画を作成してください")
        self.message.set("")
        self.kind.set("ショート" if short else "横")
        if self.video is not None:
            metadata = json.loads(self.video.with_suffix(".json").read_text(encoding="utf-8"))
            self.fields["fps"].set(str(metadata["fps"]))
        self.reset_defaults()

    def reset_defaults(self):
        if self.busy:
            return
        try:
            settings = ExportSettings.defaults(short=self.kind.get() == "ショート",
                                               fps=Fraction(self.fields["fps"].get()))
        except (ValueError, ZeroDivisionError) as error:
            messagebox.showerror("出力設定", str(error))
            return
        for name, variable in self.fields.items():
            variable.set(str(getattr(settings, name)))
        self._bitrate_default = self.fields["bitrate_mbps"].get()

    def settings(self):
        settings = ExportSettings(width=int(self.fields["width"].get()), height=int(self.fields["height"].get()),
                                  fps=Fraction(self.fields["fps"].get()),
                                  bitrate_mbps=float(self.fields["bitrate_mbps"].get()),
                                  audio_rate=int(self.fields["audio_rate"].get()))
        settings.validate()
        return settings

    def choose_project(self):
        if self.busy or self.data.running or self.video is None:
            return False
        directory = self.data._root() / "projects" / self.video.parent.name
        directory.mkdir(parents=True, exist_ok=True)
        selected = filedialog.askopenfilename(title="AviUtl2で開いている対応プロジェクトを選択",
                                              initialdir=str(directory), filetypes=(("AviUtl2", "*.aup2"),))
        if not selected:
            return False
        project = Path(selected).resolve()
        if project.parent != directory.resolve():
            messagebox.showerror("プロジェクト", "projects 内の同じ編集フォルダのプロジェクトを選んでください")
            return False
        self.project = project
        self.project_label.set(str(project))
        return True

    def _choose_new_project(self, directory):
        if self.video is None:
            return False
        directory.mkdir(parents=True, exist_ok=True)
        selected = filedialog.asksaveasfilename(
            title="AviUtl2プロジェクトに名前を付けて保存", initialdir=str(directory),
            initialfile=f"{self.video.stem}.aup2", defaultextension=".aup2",
            filetypes=(("AviUtl2", "*.aup2"),))
        if not selected:
            return False
        project = Path(selected).resolve()
        if project.parent != directory.resolve() or project.suffix.lower() != ".aup2":
            messagebox.showerror("プロジェクト", "projects 内の同じ編集フォルダに .aup2 形式で保存してください")
            return False
        if project.exists():
            messagebox.showerror("プロジェクト", "新しい保存名を指定してください。既存の編集は「対応するAviUtl2プロジェクトを選ぶ」で選択できます")
            return False
        self.project = project
        self.project_label.set(str(project))
        return True

    def _project(self):
        if self.video is None:
            raise StorageError("編集用動画を作成してください")
        if self.project is None:
            directory = self.data._root() / "projects" / self.video.parent.name
            candidates = sorted(directory.glob("*.aup2"))
            if len(candidates) == 1:
                self.project = candidates[0]
                self.project_label.set(str(self.project))
            elif not candidates:
                if not self._choose_new_project(directory):
                    raise StorageError("AviUtl2プロジェクトの保存先を選んでください")
            elif not self.choose_project():
                raise StorageError("対応するAviUtl2プロジェクトを選んでください")
        return self.project

    def _state(self):
        state = inspect_project(self._project(), self.video)
        if state.busy:
            raise StorageError("AviUtl2の処理完了を待ってください")
        return state

    def _refresh_time(self):
        self._timer_id = None
        elapsed = 0 if self._started_at is None else (self._finished_at or time.monotonic()) - self._started_at
        self.process_summary.set(f"{self._operation_state} / 処理時間 {elapsed:.1f}秒")
        if self.busy:
            self._timer_id = self.after(250, self._refresh_time)

    def _set_busy(self, busy, *, exporting=False):
        if not busy:
            if self._timer_id is not None:
                self.after_cancel(self._timer_id)
                self._timer_id = None
            self._finished_at = time.monotonic()
            self._can_force = False
        self.busy = self.data.running = busy
        self.lock_editing(busy)
        self.widget_lock.set_locked(busy)
        self.cancel_button.configure(state="normal" if busy and exporting else "disabled")
        self.force_button.configure(state="disabled")
        if not busy:
            self._refresh_time()

    def _report(self, result):
        self.message.set(result.detail)
        self.status.set(result.detail)
        if not result.confirmed and result.state != "cancelled":
            messagebox.showerror("処理の完了を確認できません", result.detail)

    def _start(self, *, destination=None, settings=None, after_save=None, save_first=True):
        if self.busy or self.data.running:
            return
        try:
            project = self._project()
            work, commit = self.prepare_drafts() if save_first else (lambda: None, lambda: None)
        except Exception as error:
            messagebox.showerror("保存・出力できません", str(error))
            return
        video = self.video
        self.cancel.clear()
        self.force.clear()
        self._can_force = False
        self._force_scope = "host"
        self._started_at = time.monotonic()
        self._finished_at = None
        self._operation_state = "保存中" if save_first else "書き出し中"
        self._set_busy(True, exporting=destination is not None)
        self._refresh_time()
        self.message.set("保存を確認しています" if save_first else "完成動画を書き出しています")
        self.status.set("保存・出力中です。同じプロジェクトへの編集を待ってください")
        def show_progress(value):
            if not self.busy:
                return
            self._force_scope = value.get("force_scope", "host")
            self._can_force = bool(value.get("can_force")) and not self.force.is_set()
            self.force_button.configure(state="normal" if self._can_force else "disabled")
            self._operation_state = "強制停止待ち" if self.force.is_set() else "停止待ち" if self.cancel.is_set() else "出力確認中" if value.get("state") == "verifying" else "書き出し中"
            detail = value.get("detail")
            if detail in ("audio", "video", "") or not detail:
                detail = "中止を要求しました。停止完了まで編集を待ってください" if self.cancel.is_set() else "完成動画を書き出しています"
            self.message.set(detail)
        def progress(value):
            self.after(0, show_progress, value)
        def worker():
            saved = False
            result = None
            try:
                if save_first:
                    work()
                    result = save_project(project, video)
                    saved = result.confirmed
                    if not saved:
                        self.after(0, lambda value=result: finish(value, False))
                        return
                if destination is not None:
                    result = export_video(project, video, destination, settings, cancel=self.cancel, force=self.force,
                                          on_progress=progress)
                if result is None:
                    raise StorageError("保存または出力を選択してください")
                self.after(0, lambda value=result: finish(value, saved))
            except Exception as error:
                reason = str(error) or type(error).__name__
                self.after(0, lambda: failed(reason, saved))
        def finish(result, saved):
            self._operation_state = "完了" if result.confirmed else "中止" if result.state == "cancelled" else "未確認" if result.state == "unconfirmed" else "失敗"
            self._set_busy(False)
            if saved:
                commit()
            self._report(result)
            if after_save is not None and saved:
                after_save()
        def failed(reason, saved):
            self._operation_state = "失敗"
            self._set_busy(False)
            if saved:
                commit()
            self.message.set(reason)
            self.status.set(reason)
            messagebox.showerror("保存・出力できません", f"{reason}\n入力は保持しています")
        threading.Thread(target=worker, daemon=True).start()

    def save(self):
        self._start()

    def export(self):
        if self.busy or self.data.running:
            return
        try:
            settings = self.settings()
            state = self._state()
        except Exception as error:
            messagebox.showerror("書き出せません", str(error))
            return
        if self.kind.get() == "ショート" and not settings.short_eligible(state.duration):
            action = choose_action(self, "ショート条件外", "ショートの条件（正方形または縦長、3分以内）から外れています。\n"
                                   "通常の動画として出力しても現在の比率・配置・長さ・設定を保持します。",
                                   (("編集・設定を直す", None), ("通常の動画として書き出す", "normal")))
            if action != "normal":
                return
        save_first = self.has_drafts() or state.dirty is not False
        if save_first and choose_action(self, "未保存の編集", "未保存の編集があります、または保存状態を確認できません。",
                                        (("保存して書き出す", "save"), ("戻る", None))) != "save":
            return
        if self.video is None:
            return
        directory = self.data._root() / "exports"
        directory.mkdir(parents=True, exist_ok=True)
        selected = filedialog.asksaveasfilename(title="完成動画の保存先（新しいファイル名）", initialdir=str(directory),
                                              initialfile=f"{self.video.stem}_finished.mp4", defaultextension=".mp4",
                                              filetypes=(("MP4", "*.mp4"),))
        if not selected:
            return
        destination = Path(selected)
        if destination.exists():
            messagebox.showerror("書き出せません", "既存の動画は上書きしません。新しいファイル名を選んでください")
            return
        self._start(destination=destination, settings=settings, save_first=save_first)

    def stop(self):
        if self.busy:
            self.cancel.set()
            self._operation_state = "停止待ち"
            self.message.set("中止を要求しました。停止完了まで編集を待ってください")
            self.status.set(self.message.get())
            self.cancel_button.configure(state="disabled")

    def force_stop(self):
        if not self.busy or not self.cancel.is_set() or not self._can_force or self.force.is_set():
            return
        scope = self._force_scope
        impact = ("完成動画の確認処理と、そのffprobeだけを強制終了します。AviUtl2内の編集は保持します。\n"
                  if scope == "verification" else
                  "この書き出しを受け付けたAviUtl2と、そのエンコーダーを強制終了します。\n"
                  "AviUtl2内の未保存の編集は失われます。\n")
        action = choose_action(self, "書き出しの強制停止", "通常の中止にまだ応答していません。\n" + impact +
            "本アプリの入力と保存済みのファイルは保持します。\n"
            "出力ファイルは完成確認済みとして扱いません。停止確認後に編集を再開できます。",
            (("強制停止する", "force"), ("停止を待つ", None)))
        if action == "force" and self.busy and self._can_force and self._force_scope == scope:
            self.force.set()
            self._can_force = False
            self._operation_state = "強制停止待ち"
            self.force_button.configure(state="disabled")
            self.message.set("強制停止を要求しました。確認処理の終了を待っています" if scope == "verification" else
                             "強制停止を要求しました。AviUtl2とエンコーダーの終了確認を待っています")
            self.status.set(self.message.get())

    def request_close(self, close):
        if self.busy:
            self.stop()
            messagebox.showinfo("停止待ち", "保存・出力の停止完了後にもう一度閉じてください")
            return
        if self.video is None:
            close()
            return
        try:
            dirty = self.project is None or self._state().dirty is not False
        except Exception:
            dirty = True
        if not dirty and not self.has_drafts():
            close()
            return
        action = choose_action(self, "未保存の編集", "未保存の編集があります、または保存状態を確認できません。",
                               (("保存する", "save"), ("破棄する", "discard"), ("戻る", None)))
        if action == "discard":
            close()
        elif action == "save":
            self._start(after_save=close)

    def has_unsaved_project(self):
        if self.video is None:
            return False
        if self.has_drafts() or self.project is None:
            return True
        try:
            return self._state().dirty is not False
        except Exception:
            return True
