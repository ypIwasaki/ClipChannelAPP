"""Registration, lossless archive, and log maintenance controls."""

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from . import operation_tasks
from .operation_logs import cleanup_logs
from .registrations import RegistrationManager
from .storage import StorageError


KIND_NAMES = {"people": "人物", "registered-words": "登録語", "excluded-words": "除外語",
              "results": "保存済み結果", "videos": "動画"}


class ManagementPanel(ttk.Frame):
    def __init__(self, parent, data, status, *, refresh_lists, start_operation, has_drafts):
        super().__init__(parent, padding=8)
        self.data = data
        self.status = status
        self.refresh_lists = refresh_lists
        self.start_operation = start_operation
        self.has_drafts = has_drafts
        self.entries = []
        self.show_hidden = tk.BooleanVar()
        ttk.Label(self, text="非表示にしても保存済み結果と辞書の内容は保持します。",
                  wraplength=440).pack(anchor="w")
        ttk.Checkbutton(self, text="非表示の項目も表示", variable=self.show_hidden,
                        command=self.refresh).pack(anchor="w")
        self.listing = tk.Listbox(self, height=9, exportselection=False)
        self.listing.pack(fill="both", expand=True)
        actions = ttk.Frame(self)
        actions.pack(fill="x", pady=4)
        ttk.Button(actions, text="非表示", command=lambda: self.set_hidden(True)).pack(side="left")
        ttk.Button(actions, text="再表示", command=lambda: self.set_hidden(False)).pack(side="left", padx=4)
        ttk.Button(actions, text="登録情報を削除…", command=self.delete_registration).pack(side="left")
        ttk.Label(self, text="登録情報の削除では実ファイルを残します。参照中の情報は削除できません。",
                  wraplength=440).pack(anchor="w")
        ttk.Button(self, text="実ファイルを選んで削除…", command=self.delete_file).pack(anchor="w", pady=6)
        archive_actions = ttk.LabelFrame(self, text="動画の可逆保管", padding=6)
        archive_actions.pack(fill="x", pady=4)
        ttk.Label(archive_actions, text="元動画・保管物は保持し、展開先は毎回別フォルダにします。",
                  wraplength=420).pack(anchor="w")
        ttk.Button(archive_actions, text="動画を保管…", command=self.archive).pack(side="left", pady=4)
        ttk.Button(archive_actions, text="保管物を展開…", command=self.restore).pack(side="left", padx=4)
        self.result_text = tk.StringVar()
        ttk.Label(self, textvariable=self.result_text, wraplength=440).pack(anchor="w", fill="x", pady=4)
        ttk.Button(self, text="30日経過した通常ログを整理", command=self.clean_logs).pack(anchor="w", pady=4)
        ttk.Label(self, text="復旧待ちの情報がある間はログを保持します。",
                  wraplength=440).pack(anchor="w")

    def refresh(self):
        self.listing.delete(0, tk.END)
        self.entries = (RegistrationManager(self.data).list_entries(include_hidden=self.show_hidden.get())
                        if self.data.path else [])
        for entry in self.entries:
            self.listing.insert(tk.END, f"{'非表示 | ' if entry.hidden else ''}{KIND_NAMES[entry.kind]} | {entry.label}")

    def reset(self):
        self.result_text.set("")
        self.refresh()

    def _ready(self):
        if not self.data.path:
            messagebox.showerror("管理できません", "データ用フォルダを選んでください")
            return False
        if self.data.running or self.has_drafts():
            messagebox.showerror("管理できません", "処理の完了と未保存入力の保存を先に行ってください")
            return False
        return True

    def _selected(self):
        indices = self.listing.curselection()
        if not indices:
            raise StorageError("管理する一覧項目を選んでください")
        return self.entries[indices[0]]

    def _changed(self):
        self.refresh_lists()
        self.refresh()

    def set_hidden(self, hidden):
        if not self._ready():
            return
        try:
            entry = self._selected()
            RegistrationManager(self.data).set_hidden(entry.kind, entry.key, hidden)
            self._changed()
            self.status.set("非表示にしました" if hidden else "再表示しました")
        except (OSError, StorageError) as error:
            messagebox.showerror("表示を変更できません", str(error))

    def delete_registration(self):
        if not self._ready():
            return
        try:
            entry = self._selected()
            if not messagebox.askyesno("登録情報を削除", f"{entry.label}\n登録情報を削除しますか？\n"
                                       "実ファイルは残ります。保存済み結果から参照されていれば削除を止めます。",
                                       default="no"):
                return
            RegistrationManager(self.data).delete_registration(entry.kind, entry.key)
            self._changed()
            self.status.set("登録情報を削除しました。実ファイルは保持しています")
        except (OSError, StorageError) as error:
            messagebox.showerror("登録情報を削除できません", str(error))

    def delete_file(self):
        if not self._ready():
            return
        selected = filedialog.askopenfilename(title="削除する実ファイルを選択", initialdir=str(self.data.path))
        if not selected:
            return
        try:
            path = Path(selected).resolve()
            relative = path.relative_to(self.data._root()).as_posix()
            if not messagebox.askyesno("実ファイルを削除", f"{path}\nこの実ファイルを完全に削除しますか？\n"
                                       "この操作は取り消せません。登録情報の削除とは別の操作です。",
                                       default="no"):
                return
            RegistrationManager(self.data).delete_file(relative, confirmed=True)
            self._changed()
            self.status.set("選択した実ファイルを削除しました")
        except (OSError, ValueError) as error:
            messagebox.showerror("実ファイルを削除できません", str(error))

    def archive(self):
        if not self._ready():
            return
        selected = filedialog.askopenfilename(title="保管する動画を選択",
                                              initialdir=str(self.data._root() / "media" / "originals"))
        if selected:
            self.start_operation("動画の可逆保管", operation_tasks.archive,
                                 (self.data, Path(selected)), on_result=self.show_result)

    def restore(self):
        if not self._ready():
            return
        selected = filedialog.askopenfilename(title="展開する保管物を選択",
                                              initialdir=str(self.data._root() / "archives"),
                                              filetypes=[("ClipChannel ZIP", "*.zip")])
        if selected:
            self.start_operation("保管物の展開", operation_tasks.restore,
                                 (self.data, Path(selected)), on_result=self.show_result)

    def show_result(self, result):
        self.result_text.set(f"{result.summary}\n保存先: {result.output}")
        self.status.set("保管・展開が完了しました")
        self.refresh()

    def clean_logs(self):
        if not self._ready():
            return
        try:
            removed = cleanup_logs(self.data)
            self.status.set(f"通常ログを {len(removed)} 件整理しました。復旧待ちの情報があればログを保持します")
        except (OSError, StorageError) as error:
            messagebox.showerror("ログを整理できません", str(error))
