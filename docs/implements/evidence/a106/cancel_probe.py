"""Disposable worker cancellation test, not application implementation."""
import json, os, subprocess, sys, time, uuid, hashlib
from pathlib import Path
base=Path('C:/Users/raimu/AppData/Local/ClipChannelAPP-validation')
source=base/'a106'
def digest(p): return hashlib.sha256(p.read_bytes()).hexdigest()
if len(sys.argv)>1:
    work=Path(sys.argv[1])
    os.environ['HF_HUB_OFFLINE']='1'
    from faster_whisper import WhisperModel
    model=WhisperModel(str(base/'asr-probe/model'),device='cpu',compute_type='int8',cpu_threads=4,local_files_only=True)
    segments,_=model.transcribe(str(source/'accurate-first.wav'),language='ja',beam_size=5,temperature=0,vad_filter=False)
    (work/'running').write_text('before consuming lazy inference')
    count=0
    for segment in segments:
        if (work/'cancel').exists():
            (work/'worker-result.json').write_text(json.dumps(dict(state='cancelled',segments_published=0,completed_output=False)))
            sys.exit(0)
        count+=1
    (work/'worker-result.json').write_text(json.dumps(dict(state='completed',segments_published=count,completed_output=True)))
    sys.exit(0)
work=base/('cancel-probe-'+uuid.uuid4().hex[:8]); work.mkdir()
protected=[source/'accurate-first.wav',source/'asr-result.json',source/'confirmed-reference.pt']
before={p.name:digest(p) for p in protected}
with (work/'worker.log').open('w') as log:
    child=subprocess.Popen([sys.executable,__file__,str(work)],stdout=log,stderr=log)
    deadline=time.monotonic()+120
    while not (work/'running').exists():
        if child.poll() is not None: raise RuntimeError('worker exited before inference')
        if time.monotonic()>deadline: raise RuntimeError(f'worker start timeout, owned PID {child.pid}')
        time.sleep(.1)
    time.sleep(.5)
    alive_at_request=child.poll() is None
    requested=time.monotonic(); (work/'cancel').write_text('test operator cancellation')
    code=child.wait(timeout=120)
result=json.loads((work/'worker-result.json').read_text())
result.update(exit_code=code,process_exited=child.poll() is not None,alive_at_request=alive_at_request,stop_latency_seconds=time.monotonic()-requested,source_hashes_unchanged=all(digest(p)==before[p.name] for p in protected),work=str(work),mechanism='cooperative check after ASR generator yields; not immediate interruption inside native inference')
assert result['state']=='cancelled' and result['source_hashes_unchanged'] and alive_at_request
(source/'cancel-result.json').write_text(json.dumps(result,indent=2))
print(json.dumps(result,indent=2))
