"""Capture only this app's rendered X11 windows, using temporary sample data.

Run in WSL: .venv/bin/python scripts/manual_capture.py
Documentation-only dependencies: Pillow. Never opens the user's data folder.
"""
import ctypes
import os
from tkinter import font as tkfont
import json
import sys
import subprocess
import tempfile
import time
from pathlib import Path
from unittest.mock import patch
import tkinter as tk

from PIL import Image, ImageDraw, ImageFont
import colorsys

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
    timer = window.after(450, window.quit)
    try:
        window.mainloop()
    finally:
        try:
            window.after_cancel(timer)
        except tk.TclError:
            pass
    window.update_idletasks()


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



def fully_visible(control, window):
    if not control.winfo_viewable() or control.winfo_width()<=1 or control.winfo_height()<=1:return False
    left,top=control.winfo_rootx(),control.winfo_rooty()
    right,bottom=left+control.winfo_width(),top+control.winfo_height()
    ancestor=control.master
    while ancestor is not None:
        if not ancestor.winfo_viewable():return False
        x,y=ancestor.winfo_rootx(),ancestor.winfo_rooty()
        if left<x or top<y or right>x+ancestor.winfo_width() or bottom>y+ancestor.winfo_height():return False
        if ancestor is window:return True
        ancestor=ancestor.master
    return control is window

def apply_label_overrides(records):
    path=ROOT/'docs'/'manual'/'manual_content.json'
    content=json.loads(path.read_text(encoding='utf-8')) if path.is_file() else {}
    metadata=content.get('controls',{})
    result=[]
    for record in records:
        value=dict(record)
        override=metadata.get(value['control_id'],{}).get('label')
        if override:
            if value['widget_class'] in ('Button','TButton','Checkbutton','TCheckbutton'):
                actual=str(value['widget'].cget('text'))
                if override!=actual:raise RuntimeError(f"Button label differs from UI: {value['control_id']}")
            value['label']=override
        result.append(value)
    return result

def annotation_font(size):
    paths=[Path('/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc'), Path('/mnt/c/Windows/Fonts/meiryo.ttc')]
    paths+=sorted(Path('/usr/share/fonts').rglob('*Sans*CJK*Regular*'))
    for path in paths:
        if path.is_file():
            try:return ImageFont.truetype(str(path),size)
            except OSError:pass
    raise RuntimeError('A Japanese font is required for readable annotations')

def wrapped_label(label,font,width):
    lines,current=[],''
    for char in label:
        if char=='\n':
            lines.append(current);current=''
        elif current and font.getlength(current+char)>width:
            lines.append(current);current=char
        else:current+=char
    if current or not lines:lines.append(current)
    return lines

def save_shot(widget,destination,highlights):
    records=apply_label_overrides(highlights)
    if not records:raise RuntimeError(f'No controls: {destination}')
    for record in records:
        if not fully_visible(record['widget'],widget):raise RuntimeError(f"Control is clipped: {record['control_id']}")
    original=capture(widget)
    font,badge_font=annotation_font(16),annotation_font(18)
    gutter=400
    rows=[];next_y=42
    for record in records:
        lines=wrapped_label(record['label'],font,gutter-74)
        rows.append((next_y,lines));next_y+=max(30,len(lines)*23+8)
    image=Image.new('RGB',(original.width+gutter,max(original.height,next_y+16)),'#f4f8ff')
    image.paste(original,(0,0))
    draw=ImageDraw.Draw(image)
    draw.line((original.width,0,original.width,image.height),fill='#c8d7e6',width=2)
    draw.text((original.width+16,12),'番号と操作箇所',fill='#173e69',font=font)
    boxes=[]
    for number,(record,(badge_y,lines)) in enumerate(zip(records,rows),1):
        control=record['widget']
        x,y=control.winfo_rootx()-widget.winfo_rootx(),control.winfo_rooty()-widget.winfo_rooty()
        actual=[x,y,x+control.winfo_width(),y+control.winfo_height()]
        bounds=[max(0,x-2),max(0,y-2),min(original.width-1,actual[2]+2),min(original.height-1,actual[3]+2)]
        color=tuple(round(v*255) for v in colorsys.hsv_to_rgb(((number-1)*0.61803398875)%1,.77,.68))
        draw.rectangle(bounds,outline=color,width=2)
        badge_x=original.width+16
        badge_bounds=[badge_x,badge_y,badge_x+32,badge_y+26]
        anchor_y=min(original.height-1,bounds[3]+2)
        points=[(bounds[2],bounds[3]),(bounds[2],anchor_y),(original.width+7,anchor_y),
                (original.width+7,badge_y+13),(badge_x,badge_y+13)]
        draw.line(points,fill=color,width=1);draw.rectangle(badge_bounds,fill=color)
        label=str(number)
        draw.text((badge_x+(32-badge_font.getlength(label))/2,badge_y+2),label,fill='white',font=badge_font)
        for i,line in enumerate(lines):draw.text((badge_x+44,badge_y+i*23),line,fill='#172f4a',font=font)
        boxes.append({**public_record(record),'number':number,'bounds':bounds,'control_bounds':actual,
                      'badge_bounds':badge_bounds,'leader_points':[list(p) for p in points]})
    image.save(destination)
    return boxes

