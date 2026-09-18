"""A107 confirmed-positive reuse probe; no classifier threshold is selected."""
import argparse, hashlib, json, os, socket
from pathlib import Path
p = argparse.ArgumentParser()
p.add_argument('--work', type=Path, required=True)
p.add_argument('--model', type=Path, required=True)
a = p.parse_args()
os.environ['HF_HUB_OFFLINE'] = '1'
os.environ['HF_HOME'] = str(a.work / 'hf-cache')
def deny(*args, **kwargs):
    raise RuntimeError('Network disabled during probe')
socket.socket.connect = deny
socket.socket.connect_ex = deny
socket.create_connection = deny
import soundfile as sf
import torch
from speechbrain.inference.classifiers import EncoderClassifier
from speechbrain.utils.fetching import LocalStrategy, FetchConfig
torch.set_num_threads(4)
model = EncoderClassifier.from_hparams(
    source=str(a.model), savedir=str(a.work / 'loaded-model'),
    overrides={'pretrained_path': a.model.as_posix()},
    run_opts={'device': 'cpu'}, local_strategy=LocalStrategy.COPY,
    fetch_config=FetchConfig(allow_network=False))
def encode(x):
    with torch.inference_mode():
        e = model.encode_batch(torch.from_numpy(x).unsqueeze(0), normalize=False).reshape(-1)
    assert e.shape == (192,) and torch.isfinite(e).all()
    return e
ref, sr = sf.read(a.work / 'accurate-first.wav', dtype='float32')
test, tr = sf.read(a.work / 'accurate-second.wav', dtype='float32')
assert sr == tr == 16000 and ref.ndim == test.ndim == 1
assert len(ref) == len(test) == 320000
feature = encode(ref)
torch.save(feature, a.work / 'confirmed-reference.pt')
del feature
restored = torch.load(a.work / 'confirmed-reference.pt', weights_only=True, map_location='cpu')
def score(e):
    return float(torch.nn.functional.cosine_similarity(restored, e, dim=0))
result = {
    'person_name': '変幻リメ', 'label_source': 'user A107',
    'reference': {'video': 'RWM4SdTZ1t8', 'start': 180, 'end': 200},
    'positive_test': {'video': 'lxYJTSK0y50', 'start': 420, 'end': 440},
    'model_revision': '0f99f2d0ebe89ac095bcc5903c4dd8f72b367286',
    'preprocessing': '16kHz mono float32; encode_batch normalize=False; cosine comparison',
    'reference_feature_shape': list(restored.shape),
    'reload_equal_to_recomputed': bool(torch.equal(restored, encode(ref))),
    'positive_20s_cosine': score(encode(test)),
    'positive_5s_windows': [{'source_start':420+i*5,'source_end':425+i*5,
        'cosine':score(encode(test[i*80000:(i+1)*80000]))} for i in range(4)],
    'audio_sha256': {n:hashlib.sha256((a.work/n).read_bytes()).hexdigest()
                     for n in ['accurate-first.wav','accurate-second.wav']},
    'threshold': None, 'negative_examples': 0,
    'limits': 'Single confirmed person, two recordings. No accuracy, false-positive, VAD or ASR verdict.'}
assert result['reload_equal_to_recomputed']
(a.work/'confirmed-reuse.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(result,ensure_ascii=False,indent=2))
