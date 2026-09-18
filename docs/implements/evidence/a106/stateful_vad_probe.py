"""Keep Silero recurrent state and the 512-sample grid across disk reads."""
import json, time
from pathlib import Path
import torch, soundfile as sf
from silero_vad import load_silero_vad
from silero_vad.utils_vad import get_speech_timestamps_from_probs
ROOT=Path('C:/Users/raimu/AppData/Local/ClipChannelAPP-validation/a106')
NAMES=['RWM4SdTZ1t8-180-480','lxYJTSK0y50-420-720']
results=[]
for name in NAMES:
    begin=time.perf_counter(); model=load_silero_vad(); model.reset_states(); probs=[]
    with sf.SoundFile(ROOT/(name+'-corrected.wav')) as f:
        length=len(f); sr=f.samplerate; assert sr==16000
        while True:
            a=f.read(512,dtype='float32')
            if not len(a): break
            x=torch.from_numpy(a)
            if len(x)<512:x=torch.nn.functional.pad(x,(0,512-len(x)))
            with torch.inference_mode():probs.append(model(x,sr).item())
    parts=get_speech_timestamps_from_probs(probs,sampling_rate=sr,threshold=.5,min_speech_duration_ms=250,min_silence_duration_ms=100,speech_pad_ms=30,audio_length_samples=length)
    intervals=[[s['start'],s['end']] for s in parts]
    baseline=json.loads((ROOT/f'chunk-{name}-full.json').read_text())
    same=intervals==baseline['intervals']; assert same
    results.append(dict(name=name,full_baseline_equal=same,interval_count=len(intervals),pcm_read_samples=512,probability_count=len(probs),elapsed_seconds=time.perf_counter()-begin,intervals=intervals))
(ROOT/'stateful-vad-result.json').write_text(json.dumps(results,indent=2))
for r in results:print(json.dumps({k:v for k,v in r.items() if k!='intervals'}))