def overview_records(window):
    widgets=list(descendants(window))
    def button(caption):return next(w for w in widgets if w.winfo_class() in ('Button','TButton') and str(w.cget('text'))==caption)
    captions=['フォルダを選択・切り替え','場所を確認','小','中','大',*WORKS.keys(),
              '実行中の処理を中止','実行中の処理を強制停止…']
    records=[dict(control_id=f'overview-button-{i:02d}',label=caption,control_index=i,
                  widget_class=button(caption).winfo_class(),widget=button(caption)) for i,caption in enumerate(captions,1)]
    notebook=next(w for w in widgets if w.winfo_class()=='TNotebook')
    page=window.nametowidget(notebook.select())
    selector=next(w for w in descendants(page) if w.winfo_class()=='TCombobox' and str(w.cget('textvariable'))==str(page.view))
    records.append(dict(control_id='overview-view',label='表示',control_index=len(records)+1,widget_class='TCombobox',widget=selector))
    role=page.view.get() if page.view.get() in page.controls else '操作'
    for i,caption in enumerate(('◁','▷'),1):
        control=next(w for w in descendants(page.controls[role][0]) if w.winfo_class()=='TButton' and str(w.cget('text'))==caption)
        records.append(dict(control_id=f'overview-item-step-{i:02d}',label=caption,control_index=len(records)+1,widget_class='TButton',widget=control))
    return records

def button_records(screen_id,controls):
    return [dict(control_id=f'{screen_id}-button-{i:02d}',label=str(c.cget('text')),control_index=i,
                 widget_class=c.winfo_class(),widget=c) for i,c in enumerate(controls,1)]

def capture_section_pages(window,output,page,work,tab_title,role,title):
    container=page.sections[role][title]
    screen_id=SCREEN_IDS[title]
    registry=control_records(screen_id,container,title,page.controls[role][1])
    canvas=getattr(container,'canvas',None)
    if canvas is not None:canvas.yview_moveto(0)
    settle(window)
    offsets=[0]
    if canvas is not None:
        total=max(canvas.winfo_height(),canvas.bbox('all')[3])
        maximum=max(0,total-canvas.winfo_height())
        offsets=list(range(0,maximum+1,max(1,canvas.winfo_height()-60)))
        if offsets[-1]!=maximum:offsets.append(maximum)
    covered,manifest=set(),[]
    substantive={r['control_id'] for r in registry if r['widget_class'] not in ('TScrollbar','Scrollbar') and not r['control_id'].endswith('-selector')}
    for offset in offsets:
        if canvas is not None:canvas.yview_moveto(offset/total);settle(window)
        visible=[r for r in registry if fully_visible(r['widget'],window)]
        new={r['control_id'] for r in visible}-covered
        if not manifest or new&substantive:
            visible=[r for r in visible if r['control_id'] in new or r['control_id'].endswith('-selector') or r['widget_class'] in ('TScrollbar','Scrollbar')]
            index=len(manifest)+1
            filename=screen_id+('' if index==1 else f'-page{index:02d}')+'.png'
            boxes=save_shot(window,output/filename,visible)
            manifest.append(dict(screen_id=screen_id,file=filename,work=work,tab=tab_title,role=role,title=title,
                                 page_index=index,boxes=boxes,captions=[b['label'] for b in boxes],
                                 sample='一時データ。ネット取得・人物照合・Whisper・AviUtl2送信は未実行。'))
            covered.update(r['control_id'] for r in visible)
    missing={r['control_id'] for r in registry}-covered
    if missing:raise RuntimeError(f'Controls were never fully visible: {screen_id}: {sorted(missing)}')
    for entry in manifest:entry['page_count']=len(manifest)
    if canvas is not None:canvas.yview_moveto(0)
    print('Captured '+screen_id,flush=True)
    return manifest


