"""Copy confirmed enrollment to a fresh folder and reuse with external model."""
import hashlib, json, shutil, uuid, os, socket
from pathlib import Path
base=Path('C:/Users/raimu/AppData/Local/ClipChannelAPP-validation')
source=base/'a106'; target=base/('person-transfer-'+uuid.uuid4().hex[:8]); target.mkdir()
names=['accurate-first.wav','confirmed-reference.pt','confirmed-reuse.json']
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
before={n:sha(source/n) for n in names}
for n in names: shutil.copy2(source/n,target/n)
# Metadata is read before ML imports or loading a separately supplied model.
metadata=json.loads((target/'confirmed-reuse.json').read_text(encoding='utf-8'))
assert metadata['person_name']=='変幻リメ'
assert all(sha(target/n)==before[n] for n in names)
os.environ['HF_HUB_OFFLINE']='1'
def deny(*a,**k): raise RuntimeError('offline inference')
socket.socket.connect=deny; socket.create_connection=deny
import torch, soundfile as sf
from speechbrain.inference.classifiers import EncoderClassifier
from speechbrain.utils.fetching import LocalStrategy, FetchConfig
torch.set_num_threads(4)
modeldir=Path('C:/Users/raimu/AppData/Local/Temp/clipchannel-a105-speaker/model')
assert metadata['model_revision']=='0f99f2d0ebe89ac095bcc5903c4dd8f72b367286'
model=EncoderClassifier.from_hparams(source=str(modeldir),savedir=str(source/'loaded-model'),overrides={'pretrained_path':modeldir.as_posix()},run_opts={'device':'cpu'},local_strategy=LocalStrategy.COPY,fetch_config=FetchConfig(allow_network=False))
reference=torch.load(target/'confirmed-reference.pt',weights_only=True,map_location='cpu')
audio,sr=sf.read(source/'accurate-second.wav',dtype='float32'); assert sr==16000
with torch.inference_mode(): query=model.encode_batch(torch.from_numpy(audio).unsqueeze(0),normalize=False).reshape(-1)
score=float(torch.nn.functional.cosine_similarity(reference,query,dim=0))
delta=abs(score-metadata['positive_20s_cosine']); assert delta < 1e-6
result=dict(target=str(target),copied_files=names,hashes=before,source_unchanged=all(sha(source/n)==before[n] for n in names),metadata_read_before_model_load=True,common_model_in_transfer=False,cosine=score,score_delta=delta,scope='same PC and same runtime, different folder; not app import, other-PC compatibility or missing-dependency UI test')
(source/'transfer-result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps(result,indent=2))
