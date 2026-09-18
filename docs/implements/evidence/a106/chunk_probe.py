"""Compare independent VAD chunks to a full-input baseline, not ground truth."""
import ctypes, json, subprocess, sys, time
from ctypes import wintypes
from pathlib import Path
ROOT=Path('C:/Users/raimu/AppData/Local/ClipChannelAPP-validation/a106')
NAMES=['RWM4SdTZ1t8-180-480','lxYJTSK0y50-420-720']
class Counters(ctypes.Structure):
    _fields_=[('cb',wintypes.DWORD),('PageFaultCount',wintypes.DWORD)]+[(n,ctypes.c_size_t) for n in ['PeakWorkingSetSize','WorkingSetSize','QuotaPeakPagedPoolUsage','QuotaPagedPoolUsage','QuotaPeakNonPagedPoolUsage','QuotaNonPagedPoolUsage','PagefileUsage','PeakPagefileUsage']]
def peak():
    c=Counters(); c.cb=ctypes.sizeof(c)
    fn=ctypes.windll.psapi.GetProcessMemoryInfo
    fn.argtypes=[wintypes.HANDLE,ctypes.POINTER(Counters),wintypes.DWORD]
    ctypes.windll.kernel32.GetCurrentProcess.restype=wintypes.HANDLE
    assert fn(ctypes.windll.kernel32.GetCurrentProcess(),ctypes.byref(c),c.cb)
    return c.PeakWorkingSetSize
if len(sys.argv)>1:
    name,mode=sys.argv[1:3]
    import torch, soundfile as sf
    from silero_vad import load_silero_vad,get_speech_timestamps
    started=time.perf_counter(); model=load_silero_vad(); intervals=[]; max_samples=0
    with sf.SoundFile(ROOT/(name+'-corrected.wav')) as f:
        sr=f.samplerate; length=len(f); assert sr==16000 and length==300*sr
        size=length if mode=='full' else 30*sr
        overlap=sr if mode=='overlap' else 0
        for core in range(0,length,size):
            end=min(length,core+size); lo=max(0,core-overlap); hi=min(length,end+overlap)
            f.seek(lo); audio=f.read(hi-lo,dtype='float32'); max_samples=max(max_samples,len(audio))
            parts=get_speech_timestamps(torch.from_numpy(audio),model,sampling_rate=sr,threshold=.5,min_speech_duration_ms=250,min_silence_duration_ms=100,speech_pad_ms=30)
            for s in parts:
                # Half-open ownership prevents duplicate samples in overlap regions.
                a=max(core,lo+s['start']); b=min(end,lo+s['end'])
                if b>a: intervals.append([a,b])
    assert all(0<=a<b<=length for a,b in intervals)
    assert all(intervals[i][1]<=intervals[i+1][0] for i in range(len(intervals)-1))
    result=dict(name=name,mode=mode,sample_rate=sr,samples=length,intervals=intervals,max_pcm_samples=max_samples,peak_working_set_bytes=peak(),elapsed_seconds=time.perf_counter()-started)
    (ROOT/f'chunk-{name}-{mode}.json').write_text(json.dumps(result,indent=2))
    sys.exit(0)
rows=[]
for name in NAMES:
    cases={}
    for mode in ['full','independent','overlap']:
        subprocess.run([sys.executable,__file__,name,mode],check=True)
        cases[mode]=json.loads((ROOT/f'chunk-{name}-{mode}.json').read_text())
    import numpy as np
    def mask(case):
        m=np.zeros(case['samples'],dtype=bool)
        for a,b in case['intervals']:m[a:b]=True
        return m
    baseline=mask(cases['full'])
    for mode,c in cases.items():
        m=mask(c); c['interval_count']=len(c['intervals']); c['speech_seconds']=float(m.sum()/16000)
        c['baseline_only_seconds']=float((baseline & ~m).sum()/16000)
        c['chunk_only_seconds']=float((m & ~baseline).sum()/16000)
        c['different_seconds']=float((m ^ baseline).sum()/16000)
        rows.append(c)
result=dict(scope='5-minute VAD only; full input is comparison baseline, not truth; no ASR chunk joining validated',rows=rows)
(ROOT/'chunk-comparison.json').write_text(json.dumps(result,indent=2))
for c in rows: print(json.dumps({k:v for k,v in c.items() if k!='intervals'}))
