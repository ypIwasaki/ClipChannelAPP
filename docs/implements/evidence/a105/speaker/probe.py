import os, sys, json, time, hashlib, socket, importlib.metadata, ctypes
from pathlib import Path
ROOT = Path(__file__).parent
os.environ['HF_HUB_OFFLINE'] = '1'
os.environ['TRANSFORMERS_OFFLINE'] = '1'
os.environ['HF_HOME'] = str(ROOT / 'hf-cache')
network_attempts = []
def deny_network(*args, **kwargs):
    network_attempts.append(repr(args))
    raise RuntimeError('Network disabled in verification process')
socket.socket.connect = deny_network
socket.socket.connect_ex = deny_network
socket.create_connection = deny_network
started = time.perf_counter()
import torch
from speechbrain.inference.classifiers import EncoderClassifier
from speechbrain.utils.fetching import LocalStrategy, FetchConfig
model_dir = ROOT / 'model'
model = EncoderClassifier.from_hparams(source=str(model_dir), savedir=str(ROOT / 'loaded-model'), overrides={'pretrained_path': model_dir.as_posix()}, run_opts={'device': 'cpu'}, local_strategy=LocalStrategy.COPY, fetch_config=FetchConfig(allow_network=False))
load_seconds = time.perf_counter() - started
torch.set_num_threads(4)
torch.manual_seed(105)
t = torch.arange(32000, dtype=torch.float32) / 16000
waveform = (0.1 * torch.sin(2 * torch.pi * 220 * t) + 0.03 * torch.sin(2 * torch.pi * 440 * t)).unsqueeze(0)
start_encode = time.perf_counter()
with torch.inference_mode():
    embedding = model.encode_batch(waveform, normalize=False)
encode_seconds = time.perf_counter() - start_encode
assert torch.isfinite(embedding).all()
torch.save(embedding, ROOT / 'person-feature.pt')
restored = torch.load(ROOT / 'person-feature.pt', weights_only=True, map_location='cpu')
assert torch.equal(embedding, restored)
result = {'python':sys.version, 'windows':sys.platform, 'admin':bool(ctypes.windll.shell32.IsUserAnAdmin()), 'torch':torch.__version__, 'cuda_build':torch.version.cuda, 'speechbrain':importlib.metadata.version('speechbrain'), 'model_revision':json.loads((ROOT/'model-api.json').read_text(encoding='utf-8-sig'))['sha'], 'input':{'type':'synthetic harmonics, not person speech', 'sample_rate':16000,'samples':32000,'channels':1,'dtype':str(waveform.dtype),'sha256':hashlib.sha256(waveform.numpy().tobytes()).hexdigest()}, 'embedding_shape':list(embedding.shape), 'finite':bool(torch.isfinite(embedding).all()), 'embedding_raw_sha256':hashlib.sha256(embedding.numpy().tobytes()).hexdigest(),'saved_equal':torch.equal(embedding,restored),'load_seconds':load_seconds,'encode_seconds':encode_seconds,'network_attempts':network_attempts,'loaded_files':[{'name':p.name,'symlink':p.is_symlink()} for p in (ROOT/'loaded-model').iterdir()]}
(ROOT/'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps(result,indent=2))
