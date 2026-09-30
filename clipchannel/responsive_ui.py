"""Persistent work navigation; pages are hidden rather than reconstructed."""

import tkinter as tk
from tkinter import font, ttk


WORKS = {
    '動画を準備': ('取得・媒体操作',),
    '動画をトリミング': ('動画をトリミング',),
    '解析・切り出し': ('人物・参照音声', '頻出語', '切り出し区間'),
    '編集・書き出し': ('画面・字幕', '補助素材', '保存・書き出し'),
    '保存結果を確認': ('保存済み情報',),
    'データを管理': ('管理・保管',),
}


class ScrollListbox(tk.Listbox):
    def __init__(self, parent, **kwargs):
        self.container = ttk.Frame(parent)
        self.container.columnconfigure(0, weight=1)
        self.container.rowconfigure(0, weight=1)
        kwargs.setdefault('width', 1)
        kwargs.setdefault('exportselection', False)
        super().__init__(self.container, **kwargs)
        self.grid(row=0, column=0, sticky='nsew')
        vertical = ttk.Scrollbar(self.container, command=self.yview)
        horizontal = ttk.Scrollbar(self.container, orient='horizontal', command=self.xview)
        vertical.grid(row=0, column=1, sticky='ns')
        horizontal.grid(row=1, column=0, sticky='ew')
        self.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)

    def pack(self, **kwargs):
        self.container.pack(**kwargs)


class ScrollText(tk.Text):
    def __init__(self, parent, **kwargs):
        self.container = ttk.Frame(parent)
        self.container.columnconfigure(0, weight=1)
        self.container.rowconfigure(0, weight=1)
        super().__init__(self.container, **kwargs)
        self.grid(row=0, column=0, sticky='nsew')
        vertical = ttk.Scrollbar(self.container, command=self.yview)
        vertical.grid(row=0, column=1, sticky='ns')
        self.configure(yscrollcommand=vertical.set, wrap='word')

    def pack(self, **kwargs):
        self.container.pack(**kwargs)


class VariableText(ScrollText):
    def __init__(self, parent, variable):
        super().__init__(parent, width=1, height=1, state='disabled', font='TkDefaultFont')
        self.variable = variable
        self._trace = variable.trace_add('write', self._update)
        self.bind('<Destroy>', self._destroy)
        self._update()

    def _update(self, *_args):
        self.configure(state='normal')
        self.delete('1.0', 'end')
        self.insert('1.0', self.variable.get())
        self.configure(state='disabled')

    def _destroy(self, event):
        if event.widget is self:
            self.variable.trace_remove('write', self._trace)


class WrappedLabel(ttk.Label):
    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        if not kwargs.get('width'):
            parent.bind('<Configure>', self._wrap, add='+')

    def _wrap(self, event):
        self.configure(wraplength=max(40, event.width - 16))


class PathLabel(ttk.Label):
    def __init__(self, parent, variable):
        super().__init__(parent, width=1)
        self.variable = variable
        self._trace = variable.trace_add('write', self._update_text)
        self.bind('<Configure>', self._update_text)
        self.bind('<Destroy>', self._destroy)

    def _update_text(self, *_args):
        value = self.variable.get()
        metrics = font.nametofont('TkDefaultFont')
        width = max(1, self.winfo_width() - 12)
        if metrics.measure(value) <= width:
            text = value
        else:
            count = 0
            while count < len(value) and metrics.measure(value[:count + 1] + '…') < width:
                count += 1
            text = value[:count] + '…'
        self.configure(text=text)

    def _destroy(self, event):
        if event.widget is self:
            self.variable.trace_remove('write', self._trace)


class ScrollRegion(ttk.Frame):
    """Scroll only an explicitly expanded detail region, never a page."""
    def __init__(self, parent):
        super().__init__(parent)
        self.canvas = tk.Canvas(self, highlightthickness=0, background='#f5f9ff')
        bar = ttk.Scrollbar(self, command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=bar.set)
        bar.pack(side='right', fill='y')
        self.canvas.pack(fill='both', expand=True)
        self.content = ttk.Frame(self.canvas, padding=6)
        item = self.canvas.create_window(0, 0, window=self.content, anchor='nw')
        self.content.bind('<Configure>', lambda e: self.canvas.configure(scrollregion=self.canvas.bbox('all')))
        self.canvas.bind('<Configure>', lambda e: self.canvas.itemconfigure(item, width=e.width))
        self.canvas.bind('<MouseWheel>', lambda e: self.canvas.yview_scroll(-int(e.delta / 120), 'units'))
        self.canvas.bind('<Button-4>', lambda e: self.canvas.yview_scroll(-1, 'units'))
        self.canvas.bind('<Button-5>', lambda e: self.canvas.yview_scroll(1, 'units'))