SCREEN_IDS = dict(zip([
'URL・取得','ローカル動画','取得結果','登録済み動画','形式・品質と取得設定',
'範囲を指定して書き出す','人物と対象動画','試聴・判定・再表示','対象話者の文字起こし',
'人物一覧','試聴区間・文字起こし','人物・参照音声の登録','発言の修正',
'集計条件','登録語・除外語','頻出語一覧','発話一覧','候補と保存版','区間を修正・試聴',
'編集用動画を作成','フレーム境界を確認','切り出し区間','編集用動画の順番','区間の境界・採否',
'画面設定とプレビュー','字幕を修正','編集用字幕','画面・字幕の配置',
'追加・適用・プレビュー','補助素材一覧','素材の配置・音声設定',
'保存・書き出し','対象プロジェクト','処理結果','書き出し設定',
'保存済み一覧','CSV本文','登録情報を管理','動画を保管・展開','ログの整理','登録一覧','保管・展開結果'
], """
download-url download-local download-results registered-videos download-settings trimming-range
speaker-target review-actions speaker-transcribe registered-people review-results speaker-registration review-edit
word-settings word-dictionary word-totals word-utterances segment-candidates segment-actions compose-actions
frame-boundaries segment-results compose-order segment-settings layout-actions subtitle-actions subtitle-results
layout-settings supporting-actions supporting-results supporting-settings save-export-actions project-target
save-export-results export-settings saved-results saved-csv management-actions archive-actions log-actions
management-results archive-results""".split()))
CONTROL_KINDS = {
'Button':'button','TButton':'button','Checkbutton':'check','TCheckbutton':'check',
'Entry':'entry','TEntry':'entry','TCombobox':'choice','Listbox':'list','Text':'text',
'Scale':'slider','TScale':'slider','Canvas':'preview','Scrollbar':'scrollbar','TScrollbar':'scrollbar'}
DIALOG_SPECS = [
('dialog-location','場所を確認',['閉じる']),
('dialog-error','エラー表示',['閉じる']),
('dialog-warning','警告表示',['閉じる']),
('dialog-short','ショート条件外',['編集・設定を直す','通常の動画として書き出す']),
('dialog-unsaved-export','未保存の編集・書き出し前',['保存して書き出す','戻る']),
('dialog-unsaved-close','未保存の編集・終了時',['保存する','破棄する','戻る']),
('dialog-screen','画面を選択',['いいえ','はい']),
('dialog-registration-delete','登録情報を削除',['いいえ','はい']),
('dialog-file-delete','実ファイルを削除',['いいえ','はい']),
('dialog-process-force','管理対象処理の強制停止',['いいえ','はい']),
('dialog-export-force','書き出しの強制停止',['強制停止する','停止を待つ']),
('dialog-verification-force','完成動画の検査を強制停止',['強制停止する','停止を待つ'])]

def associated_label(control, title):
    kind=control.winfo_class()
    if kind in ('Button','TButton','Checkbutton','TCheckbutton'):
        return str(control.cget('text'))
    if kind in ('Scrollbar','TScrollbar'):
        direction='縦' if str(control.cget('orient'))=='vertical' else '横'
        return f'{title}：{direction}スクロール'
    if kind=='Canvas':return '動画プレビュー'
    if kind in ('Scale','TScale'):return '動画の再生位置'
    node=control
    for _ in range(3):
        parent=node.master
        if parent is None:break
        siblings=parent.winfo_children()
        if node.winfo_manager()=='grid':
            info=node.grid_info()
            row,column=int(info.get('row',0)),int(info.get('column',0))
            labels=[w for w in siblings if w.winfo_class() in ('Label','TLabel')
                    and w.winfo_manager()=='grid'
                    and int(w.grid_info().get('row',-1))==row
                    and int(w.grid_info().get('column',999))<column]
            if labels:
                label=str(labels[-1].cget('text')).strip()
                if label:return label
        before=siblings[:siblings.index(node)]
        labels=[w for w in before if w.winfo_class() in ('Label','TLabel')]
        if labels:
            label=str(labels[-1].cget('text')).strip()
            if label and not label.startswith('/') and len(label)<100:return label
        node=parent
    if kind=='Listbox':return title if '一覧' in title else f'{title}の一覧'
    if kind=='Text':return f'{title}の本文'
    return f'{title}の選択欄' if kind=='TCombobox' else f'{title}の入力欄'

