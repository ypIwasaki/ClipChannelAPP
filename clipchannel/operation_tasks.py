"""Spawn-safe entry points for the application's managed operations."""

from copy import deepcopy

from .archive import archive_video, restore_archive
from .compose import adjacent_frame, compose_video, nearest_frame
from .download import DownloadError
from .media import prepare_media
from .process_control import check_cancelled
from .transcribe import propose_intervals, save_intervals, transcribe_confirmed


def download(control, session, selected=None):
    session.data.running = False

    def report():
        # The session contains no control callbacks and remains safe to pickle.
        control.report(deepcopy(session))

    try:
        if selected is None:
            session.run(report, stop_requested=control.cancelled)
        else:
            session.retry_failed(selected, report, stop_requested=control.cancelled)
    except Exception as error:
        # Extractor exceptions can contain secret query values and source URLs.
        raise DownloadError("取得処理を完了できませんでした。取得済みの成果物は保持しています") from error
    finally:
        report()
    return session


def prepare(control, data, source):
    data.running = False
    control.report("元動画を登録・確認中")
    registered = data.register_video(source, stop_requested=control.cancelled)
    control.report("媒体を確認・準備中")
    return prepare_media(data, registered, stop_requested=control.cancelled)


def propose(control, data, video, model):
    data.running = False
    return propose_intervals(data, video, model, stop=control.cancelled, progress=control.report)


def transcribe(control, data, video, rows, model, *, source_version=None):
    data.running = False
    return transcribe_confirmed(data, video, rows, model, stop=control.cancelled, progress=control.report,
                                source_version=source_version)


def save_review(control, data, video, rows, *, source_version=None):
    data.running = False
    check_cancelled(control.cancelled)
    control.report("確認した区間を保存中")
    return save_intervals(data, video, rows, stop=control.cancelled, source_version=source_version), rows


def compose(control, data, source, segments, order, duration_ms, fps=None):
    data.running = False
    return compose_video(data, source, segments, order, duration_ms, fps=fps,
                         stop_requested=control.cancelled, progress=control.report)


def align_frames(control, source, requested_times):
    control.report("フレーム境界を確認中")
    return [nearest_frame(source, value, stop_requested=control.cancelled) for value in requested_times]


def step_frame(control, source, requested, direction):
    control.report("隣のフレームを確認中")
    return adjacent_frame(source, requested, direction, stop_requested=control.cancelled)


def archive(control, data, source):
    data.running = False
    control.report("元動画を保持して圧縮・検証中")
    return archive_video(data, source, stop_requested=control.cancelled)


def restore(control, data, source):
    data.running = False
    control.report("保管物を保持して展開・検証中")
    return restore_archive(data, source, stop_requested=control.cancelled)
