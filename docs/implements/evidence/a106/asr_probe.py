import json, os, socket, time
from pathlib import Path
root=Path('C:/Users/raimu/AppData/Local/ClipChannelAPP-validation/a106')
envroot=Path('C:/Users/raimu/AppData/Local/ClipChannelAPP-validation/asr-probe')
os.environ['HF_HUB_OFFLINE']='1'
def deny(*a, **k): raise RuntimeError('offline inference')
socket.socket.connect=deny
socket.create_connection=deny
from faster_whisper import WhisperModel
started=time.perf_counter()
model=WhisperModel(str(envroot/'model'),device='cpu',compute_type='int8',cpu_threads=4,local_files_only=True)
vad=json.loads((root/'vad-result.json').read_text())
vad['segments'].append(dict(file='accurate-first.wav',input='first',start_sample=0,end_sample=320000,source_start=180,source_end=200,label='A107 target-only; diagnostic full-window ASR because VAD returned no segments',diagnostic=True))
rows=[]
for n,item in enumerate(vad['segments']):
    begin=time.perf_counter()
    segments,info=model.transcribe(str(root/item['file']),language='ja',beam_size=5,temperature=0,condition_on_previous_text=False,vad_filter=False,word_timestamps=True)
    duration=(item['end_sample']-item['start_sample'])/16000
    text=[]
    for s in segments:
        assert 0 <= s.start <= s.end <= duration+0.1
        text.append(dict(start=s.start,end=s.end,source_start=item['source_start']+s.start,source_end=item['source_start']+s.end,text=s.text,words=[dict(start=w.start,end=w.end,word=w.word,probability=w.probability) for w in (s.words or [])]))
    rows.append(dict(input=item,asr=text,elapsed_seconds=time.perf_counter()-begin))
    result=dict(model_revision='edaa852ec7e145841d8ffdb056a99866b5f0a478',compute_type='int8',language='ja',beam_size=5,completed=len(rows),total=len(vad['segments']),elapsed_seconds=time.perf_counter()-started,results=rows)
    (root/'asr-result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(f"completed {n+1}/{len(vad['segments'])}",flush=True)
