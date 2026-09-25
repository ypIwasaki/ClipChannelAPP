"""Unauthenticated media acquisition with per-item results and cooperative stop."""

import shlex
import tempfile
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from .storage import StorageError, VIDEO_EXTENSIONS
from .media import prepare_media


class DownloadError(StorageError):
    pass


class DownloadStopped(DownloadError):
    pass


@dataclass
class DownloadItem:
    url: str
    title: str
    state: str = "未着手"
    seconds: float = 0.0
    path: Path | None = None
    error: str = ""
    details: str = ""
    source_path: Path | None = None


# Only options whose effective yt-dlp API values are controlled here are accepted.
# Unknown options are rejected with a reason, never silently discarded.
EXTRA_OPTIONS = {"--format": "format", "-f": "format",
                 "--retries": "retries", "--fragment-retries": "fragment_retries",
                 "--sub-langs": "subtitleslangs"}
FORBIDDEN = ("--output", "-o", "--paths", "-P", "--exec", "--config-locations",
             "--cookies", "--cookies-from-browser", "--netrc", "--netrc-cmd",
             "--force-overwrites", "--no-keep-video", "--plugin-dirs", "--write-info-json",
             "--print", "--dump-json", "--proxy", "--add-header")


def parse_extra(value):
    try:
        tokens = shlex.split(value)
    except ValueError as error:
        raise DownloadError("追加引数の引用符が閉じていません") from error
    options = {}
    position = 0
    while position < len(tokens):
        token = tokens[position]
        option, separator, inline = token.partition("=")
        if option in FORBIDDEN or option not in EXTRA_OPTIONS:
            raise DownloadError(f"追加引数 {option} は保存・秘密値・処理管理の保護を確認できないため使えません")
        if separator:
            value = inline
        else:
            position += 1
            if position >= len(tokens) or tokens[position].startswith("-"):
                raise DownloadError(f"{option} の値を指定してください")
            value = tokens[position]
        if not value or EXTRA_OPTIONS[option] in options:
            raise DownloadError(f"{option} の値が空か重複しています")
        key = EXTRA_OPTIONS[option]
        if key in ("retries", "fragment_retries"):
            if not value.isdecimal():
                raise DownloadError(f"{option} は非負整数で指定してください")
            value = int(value)
        if key == "subtitleslangs":
            value = [language.strip() for language in value.split(",") if language.strip()]
            if not value:
                raise DownloadError("字幕言語を指定してください")
        options[key] = value
        position += 1
    return options


def _safe_url(url):
    try:
        parts = urlsplit(url.strip())
    except ValueError as error:
        raise DownloadError("URL の形式を確認してください") from error
    if parts.scheme not in ("http", "https") or not parts.hostname or parts.username or parts.password:
        raise DownloadError("認証情報を含まない HTTP(S) URL を指定してください")
    return url.strip()


