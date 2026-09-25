"""Reproducible, local Issue 18 verification over one registered video.

Run the stages in order with Windows Python environments that provide
SpeechBrain, faster-whisper, and SudachiPy respectively. Configuration is read
from a JSON file outside the repository; no media or model is committed.
"""

import hashlib
import json
import os
import subprocess
import sys
import threading
import time
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from clipchannel.people import register_person, select_target
from clipchannel.storage import DataFolder
from clipchannel.transcribe import Interval, load_intervals, propose_intervals, save_intervals, transcribe_confirmed


def main():
    config = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    stage = sys.argv[2]
    root = Path(config["root"])
    root.mkdir(parents=True, exist_ok=True)
    data = DataFolder()
    dataset = root / "data"
    dataset.mkdir(exist_ok=True)
    data.select(dataset)
    state_path = root / "state.json"
    state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {"steps": []}
    ffmpeg_bin = Path(config["ffmpeg_bin"])
    os.environ["PATH"] = str(ffmpeg_bin) + os.pathsep + os.environ["PATH"]
    os.environ["CLIPCHANNEL_FFMPEG"] = str(ffmpeg_bin / "ffmpeg.exe")

    def record(name, **details):
        state["steps"].append({"name": name, **details})
        state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        print(name, json.dumps(details, ensure_ascii=False, default=str), flush=True)

    video = Path(state["video"]) if "video" in state else None
    if stage == "speaker":
        source = Path(config["source"])
        video = data.register_video(source)
        state["video"] = str(video)
        assert hashlib.sha256(source.read_bytes()).digest() == hashlib.sha256(video.read_bytes()).digest()
        record("register", source=str(source), video=str(video), sha256=hashlib.sha256(video.read_bytes()).hexdigest())
        person = register_person(data, "検証話者", Path(config["reference"]), Path(config["speaker_model"]), 0.25, "whole-reference")
        select_target(data, video, person.person_id)
        started = time.monotonic()
        proposals = propose_intervals(data, video, Path(config["speaker_model"]))
        proposed = save_intervals(data, video, proposals)
        record("speaker-review", person_id=person.person_id, proposal_csv=str(proposed),
               windows=[asdict(row) for row in proposals], elapsed_seconds=round(time.monotonic() - started, 3))
        # This automation uses the same-source reference as a provisional
        # confirmation. Human listening remains a separate verification item.
        reviewed = [Interval(row.start_ms, row.end_ms, "target", row.score) for row in proposals]
        confirmed = save_intervals(data, video, reviewed, source_version=1)
        record("confirm-target", transcript_csv=str(confirmed), version=2,
               reviewed_windows=[asdict(row) for row in reviewed])
    elif stage == "asr":
        assert video is not None
        reviewed = load_intervals(data, video, 2)
        started = time.monotonic()
        path, rows = transcribe_confirmed(data, video, reviewed, Path(config["asr_model"]), source_version=2)
        assert any(row.state == "target" and row.text for row in rows)
        record("asr", transcript_csv=str(path), version=3, utterances=[asdict(row) for row in rows if row.text],
               elapsed_seconds=round(time.monotonic() - started, 3))
        # Exercise the user's correction and saved reload without claiming an
        # independently verified word-for-word transcription.
        index = next(i for i, row in enumerate(rows) if row.state == "target" and row.text)
        original = rows[index]
        corrected_text = original.text.rstrip("。") + "。"
        corrected = list(rows)
        corrected[index] = Interval(original.start_ms, original.end_ms, original.state, original.score, corrected_text)
        corrected_path = save_intervals(data, video, corrected, source_version=3)
        assert load_intervals(data, video, 4)[index].text == corrected_text
        record("manual-correction", transcript_csv=str(corrected_path), version=4,
               before=original.text, after=corrected_text, reloaded=True)
    elif stage == "words":
        assert video is not None
        from clipchannel.word_counts import count_words
        path = count_words(data, video, 4)
        words = data.load_result(video, "word-counts", 1)
        assert words
        chosen = words[0]
        matching = [row for row in words if row["word"] == chosen["word"]]
        assert len(matching) == int(chosen["utterances"])
        record("frequent-word", csv=str(path), word=chosen["word"], occurrences=chosen["occurrences"],
               utterances=chosen["utterances"], seek_ms=chosen["start_ms"], matching=matching)
    elif stage == "seek":
        assert video is not None
        word = next(step for step in state["steps"] if step["name"] == "frequent-word")
        frame = root / "word-seek.png"
        subprocess.run([str(ffmpeg_bin / "ffmpeg.exe"), "-v", "error", "-ss",
            str(int(word["seek_ms"]) / 1000), "-i", str(video), "-frames:v", "1", "-y", str(frame)], check=True)
        assert frame.is_file() and frame.stat().st_size > 0
        record("word-video-seek", seek_ms=word["seek_ms"], frame=str(frame),
               frame_sha256=hashlib.sha256(frame.read_bytes()).hexdigest())
    elif stage == "edit":
        assert video is not None
        from clipchannel.compose import compose_video
        from clipchannel.editor_bridge import apply_subtitles
        from clipchannel.save_export import ExportSettings, export_video, inspect_project, save_project
        from clipchannel.segments import candidates_from_transcript, load_segments, save_segments, Segment
        from clipchannel.subtitles import prepare_subtitle_import
        ffprobe = json.loads(subprocess.check_output([str(ffmpeg_bin / "ffprobe.exe"), "-v", "error", "-show_format", "-of", "json", str(video)]))
        duration_ms = round(float(ffprobe["format"]["duration"]) * 1000)
        candidates = candidates_from_transcript(data, video, 4, duration_ms)
        candidate_path = save_segments(data, video, candidates, duration_ms)
        # Explicitly adjust one boundary and retain two ranges in the same
        # registered video. Human visual selection remains to be verified.
        target_rows = [row for row in load_intervals(data, video, 4) if row.state == "target" and row.text]
        assert target_rows
        first = target_rows[0]
        last = target_rows[-1]
        left = Segment(max(0, first.start_ms - 100), min(duration_ms, first.end_ms + 100), "target")
        right = Segment(max(left.end_ms + 100, last.start_ms - 100), min(duration_ms, last.end_ms + 100), "target")
        if right.end_ms <= right.start_ms:
            right = Segment(max(0, duration_ms - 1200), duration_ms - 100, "manual")
        final = [left, right]
        final_path = save_segments(data, video, final, duration_ms)
        assert load_segments(data, video, 2, duration_ms) == final
        record("segments", candidates_csv=str(candidate_path), final_csv=str(final_path),
               candidates=[asdict(row) for row in candidates], selected=[asdict(row) for row in final])
        edit = compose_video(data, video, final, [0, 1], duration_ms)
        metadata = json.loads(edit.with_suffix(".json").read_text(encoding="utf-8"))
        subtitles_path, subtitles = prepare_subtitle_import(data, video, edit, 4)
        assert subtitles
        project = data.path / "projects" / edit.parent.name / (edit.stem + ".aup2")
        record("compose", edit=str(edit), metadata=metadata, project=str(project),
               subtitles=str(subtitles_path), caption_objects=[asdict(row) for row in subtitles])
        host = subprocess.Popen([config["host"], str(project)])
        try:
            deadline = time.monotonic() + 30
            while True:
                try:
                    inspected = inspect_project(project, edit)
                    break
                except Exception:
                    if time.monotonic() > deadline or host.poll() is not None:
                        raise
                    time.sleep(0.5)
            assert apply_subtitles(subtitles_path)
            saved = save_project(project, edit)
            assert saved.confirmed, saved
            output = data.path / "exports" / "full-flow.mp4"
            rendered = export_video(project, edit, output,
                                    ExportSettings(inspected.width, inspected.height, inspected.fps, 8, 48000),
                                    cancel=threading.Event())
            assert rendered.confirmed, rendered
            inspected_output = json.loads(subprocess.check_output([str(ffmpeg_bin / "ffprobe.exe"), "-v", "error",
                "-count_frames", "-show_streams", "-show_format", "-of", "json", str(output)]))
            assert any(stream.get("codec_name") == "h264" for stream in inspected_output["streams"])
            assert any(stream.get("codec_name") == "aac" for stream in inspected_output["streams"])
            record("save-export", save=asdict(saved), export=asdict(rendered),
                   output_probe=inspected_output, project_contains_caption=bool(subtitles[0].text in project.read_text(encoding="utf-8-sig")))
        finally:
            if host.poll() is None:
                host.terminate()
                host.wait(timeout=10)
    elif stage == "layout":
        from clipchannel.editor_bridge import apply_layout
        from clipchannel.layout import Layout, save_layout
        from clipchannel.save_export import ExportSettings, export_video, inspect_project, save_project
        edit = Path(next(step for step in state["steps"] if step["name"] == "compose")["edit"])
        project = data.path / "projects" / edit.parent.name / (edit.stem + ".aup2")
        host = subprocess.Popen([config["host"], str(project)])
        try:
            deadline = time.monotonic() + 30
            while True:
                try:
                    inspected = inspect_project(project, edit)
                    break
                except Exception:
                    if time.monotonic() > deadline or host.poll() is not None:
                        raise
                    time.sleep(0.5)
            instruction = save_layout(data, edit, Layout(inspected.width, inspected.height,
                subtitle_y=0, subtitle_size=24), inspected.width, inspected.height)
            assert apply_layout(instruction) == "preview"
            saved = save_project(project, edit)
            assert saved.confirmed, saved
            output = data.path / "exports" / "full-flow-layout.mp4"
            rendered = export_video(project, edit, output,
                ExportSettings(inspected.width, inspected.height, inspected.fps, 8, 48000),
                cancel=threading.Event())
            assert rendered.confirmed, rendered
            frame = root / "caption-visible.png"
            subprocess.run([str(ffmpeg_bin / "ffmpeg.exe"), "-v", "error", "-ss", "1", "-i", str(output),
                "-frames:v", "1", "-y", str(frame)], check=True)
            record("layout-export", instruction=str(instruction), save=asdict(saved),
                   export=asdict(rendered), frame=str(frame))
        finally:
            if host.poll() is None:
                host.terminate()
                host.wait(timeout=10)
    else:
        raise ValueError(stage)


if __name__ == "__main__":
    main()
