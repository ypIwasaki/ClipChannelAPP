"""Fixed-input ASR boundary comparison, not transcription accuracy scoring."""
import json, os, time, wave
from pathlib import Path
root=Path('C:/Users/raimu/AppData/Local/ClipChannelAPP-validation/a106')
modelroot=Path('C:/Users/raimu/AppData/Local/ClipChannelAPP-validation/asr-probe/model')
os.environ['HF_HUB_OFFLINE']='1'
from faster_whisper import WhisperModel
import numpy as np
with wave.open(str(root/'accurate-second.wav'),'rb') as f:
    rate=f.getframerate(); assert rate==16000 and f.getnchannels()==1 and f.getsampwidth()==2
    audio=np.frombuffer(f.readframes(f.getnframes()),dtype='<i2').astype(np.float32)/32768
assert len(audio)==20*rate
begin=time.perf_counter()
model=WhisperModel(str(modelroot),device='cpu',compute_type='int8',cpu_threads=4,local_files_only=True)
results=[]
for mode,pieces in [('full',[(0,20,0,20)]),('split',[(0,10,0,10),(10,20,10,20)]),('overlap',[(0,11,0,10),(9,20,10,20)])]:
    for lo,hi,core_lo,core_hi in pieces:
        started=time.perf_counter()
        segments,_=model.transcribe(audio[int(lo*rate):int(hi*rate)],language='ja',beam_size=5,temperature=0,condition_on_previous_text=False,vad_filter=False,word_timestamps=True)
        words=[]; text=[]
        for s in segments:
            assert 0<=s.start<=s.end<=hi-lo+.1
            text.append(dict(start=lo+s.start,end=lo+s.end,text=s.text))
            for w in s.words or []:
                start=float(lo+w.start); end=float(lo+w.end)
                # Experimental ownership: midpoint, no deletion from raw results.
                owned=core_lo <= (start+end)/2 < core_hi
                words.append(dict(start=start,end=end,source_start=420+start,source_end=420+end,text=w.word,owned=owned,crosses_core_boundary=start<core_lo or end>core_hi))
        results.append(dict(mode=mode,read_start=lo,read_end=hi,core_start=core_lo,core_end=core_hi,segments=text,words=words,elapsed_seconds=time.perf_counter()-started))
        result=dict(model_revision='edaa852ec7e145841d8ffdb056a99866b5f0a478',input='accurate-second.wav',source_offset=420,settings=dict(language='ja',beam_size=5,temperature=0,compute_type='int8',cpu_threads=4,condition_on_previous_text=False,vad_filter=False,word_timestamps=True),elapsed_seconds=time.perf_counter()-begin,runs=results)
        (root/'asr-boundary-result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        print(f'{mode} {lo}-{hi} done',flush=True)