class ActionRow(ttk.Frame):
    """Wrap a group of actions to its allocated width."""
    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        self.pack_propagate(False)
        self.bind('<Configure>', self._arrange)
        self.bind('<Map>', self._arrange)

    def pack(self, **kwargs):
        kwargs.setdefault('fill', 'x')
        super().pack(**kwargs)

    def _arrange(self, event=None):
        padding = [self.winfo_pixels(value) for value in self.tk.splitlist(self.cget('padding'))]
        if not padding:
            padding = [0]
        left = padding[0]
        top = padding[1] if len(padding) > 1 else left
        right = padding[2] if len(padding) > 2 else left
        bottom = padding[3] if len(padding) > 3 else top
        width = max(1, self.winfo_width() - left - right)
        y, used, row_height = 2, 0, 0
        for child in self.winfo_children():
            if child.winfo_manager() == 'pack':
                child.pack_forget()
        for child in self.winfo_children():
            required = min(child.winfo_reqwidth() + 8, width)
            if used and used + required > width:
                y, used, row_height = y + row_height + 4, 0, 0
            child.place(x=used + 3, y=y, width=max(1, required - 6), height=child.winfo_reqheight())
            row_height = max(row_height, child.winfo_reqheight())
            used += required
        self.configure(height=y + row_height + 2 + top + bottom)


class ResponsivePage(ttk.Frame):
    """A fixed page with explicit operation, result and detail selection."""
    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        self.sections = {'操作': {}, '結果': {}, '詳細設定': {}}
        self.view = tk.StringVar(value='自動')
        self.choice = {role: tk.StringVar() for role in self.sections}
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)
        toolbar = ttk.Frame(self)
        toolbar.grid(row=0, column=0, sticky='ew')
        ttk.Label(toolbar, text='表示').pack(side='left', padx=4)
        selector = ttk.Combobox(toolbar, values=('操作', '結果', '詳細設定', '自動'),
                                textvariable=self.view, state='readonly', width=9)
        selector.pack(side='left')
        selector.bind('<<ComboboxSelected>>', lambda e: self._render())
        self.choosers = ttk.Frame(self)
        self.choosers.grid(row=1, column=0, sticky='ew', pady=4)
        self.controls = {}
        for role in self.sections:
            line = ttk.Frame(self.choosers)
            line.columnconfigure(1, weight=1)
            ttk.Label(line, text=role).grid(row=0, column=0, padx=4)
            box = ttk.Combobox(line, textvariable=self.choice[role], state='readonly', width=15)
            box.grid(row=0, column=1, sticky='ew')
            box.bind('<<ComboboxSelected>>', lambda e: self._render())
            ttk.Button(line, text='◁', width=2, command=lambda r=role: self._step(r, -1)).grid(row=0, column=2)
            ttk.Button(line, text='▷', width=2, command=lambda r=role: self._step(r, 1)).grid(row=0, column=3)
            self.controls[role] = (line, box)
        self.body = ttk.Frame(self)
        self.body.grid(row=2, column=0, sticky='nsew')
        self.body.grid_propagate(False)
        self.body.rowconfigure(0, weight=1)
        self.slots = [ttk.Frame(self.body), ttk.Frame(self.body)]
        for slot in self.slots:
            slot.grid_propagate(False)
            slot.columnconfigure(0, weight=1)
            slot.rowconfigure(0, weight=1)
        self.body.bind('<Configure>', lambda e: self._render())
        self._rendering = False

    def section(self, title, role='操作'):
        if role == '詳細設定':
            container = ScrollRegion(self.body)
            content = container.content
        else:
            container = content = ttk.Frame(self.body, padding=4)
        self.sections[role][title] = container
        self.controls[role][1].configure(values=tuple(self.sections[role]))
        if not self.choice[role].get():
            self.choice[role].set(title)
        self._render()
        return content

    def show(self, title):
        for role, sections in self.sections.items():
            if title in sections:
                self.choice[role].set(title)
                self.view.set(role)
                self._render()
                return
        raise ValueError(title)

    @property
    def editing_roots(self):
        return tuple(container for sections in self.sections.values() for container in sections.values())

    def _step(self, role, direction):
        names = tuple(self.sections[role])
        if names:
            index = names.index(self.choice[role].get())
            self.choice[role].set(names[(index + direction) % len(names)])
            self._render()

    def _render(self):
        if self._rendering:
            return
        self._rendering = True
        try:
            for sections in self.sections.values():
                for container in sections.values():
                    container.grid_remove()
            for line, _ in self.controls.values():
                line.grid_remove()
            view = self.view.get()
            roles = [view] if view != '自動' else ['操作']
            if view == '自動' and self.body.winfo_width() >= font.nametofont('TkDefaultFont').measure('あ') * 85:
                roles = ['操作', '結果']
            roles = [r for r in roles if self.sections[r]]
            if not roles:
                roles = [r for r in self.sections if self.sections[r]][:1]
            for column in (0, 1):
                self.slots[column].grid_remove()
                self.body.columnconfigure(column, weight=1 if column < len(roles) else 0,
                                          uniform='views' if column < len(roles) else '')
                self.choosers.columnconfigure(column, weight=1 if column < len(roles) else 0)
            for column, role in enumerate(roles):
                self.slots[column].grid(row=0, column=column, sticky='nsew')
                self.controls[role][0].grid(row=0, column=column, sticky='ew')
                name = self.choice[role].get()
                if name in self.sections[role]:
                    self.sections[role][name].grid(in_=self.slots[column], row=0, column=0, sticky='nsew')
        finally:
            self._rendering = False


