"""One palette for action roles across work pages and application dialogs."""

import tkinter as tk
from tkinter import font, ttk


PRIMARY_ACTIONS = {
    '取得・情報表示', 'ローカル動画を登録', '人物を登録', '動画の対象話者に設定',
    '試聴区間を作成', '対象発話を文字起こし・別版保存', '候補を生成して別版保存',
    '解析なしで区間を手動作成', '新しい編集を作成', '字幕をAviUtl2へ追加',
    '画面設定をAviUtl2へ渡す', '選択字幕を別版保存', '配置をAviUtl2へ適用・プレビュー',
    '再集計して別版保存', '保存', '完成動画を書き出す', '動画を保管…', '保管物を展開…',
}
DANGER_ACTIONS = {'登録情報を削除…', '実ファイルを選んで削除…', '未適用入力を破棄',
                  '登録語から削除', '除外語から削除', '強制停止…', '実行中の処理を強制停止…'}


def configure_theme(window):
    window.configure(background='#f5f9ff')
    style = ttk.Style(window)
    style.theme_use('clam')
    style.configure('.', background='#f5f9ff', foreground='#142d4e')
    style.configure('TNotebook', background='#f5f9ff', borderwidth=1)
    style.configure('TNotebook.Tab', padding=(8, 4))
    style.map('TNotebook.Tab', background=[('selected', '#dceaff')], foreground=[('selected', '#103f84')])
    family = font.nametofont('TkDefaultFont').actual('family')
    size = font.nametofont('TkDefaultFont').actual('size')
    style.configure('Heading.TLabel', font=(family, size, 'bold'))
    style.configure('TButton', padding=(7, 4), background='#e7eef7', foreground='#142d4e')
    for name, background, foreground in (
        ('Primary.TButton', '#1859ad', '#ffffff'),
        ('Danger.TButton', '#ab2638', '#ffffff'),
        ('TButton', '#e7eef7', '#142d4e')):
        style.configure(name, background=background, foreground=foreground)
        style.map(name, background=[('disabled', '#e1e5eb'), ('pressed', '#c8d6e7'),
                                   ('active', '#d4e5fb' if name == 'TButton' else background)],
                  foreground=[('disabled', '#677489'), ('pressed', '#142d4e')])
    style.configure('TEntry', fieldbackground='#ffffff', bordercolor='#7c98bc')
    style.map('TEntry', fieldbackground=[('disabled', '#edf0f5')], foreground=[('disabled', '#677489')])
    style.configure('TCombobox', fieldbackground='#ffffff', bordercolor='#7c98bc')
    style.map('TCombobox', fieldbackground=[('readonly', '#ffffff'), ('disabled', '#edf0f5')])
    style.configure('Vertical.TScrollbar', background='#c3d6ee', troughcolor='#edf4ff')


def apply_widget_roles(root):
    for widget in root.winfo_children():
        if isinstance(widget, ttk.Button):
            caption = widget.cget('text')
            if caption in PRIMARY_ACTIONS:
                widget.configure(style='Primary.TButton')
            elif caption in DANGER_ACTIONS:
                widget.configure(style='Danger.TButton')
        elif isinstance(widget, tk.Button):
            primary = widget.cget('text') in PRIMARY_ACTIONS
            widget.configure(background='#1859ad' if primary else '#e7eef7',
                             foreground='#ffffff' if primary else '#142d4e',
                             activebackground='#d4e5fb', activeforeground='#142d4e',
                             disabledforeground='#677489', relief='flat', padx=7, pady=4)
        elif widget.winfo_class() in ('Entry', 'Text', 'Listbox'):
            widget.configure(background='#ffffff', foreground='#142d4e',
                             selectbackground='#1859ad', selectforeground='#ffffff',
                             highlightbackground='#7c98bc', highlightcolor='#1859ad', highlightthickness=1)
            if isinstance(widget, (tk.Listbox, tk.Entry)):
                widget.configure(disabledforeground='#677489')
        apply_widget_roles(widget)
