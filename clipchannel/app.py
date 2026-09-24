"""Small standalone browser for saved data; no media dependencies required."""

import tkinter as tk
import threading
from tkinter import filedialog, messagebox, ttk

from .download import DownloadSession, DownloadError
from .media import MediaError, prepare_media
from .storage import DataFolder, RESULT_KINDS, StorageError


def main():
    data = DataFolder()
    window = tk.Tk()
    window.title("ClipChannelAPP — 保存済みデータ")
    location = tk.StringVar(value="データ用フォルダを選択してください")
    status = tk.StringVar()
    unsaved = tk.BooleanVar()
    tk.Label(window, textvariable=location).pack(anchor="w", padx=12, pady=8)
    listing = tk.Listbox(window, width=85, height=15)
    listing.pack(fill="both", expand=True, padx=12)
    videos = tk.Listbox(window, width=85, height=6)
    videos.pack(fill="both", padx=12)
    detail = tk.Text(window, width=85, height=12, state="disabled")
    detail.pack(fill="both", expand=True, padx=12, pady=8)
    url = tk.StringVar()
    media_format = tk.StringVar(value="bestvideo*+bestaudio/best")
    retries = tk.StringVar(value="3")
    extra = tk.StringVar()
    audio_only = tk.BooleanVar()
    info_only = tk.BooleanVar()
    session = [None]
    pending = [False]
    preparing = [False]
    prepare_stop = [False]
    tk.Label(window, text="認証不要のURL").pack(anchor="w", padx=12)
    tk.Entry(window, textvariable=url, width=85).pack(fill="x", padx=12)
    tk.Label(window, text="形式・品質 (yt-dlp format)").pack(anchor="w", padx=12)
    tk.Entry(window, textvariable=media_format, width=85).pack(fill="x", padx=12)
    tk.Label(window, text="取得の再試行回数").pack(anchor="w", padx=12)
    tk.Entry(window, textvariable=retries, width=10).pack(anchor="w", padx=12)
    ttk.Checkbutton(window, text="音声のみ（音声成果物）", variable=audio_only).pack(anchor="w", padx=12)
    ttk.Checkbutton(window, text="情報のみ", variable=info_only).pack(anchor="w", padx=12)
    tk.Label(window, text="追加引数（-f, --retries, --fragment-retries, --sub-langs）").pack(anchor="w", padx=12)
    tk.Entry(window, textvariable=extra, width=85).pack(fill="x", padx=12)
    downloads = tk.Listbox(window, width=85, height=7)
    downloads.pack(fill="both", padx=12)

    def refresh_downloads():
        downloads.delete(0, tk.END)
        current = session[0]
        if current is None:
            return
        for item in current.items:
            downloads.insert(tk.END, f"{item.state} | {item.seconds:.1f}秒 | {item.title} | {item.details} | {item.path or item.error}")
        status.set(f"{current.state} | {current.elapsed:.1f}秒")
        refresh_videos()

    def run_download(retry=False):
        if pending[0] or data.running:
            messagebox.showerror("取得できません", "別の処理が実行中です")
            return
        try:
            if not retry:
                session[0] = DownloadSession(data, url.get(), format=media_format.get(), retries=int(retries.get()),
                                             audio_only=audio_only.get(), info_only=info_only.get(), extra=extra.get())
            elif session[0] is None or not downloads.curselection():
                raise DownloadError("失敗項目を選択してください")
        except (DownloadError, ValueError) as error:
            messagebox.showerror("取得できません", str(error))
            return
        current = session[0]
        selected = set(downloads.curselection()) if retry else set()
        pending[0] = True
        status.set("取得を開始します")

        def tick():
            if pending[0]:
                status.set(f"{current.state} | {current.elapsed:.1f}秒")
                window.after(500, tick)

        window.after(500, tick)

        def finish():
            pending[0] = False
            refresh_downloads()

        def worker():
            try:
                callback = lambda: window.after(0, refresh_downloads)
                if retry:
                    current.retry_failed(selected, callback)
                else:
                    current.run(callback)
            except DownloadError as error:
                reason = str(error)
                window.after(0, lambda: messagebox.showerror("取得できません", reason))
            except Exception:
                window.after(0, lambda: messagebox.showerror("取得できません", "情報取得に失敗しました。URLと依存物を確認してください"))
            finally:
                window.after(0, finish)

        threading.Thread(target=worker, daemon=True).start()

    tk.Button(window, text="取得・情報表示", command=run_download).pack(pady=3)
    tk.Button(window, text="失敗項目を再試行", command=lambda: run_download(True)).pack(pady=3)
    def stop_download():
        if preparing[0]:
            prepare_stop[0] = True
            status.set("媒体変換の停止待ち")
            return
        if session[0] and (pending[0] or data.running):
            session[0].stop()
            status.set("停止待ち")

    tk.Button(window, text="通常中止", command=stop_download).pack(pady=3)
    tk.Button(window, text="機能案内", command=lambda: messagebox.showinfo(
        "取得機能", "yt-dlp が必要です。動画は media/originals、音声のみは media/audio に保存します。"
        "追加引数は表示された形式・再試行等の指定に対応します。保存先・上書き・認証・外部コマンド・プラグイン指定は保護条件のため実行前に停止します。"
        "情報のみはファイルを保存しません。" )).pack(pady=3)

    def choose():
        if pending[0]:
            messagebox.showerror("フォルダを切り替えられません", "処理中のためフォルダを切り替えられません")
            return
        selected = filedialog.askdirectory(mustexist=True)
        if not selected:
            return
        data.unsaved = unsaved.get()
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
        prepare_video(path)

    def prepare_video(path):
        if pending[0] or data.running:
            messagebox.showerror("媒体を準備できません", "処理完了を待ってください")
            return
        pending[0] = True
        preparing[0] = True
        prepare_stop[0] = False
        data.running = True
        status.set(f"媒体確認・編集互換変換中: {path.name}")

        def worker():
            try:
                result = prepare_media(data, path, stop_requested=lambda: prepare_stop[0])
                summary = (f"編集用: {result.editing}\n"
                           f"元映像開始: {result.source_info.video.start}秒 / "
                           f"元音声開始: {result.source_info.audio.start if result.source_info.audio else 'なし'}秒\n"
                           f"時刻対応: {result.manifest}")
                window.after(0, lambda: messagebox.showinfo("媒体を準備しました", summary))
                window.after(0, lambda: status.set(f"媒体準備完了: {path.name}"))
            except (OSError, MediaError) as error:
                reason = str(error)
                window.after(0, lambda: messagebox.showerror("媒体を準備できません", reason))
            finally:
                data.running = False
                preparing[0] = False
                window.after(0, lambda: pending.__setitem__(0, False))

        threading.Thread(target=worker, daemon=True).start()

    def prepare_selected():
        if not videos.curselection():
            messagebox.showerror("媒体を準備できません", "登録済み動画を選んでください")
            return
        prepare_video(data.list_videos()[videos.curselection()[0]])

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
    tk.Button(window, text="選択した動画を媒体確認・変換（再試行）", command=prepare_selected).pack(pady=6)
    ttk.Checkbutton(window, text="未保存入力あり", variable=unsaved).pack(anchor="w", padx=12)
    def close():
        if pending[0] or data.running:
            stop_download()
            status.set("停止完了を待っています")
            window.after(200, close)
        else:
            window.destroy()

    window.protocol("WM_DELETE_WINDOW", close)
    listing.bind("<<ListboxSelect>>", show)
    videos.bind("<<ListboxSelect>>", select_video)
    tk.Label(window, textvariable=status).pack(anchor="w", padx=12, pady=6)
    window.mainloop()


if __name__ == "__main__":
    main()
