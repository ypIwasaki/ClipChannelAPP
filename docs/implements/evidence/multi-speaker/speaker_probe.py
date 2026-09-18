"""Bounded 20-minute, unlabelled multi-speaker VAD/ECAPA feasibility probe."""
import argparse, hashlib, json, os, socket, time, ctypes
from pathlib import Path
p=argparse.ArgumentParser(); p.add_argument('--work', type=Path, required=True); a=p.parse_args()
os.environ['HF_HUB_OFFLINE']='1'; os.environ['HF_HOME']=str(a.work/'hf-cache')
def deny(*args, **kwargs): raise RuntimeError('Offline inference only')
socket.socket.connect=deny; socket.socket.connect_ex=deny; socket.create_connection=deny
import numpy as np
import torch, soundfile as sf
from silero_vad import load_silero_vad
from silero_vad.utils_vad import get_speech_timestamps_from_probs
from speechbrain.inference.classifiers import EncoderClassifier
from speechbrain.utils.fetching import LocalStrategy, FetchConfig
class Memory(ctypes.Structure):
    _fields_=[('cb',ctypes.c_ulong),('PageFaultCount',ctypes.c_ulong)]+[(n,ctypes.c_size_t) for n in ['PeakWorkingSetSize','WorkingSetSize','QuotaPeakPagedPoolUsage','QuotaPagedPoolUsage','QuotaPeakNonPagedPoolUsage','QuotaNonPagedPoolUsage','PagefileUsage','PeakPagefileUsage']]
def memory():
    m=Memory(); m.cb=ctypes.sizeof(m)
    h=ctypes.windll.kernel32.GetCurrentProcess
    h.restype=ctypes.c_void_p
    q=ctypes.windll.psapi.GetProcessMemoryInfo
    q.argtypes=[ctypes.c_void_p,ctypes.POINTER(Memory),ctypes.c_ulong]
    if not q(h(),ctypes.byref(m),m.cb): raise ctypes.WinError()
    return {'working_set':m.WorkingSetSize,'peak_working_set':m.PeakWorkingSetSize}
def file_hash(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()
def dump(name,data): (a.work/name).write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
begin=time.perf_counter(); torch.set_num_threads(4); sr=16000; offset=1200
wav=a.work/'audio-20m40m.wav'
reference_path=Path('C:/Users/raimu/AppData/Local/ClipChannelAPP-validation/a106/confirmed-reference.pt')
modeldir=Path('C:/Users/raimu/AppData/Local/Temp/clipchannel-a105-speaker/model')
reference=torch.load(reference_path,weights_only=True,map_location='cpu')
vad=load_silero_vad(); vad.reset_states(); probs=[]; readings=[]
with sf.SoundFile(wav) as f:
    length=len(f); assert f.samplerate==sr and f.channels==1; assert length==1200*sr, (length,1200*sr)
    while True:
        audio=f.read(512,dtype='float32')
        if not len(audio): break
        t=torch.from_numpy(audio)
        if len(t)<512:t=torch.nn.functional.pad(t,(0,512-len(t)))
        with torch.inference_mode():probs.append(float(vad(t,sr)))
        if len(probs)%9375==0:
            readings.append({'stage':'vad','seconds':min(len(probs)*512/sr,length/sr),**memory()})
            print('VAD seconds',readings[-1]['seconds'],flush=True)
stamps=get_speech_timestamps_from_probs(probs,sampling_rate=sr,threshold=.5,min_speech_duration_ms=250,min_silence_duration_ms=100,speech_pad_ms=30,audio_length_samples=length)
vad_done=time.perf_counter(); assert all(0<=s['start']<s['end']<=length for s in stamps)
assert all(b['start']>=a['end'] for a,b in zip(stamps,stamps[1:]))
# Each finite local PCM read is <=5 seconds; score all voiced windows, including mixtures.
ecapa=EncoderClassifier.from_hparams(source=str(modeldir),savedir=str(a.work/'loaded-model'),overrides={'pretrained_path':modeldir.as_posix()},run_opts={'device':'cpu'},local_strategy=LocalStrategy.COPY,fetch_config=FetchConfig(allow_network=False))
rows=[]
with sf.SoundFile(wav) as f:
    for start in range(0,length,40000):
        end=min(start+80000,length)
        speech=sum(max(0,min(end,s['end'])-max(start,s['start'])) for s in stamps)
        item={'start_sample':start,'end_sample':end,'source_start':offset+start/sr,'source_end':offset+end/sr,'vad_speech_seconds':speech/sr,'label':'unlabelled','cosine':None}
        if speech>=8000 and end-start>=8000:
            f.seek(start); audio=f.read(end-start,dtype='float32')
            with torch.inference_mode():emb=ecapa.encode_batch(torch.from_numpy(audio).unsqueeze(0),normalize=False).reshape(-1)
            assert emb.shape==(192,) and torch.isfinite(emb).all()
            item['cosine']=float(torch.nn.functional.cosine_similarity(reference,emb,dim=0))
        rows.append(item)
        if len(rows)%60==0:
            readings.append({'stage':'ecapa','windows':len(rows),**memory()}); print('ECAPA windows',len(rows),flush=True)
values=[r['cosine'] for r in rows if r['cosine'] is not None]
# Choose listening examples by score quantiles; these are not identity annotations.
ranked=sorted([r for r in rows if r['cosine'] is not None],key=lambda r:r['cosine']); chosen=[]
for quant in [.05,.25,.5,.75,.95]:
    if ranked:
        r=ranked[round((len(ranked)-1)*quant)]
        clip=a.work/f"listen-{int(r['source_start']*1000):07}.wav"
        with sf.SoundFile(wav) as f:
            f.seek(r['start_sample']); sf.write(clip,f.read(r['end_sample']-r['start_sample'],dtype='float32'),sr,subtype='PCM_16')
        chosen.append({**r,'quantile':quant,'file':str(clip)})
result={'video_id':'8Xyb7UB3OlM','source_range':[1200,2400],'audio_samples':length,'sample_rate':sr,'audio_sha256':file_hash(wav),'reference_sha256':file_hash(reference_path),'reference_user_label':'A107 target-only; RWM4SdTZ1t8 180-200s','model_revision':'0f99f2d0ebe89ac095bcc5903c4dd8f72b367286','settings':{'cpu_threads':4,'vad_threshold':.5,'vad_min_speech_ms':250,'vad_min_silence_ms':100,'vad_pad_ms':30,'window_seconds':5,'stride_seconds':2.5,'min_vad_speech_seconds':.5},'vad_intervals':stamps,'vad_probability_count':len(probs),'vad_speech_seconds':sum(s['end']-s['start'] for s in stamps)/sr,'windows':rows,'score_quantiles':dict(zip(['min','p10','median','p90','max'],map(float,np.quantile(values,[0,.1,.5,.9,1])))) if values else {},'listening_examples':chosen,'vad_elapsed_seconds':vad_done-begin,'total_elapsed_seconds':time.perf_counter()-begin,'memory_samples':readings+[{'stage':'done',**memory()}],'identity_accuracy':None,'classification_threshold':None,'limitations':['No target/non-target/overlap ground truth in new clip; no accuracy or threshold validation','Scores on 5s windows may include mixed speakers, silence, BGM','VAD non-detection is not proof of non-speech; no audio source separation','20-minute excerpt is not full 7-hour execution']}
dump('speaker-result.json',result)
print(json.dumps({k:result[k] for k in ['vad_speech_seconds','score_quantiles','vad_elapsed_seconds','total_elapsed_seconds']},ensure_ascii=False),flush=True)

