"""Small standalone browser for saved data; no media dependencies required."""

import os
import shutil
import subprocess
import tkinter as tk
import threading
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from tkinter import font

from .download import DownloadSession, DownloadError
from .media import MediaError, prepare_media
from .people import PersonError, list_people, register_person, select_target, target_for_video, SPLITS
from .storage import DataFolder, RESULT_KINDS, SHARED_KINDS, StorageError
from .transcribe import (Interval, load_intervals, propose_intervals,
                         save_intervals, transcribe_confirmed, validate_intervals)


def configure_japanese_fonts(window):
    """Use a font that can render Japanese labels and saved CSV text."""
    families = set(font.families(window))
    for family in ("Yu Gothic UI", "Meiryo UI", "Noto Sans CJK JP", "IPAexGothic", "IPAGothic"):
        if family in families:
            for name in ("TkDefaultFont", "TkTextFont", "TkFixedFont", "TkMenuFont", "TkHeadingFont"):
                font.nametofont(name, window).configure(family=family)
            return family
    return None


def build_app():
    if os.name != "nt" and Path("/mnt/c/Windows/Fonts").is_dir() and "FONTCONFIG_FILE" not in os.environ:
        os.environ["FONTCONFIG_FILE"] = str(Path(__file__).with_name("fonts.conf"))
    data = DataFolder()
    window = tk.Tk()
    configure_japanese_fonts(window)
    window.title("ClipChannelAPP — 保存済みデータ")
    window.geometry("1180x720")
    window.minsize(960, 600)
    location = tk.StringVar(value="データ用フォルダを選択してください")
    status = tk.StringVar()
    unsaved = tk.BooleanVar()
    def mark_unsaved(*_args):
        unsaved.set(True)
    header = ttk.Frame(window, padding=10)
    header.pack(fill="x")
    tk.Button(header, text="フォルダを選択・切り替え", command=lambda: choose()).pack(side="left", padx=(0, 12))
    ttk.Label(header, textvariable=location).pack(side="left", fill="x", expand=True)
    panes = ttk.Panedwindow(window, orient="horizontal")
    panes.pack(fill="both", expand=True, padx=10, pady=5)
    saved_panel = ttk.Frame(panes, padding=8)
    media_panel = ttk.Frame(panes, padding=8)
    panes.add(saved_panel, weight=1)
    panes.add(media_panel, weight=1)
    saved_tabs = ttk.Notebook(saved_panel)
    saved_tabs.pack(fill="both", expand=True)
    results_tab = ttk.Frame(saved_tabs, padding=4)
    people_tab = ttk.Frame(saved_tabs, padding=4)
    saved_tabs.add(results_tab, text="保存済み情報")
    saved_tabs.add(people_tab, text="人物・参照音声")
    ttk.Label(results_tab, text="保存済み情報").pack(anchor="w")
    listing = tk.Listbox(results_tab, height=10)
    listing.pack(fill="both", expand=True)
    ttk.Label(results_tab, text="選択したCSVの内容").pack(anchor="w", pady=(8, 0))
    detail = tk.Text(results_tab, height=12, state="disabled")
    detail.pack(fill="both", expand=True)
    ttk.Label(media_panel, text="取得・媒体操作").pack(anchor="w")
    url = tk.StringVar()
    media_format = tk.StringVar(value="bestvideo*+bestaudio/best")
    retries = tk.StringVar(value="3")
    extra = tk.StringVar()
    audio_only = tk.BooleanVar()
    info_only = tk.BooleanVar()
    for field in (url, media_format, retries, extra, audio_only, info_only):
        field.trace_add("write", mark_unsaved)
    session = [None]
    pending = [False]
    preparing = [False]
    prepare_stop = [False]
    ttk.Label(media_panel, text="認証不要のURL").pack(anchor="w")
    tk.Entry(media_panel, textvariable=url).pack(fill="x")
    ttk.Label(media_panel, text="形式・品質 (yt-dlp format)").pack(anchor="w")
    tk.Entry(media_panel, textvariable=media_format).pack(fill="x")
    ttk.Label(media_panel, text="取得の再試行回数").pack(anchor="w")
    tk.Entry(media_panel, textvariable=retries, width=10).pack(anchor="w")
    ttk.Checkbutton(media_panel, text="音声のみ（音声成果物）", variable=audio_only).pack(anchor="w")
    ttk.Checkbutton(media_panel, text="情報のみ", variable=info_only).pack(anchor="w")
    ttk.Label(media_panel, text="追加引数（-f, --retries, --fragment-retries, --sub-langs）").pack(anchor="w")
    tk.Entry(media_panel, textvariable=extra).pack(fill="x")
    downloads = tk.Listbox(media_panel, height=5)
    downloads.pack(fill="both", expand=True, pady=(8, 0))
    videos = tk.Listbox(media_panel, height=5)
    videos.pack(fill="both", expand=True, pady=(8, 0))
    people_panel = ttk.LabelFrame(people_tab, text="人物と参照音声", padding=6)
    people_panel.pack(fill="both", expand=True, pady=(8, 0))
    people_list = tk.Listbox(people_panel, height=5)
    people_list.pack(fill="both", expand=True)
    selected_person = tk.StringVar(value="対象話者: 未選択")
    ttk.Label(people_panel, textvariable=selected_person).pack(anchor="w")
    target_video = tk.StringVar()
    ttk.Label(people_panel, text="対象動画（別動画にも同じ人物を指定できます）").pack(anchor="w")
    target_video_box = ttk.Combobox(people_panel, textvariable=target_video, state="readonly")
    target_video_box.pack(fill="x")
    review_rows = [[]]
    review_source = [None]
    review_list = tk.Listbox(people_panel, height=6)
    review_list.pack(fill="both", expand=True, pady=(6, 0))
    asr_model_path = tk.StringVar()
    review_stop = [False]
    review_dirty = [False]
    edit_start = tk.StringVar()
    edit_end = tk.StringVar()
    edit_text = tk.StringVar()
    edit_state = tk.StringVar(value="unknown")

    def run_review_worker(work, title):
        review_stop[0] = False
        pending[0] = data.running = True
        def worker():
            try:
                work()
            except Exception as error:
                reason = str(error) or type(error).__name__
                window.after(0, lambda: (status.set(reason), messagebox.showerror(title, reason)))
            finally:
                data.running = False
                window.after(0, lambda: pending.__setitem__(0, False))
        threading.Thread(target=worker, daemon=True).start()

    def display_review():
        review_list.delete(0, tk.END)
        for row in review_rows[0]:
            score = f" cosine {row.score:.3f}" if row.score is not None else ""
            review_list.insert(tk.END, f"{row.start_ms / 1000:.3f}–{row.end_ms / 1000:.3f}  {row.state}{score}  {row.text}")

    def review_video():
        if not target_video.get() or pending[0] or data.running:
            messagebox.showerror("解析できません", "対象動画を選び、処理完了を待ってください")
            return
        if review_dirty[0]:
            messagebox.showerror("解析できません", "未保存の入力を保存してから解析してください")
            return
        video = next((path for path in data.list_videos() if path.name == target_video.get()), None)
        if video is None:
            return
        ecapa_directory = model_path.get()
        def worker():
            rows = propose_intervals(data, video, ecapa_directory, stop=lambda: review_stop[0],
                                     progress=lambda value: window.after(0, status.set, value))
            def finish():
                review_rows[0] = rows
                review_source[0] = video
                display_review()
                status.set(f"試聴待ち: {len(rows)} 区間")
            window.after(0, finish)
        run_review_worker(worker, "解析できません")

    def mark_review(state):
        if not review_list.curselection() or pending[0]:
            return
        index = review_list.curselection()[0]
        row = review_rows[0][index]
        review_rows[0][index] = Interval(row.start_ms, row.end_ms, state, row.score,
                                         row.text if state == "target" and row.state == "target" else "")
        unsaved.set(True)
        review_dirty[0] = True
        display_review()
        review_list.selection_set(index)

    def select_review(_event=None):
        if not review_list.curselection():
            return
        row = review_rows[0][review_list.curselection()[0]]
        edit_start.set(f"{row.start_ms / 1000:.3f}")
        edit_end.set(f"{row.end_ms / 1000:.3f}")
        edit_state.set(row.state)
        edit_text.set(row.text)

    def edit_review(add=False):
        if pending[0] or (not add and not review_list.curselection()):
            return
        try:
            start = round(float(edit_start.get()) * 1000)
            end = round(float(edit_end.get()) * 1000)
            row = Interval(start, end, edit_state.get(),
                           text=edit_text.get() if edit_state.get() == "target" else "")
            candidate = list(review_rows[0])
            if add:
                candidate.append(row)
                candidate.sort(key=lambda item: item.start_ms)
            else:
                candidate[review_list.curselection()[0]] = row
                candidate.sort(key=lambda item: item.start_ms)
            validate_intervals(candidate)
        except (ValueError, StorageError) as error:
            messagebox.showerror("区間を変更できません", str(error))
            return
        review_rows[0] = candidate
        unsaved.set(True)
        review_dirty[0] = True
        display_review()
        status.set("区間を変更しました。保存してください")

    def split_review():
        if pending[0] or not review_list.curselection():
            return
        index = review_list.curselection()[0]
        row = review_rows[0][index]
        try:
            boundary = round(float(edit_end.get()) * 1000)
            if not row.start_ms < boundary < row.end_ms:
                raise ValueError("分割時刻は選択区間の内側にしてください")
        except ValueError as error:
            messagebox.showerror("分割できません", str(error))
            return
        review_rows[0][index:index + 1] = [
            Interval(row.start_ms, boundary, "unknown", row.score),
            Interval(boundary, row.end_ms, "unknown", row.score)]
        unsaved.set(True)
        review_dirty[0] = True
        display_review()
        status.set("区間を分割しました。試聴して判定してください")

    def play_review():
        if not review_list.curselection() or not target_video.get():
            return
        ffplay = shutil.which("ffplay")
        if not ffplay:
            messagebox.showerror("試聴できません", "ffplay が必要です")
            return
        row = review_rows[0][review_list.curselection()[0]]
        video = next(path for path in data.list_videos() if path.name == target_video.get())
        if player[0] and player[0].poll() is None:
            player[0].terminate()
        player[0] = subprocess.Popen([ffplay, "-nodisp", "-autoexit", "-loglevel", "error",
                                      "-ss", str(row.start_ms / 1000), "-t",
                                      str((row.end_ms - row.start_ms) / 1000), str(video)],
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def save_review(recognize=False):
        if not review_rows[0] or pending[0] or data.running:
            return
        video = next(path for path in data.list_videos() if path.name == target_video.get())
        if video != review_source[0]:
            messagebox.showerror("保存できません", "試聴区間の元動画を選んでください")
            return
        rows = tuple(review_rows[0])
        whisper_directory = asr_model_path.get()
        def worker():
            if recognize:
                path, completed = transcribe_confirmed(
                    data, video, rows, whisper_directory, stop=lambda: review_stop[0],
                    progress=lambda value: window.after(0, status.set, value))
            else:
                path = save_intervals(data, video, rows)
                completed = rows
            def finish():
                review_rows[0] = completed
                display_review()
                listing.insert(tk.END, path.relative_to(data._root()).as_posix())
                unsaved.set(False)
                review_dirty[0] = False
                status.set(f"保存しました: {path.name}")
            window.after(0, finish)
        run_review_worker(worker, "保存できません")

    def reopen_review():
        if not listing.curselection() or not target_video.get() or pending[0]:
            return
        if review_dirty[0]:
            messagebox.showerror("再表示できません", "未保存の入力を保存してから再表示してください")
            return
        relative = listing.get(listing.curselection()[0])
        video = next((path for path in data.list_videos() if path.name == target_video.get()), None)
        if video is None or relative.split("/")[:3] != ["catalog", video.stem, "transcripts"]:
            messagebox.showerror("再表示できません", "対象動画の文字起こしCSVを選んでください")
            return
        try:
            version = int(relative.rsplit("_v", 1)[1].removesuffix(".csv"))
            review_rows[0] = load_intervals(data, video, version)
            review_source[0] = video
            display_review()
            unsaved.set(False)
            review_dirty[0] = False
            status.set(f"再表示しました: {relative}")
        except (OSError, StorageError, ValueError) as error:
            messagebox.showerror("再表示できません", str(error))

    review_actions = ttk.Frame(people_panel)
    review_actions.pack(fill="x")
    for caption, action in (("試聴区間を作成", review_video), ("試聴", play_review),
                            ("対象発話", lambda: mark_review("target")),
                            ("対象話者の非発話", lambda: mark_review("non-target")),
                            ("不明", lambda: mark_review("unknown")),
                            ("判定を保存", save_review), ("保存版を再表示", reopen_review)):
        ttk.Button(review_actions, text=caption, command=action).pack(side="left")
    ttk.Label(people_panel, text="ローカル Whisper モデル（対象発話の区間のみ認識）").pack(anchor="w")
    ttk.Entry(people_panel, textvariable=asr_model_path).pack(fill="x")
    ttk.Button(people_panel, text="対象発話を文字起こし・別版保存",
               command=lambda: save_review(True)).pack(anchor="w")
    ttk.Button(people_panel, text="解析を中止", command=lambda: review_stop.__setitem__(0, True)).pack(anchor="w")
    edit_line = ttk.Frame(people_panel)
    edit_line.pack(fill="x")
    for caption, variable, width in (("開始秒", edit_start, 9), ("終了秒", edit_end, 9),
                                      ("本文", edit_text, 30)):
        ttk.Label(edit_line, text=caption).pack(side="left")
        ttk.Entry(edit_line, textvariable=variable, width=width).pack(side="left")
    ttk.Combobox(edit_line, textvariable=edit_state,
                 values=("target", "non-target", "unknown"), state="readonly", width=12).pack(side="left")
    ttk.Button(edit_line, text="選択行を修正", command=edit_review).pack(side="left")
    ttk.Button(edit_line, text="終了秒で分割", command=split_review).pack(side="left")
    ttk.Button(edit_line, text="発言を追加", command=lambda: edit_review(True)).pack(side="left")
    review_list.bind("<<ListboxSelect>>", select_review)
    person_name = tk.StringVar()
    audio_path = tk.StringVar()
    model_path = tk.StringVar()
    start_time = tk.StringVar()
    end_time = tk.StringVar()
    threshold = tk.StringVar()
    split = tk.StringVar(value="whole-reference")
    for field in (person_name, audio_path, model_path, start_time, end_time, threshold, split):
        field.trace_add("write", mark_unsaved)
    ttk.Label(people_panel, text="名前").pack(anchor="w")
    ttk.Entry(people_panel, textvariable=person_name).pack(fill="x")
    ttk.Label(people_panel, text="参照音声ファイル（動画を使う場合は空欄）").pack(anchor="w")
    ttk.Entry(people_panel, textvariable=audio_path).pack(fill="x")
    ttk.Button(people_panel, text="音声ファイルを選択", command=lambda: audio_path.set(
        filedialog.askopenfilename(title="参照音声を選択") or audio_path.get())).pack(anchor="w")
    ttk.Label(people_panel, text="動画を使う場合: 右側の登録済み動画を選び、開始・終了秒を指定").pack(anchor="w")
    times = ttk.Frame(people_panel)
    times.pack(fill="x")
    ttk.Entry(times, textvariable=start_time, width=9).pack(side="left")
    ttk.Label(times, text=" 〜 ").pack(side="left")
    ttk.Entry(times, textvariable=end_time, width=9).pack(side="left")
    ttk.Label(people_panel, text="ローカル ECAPA モデルフォルダ").pack(anchor="w")
    ttk.Entry(people_panel, textvariable=model_path).pack(fill="x")
    ttk.Button(people_panel, text="モデルを選択", command=lambda: model_path.set(
        filedialog.askdirectory(title="ローカル ECAPA モデル") or model_path.get())).pack(anchor="w")
    ttk.Label(people_panel, text="照合閾値（-1〜1、品質は別動画で確認）").pack(anchor="w")
    ttk.Entry(people_panel, textvariable=threshold).pack(fill="x")
    ttk.Combobox(people_panel, textvariable=split, values=sorted(SPLITS), state="readonly").pack(fill="x")
    current_people = [()]
    player = [None]

    def refresh_people():
        current_people[0] = tuple(list_people(data))
        people_list.delete(0, tk.END)
        for person in current_people[0]:
            people_list.insert(tk.END, f"{person.name} | {person.person_id[:8]} | {person.split}")

    def select_person(_event=None):
        if people_list.curselection():
            person = current_people[0][people_list.curselection()[0]]
            selected_person.set(f"選択中の人物: {person.name} ({person.person_id}) / 閾値 {person.threshold} / {person.split}")

    def preview_person():
        if not people_list.curselection():
            messagebox.showerror("試聴できません", "人物を選んでください")
            return
        person = current_people[0][people_list.curselection()[0]]
        if not person.reference_audio.is_file():
            messagebox.showerror("試聴できません", "参照音声ファイルが見つかりません")
            return
        ffplay = shutil.which("ffplay")
        if not ffplay:
            messagebox.showerror("試聴できません", "試聴に ffplay が必要です")
            return
        if player[0] and player[0].poll() is None:
            player[0].terminate()
        try:
            player[0] = subprocess.Popen([ffplay, "-nodisp", "-autoexit", "-loglevel", "error",
                                          str(person.reference_audio)], stdout=subprocess.DEVNULL,
                                         stderr=subprocess.DEVNULL)
        except OSError as error:
            messagebox.showerror("試聴できません", str(error))

    def assign_target():
        if pending[0] or data.running:
            messagebox.showerror("対象話者を選べません", "処理完了を待ってください")
            return
        if not target_video.get() or not people_list.curselection():
            messagebox.showerror("対象話者を選べません", "動画と人物を選んでください")
            return
        person = current_people[0][people_list.curselection()[0]]
        try:
            selected = select_target(data, next(path for path in data.list_videos()
                                                 if path.name == target_video.get()), person.person_id)
        except (OSError, StorageError, StopIteration) as error:
            messagebox.showerror("対象話者を選べません", str(error))
            return
        selected_person.set(f"{target_video.get()} の対象話者: {selected.name} ({selected.person_id})")
        status.set(f"対象話者を保存しました: {selected.name}")

    def show_target(_event=None):
        if not target_video.get():
            return
        try:
            selected = target_for_video(data, next(path for path in data.list_videos()
                                                   if path.name == target_video.get()))
        except (OSError, StorageError, StopIteration) as error:
            messagebox.showerror("対象話者を読めません", str(error))
            return
        selected_person.set(f"{target_video.get()} の対象話者: " +
                            (f"{selected.name} ({selected.person_id})" if selected else "未選択"))

    def enroll_person():
        if pending[0] or data.running:
            messagebox.showerror("登録できません", "処理完了を待ってください")
            return
        use_video = not audio_path.get().strip()
        if use_video and not videos.curselection():
            messagebox.showerror("登録できません", "音声ファイルか登録済み動画を選んでください")
            return
        video = data.list_videos()[videos.curselection()[0]] if use_video else None
        args = (person_name.get(), audio_path.get(), model_path.get(), threshold.get(), split.get())
        start, end = start_time.get(), end_time.get()
        pending[0] = data.running = True
        status.set("人物特徴を生成しています")

        def worker():
            try:
                person = register_person(data, *args, video=video, start=start, end=end)
                def finish():
                    refresh_people()
                    index = next(i for i, item in enumerate(current_people[0]) if item.person_id == person.person_id)
                    people_list.selection_set(index)
                    select_person()
                    unsaved.set(False)
                    status.set(f"人物を登録しました: {person.name}")
                window.after(0, finish)
            except Exception as error:
                reason = str(error)
                window.after(0, lambda: messagebox.showerror("登録できません", reason))
            finally:
                data.running = False
                window.after(0, lambda: pending.__setitem__(0, False))

        threading.Thread(target=worker, daemon=True).start()

    person_actions = ttk.Frame(people_panel)
    person_actions.pack(fill="x", pady=4)
    ttk.Button(person_actions, text="人物を登録", command=enroll_person).pack(side="left")
    ttk.Button(person_actions, text="参照音声を試聴", command=preview_person).pack(side="left", padx=6)
    ttk.Button(person_actions, text="動画の対象話者に設定", command=assign_target).pack(side="left")
    people_list.bind("<<ListboxSelect>>", select_person)
    target_video_box.bind("<<ComboboxSelected>>", show_target)

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
        unsaved.set(False)
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

    download_actions = ttk.Frame(media_panel)
    download_actions.pack(fill="x", pady=5)
    tk.Button(download_actions, text="取得・情報表示", command=run_download).pack(side="left", padx=(0, 4))
    tk.Button(download_actions, text="失敗項目を再試行", command=lambda: run_download(True)).pack(side="left", padx=4)
    def stop_download():
        if preparing[0]:
            prepare_stop[0] = True
            status.set("媒体変換の停止待ち")
            return
        if session[0] and (pending[0] or data.running):
            session[0].stop()
            status.set("停止待ち")

    tk.Button(download_actions, text="通常中止", command=stop_download).pack(side="left", padx=4)
    tk.Button(download_actions, text="機能案内", command=lambda: messagebox.showinfo(
        "取得機能", "yt-dlp が必要です。動画は media/originals、音声のみは media/audio に保存します。"
        "追加引数は表示された形式・再試行等の指定に対応します。保存先・上書き・認証・外部コマンド・プラグイン指定は保護条件のため実行前に停止します。"
        "情報のみはファイルを保存しません。" )).pack(side="left", padx=4)

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
        refresh_people()

    def refresh_videos():
        videos.delete(0, tk.END)
        registered = data.list_videos()
        for path in registered:
            videos.insert(tk.END, path.name)
        target_video_box.configure(values=[path.name for path in registered])
        if target_video.get() not in {path.name for path in registered}:
            target_video.set(registered[0].name if registered else "")
        if registered:
            show_target()

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
        try:
            if len(parts) == 2 and parts[0] == "people":
                kind = parts[1].removesuffix(".csv")
                if kind not in SHARED_KINDS:
                    return
                rows = data.load_shared(kind)
            elif len(parts) == 4 and parts[0] == "catalog" and parts[2] in RESULT_KINDS:
                kind = parts[2]
                version = int(parts[3].rsplit("_v", 1)[1].removesuffix(".csv"))
                rows = data.load_result(parts[1], kind, version)
            else:
                return
        except (OSError, StorageError, ValueError, IndexError) as error:
            messagebox.showerror("CSVを読み取れません", str(error))
            return
        detail.configure(state="normal")
        detail.delete("1.0", tk.END)
        for row in rows:
            detail.insert(tk.END, f"{row}\n")
        detail.configure(state="disabled")

    media_actions = ttk.Frame(media_panel)
    media_actions.pack(fill="x", pady=5)
    tk.Button(media_actions, text="ローカル動画を登録", command=register).pack(side="left", padx=(0, 4))
    tk.Button(media_actions, text="選択した動画を媒体確認・変換（再試行）", command=prepare_selected).pack(side="left", padx=4)
    def close():
        if pending[0] or data.running:
            stop_download()
            status.set("停止完了を待っています")
            window.after(200, close)
        else:
            if player[0] and player[0].poll() is None:
                player[0].terminate()
            window.destroy()

    window.protocol("WM_DELETE_WINDOW", close)
    listing.bind("<<ListboxSelect>>", show)
    videos.bind("<<ListboxSelect>>", select_video)
    ttk.Label(window, textvariable=status, padding=(12, 5)).pack(fill="x")
    return window


def main():
    window = build_app()
    window.mainloop()


if __name__ == "__main__":
    main()
