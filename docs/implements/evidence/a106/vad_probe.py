import json, socket, hashlib, time
from pathlib import Path
def deny(*a, **k): raise RuntimeError('offline inference')
socket.socket.connect = deny
socket.create_connection = deny
import torch, soundfile as sf
import silero_vad
from silero_vad import load_silero_vad, get_speech_timestamps
from speechbrain.inference.classifiers import EncoderClassifier
from speechbrain.utils.fetching import LocalStrategy, FetchConfig
root=Path('C:/Users/raimu/AppData/Local/ClipChannelAPP-validation/a106')
modeldir=Path('C:/Users/raimu/AppData/Local/Temp/clipchannel-a105-speaker/model')
started=time.perf_counter()
vad=load_silero_vad(onnx=False)
ecapa=EncoderClassifier.from_hparams(source=str(modeldir),savedir=str(root/'loaded-model'),overrides={'pretrained_path':modeldir.as_posix()},run_opts={'device':'cpu'},local_strategy=LocalStrategy.COPY,fetch_config=FetchConfig(allow_network=False))
reference=torch.load(root/'confirmed-reference.pt',weights_only=True,map_location='cpu')
rows=[]
for name,offset in [('first',180),('second',420)]:
    audio,sr=sf.read(root/f'accurate-{name}.wav',dtype='float32'); assert sr==16000
    stamps=get_speech_timestamps(torch.from_numpy(audio),vad,sampling_rate=sr,threshold=0.5,min_speech_duration_ms=250,min_silence_duration_ms=100,speech_pad_ms=30)
    for i,s in enumerate(stamps):
        part=audio[s['start']:s['end']]
        with torch.inference_mode(): e=ecapa.encode_batch(torch.from_numpy(part).unsqueeze(0),normalize=False).reshape(-1)
        assert torch.isfinite(e).all()
        out=root/f'vad-{name}-{i:02}.wav'; sf.write(out,part,sr,subtype='PCM_16')
        rows.append(dict(file=out.name,input=name,start_sample=s['start'],end_sample=s['end'],source_start=offset+s['start']/sr,source_end=offset+s['end']/sr,cosine=float(torch.nn.functional.cosine_similarity(reference,e,dim=0)),label='target-only per user A107; not automatic classification'))
weight=Path(silero_vad.__file__).parent/'data/silero_vad.jit'
result=dict(silero_version='6.2.2',weight_sha256=hashlib.sha256(weight.read_bytes()).hexdigest(),settings=dict(threshold=0.5,min_speech_duration_ms=250,min_silence_duration_ms=100,speech_pad_ms=30,sampling_rate=16000),elapsed_seconds=time.perf_counter()-started,segments=rows)
(root/'vad-result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps(result,indent=2))
