"""Bounded ECAPA plumbing probe; scores are not speaker labels."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import socket
import time

p = argparse.ArgumentParser()
p.add_argument('--model', type=Path, required=True)
p.add_argument('--work', type=Path, required=True)
a = p.parse_args()
os.environ['HF_HUB_OFFLINE'] = '1'
os.environ['HF_HOME'] = str(a.work / 'hf-cache')
def deny(*args, **kwargs):
    raise RuntimeError('Network disabled during inference')
socket.socket.connect = deny
socket.socket.connect_ex = deny
socket.create_connection = deny
import soundfile as sf
import torch
from speechbrain.inference.classifiers import EncoderClassifier
from speechbrain.utils.fetching import LocalStrategy, FetchConfig

torch.set_num_threads(4)
start = time.perf_counter()
model = EncoderClassifier.from_hparams(
    source=str(a.model), savedir=str(a.work / 'loaded-model'),
    overrides={'pretrained_path': a.model.as_posix()},
    run_opts={'device': 'cpu'}, local_strategy=LocalStrategy.COPY,
    fetch_config=FetchConfig(allow_network=False))
metadata = []
features = []
for name, offset in [('RWM4SdTZ1t8-180-480', 180), ('lxYJTSK0y50-420-720', 420)]:
    path = a.work / (name + '.wav')
    samples, rate = sf.read(path, dtype='float32')
    assert rate == 16000 and samples.ndim == 1
    rows = []
    windows = []
    for n in range(min(30, len(samples) // (10 * rate))):
        waveform = torch.from_numpy(samples[n*10*rate:(n+1)*10*rate]).unsqueeze(0)
        with torch.inference_mode():
            feature = model.encode_batch(waveform, normalize=False).reshape(-1)
        assert feature.shape == (192,) and torch.isfinite(feature).all()
        rows.append(feature)
        windows.append({'relative_start': n*10, 'nominal_source_start': offset+n*10,
                        'seconds': 10, 'rms': float(waveform.square().mean().sqrt())})
    assert rows
    tensor = torch.stack(rows)
    torch.save(tensor, a.work / (name + '.pt'))
    restored = torch.load(a.work / (name + '.pt'), weights_only=True, map_location='cpu')
    assert torch.equal(tensor, restored)
    features.append(restored)
    metadata.append({'id': name, 'sha256_wav': hashlib.sha256(path.read_bytes()).hexdigest(),
                     'duration': len(samples)/rate, 'windows': windows,
                     'shape': list(tensor.shape), 'reload_equal': True})
matrix = torch.nn.functional.normalize(features[0], dim=1) @ torch.nn.functional.normalize(features[1], dim=1).T
assert torch.isfinite(matrix).all()
result = {'purpose': 'unlabelled cross-video feature comparison; no identity/quality verdict',
          'window_seconds': 10, 'vad': False, 'speaker_labels': None,
          'source_times': 'nominal offsets; stream-copy section boundary accuracy not validated',
          'inputs': metadata, 'cosine_matrix': matrix.tolist(),
          'score_min': float(matrix.min()), 'score_max': float(matrix.max()),
          'elapsed_seconds': time.perf_counter()-start}
(a.work / 'comparison.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
print(json.dumps({k:v for k,v in result.items() if k not in ('inputs','cosine_matrix')}, indent=2))
