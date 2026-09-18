"""Prepare a bounded audio excerpt and retain acquisition provenance, not signed URLs."""
import argparse, hashlib, json, subprocess, wave
from pathlib import Path
p=argparse.ArgumentParser(); p.add_argument('--work',type=Path,required=True); p.add_argument('--evidence',type=Path,required=True); a=p.parse_args()
binroot=Path('C:/Users/raimu/AppData/Local/ClipChannelAPP-validation/a106/ffmpeg-mirror/ffmpeg-9.0.1-essentials_build/bin')
source=a.work/'source-20m40m.webm'; audio=a.work/'audio-20m40m.wav'
assert source.is_file() and source.stat().st_size>0
probe=json.loads(subprocess.check_output([str(binroot/'ffprobe.exe'),'-v','error','-show_streams','-show_format','-of','json',str(source)],encoding='utf-8'))
command=[str(binroot/'ffmpeg.exe'),'-hide_banner','-v','error','-nostdin','-n','-i',str(source),'-map','0:a:0','-t','1200','-ac','1','-ar','16000','-c:a','pcm_s16le',str(audio)]
run=subprocess.run(command,capture_output=True,text=True); assert run.returncode==0,run.stderr
with wave.open(str(audio),'rb') as f:
    pcm=dict(sample_rate=f.getframerate(),channels=f.getnchannels(),sample_width=f.getsampwidth(),frames=f.getnframes())
assert pcm==dict(sample_rate=16000,channels=1,sample_width=2,frames=19200000),pcm
def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()
report=dict(video_id='8Xyb7UB3OlM',url='https://www.youtube.com/watch?v=8Xyb7UB3OlM',archive_duration_seconds=25567,availability='public',source_range_seconds=[1200,2400],download_settings=['--ignore-config','--no-playlist','--no-cache-dir','--compat-options no-certifi','format 251/bestaudio','--download-sections *00:20:00-00:40:00','--force-keyframes-at-cuts'],authentication_used=False,format=probe['format'],streams=probe['streams'],pcm=pcm,files={p.name:dict(bytes=p.stat().st_size,sha256=sha(p)) for p in (source,audio)},conversion_exit=run.returncode,conversion_stderr=run.stderr,source_time_mapping='PCM time + 1200s based on accurate-seek re-encoded acquisition request; no independent waveform alignment to full archive',limits=['Audio excerpt only; no new video format or AviUtl2 test','20 minutes is not full 7h06m07s execution','No target/other/overlap ground-truth timestamps supplied'])
for path in (a.work/'acquisition-result.json',a.evidence/'acquisition-result.json'):
    path.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'pcm':pcm,'format_duration':probe['format'].get('duration'),'files':report['files']},ensure_ascii=False),flush=True)
