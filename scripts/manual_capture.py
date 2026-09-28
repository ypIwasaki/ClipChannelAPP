"""Capture only this app's rendered X11 windows, using temporary sample data.

Run in WSL: .venv/bin/python scripts/manual_capture.py
Documentation-only dependencies: Pillow. Never opens the user's data folder.
"""
import ctypes
import json
import sys
import subprocess
import tempfile
import time
from pathlib import Path
from unittest.mock import patch
import tkinter as tk

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from clipchannel.app import build_app
from clipchannel.storage import DataFolder
from clipchannel.responsive_ui import WORKS, ResponsivePage
from clipchannel.window_preferences import DisplayArea
from clipchannel.dialogs import choose_action, show_image_preview


class XImage(ctypes.Structure):
    _fields_ = [('width', ctypes.c_int), ('height', ctypes.c_int),
                ('xoffset', ctypes.c_int), ('format', ctypes.c_int),
                ('data', ctypes.c_void_p), ('byte_order', ctypes.c_int),
                ('bitmap_unit', ctypes.c_int), ('bitmap_bit_order', ctypes.c_int),
                ('bitmap_pad', ctypes.c_int), ('depth', ctypes.c_int),
                ('bytes_per_line', ctypes.c_int), ('bits_per_pixel', ctypes.c_int)]


def descendants(widget):
    for child in widget.winfo_children():
        yield child
        yield from descendants(child)


def settle(window):
    for _ in range(5):
        window.update()
        time.sleep(.08)


def demonstration_work(control):
    control.report('説明用の一時処理です。実データは変更しません。')
    while not control.cancelled():
        time.sleep(.05)
    # Allow screenshots of the actual waiting state and its force option.
    time.sleep(4)
    return '説明用処理を停止しました'


def capture(widget):
    """Read the app window itself, never the desktop or other apps."""
    lib = ctypes.CDLL('libX11.so.6')
    lib.XOpenDisplay.restype = ctypes.c_void_p
    display = lib.XOpenDisplay(None)
    if not display:
        raise RuntimeError('An X11 display is required')
    lib.XGetImage.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_int,
                             ctypes.c_int, ctypes.c_uint, ctypes.c_uint,
                             ctypes.c_ulong, ctypes.c_int]
    lib.XGetImage.restype = ctypes.POINTER(XImage)
    lib.XDestroyImage.argtypes = [ctypes.POINTER(XImage)]
    lib.XCloseDisplay.argtypes = [ctypes.c_void_p]
    result = None
    try:
        result = lib.XGetImage(display, widget.winfo_id(), 0, 0,
                              widget.winfo_width(), widget.winfo_height(),
                              ctypes.c_ulong(-1).value, 2)
        if not result:
            raise RuntimeError('Could not capture the rendered app window')
        raw = result.contents
        if raw.bits_per_pixel != 32 or raw.byte_order != 0:
            raise RuntimeError('Unsupported X11 image format')
        pixels = ctypes.string_at(raw.data, raw.bytes_per_line * raw.height)
        return Image.frombytes('RGB', (raw.width, raw.height), pixels,
                               'raw', 'BGRX', raw.bytes_per_line)
    finally:
        if result:
            lib.XDestroyImage(result)
        lib.XCloseDisplay(display)


def save_shot(widget, destination, highlights):
    image = capture(widget)
    draw = ImageDraw.Draw(image)
    boxes = []
    for number, control in enumerate(highlights, 1):
        if not control.winfo_viewable():
            continue
        x = control.winfo_rootx() - widget.winfo_rootx()
        y = control.winfo_rooty() - widget.winfo_rooty()
        bounds = [max(2, x-2), max(2, y-2),
                  min(image.width-3, x+control.winfo_width()+2),
                  min(image.height-3, y+control.winfo_height()+2)]
        draw.rectangle(bounds, outline='#e21c2a', width=3)
        label = str(number)
        badge_x = max(bounds[0], bounds[2]-22)
        badge_y = max(0, bounds[1]-20)
        draw.rectangle((badge_x, badge_y, badge_x+22, badge_y+20), fill='#e21c2a')
        draw.text((badge_x+6, badge_y+3), label, fill='white')
        boxes.append({'number': number, 'bounds': bounds})
    image.save(destination)
    return boxes


