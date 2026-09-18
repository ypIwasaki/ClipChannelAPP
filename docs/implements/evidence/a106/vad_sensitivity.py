import json, soundfile as sf, torch, numpy as np
from silero_vad import load_silero_vad,get_speech_timestamps
from pathlib import Path
r=Path('C:/Users/raimu/AppData/Local/ClipChannelAPP-validation/a106'); m=load_silero_vad(); rows=[]
for name in ['first','second']:
 a,s=sf.read(r/f'accurate-{name}.wav',dtype='float32')
 for threshold in [0.5,0.3,0.1]:
  ts=get_speech_timestamps(torch.from_numpy(a),m,sampling_rate=s,threshold=threshold)
  rows.append(dict(input=name,threshold=threshold,rms=float(np.sqrt(np.mean(a*a))),count=len(ts),detected_seconds=sum(x['end']-x['start'] for x in ts)/s,segments=ts))
(r/'vad-sensitivity.json').write_text(json.dumps(rows,indent=2)); print([(x['input'],x['threshold'],x['count'],x['detected_seconds']) for x in rows])
