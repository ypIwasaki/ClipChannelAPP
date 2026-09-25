"""Open a saved word-count version and play an utterance through the Tk UI."""

import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from tkinter import filedialog

from clipchannel import app


def descendants(widget):
    for child in widget.winfo_children():
        yield child
        yield from descendants(child)


def main():
    config = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    root = Path(config["root"])
    dataset = root / "data"
    state_path = root / "state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    os.environ["PATH"] = config["ffmpeg_bin"] + os.pathsep + os.environ["PATH"]
    original_askdirectory = filedialog.askdirectory
    original_popen = subprocess.Popen
    launched = []

    def start_process(command, *args, **kwargs):
        child = original_popen(command, *args, **kwargs)
        launched.append((command, child))
        return child

    filedialog.askdirectory = lambda **_kwargs: str(dataset)
    app.subprocess.Popen = start_process
    window = app.build_app()
    try:
        window.update()
        buttons = [item for item in descendants(window) if item.winfo_class() in {"Button", "TButton"}]
        next(item for item in buttons if item.cget("text") == "フォルダを選択・切り替え").invoke()
        window.update()
        listing = next(item for item in descendants(window) if item.winfo_class() == "Listbox"
                       and any("/word-counts/" in item.get(i) for i in range(item.size())))
        index = next(i for i in range(listing.size()) if "/word-counts/" in listing.get(i))
        listing.selection_clear(0, "end")
        listing.selection_set(index)
        listing.event_generate("<<ListboxSelect>>")
        next(item for item in buttons if item.cget("text") == "選択した保存版を表示").invoke()
        window.update()
        notebook = next(item for item in descendants(window) if item.winfo_class() == "TNotebook"
                        and any(item.tab(tab, "text") == "頻出語" for tab in item.tabs()))
        notebook.select(next(tab for tab in notebook.tabs() if notebook.tab(tab, "text") == "頻出語"))
        window.update()
        words = next(item for item in descendants(window) if item.winfo_class() == "Listbox"
                     and any(item.get(i).startswith("こと  出現 2 / 発言 2") for i in range(item.size())))
        word_index = next(i for i in range(words.size()) if words.get(i).startswith("こと  出現 2 / 発言 2"))
        words.selection_set(word_index)
        words.event_generate("<<ListboxSelect>>")
        window.update()
        hits = next(item for item in descendants(window) if item.winfo_class() == "Listbox"
                    and any(item.get(i).startswith("10.000秒") for i in range(item.size())))
        assert hits.size() == 2
        hits.selection_set(0)
        hits.event_generate("<Button-1>", x=5, y=5)
        hits.event_generate("<Button-1>", x=5, y=5)
        window.update()
        command, child = launched[-1]
        assert Path(command[0]).name.lower() == "ffplay.exe"
        assert command[command.index("-ss") + 1] == "10.0"
        assert Path(command[-1]).samefile(dataset / "media" / "originals" / Path(config["source"]).name)
        code = child.wait(timeout=15)
        assert code == 0, code
        result = {"name": "frequent-word-ui", "saved_version": listing.get(index),
                  "selected_word": words.get(word_index), "utterance_rows": [hits.get(i) for i in range(hits.size())],
                  "play_command": [str(part) for part in command], "player_exit_code": code}
        state["steps"].append(result)
        state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(result, ensure_ascii=False), flush=True)
    finally:
        window.destroy()
        filedialog.askdirectory = original_askdirectory
        app.subprocess.Popen = original_popen


if __name__ == "__main__":
    main()