def control_records(screen_id,container,title,selector=None):
    records=[]
    if selector is not None:
        records.append(dict(control_id=screen_id+'-selector',label='表示項目',
                            control_index=0,widget_class=selector.winfo_class(),widget=selector))
    counters={}
    for control in descendants(container):
        widget_class=control.winfo_class()
        kind=CONTROL_KINDS.get(widget_class)
        if not kind:continue
        if widget_class=='Canvas' and control.master.__class__.__name__!='TrimmingPanel':continue
        counters[kind]=counters.get(kind,0)+1
        records.append(dict(control_id=f'{screen_id}-{kind}-{counters[kind]:02d}',
                            label=associated_label(control,title),control_index=len(records),
                            widget_class=widget_class,widget=control))
    if not records or (len(records)==1 and selector is not None):
        records.append(dict(control_id=screen_id+'-region-01',label=title,
                            control_index=len(records),widget_class='Region',widget=container))
    return records

def public_record(record):
    return {key:value for key,value in record.items() if key!='widget'}

def write_control_inventory(window):
    all_widgets=list(descendants(window))
    notebook=next(w for w in all_widgets if w.winfo_class()=='TNotebook')
    def button(caption):
        return next(w for w in all_widgets if w.winfo_class() in ('Button','TButton')
                    and str(w.cget('text'))==caption)
    inventory=[]
    captions=['フォルダを選択・切り替え','場所を確認','小','中','大',*WORKS.keys(),
              '実行中の処理を中止','実行中の処理を強制停止…']
    overview=[dict(control_id=f'overview-button-{index:02d}',label=caption,control_index=index,
                   widget_class=button(caption).winfo_class()) for index,caption in enumerate(captions,1)]
    overview.append(dict(control_id='overview-view',label='表示',control_index=len(overview)+1,widget_class='TCombobox'))
    for index,caption in enumerate(('◁','▷'),1):
        overview.append(dict(control_id=f'overview-item-step-{index:02d}',label=caption,
                             control_index=len(overview)+1,widget_class='TButton'))
    inventory.append(dict(screen_id='overview',title='全体の操作',controls=overview))
    for work,tabs in WORKS.items():
        button(work).invoke()
        for tab_title in tabs:
            tab=next(t for t in notebook.tabs() if notebook.tab(t,'text')==tab_title)
            notebook.select(tab)
            page=window.nametowidget(tab)
            for role,sections in page.sections.items():
                for title,container in sections.items():
                    page.show(title);settle(window)
                    screen_id=SCREEN_IDS[title]
                    records=control_records(screen_id,container,title,page.controls[role][1])
                    inventory.append(dict(screen_id=screen_id,work=work,tab=tab_title,role=role,title=title,
                                          controls=[public_record(record) for record in records]))
    for screen_id,title in [('process-running','実行中'),('process-stopping','停止待ち・強制停止選択可能'),('process-stopped','停止完了')]:
        inventory.append(dict(screen_id=screen_id,title=title,controls=[
            dict(control_id=f'{screen_id}-button-{index:02d}',label=caption,control_index=index,widget_class='TButton')
            for index,caption in enumerate(('実行中の処理を中止','実行中の処理を強制停止…'),1)]))
    for screen_id,title,captions in DIALOG_SPECS:
        inventory.append(dict(screen_id=screen_id,title=title,controls=[
            dict(control_id=f'{screen_id}-button-{index:02d}',label=caption,control_index=index,widget_class='TButton')
            for index,caption in enumerate(captions,1)]))
    inventory.append(dict(screen_id='preview',title='画像・音声プレビュー',controls=[
        dict(control_id=f'preview-button-{index:02d}',label=caption,control_index=index,widget_class='TButton')
        for index,caption in enumerate(('この位置から音声を試聴（最大5秒）','試聴を停止','閉じる'),1)]))
    destination=ROOT/'docs'/'manual'/'control-inventory.json'
    destination.write_text(json.dumps(inventory,ensure_ascii=False,indent=2),encoding='utf-8')
    print(f'Inventory: {len(inventory)} screens / {sum(len(row["controls"]) for row in inventory)} controls')

