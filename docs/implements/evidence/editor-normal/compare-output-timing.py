import json, subprocess, hashlib
from pathlib import Path
import numpy as np
from scipy.signal import correlate
root=Path(r'C:\Users\raimu\AppData\Local\Temp\clipchannel-a105-editor-6f349375')
bin=Path(r'C:\Users\raimu\AppData\Local\ClipChannelAPP-validation\a106\ffmpeg-mirror\ffmpeg-9.0.1-essentials_build\bin')
def run(args):
    p=subprocess.run([str(bin/'ffmpeg.exe'),'-v','error',*args],capture_output=True,check=True)
    if p.stderr: raise RuntimeError(p.stderr.decode(errors='replace'))
    return p.stdout
def audio(path,secs):
    return np.frombuffer(run(['-i',str(path),'-t',str(secs),'-map','0:a:0','-ac','1','-ar','16000','-f','f32le','-']),dtype='<f4').astype(np.float64)
def video(path,count):
    return np.frombuffer(run(['-i',str(path),'-map','0:v:0','-vf','scale=80:45','-frames:v',str(count),'-fps_mode','passthrough','-pix_fmt','gray','-f','rawvideo','-']),dtype=np.uint8).reshape(-1,45,80)
results={'method':{'audio':'FFmpeg decode to mono 16k float32; normalized correlation of output seconds 1..7 against source first 20 seconds; inferred origin = match time - 1 second','video':'FFmpeg gray 80x45 decode; MSE match selected output frames against first 1200 source frames; decoded source frame index, not container timestamp'},'cases':[]}
for kind,ext in [('original','mkv'),('corrected','mp4')]:
    src=root/'input-check'/f'{kind}.{ext}'
    dst=root/f'timing-{kind}-8s.avi'
    probe=json.loads(subprocess.check_output([str(bin/'ffprobe.exe'),'-v','error','-show_streams','-show_format','-of','json',str(dst)]))
    a=audio(src,20); b=audio(dst,8)
    template=b[16000:7*16000]; template=template-template.mean()
    dots=correlate(a,template,mode='valid',method='fft')
    n=len(template); cs=np.r_[0,np.cumsum(a)]; cs2=np.r_[0,np.cumsum(a*a)]
    variance=cs2[n:]-cs2[:-n]-(cs[n:]-cs[:-n])**2/n
    scores=dots/np.sqrt(np.maximum(variance,1e-20)*np.dot(template,template))
    match=int(np.argmax(scores))
    av=video(src,1200); bv=video(dst,240)
    frames=[]
    for idx in [0,30,90,180,239]:
        error=np.mean((av.astype(np.float32)-bv[idx].astype(np.float32))**2,axis=(1,2))
        best=int(np.argmin(error))
        frames.append({'output_frame':idx,'output_time':idx/30,'source_decoded_frame':best,'source_time_from_first_video_frame':best/60,'mse':float(error[best])})
    results['cases'].append({'kind':kind,'output_sha256':hashlib.sha256(dst.read_bytes()).hexdigest(),'output_bytes':dst.stat().st_size,'probe':probe,'audio_output_samples_16k':len(b),'audio_match_source_sample':match,'audio_inferred_origin_seconds':match/16000-1,'audio_correlation':float(scores[match]),'video_output_frames':len(bv),'frame_matches':frames})
    print(kind,'audio origin',match/16000-1,'correlation',scores[match],'frames',frames,flush=True)
Path('docs/implements/evidence/editor-normal/lsmash-output-timing.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')