class DownloadSession:
    def __init__(self, data, url, *, format="bestvideo*+bestaudio/best", audio_only=False,
                 info_only=False, retries=3, extra=""):
        self.data = data
        self.url = _safe_url(url)
        self.audio_only = audio_only
        self.info_only = info_only
        self.options = parse_extra(extra)
        if not isinstance(retries, int) or retries < 0:
            raise DownloadError("再試行回数は非負整数で指定してください")
        if "retries" in self.options and retries != 3:
            raise DownloadError("再試行回数が主要設定と追加引数で重複しています")
        self.options.setdefault("retries", retries)
        if "format" in self.options and format != "bestvideo*+bestaudio/best":
            raise DownloadError("形式が主要設定と追加引数で重複しています")
        self.options.setdefault("format", "bestaudio/best" if audio_only else format)
        self.items = []
        self.stopping = False
        self.state = "未着手"
        self.started_at = None
        self.ended_at = None

    @property
    def elapsed(self):
        if self.started_at is None:
            return 0.0
        end = self.ended_at if self.ended_at is not None else time.monotonic()
        return max(0.0, end - self.started_at)

    def stop(self):
        self.stopping = True
        self.state = "停止待ち"

    def _is_stopping(self, stop_requested):
        if stop_requested and stop_requested():
            self.stop()
        return self.stopping

    def _hook(self, _progress, stop_requested=None):
        if self._is_stopping(stop_requested):
            raise DownloadStopped("通常中止しました")

    def run(self, on_change=None, *, stop_requested=None):
        if self.data.path is None:
            raise DownloadError("データ用フォルダを選んでください")
        if self.data.running:
            raise DownloadError("別の処理が実行中です")
        try:
            import yt_dlp
        except ImportError as error:
            raise DownloadError("yt-dlp が必要です") from error
        self.data.running = True
        self.started_at = time.monotonic()
        self.ended_at = None
        self.state = "情報取得中"
        notify = on_change or (lambda: None)
        try:
            if self._is_stopping(stop_requested):
                self.state = "停止完了"
                notify()
                return self.items
            try:
                with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True, "extract_flat": "in_playlist",
                                        "skip_download": True, "noplaylist": False, "cachedir": False,
                                        "socket_timeout": 10}) as ydl:
                    info = ydl.extract_info(self.url, download=False, process=False)
                entries = list(info.get("entries") or [info])
            except Exception as error:
                if self._is_stopping(stop_requested):
                    self.state = "停止完了"
                    notify()
                    return self.items
                raise DownloadError("項目一覧を取得できませんでした。URLを確認してください") from error
            for entry in entries:
                if entry:
                    item_url = entry.get("webpage_url") or entry.get("original_url") or entry.get("url") or self.url
                    if not str(item_url).startswith(("http://", "https://")) and entry.get("ie_key") == "Youtube":
                        item_url = "https://www.youtube.com/watch?v=" + str(entry.get("id", ""))
                    item = DownloadItem(item_url, entry.get("title") or entry.get("id") or "項目")
                    item.details = self._details(entry)
                    self.items.append(item)
            notify()
            if self._is_stopping(stop_requested):
                self.state = "停止完了"
                notify()
                return self.items
            if self.info_only:
                for item in self.items:
                    if self._is_stopping(stop_requested):
                        break
                    self._run_info_item(item, yt_dlp, stop_requested)
                    notify()
                self.state = "停止完了" if self._is_stopping(stop_requested) else "完了"
                notify()
                return self.items
            for item in self.items:
                if self._is_stopping(stop_requested):
                    break
                self._run_item(item, yt_dlp, stop_requested, notify)
                notify()
            self.state = "停止完了" if self._is_stopping(stop_requested) else "完了"
            notify()
            return self.items
        finally:
            self.ended_at = time.monotonic()
            self.data.running = False

    def retry_failed(self, indices, on_change=None, *, stop_requested=None):
        if self.data.running:
            raise DownloadError("別の処理が実行中です")
        try:
            import yt_dlp
        except ImportError as error:
            raise DownloadError("yt-dlp が必要です") from error
        self.stopping = False
        self.data.running = True
        self.started_at = time.monotonic()
        self.ended_at = None
        notify = on_change or (lambda: None)
        try:
            for index, item in enumerate(self.items):
                if index in indices and item.state == "失敗" and not self._is_stopping(stop_requested):
                    if self.info_only:
                        self._run_info_item(item, yt_dlp, stop_requested)
                    else:
                        self._run_item(item, yt_dlp, stop_requested, notify)
                    notify()
            self.state = "停止完了" if self._is_stopping(stop_requested) else "完了"
            notify()
        finally:
            self.ended_at = time.monotonic()
            self.data.running = False

    def _run_info_item(self, item, yt_dlp, stop_requested=None):
        started = time.monotonic()
        try:
            with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True,
                                    "skip_download": True, "cachedir": False,
                                    "socket_timeout": 10}) as ydl:
                item.details = self._details(ydl.extract_info(_safe_url(item.url), download=False))
            item.state, item.error = ("中止", "") if self._is_stopping(stop_requested) else ("情報のみ", "")
        except Exception:
            item.state, item.error = (("中止", "") if self._is_stopping(stop_requested) else
                                      ("失敗", "情報取得に失敗しました"))
        finally:
            item.seconds += time.monotonic() - started

    def _run_item(self, item, yt_dlp, stop_requested=None, notify=lambda: None):
        started = time.monotonic()
        self.state = "取得中"
        item.state, item.error = "取得中", ""
        notify()
        try:
            self._hook(None, stop_requested)
            if item.source_path and item.source_path.is_file():
                item.path = self._prepare_video(item.source_path, stop_requested)
                item.state = "成功"
                return
            with tempfile.TemporaryDirectory(dir=self.data.path / "work", prefix="download-") as temporary:
                options = {"quiet": True, "no_warnings": True, "noplaylist": True,
                           "cachedir": False, "socket_timeout": 10,
                           "outtmpl": str(Path(temporary) / "%(id)s.%(ext)s"),
                           "progress_hooks": [lambda value: self._hook(value, stop_requested)],
                           "postprocessor_hooks": [lambda value: self._hook(value, stop_requested)], "overwrites": False,
                           "restrictfilenames": True, **self.options}
                if "subtitleslangs" in options:
                    options["writesubtitles"] = True
                with yt_dlp.YoutubeDL(options) as ydl:
                    result = ydl.extract_info(_safe_url(item.url), download=True)
                    item.details = self._details(result)
                    paths = [Path(path) for path in Path(temporary).iterdir() if path.is_file()]
                if self._is_stopping(stop_requested):
                    raise DownloadStopped("通常中止しました")
                if self.audio_only and result.get("vcodec") not in (None, "none"):
                    raise DownloadError("音声のみの成果物を確認できませんでした")
                if not self.audio_only and result.get("vcodec") in (None, "none"):
                    raise DownloadError("動画ストリームを確認できませんでした")
                allowed = {".mp3", ".m4a", ".wav", ".opus", ".ogg", ".flac", ".webm"} if self.audio_only else VIDEO_EXTENSIONS
                media = [path for path in paths if path.suffix.lower() in allowed and path.stat().st_size]
                if len(media) != 1:
                    raise DownloadError("成果物の種類または数を確認できませんでした")
                if self.audio_only:
                    destination = self.data.path / "media" / "audio"
                    destination.mkdir(parents=True, exist_ok=True)
                    target = destination / media[0].name
                    if target.exists():
                        raise DownloadError("同名の音声成果物があります")
                    self._hook(None, stop_requested)
                    media[0].replace(target)
                else:
                    source_dir = self.data.path / "media" / "downloaded" / uuid.uuid4().hex
                    source_dir.mkdir(parents=True)
                    source = source_dir / media[0].name
                    media[0].replace(source)
                    for sidecar in paths:
                        if sidecar.is_file() and sidecar.suffix.lower() in (".srt", ".vtt", ".ass"):
                            sidecar.replace(source_dir / sidecar.name)
                    item.source_path = source
                    notify()
                    target = self._prepare_video(source, stop_requested)
                item.path = target
                item.state = "成功"
        except DownloadStopped:
            item.state = "中止"
            self.stopping = True
        except Exception:
            item.state = "中止" if self._is_stopping(stop_requested) else "失敗"
            # yt-dlp errors may contain credentials or the source URL.
            item.error = "取得または成果物の確認に失敗しました。URL・形式・空き容量を確認してください"
            if item.source_path:
                item.error += f" 取得済みファイル: {item.source_path}"
        finally:
            item.seconds += time.monotonic() - started

    def _prepare_video(self, source, stop_requested=None):
        self._hook(None, stop_requested)
        registered = self.data.register_video(source, stop_requested=stop_requested)
        self._hook(None, stop_requested)
        self.state = "媒体確認・編集互換変換中"
        return prepare_media(self.data, registered, stop_requested=lambda: self._is_stopping(stop_requested)).editing

    @staticmethod
    def _details(info):
        duration = info.get("duration")
        duration_text = f"{duration}秒" if isinstance(duration, (int, float)) else "長さ不明"
        formats = info.get("formats") or []
        return f"{duration_text}・形式 {len(formats)} 件・{info.get('extractor_key') or '取得元不明'}"