def main():
    output = ROOT / 'docs' / 'manual' / 'images'
    output.mkdir(parents=True, exist_ok=True)
    manifest = []
    with tempfile.TemporaryDirectory(prefix='clipchannel-manual-') as temporary:
        root = Path(temporary)
        font_config=root/'fonts.conf'
        font_config.write_text('<fontconfig><include ignore_missing="yes">/etc/fonts/fonts.conf</include>'
                               '<dir>/mnt/c/Windows/Fonts</dir><cachedir>'+str(root/'font-cache')+'</cachedir></fontconfig>')
        os.environ['FONTCONFIG_FILE']=str(font_config)
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
        for name in tkfont.names(window):
            tkfont.nametofont(name, root=window).configure(family='Meiryo')
        window.geometry('1360x850+30+30')
        try:
            settle(window)
            if '--inventory-only' in sys.argv:
                write_control_inventory(window)
                return
            all_widgets = list(descendants(window))
            notebook = next(w for w in all_widgets if w.winfo_class() == 'TNotebook')
            def button(caption):
                return next(w for w in all_widgets if w.winfo_class() in ('Button', 'TButton')
                            and w.cget('text') == caption)
            button('動画を準備').invoke()
            notebook.select(next(t for t in notebook.tabs() if notebook.tab(t,'text')=='取得・媒体操作'))
            window.nametowidget(notebook.select()).show('URL・取得')
            settle(window)
            boxes=save_shot(window,output/'overview.png',overview_records(window))
            manifest.append(dict(screen_id='overview',file='overview.png',title='全体の操作',page_index=1,page_count=1,
                                 boxes=boxes,captions=[b['label'] for b in boxes],
                                 sample='一時データの本番UI。ネット取得・解析モデル・AviUtl2送信は未実行。'))
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
            for work,tabs in WORKS.items():
                button(work).invoke()
                for tab_title in tabs:
                    tab=next(t for t in notebook.tabs() if notebook.tab(t,'text')==tab_title)
                    notebook.select(tab)
                    page=window.nametowidget(tab)
                    for role,sections in page.sections.items():
                        for title,container in sections.items():
                            if title=='字幕を修正':
                                page.show('編集用字幕');settle(window)
                                subtitle_listing.selection_set(0)
                                subtitle_listing.event_generate('<<ListboxSelect>>')
                            page.show(title)
                            if title in ('編集用字幕','試聴区間・文字起こし','切り出し区間','頻出語一覧'):
                                listing_widget=next(w for w in descendants(container) if w.winfo_class()=='Listbox')
                                if listing_widget.size():
                                    listing_widget.selection_set(0)
                                    listing_widget.event_generate('<<ListboxSelect>>')
                            settle(window)
                            manifest.extend(capture_section_pages(window,output,page,work,tab_title,role,title))
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
                screen_id=filename.removesuffix('.png')
                controls=[button('実行中の処理を中止'),button('実行中の処理を強制停止…')]
                boxes=save_shot(window,output/filename,button_records(screen_id,controls))
                manifest.append(dict(screen_id=screen_id,file=filename,title=title,page_index=1,page_count=1,
                                     boxes=boxes,captions=[b['label'] for b in boxes],
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
            dialog_ids={title:screen_id for screen_id,title,_ in DIALOG_SPECS}
            for title,message,choices,severity in prompts:
                screen_id=dialog_ids[title]
                filename=screen_id+'.png'
                errors=[]
                def record_dialog(filename=filename,title=title,screen_id=screen_id):
                    dialog=next(w for w in window.winfo_children() if isinstance(w,tk.Toplevel))
                    try:
                        settle(window)
                        controls=[w for w in descendants(dialog) if w.winfo_class()=='TButton']
                        boxes=save_shot(dialog,output/filename,button_records(screen_id,controls))
                        manifest.append(dict(screen_id=screen_id,file=filename,title=title,page_index=1,page_count=1,
                                             boxes=boxes,captions=[b['label'] for b in boxes],
                                             sample='本番ダイアログに説明用メッセージを表示。処理は未実行。'))
                    except Exception as error:errors.append(error)
                    finally:dialog.destroy()
                window.after(300,record_dialog)
                choose_action(window,title,message,choices,severity=severity)
                if errors:raise errors[0]
            preview = Image.new('RGB', (960, 540), '#193557')
            draw = ImageDraw.Draw(preview)
            draw.rectangle((120, 100, 840, 440), fill='#88afcb')
            draw.text((370, 270), 'SAMPLE / NOT AVIUTL2 OUTPUT', fill='#142d4e')
            preview_path = root / 'sample.png'
            preview.save(preview_path)
            dialog=show_image_preview(window,preview_path,'説明用プレビュー',actions=(
                ('この位置から音声を試聴（最大5秒）',lambda:None),('試聴を停止',lambda:None)))
            settle(window)
            controls=[w for w in descendants(dialog) if w.winfo_class()=='TButton']
            boxes=save_shot(dialog,output/'preview.png',button_records('preview',controls))
            manifest.append(dict(screen_id='preview',file='preview.png',title='画像・音声プレビュー',page_index=1,page_count=1,
                                 boxes=boxes,captions=[b['label'] for b in boxes],
                                 sample='説明用の図形画像。AviUtl2の描画結果ではなく、試聴ボタンも未実行です。'))
            dialog.destroy()
            (output.parent / 'screens.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
            print(f'Captured {len(manifest)} app screens in {output}')
        finally:
            window.destroy()


if __name__ == '__main__':
    main()