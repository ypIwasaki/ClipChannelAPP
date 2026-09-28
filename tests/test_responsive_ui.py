import tempfile
import json
import threading
import tkinter as tk
import unittest
import time
from pathlib import Path
from unittest.mock import patch

from clipchannel.app import build_app
from clipchannel.storage import DataFolder


def descendants(widget):
    for child in widget.winfo_children():
        yield child
        yield from descendants(child)


def button(window, caption):
    return next(w for w in descendants(window)
                if isinstance(w, (tk.Button,)) or w.winfo_class() == 'TButton'
                if w.cget('text') == caption)


def wait_for(window, predicate, timeout=5):
    end = time.monotonic() + timeout
    while not predicate() and time.monotonic() < end:
        window.update()
        time.sleep(.01)
    if not predicate():
        raise AssertionError('Operation did not reach expected state')


def cancellable_work(control):
    control.report('入力を保持して処理中')
    while not control.cancelled():
        time.sleep(.02)
    return 'stopped'


def completed_work(control):
    return 'temporary result'


def ignores_cancel_temporarily(control):
    control.report('一時処理を実行中')
    time.sleep(10)
    return 'temporary result'


def failed_work(control):
    raise ValueError('一時処理の失敗詳細')


class ResponsiveAppTests(unittest.TestCase):
    def test_project_folder_opens_after_restart_without_edit_video(self):
        import os
        data = DataFolder()
        with tempfile.TemporaryDirectory() as temporary:
            data.select(temporary)
            window = build_app(data=data, preferences=Path(temporary) / 'ui.json')
            self.addCleanup(window.destroy)
            if os.name == 'nt':
                with patch('clipchannel.save_export_ui.os.startfile') as launch:
                    button(window, 'プロジェクトの保存フォルダを開く').invoke()
                launch.assert_called_once_with(Path(temporary) / 'projects')
                return
            from clipchannel.editor_bridge import windows_path
            expected = windows_path(Path(temporary) / 'projects')
            with patch('clipchannel.save_export_ui.windows_path', return_value=expected), \
                    patch('clipchannel.save_export_ui.subprocess.Popen') as launch:
                button(window, 'プロジェクトの保存フォルダを開く').invoke()
            launch.assert_called_once()
            self.assertEqual(launch.call_args.args[0], ['explorer.exe', expected])

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def test_work_switch_retains_download_input_and_hides_unrelated_tabs(self):
        window = build_app(data=DataFolder(), preferences=self.root / 'ui.json')
        self.addCleanup(window.destroy)
        window.update()
        url = next(w for w in descendants(window) if w.winfo_class() == 'Entry')
        url.insert(0, 'https://example.invalid/temporary-video')
        button(window, '解析・切り出し').invoke()
        window.update()
        notebook = next(w for w in descendants(window) if w.winfo_class() == 'TNotebook')
        visible = [notebook.tab(tab, 'text') for tab in notebook.tabs()
                   if notebook.tab(tab, 'state') != 'hidden']
        self.assertEqual(visible, ['人物・参照音声', '頻出語', '切り出し区間'])
        button(window, '動画を準備').invoke()
        window.update()
        self.assertEqual(url.get(), 'https://example.invalid/temporary-video')
        self.assertTrue(url.winfo_viewable())

    def test_small_window_can_reach_layout_inputs_and_actions_without_body_scroll(self):
        from clipchannel.window_preferences import DisplayArea
        window = build_app(data=DataFolder(), preferences=self.root / 'ui.json',
                           display=DisplayArea(0, 0, 1280, 680))
        self.addCleanup(window.destroy)
        button(window, '小').invoke()
        button(window, '編集・書き出し').invoke()
        window.update()
        notebook = next(w for w in descendants(window) if w.winfo_class() == 'TNotebook')
        notebook.select(next(t for t in notebook.tabs() if notebook.tab(t, 'text') == '画面・字幕'))
        window.update()
        page = window.nametowidget(notebook.select())
        selector = next(w for w in descendants(page) if w.winfo_class() == 'TCombobox'
                        and tuple(w.cget('values')) == ('操作', '結果', '詳細設定', '自動'))
        selector.set('詳細設定')
        selector.event_generate('<<ComboboxSelected>>')
        window.update()
        fields = [w for w in descendants(page) if w.winfo_class() == 'TEntry']
        fields[0].delete(0, tk.END)
        fields[0].insert(0, '1280')
        selector.set('操作')
        selector.event_generate('<<ComboboxSelected>>')
        window.update()
        action = button(page, '画面設定をAviUtl2へ渡す')
        self.assertTrue(action.winfo_viewable())
        self.assertLessEqual(action.winfo_rooty() + action.winfo_height(),
                             window.winfo_rooty() + window.winfo_height())
        selector.set('詳細設定')
        selector.event_generate('<<ComboboxSelected>>')
        window.update()
        self.assertEqual(fields[0].get(), '1280')

    def test_every_function_has_explicit_views_and_small_window_controls_fit(self):
        from clipchannel.responsive_ui import WORKS
        from clipchannel.window_preferences import DisplayArea
        window = build_app(data=DataFolder(), preferences=self.root / 'ui.json',
                           display=DisplayArea(0, 0, 1920, 1040))
        self.addCleanup(window.destroy)
        errors = []
        window.report_callback_exception = lambda *error: errors.append(error)
        button(window, '小').invoke()
        for work, names in WORKS.items():
            button(window, work).invoke()
            window.update()
            notebook = next(w for w in descendants(window) if w.winfo_class() == 'TNotebook')
            for name in names:
                notebook.select(next(t for t in notebook.tabs() if notebook.tab(t, 'text') == name))
                window.update()
                page = window.nametowidget(notebook.select())
                view = next(w for w in descendants(page) if w.winfo_class() == 'TCombobox'
                            and tuple(w.cget('values')) == ('操作', '結果', '詳細設定', '自動'))
                for role in ('操作', '結果', '詳細設定'):
                    view.set(role)
                    view.event_generate('<<ComboboxSelected>>')
                    window.update()
                    selectors = [w for w in descendants(page) if w.winfo_class() == 'TCombobox'
                                 and w is not view and w.winfo_viewable()]
                    for selector in selectors[:1]:
                        for section in selector.cget('values'):
                            selector.set(section)
                            selector.event_generate('<<ComboboxSelected>>')
                            window.update()
                            for control in descendants(page):
                                if control.winfo_viewable() and control.winfo_class() in ('TButton', 'Button'):
                                    self.assertLessEqual(control.winfo_rootx() + control.winfo_width(),
                                        window.winfo_rootx() + window.winfo_width(), (name, role, section, control.cget('text')))
                                    self.assertLessEqual(control.winfo_rooty() + control.winfo_height(),
                                        window.winfo_rooty() + window.winfo_height(), (name, role, section, control.cget('text')))
        self.assertEqual(errors, [])

    def test_running_work_can_switch_page_and_cancel_from_permanent_controls(self):
        from clipchannel.managed_process_ui import ProcessPanel
        data = DataFolder()
        (self.root / 'data').mkdir()
        data.select(self.root / 'data')
        window = build_app(data=data, preferences=self.root / 'ui.json')
        self.addCleanup(window.destroy)
        panel = next(w for w in descendants(window) if isinstance(w, ProcessPanel))
        panel.start('一時処理', cancellable_work)
        def stop_temporary_work():
            if panel.active:
                panel.stop()
                wait_for(window, lambda: not panel.active)
        self.addCleanup(stop_temporary_work)
        button(window, '編集・書き出し').invoke()
        window.update()
        notebook = next(w for w in descendants(window) if w.winfo_class() == 'TNotebook')
        self.assertEqual(notebook.tab(notebook.select(), 'text'), '画面・字幕')
        cancel = button(window, '実行中の処理を中止')
        self.assertTrue(cancel.winfo_viewable())
        wait_for(window, lambda: str(cancel.cget('state')) == 'normal')
        cancel.invoke()
        wait_for(window, lambda: not panel.active)
        self.assertEqual(panel.operation.state, '中止')

    def test_invalid_export_setting_reveals_details_and_retains_value(self):
        from clipchannel.save_export_ui import SaveExportPanel
        window = build_app(data=DataFolder(), preferences=self.root / 'ui.json')
        self.addCleanup(window.destroy)
        button(window, '編集・書き出し').invoke()
        panel = next(w for w in descendants(window) if isinstance(w, SaveExportPanel))
        notebook = panel.master
        notebook.select(panel)
        panel.fields['fps'].set('invalid-fps')
        with patch('clipchannel.dialogs.messagebox.showerror'):
            button(panel, '完成動画を書き出す').invoke()
        window.update()
        self.assertEqual(panel.view.get(), '詳細設定')
        self.assertEqual(panel.fields['fps'].get(), 'invalid-fps')

    def test_close_and_reopen_restore_work_tab_and_normal_size(self):
        from clipchannel.window_preferences import DisplayArea
        path = self.root / 'ui.json'
        display = DisplayArea(0, 0, 1920, 1040)
        window = build_app(data=DataFolder(), preferences=path, display=display)
        button(window, '小').invoke()
        button(window, '解析・切り出し').invoke()
        notebook = next(w for w in descendants(window) if w.winfo_class() == 'TNotebook')
        notebook.select(next(t for t in notebook.tabs() if notebook.tab(t, 'text') == '頻出語'))
        window.update()
        size = window.winfo_width(), window.winfo_height()
        window.tk.call(window.protocol('WM_DELETE_WINDOW'))
        reopened = build_app(data=DataFolder(), preferences=path, display=display)
        self.addCleanup(reopened.destroy)
        reopened.update()
        tabs = next(w for w in descendants(reopened) if w.winfo_class() == 'TNotebook')
        self.assertEqual(tabs.tab(tabs.select(), 'text'), '頻出語')
        self.assertEqual((reopened.winfo_width(), reopened.winfo_height()), size)

    def test_long_status_cannot_hide_stop_or_work_controls(self):
        from clipchannel.save_export_ui import SaveExportPanel
        from clipchannel.window_preferences import DisplayArea
        window = build_app(data=DataFolder(), preferences=self.root / 'ui.json',
                           display=DisplayArea(0, 0, 1280, 680))
        self.addCleanup(window.destroy)
        button(window, '小').invoke()
        panel = next(w for w in descendants(window) if isinstance(w, SaveExportPanel))
        window.update()
        panel.status.set('失敗: とても長い状態文とパス。' * 1000)
        wait_for(window, lambda: any(w.winfo_class() == 'Text' and
            w.get('1.0', 'end-1c').startswith('失敗:') for w in descendants(window)))
        for caption in ('実行中の処理を中止', '実行中の処理を強制停止…', 'データを管理'):
            control = button(window, caption)
            self.assertTrue(control.winfo_viewable())
            self.assertLessEqual(control.winfo_rootx() + control.winfo_width(),
                                 window.winfo_rootx() + window.winfo_width())
            self.assertLessEqual(control.winfo_rooty() + control.winfo_height(),
                                 window.winfo_rooty() + window.winfo_height())

    def test_action_roles_have_consistent_styles_across_work_pages(self):
        from tkinter import ttk
        window = build_app(data=DataFolder(), preferences=self.root / 'ui.json')
        self.addCleanup(window.destroy)
        style = ttk.Style(window)
        background = lambda caption: style.lookup(button(window, caption).cget('style'), 'background')
        self.assertEqual(background('候補を生成して別版保存'), background('保存'))
        self.assertNotEqual(background('保存'), background('実ファイルを選んで削除…'))

    def test_all_operation_controls_fit_at_supported_scale_and_size_equivalents(self):
        from clipchannel.responsive_ui import WORKS
        from clipchannel.window_preferences import DisplayArea
        real_tk = tk.Tk
        for scale in (1, 1.25, 1.5):
            previous_scaling = []
            def scaled_window():
                root = real_tk()
                previous_scaling.append(root.tk.call('tk', 'scaling'))
                root.tk.call('tk', 'scaling', 96 / 72 * scale)
                return root
            with patch('clipchannel.app.tk.Tk', side_effect=scaled_window):
                window = build_app(data=DataFolder(), preferences=self.root / 'ui.json',
                                   display=DisplayArea(0, 0, 1920, 1040))
            try:
                errors = []
                window.report_callback_exception = lambda *error: errors.append(error)
                for fraction in (.7, .85, 1):
                    window.geometry(f'{round(1920 * fraction)}x{round(1040 * fraction)}+0+0')
                    for work, names in WORKS.items():
                        button(window, work).invoke()
                        window.update()
                        notebook = next(w for w in descendants(window) if w.winfo_class() == 'TNotebook')
                        for name in names:
                            notebook.select(next(t for t in notebook.tabs() if notebook.tab(t, 'text') == name))
                            window.update()
                            page = window.nametowidget(notebook.select())
                            view = next(w for w in descendants(page) if w.winfo_class() == 'TCombobox'
                                        and tuple(w.cget('values')) == ('操作', '結果', '詳細設定', '自動'))
                            view.set('操作')
                            view.event_generate('<<ComboboxSelected>>')
                            window.update()
                            selector = next(w for w in descendants(page) if w.winfo_class() == 'TCombobox'
                                            and w is not view and w.winfo_viewable())
                            for section in selector.cget('values'):
                                selector.set(section)
                                selector.event_generate('<<ComboboxSelected>>')
                                window.update()
                                for control in descendants(page):
                                    if control.winfo_viewable() and control.winfo_class() in ('TButton', 'Button', 'TEntry', 'Entry'):
                                        if control.winfo_class() in ('TButton', 'Button'):
                                            self.assertGreaterEqual(control.winfo_width(), control.winfo_reqwidth(),
                                                (scale, fraction, name, section, control.cget('text')))
                                        self.assertLessEqual(control.winfo_rootx() + control.winfo_width(),
                                            page.winfo_rootx() + page.winfo_width(), (scale, fraction, name, section, str(control)))
                                        self.assertLessEqual(control.winfo_rooty() + control.winfo_height(),
                                            page.winfo_rooty() + page.winfo_height(), (scale, fraction, name, section, str(control)))
                    self.assertLessEqual(button(window, '実行中の処理を中止').winfo_rooty() +
                        button(window, '実行中の処理を中止').winfo_height(),
                        window.winfo_rooty() + window.winfo_height())
                self.assertEqual(errors, [])
            finally:
                window.tk.call('tk', 'scaling', previous_scaling[0])
                window.destroy()

    def test_management_selection_survives_work_and_tab_switches(self):
        from clipchannel.management_ui import ManagementPanel
        data = DataFolder()
        data.select(self.root)
        source = self.root / 'temporary.mp4'
        source.write_bytes(b'temporary fixture')
        data.register_video(source)
        window = build_app(data=data, preferences=self.root / 'ui.json')
        self.addCleanup(window.destroy)
        button(window, 'データを管理').invoke()
        window.update()
        panel = next(w for w in descendants(window) if isinstance(w, ManagementPanel))
        panel.listing.selection_set(0)
        selected = panel.listing.get(0)
        button(window, '動画を準備').invoke()
        window.update()
        button(window, 'データを管理').invoke()
        window.update()
        self.assertEqual(panel.listing.curselection(), (0,))
        self.assertEqual(panel.listing.get(0), selected)

    def test_long_results_can_scroll_internally_and_keep_selection(self):
        from clipchannel.management_ui import ManagementPanel
        window = build_app(data=DataFolder(), preferences=self.root / 'ui.json')
        self.addCleanup(window.destroy)
        button(window, 'データを管理').invoke()
        window.update()
        panel = next(w for w in descendants(window) if isinstance(w, ManagementPanel))
        panel.listing.insert(tk.END, *[f'{i}: ' + '長いパス/' * 50 for i in range(100)])
        panel.show('登録一覧')
        window.update()
        bars = [w for w in descendants(panel.listing.master) if w.winfo_class() == 'TScrollbar']
        self.assertEqual({str(bar.cget('orient')) for bar in bars}, {'vertical', 'horizontal'})
        panel.listing.selection_set(99)
        panel.listing.see(99)
        panel.listing.xview_moveto(1)
        panel.show('登録情報を管理')
        window.update()
        panel.show('登録一覧')
        window.update()
        self.assertEqual(panel.listing.curselection(), (99,))
        self.assertEqual(panel.listing.yview()[1], 1)
        self.assertEqual(panel.listing.xview()[1], 1)

    def test_long_folder_path_keeps_size_controls_visible_and_can_be_read(self):
        from clipchannel.window_preferences import DisplayArea
        directory = self.root
        for index in range(6):
            directory = directory / ('long-folder-name-' * 5 + str(index))
        directory.mkdir(parents=True)
        window = build_app(preferences=self.root / 'ui.json', display=DisplayArea(0, 0, 1280, 680))
        self.addCleanup(window.destroy)
        with patch('tkinter.filedialog.askdirectory', return_value=str(directory)):
            button(window, 'フォルダを選択・切り替え').invoke()
        window.update()
        for name in ('小', '中', '大', '場所を確認'):
            control = button(window, name)
            self.assertTrue(control.winfo_viewable())
            self.assertLessEqual(control.winfo_rootx() + control.winfo_width(),
                                 window.winfo_rootx() + window.winfo_width())
        with patch('clipchannel.dialogs.messagebox.showinfo') as message:
            button(window, '場所を確認').invoke()
            self.assertIn(str(directory), message.call_args.args[1])

    def test_completion_guides_next_work_without_switching_current_page(self):
        from clipchannel.managed_process_ui import ProcessPanel
        data = DataFolder()
        data.select(self.root)
        window = build_app(data=data, preferences=self.root / 'ui.json')
        self.addCleanup(window.destroy)
        panel = next(w for w in descendants(window) if isinstance(w, ProcessPanel))
        panel.start('動画の情報取得', completed_work)
        button(window, '編集・書き出し').invoke()
        wait_for(window, lambda: not panel.active)
        window.update()
        notebook = next(w for w in descendants(window) if w.winfo_class() == 'TNotebook')
        self.assertEqual(notebook.tab(notebook.select(), 'text'), '画面・字幕')
        self.assertIn('次の作業: 解析・切り出し', panel.status.get())

    def test_populated_results_and_detail_inputs_are_reachable_at_150_percent_small(self):
        from clipchannel.responsive_ui import WORKS
        from clipchannel.save_export_ui import SaveExportPanel
        from clipchannel.window_preferences import DisplayArea
        real_tk = tk.Tk
        old_scaling = []
        def scaled_window():
            root = real_tk()
            old_scaling.append(root.tk.call('tk', 'scaling'))
            root.tk.call('tk', 'scaling', 2)
            return root
        with patch('clipchannel.app.tk.Tk', side_effect=scaled_window):
            window = build_app(data=DataFolder(), preferences=self.root / 'ui.json',
                               display=DisplayArea(0, 0, 1920, 1040))
        try:
            button(window, '小').invoke()
            for widget in descendants(window):
                if widget.winfo_class() == 'Listbox':
                    widget.insert(tk.END, *['長い本文・パス/' * 40 for _ in range(100)])
            export = next(w for w in descendants(window) if isinstance(w, SaveExportPanel))
            export.message.set('失敗: 長い詳細文。' * 1000)
            for work, names in WORKS.items():
                button(window, work).invoke()
                window.update()
                notebook = next(w for w in descendants(window) if w.winfo_class() == 'TNotebook')
                for name in names:
                    notebook.select(next(t for t in notebook.tabs() if notebook.tab(t, 'text') == name))
                    window.update()
                    page = window.nametowidget(notebook.select())
                    view = next(w for w in descendants(page) if w.winfo_class() == 'TCombobox'
                                and tuple(w.cget('values')) == ('操作', '結果', '詳細設定', '自動'))
                    for role in ('結果', '詳細設定', '自動'):
                        view.set(role)
                        view.event_generate('<<ComboboxSelected>>')
                        window.update()
                        selectors = [w for w in descendants(page) if w.winfo_class() == 'TCombobox'
                                     and w is not view and w.winfo_viewable()]
                        for selector in selectors:
                            for section in selector.cget('values'):
                                selector.set(section)
                                selector.event_generate('<<ComboboxSelected>>')
                                window.update()
                                canvases = [w for w in descendants(page) if w.winfo_class() == 'Canvas' and w.winfo_viewable()]
                                controls = [w for w in descendants(page) if w.winfo_class() in ('Entry', 'TEntry', 'TButton', 'Button')
                                            and w.winfo_viewable()]
                                seen = set()
                                for position in (0, .2, .4, .6, .8, 1):
                                    for canvas in canvases:
                                        canvas.yview_moveto(position)
                                    window.update()
                                    for control in controls:
                                        left, top = control.winfo_rootx(), control.winfo_rooty()
                                        right, bottom = left + control.winfo_width(), top + control.winfo_height()
                                        if (left >= page.winfo_rootx() and right <= page.winfo_rootx() + page.winfo_width()
                                                and top >= page.winfo_rooty() and bottom <= page.winfo_rooty() + page.winfo_height()):
                                            seen.add(str(control))
                                self.assertEqual(seen, {str(c) for c in controls}, (name, role, section))
        finally:
            window.tk.call('tk', 'scaling', old_scaling[0])
            window.destroy()

    def test_export_can_switch_work_then_cancel_without_losing_output_settings(self):
        from fractions import Fraction
        from clipchannel.save_export import OperationResult, ProjectState
        from clipchannel.save_export_ui import SaveExportPanel
        data = DataFolder()
        data.select(self.root)
        video = self.root / 'media' / 'edits' / 'temporary-edit' / 'sample.mp4'
        video.parent.mkdir(parents=True)
        video.write_bytes(b'temporary video fixture')
        video.with_suffix('.json').write_text(json.dumps({'fps': '30', 'frame_counts': [300]}))
        project = self.root / 'projects' / 'temporary-edit' / 'sample.aup2'
        project.parent.mkdir(parents=True)
        project.write_bytes(b'temporary project fixture')
        window = build_app(data=data, preferences=self.root / 'ui.json')
        self.addCleanup(window.destroy)
        panel = next(w for w in descendants(window) if isinstance(w, SaveExportPanel))
        panel.set_video(video)
        panel.fields['width'].set('1600')
        panel.fields['fps'].set('24')
        started = threading.Event()
        snapshots, errors = [], []
        window.report_callback_exception = lambda *error: errors.append(error)
        def export_adapter(project, video, destination, settings, *, cancel, force, on_progress):
            snapshots.append(settings)
            started.set()
            cancel.wait(5)
            return OperationResult('cancelled', '一時書き出しを中止しました', destination)
        stopped = []
        def drive():
            try:
                if not started.is_set():
                    window.after(20, drive)
                    return
                if not stopped:
                    button(window, '動画を準備').invoke()
                    cancel = button(window, '実行中の処理を中止')
                    if str(cancel.cget('state')) != 'normal':
                        window.after(20, drive)
                        return
                    cancel.invoke()
                    stopped.append(panel.cancel.is_set() and data.running)
                if panel.busy:
                    window.after(20, drive)
                    return
                window.quit()
            except Exception as error:
                errors.append(error)
                panel.stop()
                window.quit()
        with patch('clipchannel.save_export_ui.inspect_project', return_value=ProjectState(
                project, 1920, 1080, Fraction(30), 300, False, False)), \
                patch('clipchannel.save_export_ui.export_video', side_effect=export_adapter), \
                patch('tkinter.filedialog.asksaveasfilename', return_value=str(self.root / 'exports' / 'temporary.mp4')):
            button(window, '編集・書き出し').invoke()
            panel.master.select(panel)
            button(panel, '完成動画を書き出す').invoke()
            window.after(20, drive)
            watchdog = window.after(6000, window.quit)
            window.mainloop()
            window.after_cancel(watchdog)
        self.assertEqual(errors, [])
        self.assertEqual(stopped, [True])
        self.assertFalse(panel.busy)
        self.assertFalse(data.running)
        self.assertEqual((snapshots[0].width, snapshots[0].fps), (1600, Fraction(24)))
        self.assertEqual((panel.fields['width'].get(), panel.fields['fps'].get()), ('1600', '24'))
        self.assertEqual(panel.master.tab(panel.master.select(), 'text'), '取得・媒体操作')

    def test_force_stop_from_another_work_only_ends_the_owned_temporary_process(self):
        from clipchannel.managed_process_ui import ProcessPanel
        data = DataFolder()
        data.select(self.root)
        window = build_app(data=data, preferences=self.root / 'ui.json')
        self.addCleanup(window.destroy)
        window.update()
        url = next(w for w in descendants(window) if w.winfo_class() == 'Entry')
        url.insert(0, 'https://example.invalid/retained')
        panel = next(w for w in descendants(window) if isinstance(w, ProcessPanel))
        panel.start('一時処理の停止確認', ignores_cancel_temporarily)
        def cleanup():
            if panel.active:
                panel.stop()
                wait_for(window, lambda: panel.operation.can_force or not panel.active, timeout=5)
                if panel.active:
                    panel.operation.force_stop()
                    wait_for(window, lambda: not panel.active)
        self.addCleanup(cleanup)
        wait_for(window, lambda: panel.operation.progress == '一時処理を実行中')
        button(window, 'データを管理').invoke()
        cancel = button(window, '実行中の処理を中止')
        wait_for(window, lambda: str(cancel.cget('state')) == 'normal')
        cancel.invoke()
        force = button(window, '実行中の処理を強制停止…')
        wait_for(window, lambda: str(force.cget('state')) == 'normal')
        with patch('clipchannel.dialogs.messagebox.askyesno', return_value=True):
            force.invoke()
        wait_for(window, lambda: not panel.active)
        self.assertEqual(panel.operation.state, '強制停止')
        self.assertFalse(data.running)
        button(window, '動画を準備').invoke()
        window.update()
        self.assertEqual(url.get(), 'https://example.invalid/retained')

    def test_failed_work_retains_input_and_reveals_its_settings_without_work_switch(self):
        from clipchannel.managed_process_ui import ProcessPanel
        data = DataFolder()
        data.select(self.root)
        window = build_app(data=data, preferences=self.root / 'ui.json')
        self.addCleanup(window.destroy)
        window.update()
        url = next(w for w in descendants(window) if w.winfo_class() == 'Entry')
        url.insert(0, 'https://example.invalid/retry')
        panel = next(w for w in descendants(window) if isinstance(w, ProcessPanel))
        panel.start('動画の情報取得', failed_work)
        button(window, '編集・書き出し').invoke()
        with patch('clipchannel.dialogs.messagebox.showerror'):
            wait_for(window, lambda: not panel.active)
        notebook = next(w for w in descendants(window) if w.winfo_class() == 'TNotebook')
        self.assertEqual(notebook.tab(notebook.select(), 'text'), '画面・字幕')
        self.assertIn('一時処理の失敗詳細', panel.status.get())
        button(window, '動画を準備').invoke()
        window.update()
        page = window.nametowidget(notebook.select())
        self.assertEqual(page.view.get(), '詳細設定')
        self.assertEqual(url.get(), 'https://example.invalid/retry')


class WindowPreferencesTests(unittest.TestCase):
    def test_first_run_uses_medium_then_restores_and_clamps_saved_window(self):
        from clipchannel.window_preferences import DisplayArea, UiState, WindowPreferences
        with tempfile.TemporaryDirectory() as temporary:
            preferences = WindowPreferences(Path(temporary) / 'ui.json')
            first = preferences.load(DisplayArea(0, 0, 1920, 1040))
            self.assertEqual((first.width, first.height, first.work),
                             (1632, 884, '動画を準備'))
            preferences.save(UiState(width=1800, height=950, x=100, y=50,
                maximized=True, work='編集・書き出し', tab='補助素材'))
            restored = preferences.load(DisplayArea(0, 0, 1280, 680))
            self.assertEqual((restored.width, restored.height, restored.x, restored.y),
                             (1280, 680, 0, 0))
            self.assertTrue(restored.maximized)
            self.assertEqual((restored.work, restored.tab), ('編集・書き出し', '補助素材'))