def main():
    output = ROOT / 'docs' / 'manual' / 'images'
    output.mkdir(parents=True, exist_ok=True)
    manifest = []
    with tempfile.TemporaryDirectory(prefix='clipchannel-manual-') as temporary:
        root = Path(temporary)
        data = DataFolder()
        data.select(root)
        source = root / 'sample-video.mp4'
        subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i',
                        'color=c=steelblue:s=640x360:r=30:d=10', '-f', 'lavfi', '-i',
                        'sine=frequency=440:duration=10', '-c:v', 'libx264',
                        '-c:a', 'aac', '-shortest', str(source)], check=True)
        video = data.register_video(source)
        data.save_result(video, 'transcripts', [
            {'start_ms': '1000', 'end_ms': '4500', 'speaker_id': 'target', 'text': '今日はゲームの攻略を紹介します。'},
            {'start_ms': '5000', 'end_ms': '8500', 'speaker_id': 'target', 'text': 'この場面ではアイテムを使います。'}])
        from clipchannel.segments import Segment, save_segments
        save_segments(data, video, [Segment(1000, 4500, 'target'), Segment(5000, 8500, 'target')], 10000)
        data.save_shared('registered-words', [{'word': 'ゲーム攻略'}])
        data.save_shared('excluded-words', [{'word': 'こと'}])
        data.save_result(video, 'word-counts', [{'word': 'ゲーム', 'occurrences': '1',
            'utterances': '1', 'start_ms': '1000', 'end_ms': '4500',
            'text': '今日はゲームの攻略を紹介します。', 'transcript_version': '1',
            'include_verbs': 'False', 'include_adjectives': 'False'}])
        window = build_app(data=data, preferences=root / 'ui.json',
                           display=DisplayArea(0, 0, 1600, 1000))
        window.geometry('1360x850+30+30')
        try:
            settle(window)
            all_widgets = list(descendants(window))
            notebook = next(w for w in all_widgets if w.winfo_class() == 'TNotebook')
            def button(caption):
                return next(w for w in all_widgets if w.winfo_class() in ('Button', 'TButton')
                            and w.cget('text') == caption)
            navigation = [button('フォルダを選択・切り替え'), button('編集・書き出し'),
                          button('実行中の処理を中止')]
            boxes = save_shot(window, output / '00-overview.png', navigation)
            manifest.append(dict(file='00-overview.png', title='全体の操作', boxes=boxes))
            # Load sample CSVs through the production UI, then create a real temporary
            # editing MP4/project. External AviUtl2 sending is explicitly disabled.
            listing = next(w for w in all_widgets if w.winfo_class() == 'Listbox'
                           and any('/transcripts/' in s for s in w.get(0, tk.END)))
            def select_saved(kind):
                listing.selection_clear(0, tk.END)
                index = next(i for i, value in enumerate(listing.get(0, tk.END)) if f'/{kind}/' in value)
                listing.selection_set(index)
                listing.event_generate('<<ListboxSelect>>')
                window.update()
            select_saved('transcripts')
            button('保存版を再表示').invoke()
            select_saved('segments')
            button('選択した保存版を使用').invoke()
            from clipchannel.save_export_ui import SaveExportPanel
            export = next(w for w in all_widgets if isinstance(w, SaveExportPanel))
            with patch('clipchannel.dialogs.messagebox.askyesno', return_value=False), \
                    patch('clipchannel.dialogs.messagebox.showinfo'):
                button('新しい編集を作成').invoke()
                deadline = time.monotonic() + 45
                while export.video is None and time.monotonic() < deadline:
                    window.update()
                    time.sleep(.05)
            if export.video is None:
                raise RuntimeError('Temporary editing video was not created')
            select_saved('transcripts')
            with patch('clipchannel.app.apply_subtitles', return_value=False), \
                    patch('clipchannel.dialogs.messagebox.showinfo'):
                button('字幕をAviUtl2へ追加').invoke()
            from clipchannel.supporting_media_ui import SupportingMediaPanel
            from clipchannel.supporting_media import import_supporting_media
            from clipchannel.management_ui import ManagementPanel
            from clipchannel.archive import archive_video
            supporting = next(w for w in all_widgets if isinstance(w, SupportingMediaPanel))
            sample_image = root / 'sample-image.png'
            Image.new('RGB', (320, 180), '#88afcb').save(sample_image)
            supporting.placements.append(import_supporting_media(data, export.video, sample_image, 'image'))
            supporting.refresh(0)
            management = next(w for w in all_widgets if isinstance(w, ManagementPanel))
            management.show_result(archive_video(data, video))
            select_saved('word-counts')
            button('選択した保存版を表示').invoke()
            layout_page = window.nametowidget(next(t for t in notebook.tabs()
                if notebook.tab(t, 'text') == '画面・字幕'))
            subtitle_listing = next(w for w in descendants(layout_page.sections['結果']['編集用字幕'])
                                    if w.winfo_class() == 'Listbox')
            subtitle_listing.selection_set(0)
            subtitle_listing.event_generate('<<ListboxSelect>>')
            count = 0
            for work, tabs in WORKS.items():
                button(work).invoke()
                for tab_title in tabs:
                    tab = next(t for t in notebook.tabs() if notebook.tab(t, 'text') == tab_title)
                    notebook.select(tab)
                    page = window.nametowidget(tab)
                    for role, sections in page.sections.items():
                        for title, container in sections.items():
                            if title == '字幕を修正':
                                page.show('編集用字幕')
                                settle(window)
                                subtitle_listing.selection_set(0)
                                subtitle_listing.event_generate('<<ListboxSelect>>')
                                window.update()
                            page.show(title)
                            if title in ('編集用字幕', '試聴区間・文字起こし', '切り出し区間', '頻出語一覧'):
                                listing_widget = next(w for w in descendants(container) if w.winfo_class() == 'Listbox')
                                if listing_widget.size():
                                    listing_widget.selection_set(0)
                                    listing_widget.event_generate('<<ListboxSelect>>')
                            settle(window)
                            controls = [w for w in descendants(container) if w.winfo_viewable()
                                and w.winfo_class() in ('Button', 'TButton', 'Entry', 'TEntry',
                                                       'TCombobox', 'Listbox', 'Text', 'TCheckbutton')]
                            count += 1
                            filename = f'{count:02d}-screen.png'
                            # A single red outline covers the active inputs/actions; the toolbar
                            # remains visible to make the navigation route clear.
                            boxes = save_shot(window, output / filename,
                                              [page.controls[role][1]] + (controls or [container]))
                            captions = [str(w.cget('text')) for w in controls
                                        if w.winfo_class() in ('Button', 'TButton', 'TCheckbutton')]
                            manifest.append(dict(file=filename, work=work, tab=tab_title, role=role,
                                                 title=title, captions=captions, boxes=boxes,
                                                 sample='一時データ。AviUtl2への送信・解析モデルの実行・ネット取得は未実行。'))
            # Three genuine states of an isolated, cancellable demonstration worker.
            from clipchannel.managed_process_ui import ProcessPanel
            process = next(w for w in all_widgets if isinstance(w, ProcessPanel))
            button('動画を準備').invoke()
            process.start('説明用の一時処理', demonstration_work)
            settle(window)
            for filename, title in [('process-running.png', '実行中'),
                                    ('process-stopping.png', '停止待ち・強制停止選択可能'),
                                    ('process-stopped.png', '停止完了')]:
                if filename == 'process-stopping.png':
                    button('実行中の処理を中止').invoke()
                    deadline = time.monotonic() + 3.3
                    while time.monotonic() < deadline:
                        window.update()
                        time.sleep(.04)
                elif filename == 'process-stopped.png':
                    deadline = time.monotonic() + 10
                    while process.active and time.monotonic() < deadline:
                        window.update()
                        time.sleep(.04)
                    if process.active:
                        raise RuntimeError('Demonstration worker did not stop')
                settle(window)
                boxes = save_shot(window, output / filename,
                                  [button('実行中の処理を中止'), button('実行中の処理を強制停止…')])
                manifest.append(dict(file=filename, title=title, boxes=boxes,
                                     sample='実際の管理対象処理の状態。一時的な待機処理のみ。'))
            # Capture the real dialog renderer with representative, explicitly labelled examples.
            prompts = [
                ('場所を確認', '案内\n説明用の一時データフォルダです。\nprojects/<編集フォルダ>/ に .aup2 が保存されます。', [('閉じる', None)], 'info'),
                ('エラー表示', 'エラー\n対象動画を選んでください。\n入力は保持しています。設定を確認して再試行してください。', [('閉じる', None)], 'error'),
                ('警告表示', '警告\n配置は適用しましたが、プレビューを生成できませんでした。', [('閉じる', None)], 'warning'),
                ('ショート条件外', 'ショートの条件（正方形または縦長、3分以内）から外れています。\n通常の動画として出力しても現在の比率・配置・長さ・設定を保持します。', [('編集・設定を直す', None), ('通常の動画として書き出す', 'normal')], 'confirmation'),
                ('未保存の編集・書き出し前', '未保存の編集があります、または保存状態を確認できません。', [('保存して書き出す', 'save'), ('戻る', None)], 'confirmation'),
                ('未保存の編集・終了時', '未保存の編集があります、または保存状態を確認できません。', [('保存する', 'save'), ('破棄する', 'discard'), ('戻る', None)], 'confirmation'),
                ('画面を選択', '確認\nショート画面で新しい編集を作成しますか？\n「いいえ」は横画面です', [('いいえ', None), ('はい', True)], 'confirmation'),
                ('登録情報を削除', '確認\n説明用の登録項目\n登録情報を削除しますか？\n実ファイルは残します。', [('いいえ', None), ('はい', True)], 'confirmation'),
                ('実ファイルを削除', '確認\n説明用のファイル\nこの実ファイルを完全に削除しますか？', [('いいえ', None), ('はい', True)], 'confirmation'),
                ('管理対象処理の強制停止', '確認\n通常中止の完了を確認できていません。\nこの処理と、この処理が起動した子プロセスを強制停止します。\n途中のファイルが残る場合があります。既存成果物と画面の未保存入力は保持します。\nAviUtl2の未保存編集はこの操作では変更しません。\n強制停止しますか？', [('いいえ', None), ('はい', True)], 'confirmation'),
                ('書き出しの強制停止', '通常の中止にまだ応答していません。\nこの書き出しを受け付けたAviUtl2と、そのエンコーダーを強制終了します。\nAviUtl2内の未保存の編集は失われます。', [('強制停止する', 'force'), ('停止を待つ', None)], 'confirmation'),
                ('完成動画の検査を強制停止', '完成動画の確認処理と、そのffprobeだけを強制終了します。\nAviUtl2内の編集は保持します。\n出力ファイルは完成確認済みとして扱いません。', [('強制停止する', 'force'), ('停止を待つ', None)], 'confirmation'),
            ]
            for index, (title, message, choices, severity) in enumerate(prompts, 1):
                filename = f'dialog-{index:02d}.png'
                def record_dialog(filename=filename, title=title):
                    dialog = next(w for w in window.winfo_children() if isinstance(w, tk.Toplevel))
                    settle(window)
                    controls = [w for w in descendants(dialog) if w.winfo_class() == 'TButton']
                    boxes = save_shot(dialog, output / filename, controls)
                    manifest.append(dict(file=filename, title=title, boxes=boxes,
                                         sample='本番ダイアログに説明用メッセージを表示。処理は未実行。'))
                    dialog.destroy()
                window.after(300, record_dialog)
                choose_action(window, title, message, choices, severity=severity)
            preview = Image.new('RGB', (960, 540), '#193557')
            draw = ImageDraw.Draw(preview)
            draw.rectangle((120, 100, 840, 440), fill='#88afcb')
            draw.text((370, 270), 'SAMPLE / NOT AVIUTL2 OUTPUT', fill='#142d4e')
            preview_path = root / 'sample.png'
            preview.save(preview_path)
            dialog = show_image_preview(window, preview_path, '説明用プレビュー',
                                        actions=(('ミックス音声を試聴', lambda: None),))
            settle(window)
            boxes = save_shot(dialog, output / 'preview.png',
                              [w for w in descendants(dialog) if w.winfo_class() == 'TButton'])
            manifest.append(dict(file='preview.png', title='画像・音声プレビュー', boxes=boxes,
                                 sample='説明用の図形画像。AviUtl2の描画結果ではありません。'))
            dialog.destroy()
            (output.parent / 'screens.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
            print(f'Captured {len(manifest)} app screens in {output}')
        finally:
            window.destroy()


if __name__ == '__main__':
    main()
