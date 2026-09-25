"""List presentation and registration removal, separate from physical files."""

from dataclasses import dataclass
from pathlib import Path

from .storage import StorageError, _read_csv, _write_csv


SHARED_KEYS = {"people": "person_id", "registered-words": "word", "excluded-words": "word"}


@dataclass(frozen=True)
class Registration:
    kind: str
    key: str
    label: str
    hidden: bool = False


def snapshot_references(data, source, kind, rows, extra=()):
    """Capture references at save time; later target changes cannot rewrite them."""
    references = {("videos", source.relative_to(data._root()).as_posix()), *extra}
    if kind == "transcripts":
        references.update(("people", row["person_id"]) for row in data.load_shared("targets")
                          if row["video_name"].casefold() == source.name.casefold())
        references.update(("people", row["speaker_id"]) for row in rows
                          if row["speaker_id"] not in {"target", "non-target", "unknown", ""})
    if kind == "word-counts":
        for dictionary in ("registered-words", "excluded-words"):
            references.update((dictionary, row["word"]) for row in data.load_shared(dictionary))
        references.update(("results", f"catalog/{source.stem}/transcripts/{source.stem}_v{row['transcript_version']}.csv")
                          for row in rows)
    return [{"kind": kind, "key": key} for kind, key in sorted(references)]


class RegistrationManager:
    def __init__(self, data):
        self.data = data

    def _states(self):
        path = self.data._root() / "catalog" / "list-state.csv"
        return _read_csv(path, "list-state") if path.exists() else []

    def is_hidden(self, kind, key):
        return any(row["kind"] == kind and row["key"] == key
                   and row["state"] in {"hidden", "deleted"} for row in self._states())

    def _results(self):
        root = self.data._root()
        return [root / relative for relative in self.data.list_saved(include_hidden=True)
                if relative.startswith("catalog/")]

    def list_entries(self, *, include_hidden=False):
        entries = []
        states = {(row["kind"], row["key"]): row["state"] for row in self._states()}

        def append(kind, key, label):
            state = states.get((kind, key), "")
            if state != "deleted" and (include_hidden or state != "hidden"):
                entries.append(Registration(kind, key, label, state == "hidden"))

        for kind, key_column in SHARED_KEYS.items():
            for row in self.data.load_shared(kind):
                key = row[key_column]
                append(kind, key, row.get("name", key))
        root = self.data._root()
        for path in self._results():
            relative = path.relative_to(root).as_posix()
            append("results", relative, relative)
        for path in self.data.list_videos(include_hidden=True):
            append("videos", path.relative_to(root).as_posix(), path.name)
        return entries

    def _require_entry(self, kind, key):
        if not any(entry.kind == kind and entry.key == key
                   for entry in self.list_entries(include_hidden=True)):
            raise StorageError("登録情報を選んでください")

    def _set_state(self, kind, key, state):
        rows = [row for row in self._states() if (row["kind"], row["key"]) != (kind, key)]
        if state:
            rows.append({"kind": kind, "key": key, "state": state})
        _write_csv(self.data._root() / "catalog" / "list-state.csv", "list-state", rows)

    def set_hidden(self, kind, key, hidden):
        self._require_entry(kind, key)
        self._set_state(kind, key, "hidden" if hidden else "")

    def ensure_deletable(self, kind, key):
        for result in self._results():
            references = result.with_suffix(".refs.csv")
            if references.exists():
                rows = _read_csv(references, "result-references")
                if any((row["kind"], row["key"]) == (kind, key) for row in rows):
                    raise StorageError(f"保存済み結果から参照されています: {result.name}")
            else:
                result_kind = result.parent.name
                if kind == "people" and result_kind == "transcripts":
                    raise StorageError("旧結果の人物参照を確認できません。削除せず非表示にしてください")
                if kind in {"registered-words", "excluded-words"} and result_kind == "word-counts":
                    raise StorageError("旧集計の辞書参照を確認できません。削除せず非表示にしてください")
                if kind == "videos" and result.parent.parent.name.casefold() == Path(key).stem.casefold():
                    raise StorageError("保存済み結果から元動画が参照されています")
                if kind == "results" and result_kind == "word-counts":
                    target = self.data._root() / key
                    if target.parent.name == "transcripts" and target.parent.parent == result.parent.parent:
                        rows = _read_csv(result, "word-counts")
                        if not rows or any(target.stem == f"{result.parent.parent.name}_v{row['transcript_version']}"
                                           for row in rows):
                            raise StorageError("旧集計の文字起こし参照を保持するため削除できません")
        if kind == "people" and any(row["person_id"] == key for row in self.data.load_shared("targets")):
            raise StorageError("動画の対象話者から参照されています")

    def delete_registration(self, kind, key):
        self._require_entry(kind, key)
        self.ensure_deletable(kind, key)
        if kind in SHARED_KEYS:
            column = SHARED_KEYS[kind]
            self.data.save_shared(kind, [row for row in self.data.load_shared(kind) if row[column] != key])
            self._set_state(kind, key, "")
        else:
            self._set_state(kind, key, "deleted")

    def delete_file(self, relative, *, confirmed=False):
        """Delete one explicitly selected managed file, never an external original."""
        if not confirmed:
            raise StorageError("実ファイル削除には利用者の確認が必要です")
        root = self.data._root().resolve()
        candidate = root / relative
        path = candidate.resolve()
        if not path.is_relative_to(root) or candidate.is_symlink() or not path.is_file():
            raise StorageError("データ用フォルダ内の実ファイルを選んでください")
        relative = path.relative_to(root).as_posix()
        parts = Path(relative).parts
        if path in self._results():
            self.ensure_deletable("results", relative)
        elif len(parts) == 3 and parts[:2] == ("media", "originals"):
            self.ensure_deletable("videos", relative)
        elif (len(parts) >= 2 and parts[0] == "archives" and path.suffix.lower() == ".zip"
              or len(parts) >= 3 and parts[:2] == ("media", "restored")):
            pass
        elif len(parts) >= 2 and parts[0] == "people" and path.suffix in {".wav", ".json"}:
            if any(relative in (row["reference_audio"], row["feature_file"])
                   for row in self.data.load_shared("people")):
                raise StorageError("人物登録から参照されています。先に登録情報を削除してください")
        else:
            raise StorageError("このファイルは管理画面から削除できません")
        path.unlink()
        if parts[0] == "catalog":
            path.with_suffix(".refs.csv").unlink(missing_ok=True)
            self._set_state("results", relative, "")
        elif parts[:2] == ("media", "originals"):
            self._set_state("videos", relative, "")