class Workbench(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent, padding=6)
        self.work = '動画を準備'
        self.selected = {}
        navigation = ttk.Frame(self)
        navigation.pack(side='left', fill='y', padx=(0, 8))
        ttk.Label(navigation, text='作業を選択', style='Heading.TLabel').pack(anchor='w')
        self.current = tk.StringVar(value='選択中: 動画を準備')
        ttk.Label(navigation, textvariable=self.current, wraplength=150).pack(anchor='w', pady=4)
        self.buttons = {}
        for name in WORKS:
            self.buttons[name] = ttk.Button(navigation, text=name,
                command=lambda work=name: self.select_work(work))
            self.buttons[name].pack(fill='x', pady=3)
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill='both', expand=True)

    def select_work(self, work):
        if work not in WORKS:
            raise ValueError(work)
        tabs = self.notebook.tabs()
        current = self.notebook.select()
        if current:
            self.selected[self.work] = current
        self.work = work
        self.current.set('選択中: ' + work)
        allowed = WORKS[work]
        for tab in tabs:
            if self.notebook.tab(tab, 'text') in allowed:
                self.notebook.add(tab)
            else:
                self.notebook.hide(tab)
        remembered = self.selected.get(work)
        visible = [tab for tab in tabs if self.notebook.tab(tab, 'text') in allowed]
        if visible:
            self.notebook.select(remembered if remembered in visible else visible[0])
        for name, button in self.buttons.items():
            button.configure(style='Primary.TButton' if name == work else 'TButton')


class OperationStrip(ttk.Frame):
    """Always-visible status and stop actions for the existing process owners."""
    def __init__(self, parent, status, managed, export):
        super().__init__(parent, padding=6)
        self.status, self.managed, self.export = status, managed, export
        self.columnconfigure(0, weight=1)
        self.summary = tk.Text(self, height=2, width=1, wrap='word', state='disabled',
                               background='#edf4ff', foreground='#142d4e', relief='solid', borderwidth=1)
        self.summary.grid(row=0, column=0, sticky='ew')
        bar = ttk.Scrollbar(self, command=self.summary.yview)
        bar.grid(row=0, column=1, sticky='ns')
        self.summary.configure(yscrollcommand=bar.set)
        actions = ttk.Frame(self)
        actions.grid(row=0, column=2, padx=6)
        self.cancel_button = ttk.Button(actions, text='実行中の処理を中止', command=self.stop)
        self.cancel_button.pack(fill='x')
        self.force_button = ttk.Button(actions, text='実行中の処理を強制停止…', command=self.force, style='Danger.TButton')
        self.force_button.pack(fill='x', pady=2)
        self._last = None
        self._timer = None
        self._tick()
        self.bind('<Destroy>', self._destroy)

    def _destroy(self, event):
        if event.widget is self and self._timer is not None:
            self.after_cancel(self._timer)
            self._timer = None

    def stop(self):
        if self.export.busy:
            self.export.stop()
        else:
            self.managed.stop()
        self.refresh()

    def force(self):
        if self.export.busy:
            self.export.force_stop()
        else:
            self.managed.force()
        self.refresh()

    def refresh(self):
        owner = self.export if self.export.busy else self.managed
        active = self.export.busy or self.managed.active
        text = self.status.get() or '実行中の処理はありません'
        if active:
            text = owner.message.get()
            if self.export.busy:
                text = self.export.process_summary.get() + ' — ' + text
        if text != self._last:
            background = ('#fbe7e9' if '失敗' in text else '#fff0c7' if any(word in text for word in ('停止待ち', '警告', '未確認'))
                          else '#e2f3e7' if any(word in text for word in ('完了', '保存しました')) else '#edf4ff')
            self.summary.configure(background=background)
            self.summary.configure(state='normal')
            self.summary.delete('1.0', 'end')
            self.summary.insert('1.0', text)
            self.summary.configure(state='disabled')
            self._last = text
        self.cancel_button.configure(state='normal' if active and str(owner.cancel_button.cget('state')) == 'normal' else 'disabled')
        self.force_button.configure(state='normal' if active and str(owner.force_button.cget('state')) == 'normal' else 'disabled')

    def _tick(self):
        self.refresh()
        self._timer = self.after(100, self._tick)
