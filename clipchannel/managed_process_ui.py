"""Tk controls for a single owned operation and its confirmed stop."""

import tkinter as tk
from tkinter import messagebox, ttk

from .managed_process import ManagedOperation


class ProcessPanel(ttk.LabelFrame):
    def __init__(self, parent, status, lock):
        super().__init__(parent, text="管理対象の処理", padding=6)
        self.status = status
        self.lock = lock
        self.operation = None
        self.message = tk.StringVar(value="実行中の処理はありません")
        ttk.Label(self, textvariable=self.message, wraplength=900).pack(side="left", fill="x", expand=True)
        self.cancel_button = ttk.Button(self, text="通常中止", command=self.stop, state="disabled")
        self.cancel_button.pack(side="left", padx=4)
        self.force_button = ttk.Button(self, text="強制停止…", command=self.force, state="disabled")
        self.force_button.pack(side="left", padx=4)

    @property
    def active(self):
        return self.operation is not None and self.operation.active

    def start(self, label, target, args=(), kwargs=None, *, on_result=None, on_progress=None, on_finished=None):
        if self.active:
            return
        operation = ManagedOperation(label, target, args=args, kwargs=kwargs)
        try:
            self.lock(True)
            operation.start()
        except Exception as error:
            self.lock(False)
            messagebox.showerror("処理を開始できません", str(error))
            return
        self.operation = operation
        self.cancel_button.configure(state="normal")
        last_progress = None

        def tick():
            nonlocal last_progress
            operation.poll()
            if operation.progress is not last_progress:
                last_progress = operation.progress
                if on_progress is not None:
                    on_progress(last_progress)
            detail = operation.error or (operation.progress if isinstance(operation.progress, str) else "")
            summary = f"{label} | {operation.state} | {operation.elapsed:.1f}秒"
            if operation.state in ("停止待ち", "強制停止待ち"):
                detail = "停止完了まで編集を待ってください。未保存の入力は保持します。"
            self.message.set(summary + (f" — {detail}" if detail else ""))
            self.status.set(summary)
            self.force_button.configure(state="normal" if operation.can_force else "disabled")
            if operation.active:
                self.after(100, tick)
                return
            self.cancel_button.configure(state="disabled")
            self.force_button.configure(state="disabled")
            self.lock(False)
            if on_finished is not None:
                on_finished(operation)
            if operation.state == "完了":
                if on_result is not None:
                    on_result(operation.result)
            elif operation.state == "失敗":
                self.message.set(f"{summary} — {operation.error}")
                messagebox.showerror("処理できません", operation.error + "\n未保存の入力は保持しています。保存は再試行できます。")
            else:
                self.message.set(summary + "。編集を再開できます。途中のファイルは完成扱いしません。")

        tick()

    def stop(self):
        operation = self.operation
        if operation is not None and operation.active:
            operation.request_cancel()
            self.cancel_button.configure(state="disabled")
            self.message.set("中止を要求しました。実際の停止完了まで編集を待ってください。未保存の入力は保持します。")

    def force(self):
        if self.operation is None or not self.operation.can_force:
            return
        if not messagebox.askyesno("管理対象処理を強制停止", f"{self.operation.label} は通常中止の完了を確認できていません。\n"
                                  "この処理と、この処理が起動した子プロセスを強制停止します。\n"
                                  "途中のファイルが残る場合があります。既存成果物と画面の未保存入力は保持します。\n"
                                  "AviUtl2の未保存編集はこの操作では変更しません。自動復旧は行いません。\n"
                                  "強制停止しますか？", default="no"):
            return
        try:
            self.operation.force_stop()
        except Exception as error:
            messagebox.showerror("停止を確認できません", f"{error}\n停止待ちを継続します。")
