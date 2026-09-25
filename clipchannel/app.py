"""Small standalone browser for saved data; no media dependencies required."""

import os
import json
import math
import shutil
import subprocess
import tkinter as tk
import threading
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from tkinter import font

from .download import DownloadSession, DownloadError
from .people import PersonError, list_people, register_person, select_target, target_for_video, SPLITS
from .storage import DataFolder, RESULT_KINDS, SHARED_KINDS, StorageError
from .transcribe import Interval, load_intervals, validate_intervals
from .word_counts import count_words
from .segments import (Segment, SegmentError, candidates_from_transcript,
                       load_segments, merge_segments, save_segments, split_segment,
                       validate_segments)
from .media import _probe
from .compose import probe_frames
from .subtitles import Subtitle, prepare_subtitle_import, write_subtitle_import
from .layout import Layout, save_layout
from .editor_bridge import apply_layout, apply_subtitles
from .supporting_media_ui import SupportingMediaPanel
from .save_export_ui import SaveExportPanel, WidgetLock
from .managed_process_ui import ProcessPanel
from .management_ui import ManagementPanel
from .operation_logs import record_operation, cleanup_logs
from . import operation_tasks


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
    words_tab = ttk.Frame(saved_tabs, padding=4)
    saved_tabs.add(words_tab, text="頻出語")
    segments_tab = ttk.Frame(saved_tabs, padding=4)
    saved_tabs.add(segments_tab, text="切り出し区間")
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
    session: list[DownloadSession | None] = [None]
    pending = [False]
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
    review_version: list[int | None] = [None]
    review_list = tk.Listbox(people_panel, height=6)
    review_list.pack(fill="both", expand=True, pady=(6, 0))
    asr_model_path = tk.StringVar()
    review_dirty = [False]
    edit_start = tk.StringVar()
    edit_end = tk.StringVar()
    edit_text = tk.StringVar()
    edit_state = tk.StringVar(value="unknown")

    def display_review():
        review_list.delete(0, tk.END)
        for row in review_rows[0]:
            score = f" cosine {row.score:.3f}" if row.score is not None else ""
            review_list.insert(tk.END, f"{row.start_ms / 1000:.3f}–{row.end_ms / 1000:.3f}  {row.state}{score}  {row.text}")

    def persist_review():
        """Save the current user edit; retain the rows for an explicit retry on failure."""
        review_dirty[0] = True
        video = review_source[0]
        if video is None or not review_rows[0] or pending[0] or data.running:
            return
        rows = tuple(review_rows[0])
        def finish(result):
            path, _rows = result
            review_version[0] = int(path.stem.rsplit("_v", 1)[1])
            listing.insert(tk.END, path.relative_to(data._root()).as_posix())
            review_dirty[0] = False
            status.set(f"自動保存しました: {path.name}")
        process_panel.start("文字起こし修正の自動保存", operation_tasks.save_review,
                            (data, video, rows), kwargs={"source_version": review_version[0]}, on_result=finish)

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
        def finish(rows):
            review_rows[0] = rows
            review_source[0] = video
            review_version[0] = None
            display_review()
            status.set(f"試聴待ち: {len(rows)} 区間")
        process_panel.start("対象話者の照合", operation_tasks.propose,
                            (data, video, ecapa_directory), on_result=finish)

    def mark_review(state):
        if not review_list.curselection() or pending[0]:
            return
        index = review_list.curselection()[0]
        row = review_rows[0][index]
        review_rows[0][index] = Interval(row.start_ms, row.end_ms, state, row.score,
                                         row.text if state == "target" and row.state == "target" else "")
        review_dirty[0] = True
        display_review()
        review_list.selection_set(index)
        persist_review()

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
            start_seconds, end_seconds = float(edit_start.get()), float(edit_end.get())
            if not math.isfinite(start_seconds) or not math.isfinite(end_seconds):
                raise ValueError("時刻は有限の数値で指定してください")
            start = round(start_seconds * 1000)
            end = round(end_seconds * 1000)
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
        display_review()
        persist_review()

    def split_review():
        if pending[0] or not review_list.curselection():
            return
        index = review_list.curselection()[0]
        row = review_rows[0][index]
        try:
            boundary_seconds = float(edit_end.get())
            if not math.isfinite(boundary_seconds):
                raise ValueError("分割時刻は有限の数値で指定してください")
            boundary = round(boundary_seconds * 1000)
            if not row.start_ms < boundary < row.end_ms:
                raise ValueError("分割時刻は選択区間の内側にしてください")
        except ValueError as error:
            messagebox.showerror("分割できません", str(error))
            return
        review_rows[0][index:index + 1] = [
            Interval(row.start_ms, boundary, "unknown", row.score),
            Interval(boundary, row.end_ms, "unknown", row.score)]
        display_review()
        persist_review()

    def play_review():
        if not review_list.curselection() or not target_video.get():
            return
        video = next((path for path in data.list_videos() if path.name == target_video.get()), None)
        if video is None or video != review_source[0]:
            messagebox.showerror("試聴できません", "試聴区間の元動画を選んでください")
            return
        ffplay = shutil.which("ffplay")
        if not ffplay:
            messagebox.showerror("試聴できません", "ffplay が必要です")
            return
        row = review_rows[0][review_list.curselection()[0]]
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
        def finish(result):
            path, completed = result
            review_version[0] = int(path.stem.rsplit("_v", 1)[1])
            review_rows[0] = completed
            display_review()
            listing.insert(tk.END, path.relative_to(data._root()).as_posix())
            review_dirty[0] = False
            status.set(f"保存しました: {path.name}")
        target = operation_tasks.transcribe if recognize else operation_tasks.save_review
        args = (data, video, rows, whisper_directory) if recognize else (data, video, rows)
        process_panel.start("対象話者の文字起こし" if recognize else "文字起こしの保存",
                            target, args, kwargs={"source_version": review_version[0]}, on_result=finish)

    def retry_review():
        if review_dirty[0] and not pending[0] and not data.running:
            persist_review()

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
            review_version[0] = version
            review_source[0] = video
            display_review()
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
                            ("保存を再試行", retry_review), ("保存版を再表示", reopen_review)):
        ttk.Button(review_actions, text=caption, command=action).pack(side="left")
    ttk.Label(people_panel, text="ローカル Whisper モデル（対象発話の区間のみ認識）").pack(anchor="w")
    ttk.Entry(people_panel, textvariable=asr_model_path).pack(fill="x")
    ttk.Button(people_panel, text="対象発話を文字起こし・別版保存",
               command=lambda: save_review(True)).pack(anchor="w")
    ttk.Button(people_panel, text="解析を中止", command=lambda: process_panel.stop()).pack(anchor="w")
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

    segment_rows = [[]]
    segment_source = [None]
    segment_duration = [0]
    segment_dirty = [False]
    segment_version = tk.StringVar(value="1")
    before_padding = tk.StringVar(value="5")
    after_padding = tk.StringVar(value="5")
    segment_start = tk.StringVar()
    segment_end = tk.StringVar()
    segment_selected = tk.BooleanVar(value=True)
    segment_list = tk.Listbox(segments_tab, selectmode=tk.EXTENDED, exportselection=False)
    compose_order = []
    ttk.Label(segments_tab, text="対象動画は人物タブで選択。文字起こし版と前後余白（秒）").pack(anchor="w")
    segment_settings = ttk.Frame(segments_tab)
    segment_settings.pack(fill="x")
    for label, variable in (("文字起こし版", segment_version), ("前", before_padding), ("後", after_padding)):
        ttk.Label(segment_settings, text=label).pack(side="left")
        ttk.Entry(segment_settings, textvariable=variable, width=7).pack(side="left")

    def segment_video():
        return next((path for path in data.list_videos() if path.name == target_video.get()), None) if data.path else None

    def segment_video_duration(video):
        info = _probe(video)
        if info.duration is None:
            raise SegmentError("動画の長さを確認できません")
        duration = round(float(info.duration) * 1000)
        validate_segments([], duration)
        return duration

    def display_segments():
        segment_list.delete(0, tk.END)
        compose_order.clear()
        compose_list.delete(0, tk.END)
        for row in segment_rows[0]:
            segment_list.insert(tk.END, f"{'✓' if row.selected else '—'} {row.start_ms / 1000:.3f}–{row.end_ms / 1000:.3f}  {row.kind}")

    def persist_segments():
        if pending[0] or data.running or segment_source[0] is None:
            segment_dirty[0] = True
            return
        try:
            path = save_segments(data, segment_source[0], segment_rows[0], segment_duration[0])
            listing.insert(tk.END, path.relative_to(data._root()).as_posix())
            segment_dirty[0] = False
            status.set(f"切り出し区間を自動保存しました: {path.name}")
        except (OSError, StorageError) as error:
            segment_dirty[0] = True
            messagebox.showerror("切り出し区間を保存できません", f"{error}\n入力は保持しています。保存を再試行してください")

    def generate_segments():
        video = segment_video()
        if video is None or segment_dirty[0] or pending[0] or data.running:
            messagebox.showerror("候補を作れません", "対象動画を選び、未保存の区間を保存してください")
            return
        try:
            before, after = float(before_padding.get()), float(after_padding.get())
            if not all(math.isfinite(value) and value >= 0 for value in (before, after)):
                raise ValueError("余白は0秒以上にしてください")
            duration = segment_video_duration(video)
            rows = candidates_from_transcript(data, video, int(segment_version.get()), duration,
                                              round(before * 1000), round(after * 1000))
            path = save_segments(data, video, rows, duration)
        except (OSError, StorageError, ValueError) as error:
            messagebox.showerror("候補を作れません", str(error))
            return
        segment_rows[0], segment_source[0], segment_duration[0] = rows, video, duration
        display_segments()
        listing.insert(tk.END, path.relative_to(data._root()).as_posix())
        status.set(f"候補を別版で保存しました: {path.name}")

    def start_manual_segments():
        video = segment_video()
        if video is None or segment_dirty[0]:
            messagebox.showerror("区間を作れません", "対象動画を選び、未保存の区間を保存してください")
            return
        try:
            duration = segment_video_duration(video)
        except (OSError, StorageError, ValueError) as error:
            messagebox.showerror("区間を作れません", str(error))
            return
        segment_rows[0], segment_source[0], segment_duration[0] = [], video, duration
        display_segments()
        status.set("手動追加する開始秒・終了秒を入力してください")

    def reopen_segments():
        if not listing.curselection() or segment_dirty[0]:
            messagebox.showerror("区間を開けません", "保存版を選び、未保存の入力を保存してください")
            return
        relative = listing.get(listing.curselection()[0])
        parts = relative.split("/")
        video = segment_video()
        if video is None or len(parts) != 4 or parts[:3] != ["catalog", video.stem, "segments"]:
            messagebox.showerror("区間を開けません", "対象動画の区間CSVを選んでください")
            return
        try:
            duration = segment_video_duration(video)
            version = int(parts[3].rsplit("_v", 1)[1].removesuffix(".csv"))
            rows = load_segments(data, video, version, duration)
        except (OSError, StorageError, ValueError) as error:
            messagebox.showerror("区間を開けません", str(error))
            return
        segment_rows[0], segment_source[0], segment_duration[0] = rows, video, duration
        display_segments()
        status.set(f"使用版を選びました: {relative}")

    def selected_segment(_event=None):
        indices = segment_list.curselection()
        if len(indices) == 1:
            row = segment_rows[0][indices[0]]
            segment_start.set(f"{row.start_ms / 1000:.3f}")
            segment_end.set(f"{row.end_ms / 1000:.3f}")
            segment_selected.set(row.selected)

    def change_segment(add=False):
        indices = segment_list.curselection()
        if segment_source[0] != segment_video() or pending[0] or data.running or (not add and len(indices) != 1):
            return
        try:
            start, end = float(segment_start.get()), float(segment_end.get())
            if not math.isfinite(start) or not math.isfinite(end):
                raise ValueError("時刻は有限の数値にしてください")
            row = Segment(round(start * 1000), round(end * 1000),
                          "manual" if add else segment_rows[0][indices[0]].kind, segment_selected.get())
            rows = list(segment_rows[0])
            if add:
                rows.append(row)
                rows.sort(key=lambda item: item.start_ms)
            else:
                rows[indices[0]] = row
            validate_segments(rows, segment_duration[0])
        except (ValueError, StorageError) as error:
            messagebox.showerror("区間を変更できません", str(error))
            return
        segment_rows[0] = rows
        display_segments()
        persist_segments()

    def split_selected_segment():
        indices = segment_list.curselection()
        if len(indices) != 1 or segment_source[0] != segment_video():
            return
        try:
            boundary = float(segment_end.get())
            if not math.isfinite(boundary):
                raise ValueError("分割時刻は有限の数値にしてください")
            rows = split_segment(segment_rows[0], indices[0], round(boundary * 1000), segment_duration[0])
        except (ValueError, StorageError) as error:
            messagebox.showerror("分割できません", str(error))
            return
        segment_rows[0] = rows
        display_segments()
        persist_segments()

    def set_segment_selection():
        indices = segment_list.curselection()
        if not indices or segment_source[0] != segment_video():
            return
        rows = list(segment_rows[0])
        for index in indices:
            row = rows[index]
            rows[index] = Segment(row.start_ms, row.end_ms, row.kind, segment_selected.get())
        segment_rows[0] = rows
        display_segments()
        persist_segments()

    def merge_selected_segments():
        if segment_source[0] != segment_video():
            return
        try:
            rows = merge_segments(segment_rows[0], segment_list.curselection(), segment_duration[0])
        except (IndexError, StorageError) as error:
            messagebox.showerror("結合できません", str(error))
            return
        segment_rows[0] = rows
        display_segments()
        persist_segments()

    def play_segment():
        indices = segment_list.curselection()
        if len(indices) != 1 or segment_source[0] != segment_video():
            return
        ffplay = shutil.which("ffplay")
        if not ffplay:
            messagebox.showerror("再生できません", "ffplay が必要です")
            return
        row = segment_rows[0][indices[0]]
        if player[0] and player[0].poll() is None:
            player[0].terminate()
        player[0] = subprocess.Popen([ffplay, "-autoexit", "-loglevel", "error", "-ss",
                                      str(row.start_ms / 1000), "-t", str((row.end_ms - row.start_ms) / 1000),
                                      str(segment_source[0])], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    ttk.Button(segments_tab, text="候補を生成して別版保存", command=generate_segments).pack(anchor="w")
    ttk.Button(segments_tab, text="解析なしで区間を手動作成", command=start_manual_segments).pack(anchor="w")
    ttk.Button(segments_tab, text="選択した保存版を使用", command=reopen_segments).pack(anchor="w")
    segment_list.pack(fill="both", expand=True)
    segment_list.bind("<<ListboxSelect>>", selected_segment)
    segment_actions = ttk.Frame(segments_tab)
    segment_actions.pack(fill="x")
    for caption, action in (("映像を再生", play_segment), ("境界を修正", change_segment),
                            ("終了秒で分割", split_selected_segment), ("区間結合", merge_selected_segments),
                            ("手動追加", lambda: change_segment(True)), ("採否を適用", set_segment_selection),
                            ("保存を再試行", persist_segments)):
        ttk.Button(segment_actions, text=caption, command=action).pack(side="left")
    segment_edit = ttk.Frame(segments_tab)
    segment_edit.pack(fill="x")
    for caption, variable in (("開始秒", segment_start), ("終了秒", segment_end)):
        ttk.Label(segment_edit, text=caption).pack(side="left")
        ttk.Entry(segment_edit, textvariable=variable, width=10).pack(side="left")
    ttk.Checkbutton(segment_edit, text="採用", variable=segment_selected).pack(side="left")

    compose_list = tk.Listbox(segments_tab, height=5, exportselection=False)
    ttk.Label(segments_tab, text="編集用動画の順番（同じ区間を複数回追加できます）").pack(anchor="w")
    compose_list.pack(fill="x")
    compose_fps = tk.StringVar()
    frame_status = tk.StringVar()
    composed_path: list[Path | None] = [None]
    screen = {name: tk.StringVar(value=str(value)) for name, value in Layout(1920, 1080).__dict__.items()}
    screen_kind = tk.StringVar(value="横")
    layout_path: list[Path | None] = [None]
    subtitle_rows = [[]]
    subtitle_first = tk.StringVar()
    subtitle_last = tk.StringVar()
    layout_dirty = [False]
    subtitle_dirty = [False]
    subtitle_pending = [False]
    subtitle_applied_rows: list[tuple[Subtitle, ...] | None] = [None]
    subtitle_selected: list[int | None] = [None]
    filling_subtitle = [False]

    def mark_layout_dirty(*_args):
        if composed_path[0] is not None:
            layout_dirty[0] = True

    def mark_subtitle_dirty(*_args):
        if not filling_subtitle[0] and subtitle_selected[0] is not None:
            subtitle_dirty[0] = True

    for variable in screen.values():
        variable.trace_add("write", mark_layout_dirty)
    for variable in (subtitle_first, subtitle_last):
        variable.trace_add("write", mark_subtitle_dirty)

    def current_layout():
        integer_fields = {"width", "height", "crop_left", "crop_top", "crop_right",
                          "crop_bottom", "subtitle_size", "preview_frame"}
        values = {name: int(variable.get()) if name in integer_fields else float(variable.get())
                  for name, variable in screen.items()}
        return Layout(**values)

    def video_dimensions():
        if composed_path[0] is None or not composed_path[0].is_file():
            raise StorageError("編集用動画を作成してください")
        return probe_frames(composed_path[0])[2:4]

    def choose_screen(kind):
        if pending[0] or data.running:
            return
        try:
            width, height = video_dimensions()
        except (OSError, StorageError) as error:
            messagebox.showerror("画面を選べません", str(error))
            return
        screen_kind.set(kind)
        # Change only the canvas. Existing video and subtitle positions stay intact.
        screen["width"].set(str(height if kind == "ショート" else width))
        screen["height"].set(str(width if kind == "ショート" else height))

    def prepare_layout():
        if pending[0] or data.running:
            return
        try:
            width, height = video_dimensions()
            path = save_layout(data, composed_path[0], current_layout(), width, height)
        except (OSError, ValueError, StorageError) as error:
            messagebox.showerror("画面設定を保存できません", str(error))
            return
        layout_path[0] = path
        status.set(f"画面設定を保存しました: {path.name}")
        applied = apply_layout(path)
        layout_dirty[0] = applied not in ("preview", "applied")
        if applied == "preview":
            show_layout_preview()
        elif applied == "applied":
            messagebox.showwarning("画面設定", "AviUtl2へ画面設定を適用しましたが、プレビューの生成に失敗しました")
        else:
            messagebox.showinfo("画面設定", f"AviUtl2で直接適用できませんでした。開いている対応プロジェクトを確認するか、「ClipChannel\\画面設定を適用」から選んでください。\n{path}")

    def show_layout_preview():
        if layout_path[0] is None:
            messagebox.showerror("プレビューを開けません", "先に画面設定を渡してください")
            return
        preview = layout_path[0].with_suffix(".ppm")
        if not preview.is_file():
            messagebox.showerror("プレビューを開けません", "AviUtl2で画面設定を適用してから開いてください")
            return
        popup = tk.Toplevel(window)
        popup.title("AviUtl2プレビュー")
        picture = tk.PhotoImage(file=str(preview))
        label = ttk.Label(popup, image=picture)
        label.image = picture
        label.pack()

    def refresh_compose_order():
        compose_list.delete(0, tk.END)
        for index in compose_order:
            if index < len(segment_rows[0]):
                row = segment_rows[0][index]
                compose_list.insert(tk.END, f"{index + 1}: {row.start_ms / 1000:.3f}–{row.end_ms / 1000:.3f}")

    def add_compose_segment():
        compose_order.extend(segment_list.curselection())
        refresh_compose_order()

    def move_compose_segment(direction):
        selected = compose_list.curselection()
        if selected and 0 <= selected[0] + direction < len(compose_order):
            index = selected[0]
            compose_order[index], compose_order[index + direction] = compose_order[index + direction], compose_order[index]
            refresh_compose_order()
            compose_list.selection_set(index + direction)

    def remove_compose_segment():
        for index in reversed(compose_list.curselection()):
            del compose_order[index]
        refresh_compose_order()

    def inspect_frame():
        video = segment_video()
        if video is None or pending[0] or data.running:
            return
        try:
            requested = [round(float(value.get()) * 1000) for value in (segment_start, segment_end)]
        except (ValueError, OverflowError):
            messagebox.showerror("フレームを確認できません", "開始・終了時刻を数値で指定してください")
            return
        def finish(results):
            reports = []
            for (label, value), (closest, difference) in zip((("開始", segment_start), ("終了", segment_end)), results):
                reports.append(f"{label} {closest / 1000:.3f}秒 (差 {difference:+d}ms)")
                value.set(f"{closest / 1000:.3f}")
            frame_status.set(" / ".join(reports))
        process_panel.start("フレーム境界の確認", operation_tasks.align_frames,
                            (video, requested), on_result=finish)

    def step_frame(value, label, direction):
        video = segment_video()
        if video is None or pending[0] or data.running:
            return
        try:
            requested = round(float(value.get()) * 1000)
        except (ValueError, OverflowError):
            messagebox.showerror("フレームを調整できません", "時刻を数値で指定してください")
            return
        def finish(closest):
            difference = closest - requested
            value.set(f"{closest / 1000:.3f}")
            frame_status.set(f"{label} {closest / 1000:.3f}秒 (差 {difference:+d}ms)。境界を修正で保存")
        process_panel.start("フレーム境界の調整", operation_tasks.step_frame,
                            (video, requested, direction), on_result=finish)

    def play_composed():
        if composed_path[0] is None or not composed_path[0].is_file():
            return
        ffplay = shutil.which("ffplay")
        if not ffplay:
            messagebox.showerror("再生できません", "ffplay が必要です")
            return
        subprocess.Popen([ffplay, "-autoexit", str(composed_path[0])],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def render_compose():
        if save_export_panel.has_unsaved_project():
            messagebox.showerror("編集用動画を作れません", "現在の編集を「保存」してから別の編集用動画を作成してください")
            return
        if supporting_panel.has_unsaved:
            messagebox.showerror("編集用動画を作れません", "補助素材の入力を適用するか破棄してください")
            return
        video = segment_video()
        if video is None or segment_source[0] != video or segment_dirty[0] or pending[0] or data.running:
            messagebox.showerror("編集用動画を作れません", "対象動画と保存済み区間を選んでください")
            return
        order = list(compose_order) or [i for i, row in enumerate(segment_rows[0]) if row.selected]
        try:
            fps = float(compose_fps.get()) if compose_fps.get().strip() else None
        except ValueError:
            messagebox.showerror("編集用動画を作れません", "固定fpsを数値で指定してください")
            return
        short = messagebox.askyesno("画面を選択", "ショート画面で新しい編集を作成しますか？\n「いいえ」は横画面です")
        def finish(path):
            status.set(f"編集用動画と新しいAviUtl2プロジェクトを作成しました: {path}")
            composed_path[0] = path
            supporting_panel.set_video(path)
            width, height = video_dimensions()
            for name, value in Layout(width, height).__dict__.items():
                screen[name].set(str(value))
            layout_path[0] = None
            subtitle_rows[0] = []
            subtitle_dirty[0] = subtitle_pending[0] = False
            subtitle_selected[0] = None
            subtitle_applied_rows[0] = None
            subtitle_first.set("")
            subtitle_last.set("")
            subtitle_text.delete("1.0", tk.END)
            refresh_subtitle_list()
            choose_screen("ショート" if short else "横")
            layout_dirty[0] = False  # The new project already has these initial settings.
            save_export_panel.set_video(path, short=short)
            project = save_export_panel.project
            messagebox.showinfo("新しい編集", f"編集用動画: {path}\nAviUtl2プロジェクト: {project}\n"
                                "AviUtl2でこのプロジェクトを開いて編集してください。\n"
                                "旧編集の動画・プロジェクト・字幕・補助素材配置は保持し、新編集へ移しません。\n"
                                "過去の編集は projects 内の .aup2 をAviUtl2で直接開けます。")

        process_panel.start("編集用動画の作成", operation_tasks.compose,
                            (data, video, tuple(segment_rows[0]), order, segment_duration[0]),
                            {"fps": fps, "short": short}, on_result=finish)

    def export_subtitles():
        if subtitle_dirty[0] or subtitle_pending[0]:
            messagebox.showerror("字幕を取り込めません", "現在の字幕入力を「保存」してから取り込んでください")
            return
        if pending[0] or data.running:
            return
        video = segment_video()
        if video is None or composed_path[0] is None or not listing.curselection() or review_dirty[0]:
            messagebox.showerror("字幕を取り込めません", "編集用動画と保存済み文字起こしCSVを選んでください")
            return
        relative = listing.get(listing.curselection()[0])
        if relative.split("/")[:3] != ["catalog", video.stem, "transcripts"]:
            messagebox.showerror("字幕を取り込めません", "同じ元動画の文字起こしCSVを選んでください")
            return
        try:
            version = int(relative.rsplit("_v", 1)[1].removesuffix(".csv"))
            path, rows = prepare_subtitle_import(data, video, composed_path[0], version)
        except (OSError, ValueError, StorageError) as error:
            messagebox.showerror("字幕を取り込めません", str(error))
            return
        status.set(f"字幕 {len(rows)} 件を準備しました: {path.name}")
        subtitle_rows[0] = rows
        subtitle_selected[0] = None
        subtitle_pending[0] = True
        refresh_subtitle_list()
        apply_subtitle_version(path)

    def apply_subtitle_version(path):
        subtitle_pending[0] = True
        if not apply_subtitles(path):
            messagebox.showinfo("字幕の取込み", f"AviUtl2で直接追加できませんでした。「ClipChannel\\字幕を追加」から選んでください。\n{path}")
            return
        subtitle_dirty[0] = subtitle_pending[0] = False
        subtitle_applied_rows[0] = tuple(subtitle_rows[0])
        status.set(f"AviUtl2へ字幕を追加しました: {path.name}")
        if layout_path[0] is not None and apply_layout(layout_path[0]) == "preview":
            show_layout_preview()
        else:
            messagebox.showinfo("字幕の取込み", "AviUtl2へ字幕を追加しました。画面設定を渡すとプレビューできます")

    def refresh_subtitle_list():
        subtitle_list.delete(0, tk.END)
        for row in subtitle_rows[0]:
            subtitle_list.insert(tk.END, f"{row.start_frame}–{row.end_frame}: {row.text[:32]}")

    def select_subtitle(_event=None):
        selected = subtitle_list.curselection()
        if len(selected) != 1:
            return
        index = selected[0]
        if subtitle_dirty[0] and index != subtitle_selected[0]:
            subtitle_list.selection_clear(0, tk.END)
            if subtitle_selected[0] is not None:
                subtitle_list.selection_set(subtitle_selected[0])
            messagebox.showerror("編集用字幕", "現在の字幕入力を保存してから別の字幕を選んでください")
            return
        if subtitle_dirty[0]:
            return
        row = subtitle_rows[0][index]
        subtitle_selected[0] = index
        filling_subtitle[0] = True
        try:
            subtitle_first.set(str(row.start_frame))
            subtitle_last.set(str(row.end_frame))
            subtitle_text.delete("1.0", tk.END)
            subtitle_text.insert("1.0", row.text)
            subtitle_text.edit_modified(False)
        finally:
            filling_subtitle[0] = False

    def save_subtitle_edit():
        if pending[0] or data.running:
            return
        selected = subtitle_list.curselection()
        if composed_path[0] is None or len(selected) != 1:
            messagebox.showerror("字幕を変更できません", "編集用動画と字幕を選んでください")
            return
        try:
            index = selected[0]
            rows = list(subtitle_rows[0])
            rows[index] = Subtitle(int(subtitle_first.get()), int(subtitle_last.get()),
                                   subtitle_text.get("1.0", "end-1c"))
            metadata = json.loads(composed_path[0].with_suffix(".json").read_text(encoding="utf-8"))
            path, _ = write_subtitle_import(data, composed_path[0], rows,
                                            sum(metadata["frame_counts"]))
        except (OSError, ValueError, KeyError, TypeError, StorageError) as error:
            messagebox.showerror("字幕を変更できません", str(error))
            return
        subtitle_rows[0] = rows
        refresh_subtitle_list()
        subtitle_list.selection_set(index)
        status.set(f"編集用字幕を別版保存しました: {path.name}")
        apply_subtitle_version(path)

    compose_actions = ttk.Frame(segments_tab)
    compose_actions.pack(fill="x")
    for caption, action in (("区間を追加", add_compose_segment), ("上へ", lambda: move_compose_segment(-1)),
                            ("下へ", lambda: move_compose_segment(1)), ("外す", remove_compose_segment),
                            ("フレーム境界へ合わせる", inspect_frame),
                            ("開始-1F", lambda: step_frame(segment_start, "開始", -1)),
                            ("開始+1F", lambda: step_frame(segment_start, "開始", 1)),
                            ("終了-1F", lambda: step_frame(segment_end, "終了", -1)),
                            ("終了+1F", lambda: step_frame(segment_end, "終了", 1)),
                            ("新しい編集を作成", render_compose),
                            ("字幕をAviUtl2へ追加", export_subtitles),
                            ("編集用動画を再生", play_composed)):
        ttk.Button(compose_actions, text=caption, command=action).pack(side="left")
    ttk.Label(segments_tab, text="固定fps（可変fpsでは必須。空欄なら元動画優先）").pack(anchor="w")
    ttk.Entry(segments_tab, textvariable=compose_fps, width=10).pack(anchor="w")
    ttk.Label(segments_tab, textvariable=frame_status).pack(anchor="w")

    layout_tab = ttk.Frame(saved_tabs, padding=4)
    saved_tabs.add(layout_tab, text="画面・字幕")
    ttk.Label(layout_tab, text="編集用動画の画面設定（切替時に配置は保持）").pack(anchor="w")
    layout_buttons = ttk.Frame(layout_tab)
    layout_buttons.pack(anchor="w")
    for kind in ("横", "ショート"):
        ttk.Button(layout_buttons, text=kind, command=lambda selected=kind: choose_screen(selected)).pack(side="left")
    ttk.Label(layout_buttons, textvariable=screen_kind).pack(side="left", padx=10)
    for caption, name in (("画面幅", "width"), ("画面高さ", "height"),
                          ("動画拡大率 %", "scale"), ("動画 X", "x"), ("動画 Y", "y"),
                          ("左切り取り px", "crop_left"), ("上切り取り px", "crop_top"),
                          ("右切り取り px", "crop_right"), ("下切り取り px", "crop_bottom"),
                          ("字幕 X", "subtitle_x"), ("字幕 Y", "subtitle_y"),
                          ("字幕サイズ", "subtitle_size"), ("プレビューフレーム", "preview_frame")):
        line = ttk.Frame(layout_tab)
        line.pack(anchor="w")
        ttk.Label(line, text=caption, width=18).pack(side="left")
        ttk.Entry(line, textvariable=screen[name], width=12).pack(side="left")
    ttk.Button(layout_tab, text="画面設定をAviUtl2へ渡す", command=prepare_layout).pack(anchor="w", pady=8)
    ttk.Button(layout_tab, text="AviUtl2結果のプレビューを開く", command=show_layout_preview).pack(anchor="w")
    ttk.Label(layout_tab, text="編集用字幕（変更時は別版を追加）").pack(anchor="w")
    subtitle_list = tk.Listbox(layout_tab, height=5, exportselection=False)
    subtitle_list.pack(fill="x")
    subtitle_list.bind("<<ListboxSelect>>", select_subtitle)
    subtitle_line = ttk.Frame(layout_tab)
    subtitle_line.pack(anchor="w")
    for caption, variable in (("開始F", subtitle_first), ("終了F", subtitle_last)):
        ttk.Label(subtitle_line, text=caption).pack(side="left")
        ttk.Entry(subtitle_line, textvariable=variable, width=7).pack(side="left")
    subtitle_text = tk.Text(layout_tab, height=3, width=32)
    subtitle_text.pack(fill="x")
    def text_modified(_event=None):
        if subtitle_text.edit_modified():
            mark_subtitle_dirty()
            subtitle_text.edit_modified(False)
    subtitle_text.bind("<<Modified>>", text_modified)
    ttk.Button(layout_tab, text="選択字幕を別版保存", command=save_subtitle_edit).pack(anchor="w")

    supporting_panel = SupportingMediaPanel(saved_tabs, data, status)
    saved_tabs.add(supporting_panel, text="補助素材")

    def has_editor_drafts():
        return layout_dirty[0] or subtitle_dirty[0] or subtitle_pending[0] or supporting_panel.has_unsaved

    def prepare_editor_drafts():
        """Capture Tk values before dispatch; clear drafts only after confirmed save."""
        video = composed_path[0]
        if video is None:
            raise StorageError("編集用動画を作成してください")
        layout = current_layout() if layout_dirty[0] else None
        dimensions = video_dimensions() if layout is not None else (0, 0)
        if layout is not None:
            layout.validate(*dimensions)
        rows = list(subtitle_rows[0]) if subtitle_dirty[0] or subtitle_pending[0] else None
        if subtitle_dirty[0] and rows is not None:
            index = subtitle_selected[0]
            if index is None:
                raise StorageError("変更する字幕を選択してください")
            rows[index] = Subtitle(int(subtitle_first.get()), int(subtitle_last.get()),
                                   subtitle_text.get("1.0", "end-1c"))
        placements = supporting_panel.pending_snapshot()
        layout_result: list[Path | None] = [None]
        def work():
            if rows is not None and tuple(rows) != subtitle_applied_rows[0]:
                metadata = json.loads(video.with_suffix(".json").read_text(encoding="utf-8"))
                path, _ = write_subtitle_import(data, video, rows, sum(metadata["frame_counts"]))
                if not apply_subtitles(path):
                    raise StorageError("字幕をAviUtl2へ適用できません。入力を保持しています")
                subtitle_applied_rows[0] = tuple(rows)
            if layout is not None:
                path = save_layout(data, video, layout, *dimensions)
                if apply_layout(path) not in ("preview", "applied"):
                    raise StorageError("画面設定をAviUtl2へ適用できません。入力を保持しています")
                layout_result[0] = path
            supporting_panel.apply_pending(placements)
        def commit():
            if rows is not None:
                subtitle_rows[0] = rows
                subtitle_dirty[0] = subtitle_pending[0] = False
                refresh_subtitle_list()
                if subtitle_selected[0] is not None:
                    subtitle_list.selection_set(subtitle_selected[0])
            if layout is not None:
                layout_path[0] = layout_result[0]
                layout_dirty[0] = False
            supporting_panel.commit_pending(placements)
        return work, commit

    editor_widget_lock = WidgetLock((segments_tab, layout_tab, supporting_panel))

    save_export_panel = SaveExportPanel(saved_tabs, data, status, has_drafts=has_editor_drafts,
                                        prepare_drafts=prepare_editor_drafts, lock_editing=editor_widget_lock.set_locked)
    saved_tabs.add(save_export_panel, text="保存・書き出し")

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

    word_version = tk.StringVar(value="1")
    include_verbs = tk.BooleanVar()
    include_adjectives = tk.BooleanVar()
    word_entries = tk.Listbox(words_tab, height=9, exportselection=False)
    word_hits = tk.Listbox(words_tab, height=9, exportselection=False)
    word_rows = [[]]
    word_source = [None]
    word_choice = tk.StringVar()
    ttk.Label(words_tab, text="対象動画は人物タブで選択。修正済み文字起こしの版番号").pack(anchor="w")
    ttk.Entry(words_tab, textvariable=word_version, width=8).pack(anchor="w")
    ttk.Checkbutton(words_tab, text="動詞を含める", variable=include_verbs).pack(anchor="w")
    ttk.Checkbutton(words_tab, text="形容詞を含める", variable=include_adjectives).pack(anchor="w")

    def update_words(kind, remove=False):
        if data.path is None:
            return
        value = word_choice.get().strip()
        if not value:
            return
        try:
            existing = {row["word"] for row in data.load_shared(kind)}
            if remove:
                existing.discard(value)
            else:
                existing.add(value)
            data.save_shared(kind, [{"word": item} for item in sorted(existing)])
            relative = f"people/{kind}.csv"
            if relative not in listing.get(0, tk.END):
                listing.insert(tk.END, relative)
            status.set(f"保存しました: {value}")
        except (OSError, StorageError) as error:
            messagebox.showerror("登録できません", str(error))

    ttk.Entry(words_tab, textvariable=word_choice).pack(fill="x")
    word_actions = ttk.Frame(words_tab)
    word_actions.pack(fill="x")
    ttk.Button(word_actions, text="登録語に追加", command=lambda: update_words("registered-words")).pack(side="left")
    ttk.Button(word_actions, text="除外語に追加", command=lambda: update_words("excluded-words")).pack(side="left")
    ttk.Button(word_actions, text="登録語から削除", command=lambda: update_words("registered-words", True)).pack(side="left")
    ttk.Button(word_actions, text="除外語から削除", command=lambda: update_words("excluded-words", True)).pack(side="left")

    def show_word_rows(rows, video):
        word_rows[0], word_source[0] = rows, video
        word_entries.delete(0, tk.END)
        word_hits.delete(0, tk.END)
        seen = set()
        for row in rows:
            if row["word"] not in seen:
                seen.add(row["word"])
                word_entries.insert(tk.END, f'{row["word"]}  出現 {row["occurrences"]} / 発言 {row["utterances"]}')

    def recount_words():
        video = next((path for path in data.list_videos() if path.name == target_video.get()), None) if data.path else None
        if video is None or pending[0] or data.running or review_dirty[0]:
            messagebox.showerror("再集計できません", "対象動画を選び、文字起こしの保存を完了してください")
            return
        try:
            version = int(word_version.get())
            path = count_words(data, video, version, include_verbs=include_verbs.get(),
                               include_adjectives=include_adjectives.get())
            listing.insert(tk.END, path.relative_to(data._root()).as_posix())
            show_word_rows(data.load_result(video, "word-counts", int(path.stem.rsplit("_v", 1)[1])), video)
            status.set(f"再集計を保存しました: {path.name}")
        except (OSError, StorageError, ValueError) as error:
            messagebox.showerror("再集計できません", str(error))

    def reopen_words():
        if not listing.curselection() or data.path is None:
            return
        relative = listing.get(listing.curselection()[0])
        parts = relative.split("/")
        if len(parts) != 4 or parts[2] != "word-counts":
            messagebox.showerror("表示できません", "頻出語の保存版を選んでください")
            return
        try:
            version = int(parts[3].rsplit("_v", 1)[1].removesuffix(".csv"))
            video = next(path for path in data.list_videos() if path.stem == parts[1])
            show_word_rows(data.load_result(video, "word-counts", version), video)
        except (OSError, StorageError, ValueError, StopIteration) as error:
            messagebox.showerror("表示できません", str(error))

    ttk.Button(words_tab, text="再集計して別版保存", command=recount_words).pack(anchor="w")
    ttk.Button(words_tab, text="選択した保存版を表示", command=reopen_words).pack(anchor="w")
    word_entries.pack(fill="both", expand=True)
    word_hits.pack(fill="both", expand=True)

    def choose_word(_event=None):
        if not word_entries.curselection():
            return
        words = list(dict.fromkeys(row["word"] for row in word_rows[0]))
        word = words[word_entries.curselection()[0]]
        word_hits.delete(0, tk.END)
        for row in word_rows[0]:
            if row["word"] == word:
                word_hits.insert(tk.END, f'{int(row["start_ms"]) / 1000:.3f}秒  {row["text"]}')

    def play_word(_event=None):
        if not word_hits.curselection() or not word_entries.curselection() or word_source[0] is None:
            return
        word = list(dict.fromkeys(row["word"] for row in word_rows[0]))[word_entries.curselection()[0]]
        row = [item for item in word_rows[0] if item["word"] == word][word_hits.curselection()[0]]
        ffplay = shutil.which("ffplay")
        if not ffplay:
            messagebox.showerror("動画を確認できません", "ffplay が必要です")
            return
        if player[0] and player[0].poll() is None:
            player[0].terminate()
        player[0] = subprocess.Popen([ffplay, "-autoexit", "-loglevel", "error", "-ss",
                                      str(int(row["start_ms"]) / 1000), "-t",
                                      str((int(row["end_ms"]) - int(row["start_ms"])) / 1000),
                                      str(word_source[0])], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    word_entries.bind("<<ListboxSelect>>", choose_word)
    word_hits.bind("<Double-Button-1>", play_word)

    def refresh_downloads():
        current = session[0]
        if current is None:
            return
        previous = downloads.cget("state")
        downloads.configure(state="normal")
        downloads.delete(0, tk.END)
        for item in current.items:
            downloads.insert(tk.END, f"{item.state} | {item.seconds:.1f}秒 | {item.title} | {item.details} | {item.path or item.error}")
        downloads.configure(state=previous)
        status.set(f"{current.state} | {current.elapsed:.1f}秒")
        if not process_panel.active:
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
        if current is None:
            return
        selected = set(downloads.curselection()) if retry else None
        unsaved.set(False)

        def update(snapshot):
            if isinstance(snapshot, DownloadSession):
                session[0] = snapshot
                refresh_downloads()

        def stopped(operation):
            snapshot = session[0]
            if snapshot is None:
                return
            if operation.state in ("中止", "強制停止", "失敗"):
                for item in snapshot.items:
                    if item.state == "取得中":
                        item.state = "中止" if operation.state != "失敗" else "失敗"
                snapshot.state = operation.state
                if snapshot.started_at is not None:
                    snapshot.ended_at = snapshot.started_at + operation.elapsed
            refresh_downloads()

        process_panel.start("動画の情報取得" if current.info_only else "動画・音声の取得",
                            operation_tasks.download, (current, selected),
                            on_result=update, on_progress=update, on_finished=stopped)

    download_actions = ttk.Frame(media_panel)
    download_actions.pack(fill="x", pady=5)
    tk.Button(download_actions, text="取得・情報表示", command=run_download).pack(side="left", padx=(0, 4))
    tk.Button(download_actions, text="失敗項目を再試行", command=lambda: run_download(True)).pack(side="left", padx=4)
    def stop_download():
        process_panel.stop()

    tk.Button(download_actions, text="通常中止", command=stop_download).pack(side="left", padx=4)
    tk.Button(download_actions, text="機能案内", command=lambda: messagebox.showinfo(
        "取得機能", "yt-dlp が必要です。動画は media/originals、音声のみは media/audio に保存します。"
        "追加引数は表示された形式・再試行等の指定に対応します。保存先・上書き・認証・外部コマンド・プラグイン指定は保護条件のため実行前に停止します。"
        "情報のみはファイルを保存しません。" )).pack(side="left", padx=4)

    def choose():
        if pending[0] or data.running:
            messagebox.showerror("フォルダを切り替えられません", "処理中のためフォルダを切り替えられません")
            return
        selected = filedialog.askdirectory(mustexist=True)
        if not selected:
            return
        data.unsaved = (unsaved.get() or review_dirty[0] or segment_dirty[0] or
                        has_editor_drafts() or save_export_panel.has_unsaved_project())
        try:
            paths = data.select(selected)
        except (OSError, StorageError) as error:
            messagebox.showerror("フォルダを切り替えられません", str(error))
            return
        location.set(str(data.path))
        review_rows[0], review_source[0], review_version[0] = [], None, None
        display_review()
        composed_path[0] = None
        supporting_panel.set_video(None)
        save_export_panel.set_video(None)
        layout_dirty[0] = subtitle_dirty[0] = subtitle_pending[0] = False
        subtitle_selected[0] = None
        subtitle_applied_rows[0] = None
        listing.delete(0, tk.END)
        for path in paths:
            listing.insert(tk.END, path)
        status.set(f"保存済み結果: {len(paths)} 件" +
                   (f" / ログ整理失敗: {data.log_cleanup_error}" if data.log_cleanup_error else ""))
        management_panel.reset()
        refresh_videos()
        refresh_people()
        segment_rows[0], segment_source[0], segment_duration[0] = [], None, 0
        display_segments()

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
        prepare_video(Path(selected))

    def prepare_video(path):
        if pending[0] or data.running:
            messagebox.showerror("媒体を準備できません", "処理完了を待ってください")
            return
        def finish(result):
            summary = (f"編集用: {result.editing}\n"
                       f"元映像開始: {result.source_info.video.start}秒 / "
                       f"元音声開始: {result.source_info.audio.start if result.source_info.audio else 'なし'}秒\n"
                       f"時刻対応: {result.manifest}")
            messagebox.showinfo("媒体を準備しました", summary)
            status.set(f"媒体準備完了: {path.name}")
        process_panel.start("媒体確認・編集互換変換", operation_tasks.prepare,
                            (data, path), on_result=finish,
                            on_finished=lambda _operation: refresh_videos())

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
        if save_export_panel.busy:
            save_export_panel.request_close(finish_close)
            return
        if pending[0] or data.running:
            process_panel.stop()
            status.set("停止完了後にもう一度閉じてください。未保存の入力は保持しています")
        else:
            if review_dirty[0]:
                messagebox.showerror("終了できません", "保存されていない文字起こし修正があります。「保存を再試行」を押してください")
                return
            if segment_dirty[0]:
                messagebox.showerror("終了できません", "保存されていない切り出し区間があります。「保存を再試行」を押してください")
                return
            save_export_panel.request_close(finish_close)

    def finish_close():
        if player[0] and player[0].poll() is None:
            player[0].terminate()
        supporting_panel.stop_audio()
        window.destroy()

    def refresh_managed_lists():
        listing.delete(0, tk.END)
        for path in data.list_saved():
            listing.insert(tk.END, path)
        refresh_videos()
        refresh_people()

    management_panel = ManagementPanel(
        saved_tabs, data, status, refresh_lists=refresh_managed_lists,
        start_operation=lambda *args, **kwargs: process_panel.start(*args, **kwargs),
        has_drafts=lambda: pending[0] or unsaved.get() or review_dirty[0] or segment_dirty[0] or has_editor_drafts())
    saved_tabs.add(management_panel, text="管理・保管")
    saved_tabs.bind("<<NotebookTabChanged>>", lambda _event: management_panel.refresh())

    operation_lock = WidgetLock((header, saved_panel, media_panel))

    def lock_operation(locked):
        pending[0] = data.running = locked
        operation_lock.set_locked(locked)

    def record_finished_operation(operation):
        try:
            record_operation(data, operation.label, operation.state, operation.elapsed)
            cleanup_logs(data)
        except (OSError, StorageError) as error:
            messagebox.showerror("処理ログを保存・整理できません", str(error))

    process_panel = ProcessPanel(window, status, lock_operation, on_finished=record_finished_operation)
    process_panel.pack(fill="x", padx=10, pady=4)

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
