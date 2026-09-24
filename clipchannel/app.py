"""Small standalone browser for saved data; no media dependencies required."""

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from .storage import DataFolder, RESULT_KINDS, StorageError


def main():
    data = DataFolder()
    window = tk.Tk()
    window.title("ClipChannelAPP — 保存済みデータ")
    location = tk.StringVar(value="データ用フォルダを選択してください")
    status = tk.StringVar()
    running = tk.BooleanVar()
    unsaved = tk.BooleanVar()
    tk.Label(window, textvariable=location).pack(anchor="w", padx=12, pady=8)
    listing = tk.Listbox(window, width=85, height=15)
    listing.pack(fill="both", expand=True, padx=12)
    videos = tk.Listbox(window, width=85, height=6)
    videos.pack(fill="both", padx=12)
    detail = tk.Text(window, width=85, height=12, state="disabled")
    detail.pack(fill="both", expand=True, padx=12, pady=8)

    def choose():
        selected = filedialog.askdirectory(mustexist=True)
        if not selected:
            return
        data.running, data.unsaved = running.get(), unsaved.get()
        try:
            paths = data.select(selected)
        except (OSError, StorageError) as error:
            messagebox.showerror("フォルダを切り替えられません", str(error))
            return
        location.set(str(data.path))
        listing.delete(0, tk.END)
        for path in paths:
            listing.insert(tk.END, path)
        status.set(f"保存済み結果: {len(paths)} 件")
        refresh_videos()

    def refresh_videos():
        videos.delete(0, tk.END)
        for path in data.list_videos():
            videos.insert(tk.END, path.name)

    def register():
        if data.path is None:
            messagebox.showerror("登録できません", "データ用フォルダを選んでください")
            return
        selected = filedialog.askopenfilename(title="ローカル動画を選択")
        if not selected:
            return
        try:
            path = data.register_video(selected)
        except (OSError, StorageError) as error:
            messagebox.showerror("登録できません", str(error))
            return
        refresh_videos()
        status.set(f"登録済み動画: {path.name}")

    def select_video(_event=None):
        if videos.curselection():
            status.set(f"選択中の動画: {videos.get(videos.curselection()[0])}")

    def show(_event=None):
        if not listing.curselection():
            return
        relative = listing.get(listing.curselection()[0])
        parts = relative.split("/")
        kind = parts[2]
        if kind not in RESULT_KINDS:
            return
        version = int(parts[3].rsplit("_v", 1)[1].removesuffix(".csv"))
        try:
            rows = data.load_result(parts[1], kind, version)
        except (OSError, StorageError) as error:
            messagebox.showerror("CSVを読み取れません", str(error))
            return
        detail.configure(state="normal")
        detail.delete("1.0", tk.END)
        for row in rows:
            detail.insert(tk.END, f"{row}\n")
        detail.configure(state="disabled")

    tk.Button(window, text="フォルダを選択・切り替え", command=choose).pack(pady=6)
    tk.Button(window, text="ローカル動画を登録", command=register).pack(pady=6)
    ttk.Checkbutton(window, text="処理中", variable=running).pack(anchor="w", padx=12)
    ttk.Checkbutton(window, text="未保存入力あり", variable=unsaved).pack(anchor="w", padx=12)
    listing.bind("<<ListboxSelect>>", show)
    videos.bind("<<ListboxSelect>>", select_video)
    tk.Label(window, textvariable=status).pack(anchor="w", padx=12, pady=6)
    window.mainloop()


if __name__ == "__main__":
    main()
