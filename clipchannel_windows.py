"""Entry point for the self-contained Windows folder build."""

import os
import sys
import json
import tempfile
from multiprocessing import freeze_support
from pathlib import Path


def main():
    freeze_support()
    if sys.platform != "win32":
        raise SystemExit("This launcher is for Windows only")
    tools = Path(sys.executable).resolve().parent / "tools"
    if not all((tools / name).is_file() for name in ("ffmpeg.exe", "ffprobe.exe", "ffplay.exe")):
        raise SystemExit("The tools folder must contain ffmpeg.exe, ffprobe.exe and ffplay.exe")
    os.environ["PATH"] = str(tools) + os.pathsep + os.environ.get("PATH", "")
    os.environ["CLIPCHANNEL_FFMPEG"] = str(tools / "ffmpeg.exe")
    if len(sys.argv) == 3 and sys.argv[1] == "--check-speaker-model":
        result = Path(sys.argv[2])
        try:
            import torch
            from speechbrain.inference.classifiers import EncoderClassifier
            from speechbrain.utils.fetching import FetchConfig, LocalStrategy
            model_dir = Path(sys.executable).resolve().parent / "models" / "ecapa"
            with tempfile.TemporaryDirectory() as cache:
                model = EncoderClassifier.from_hparams(
                    source=str(model_dir), savedir=cache,
                    overrides={"pretrained_path": model_dir.as_posix()},
                    run_opts={"device": "cpu"}, local_strategy=LocalStrategy.COPY,
                    fetch_config=FetchConfig(allow_network=False))
                shape = tuple(model.encode_batch(torch.zeros(1, 32000)).shape)
            result.write_text(json.dumps({"shape": shape}), encoding="utf-8")
        except Exception as error:
            result.write_text(json.dumps({"error": str(error)}), encoding="utf-8")
        return
    from clipchannel.app import main as run_app
    run_app()


if __name__ == "__main__":
    main()
