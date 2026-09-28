"""Bounded native application prompts and whole-image previews."""

import math
import tkinter as tk
from tkinter import ttk

from .responsive_ui import ActionRow
from .window_preferences import work_area


def fit_dialog(dialog, parent, *, width=None, height=None):
    dialog.update_idletasks()
    area = getattr(parent.winfo_toplevel(), 'display_area', None) or work_area(parent)
    width = min(width or dialog.winfo_reqwidth(), round(area.width * .95))
    height = min(height or dialog.winfo_reqheight(), round(area.height * .95))
    x = max(area.x, min(parent.winfo_rootx() + (parent.winfo_width() - width) // 2,
                        area.x + area.width - width))
    y = max(area.y, min(parent.winfo_rooty() + (parent.winfo_height() - height) // 2,
                        area.y + area.height - height))
    dialog.geometry(f'{width}x{height}{x:+d}{y:+d}')
    dialog.maxsize(area.width, area.height)
    return area


def choose_action(parent, title, message, choices, *, severity='confirmation'):
    """Keep actions outside the internally scrolling message; close means return."""
    dialog = tk.Toplevel(parent)
    dialog.withdraw()
    dialog.title(title)
    dialog.transient(parent.winfo_toplevel())
    dialog.columnconfigure(0, weight=1)
    dialog.rowconfigure(0, weight=1)
    content = ttk.Frame(dialog, padding=12)
    content.grid(row=0, column=0, sticky='nsew')
    background = {'error': '#fbe7e9', 'warning': '#fff0c7', 'confirmation': '#fff0c7',
                  'info': '#edf4ff'}[severity]
    text = tk.Text(content, width=48, height=min(8, message.count('\n') + max(2, len(message) // 40)),
                   wrap='word', relief='flat', font='TkDefaultFont', background=background, foreground='#142d4e')
    bar = ttk.Scrollbar(content, command=text.yview)
    bar.pack(side='right', fill='y')
    text.configure(yscrollcommand=bar.set)
    text.pack(fill='both', expand=True)
    text.insert('1.0', message)
    text.configure(state='disabled')
    result = [None]
    def selected(value):
        result[0] = value
        dialog.destroy()
    actions = ActionRow(dialog, padding=8)
    actions.grid(row=1, column=0, sticky='ew')
    for label, value in choices:
        ttk.Button(actions, text=label, command=lambda item=value: selected(item),
                   style='Danger.TButton' if value in ('force', 'discard', True) else 'TButton').pack(side='left')
    dialog.protocol('WM_DELETE_WINDOW', lambda: selected(None))
    dialog.bind('<Escape>', lambda e: selected(None))
    # ActionRow receives its final width only after the dialog is mapped. Reserve
    # enough space even if the actions wrap, so short messages cannot be squeezed
    # down to a few pixels when that row subsequently grows.
    dialog.update_idletasks()
    action_height = sum(child.winfo_reqheight() + 4 for child in actions.winfo_children()) + 16
    fit_dialog(dialog, parent, height=content.winfo_reqheight() + action_height)
    dialog.deiconify()
    dialog.grab_set()
    dialog.wait_window()
    return result[0]


def show_image_preview(parent, path, title, *, actions=(), on_close=None):
    source = tk.PhotoImage(master=parent, file=str(path))
    dialog = tk.Toplevel(parent)
    dialog.withdraw()
    dialog.title(title)
    dialog.columnconfigure(0, weight=1)
    dialog.rowconfigure(0, weight=1)
    area = getattr(parent.winfo_toplevel(), 'display_area', None) or work_area(parent)
    body = ttk.Frame(dialog)
    body.grid(row=0, column=0, sticky='nsew')
    body.grid_propagate(False)
    label = ttk.Label(body, anchor='center')
    label.pack(fill='both', expand=True)
    def resize(event):
        factor = max(1, math.ceil(source.width() / max(1, event.width)),
                        math.ceil(source.height() / max(1, event.height)))
        label.picture = source.subsample(factor)
        label.configure(image=label.picture)
    body.bind('<Configure>', resize)
    buttons = ActionRow(dialog, padding=6)
    buttons.grid(row=1, column=0, sticky='ew')
    def close():
        if on_close is not None:
            on_close()
        dialog.destroy()
    for caption, command in actions:
        ttk.Button(buttons, text=caption, command=command).pack(side='left')
    ttk.Button(buttons, text='閉じる', command=close).pack(side='left')
    dialog.protocol('WM_DELETE_WINDOW', close)
    dialog.bind('<Escape>', lambda e: close())
    fit_dialog(dialog, parent, width=min(source.width() + 16, round(area.width * .85)),
               height=min(source.height() + 100, round(area.height * .85)))
    dialog.deiconify()
    return dialog


class MessageDialogs:
    """Adapter with the existing message-dialog interface and bounded content."""
    def _show(self, title, message, severity, *, parent=None, **options):
        parent = parent or tk._default_root
        if parent is None:
            raise RuntimeError('Create the application window before showing a message')
        marker = {'error': 'エラー', 'warning': '警告', 'info': '案内'}[severity]
        return choose_action(parent, title, marker + '\n' + str(message),
                             (('閉じる', 'ok'),), severity=severity)

    def showerror(self, title, message, **options):
        return self._show(title, message, 'error', **options)

    def showwarning(self, title, message, **options):
        return self._show(title, message, 'warning', **options)

    def showinfo(self, title, message, **options):
        return self._show(title, message, 'info', **options)

    def askyesno(self, title, message, *, parent=None, **options):
        parent = parent or tk._default_root
        if parent is None:
            raise RuntimeError('Create the application window before showing a confirmation')
        return choose_action(parent, title, '確認\n' + str(message),
                             (('いいえ', None), ('はい', True))) is True


messagebox = MessageDialogs()
