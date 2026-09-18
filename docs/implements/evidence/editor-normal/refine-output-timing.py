import json,subprocess
from pathlib import Path
import numpy as np
from scipy.signal import correlate
root=Path(r'C:\Users\raimu\AppData\Local\Temp\clipchannel-a105-editor-6f349375')
ff=Path(r'C:\Users\raimu\AppData\Local\ClipChannelAPP-validation\a106\ffmpeg-mirror\ffmpeg-9.0.1-essentials_build\bin')
def decode(path,args):
 p=subprocess.run([str(ff/'ffmpeg.exe'),'-v','error','-i',str(path),*args],capture_output=True,check=True)
 if p.stderr: raise RuntimeError(p.stderr.decode(errors='replace'))
 return p.stdout
def pcm(path,seconds):
 return np.frombuffer(decode(path,['-t',str(seconds),'-map','0:a:0','-ac','1','-ar','44100','-f','f32le','-']),dtype='<f4').astype(float)
def frames(path,count):
 a=np.frombuffer(decode(path,['-map','0:v:0','-vf','scale=160:90','-frames:v',str(count),'-fps_mode','passthrough','-pix_fmt','gray','-f','rawvideo','-']),dtype='u1').reshape(-1,160*90).astype(np.float32)
 a-=a.mean(axis=1,keepdims=True)
 a/=np.sqrt((a*a).sum(axis=1,keepdims=True))
 return a
report={'audio_rate':44100,'video_method':'160x90 grayscale, per-frame mean subtraction and L2 normalization, cosine match within expected source frame +/-2; not exact pixel identity','cases':[]}
for kind,ext in [('original','mkv'),('corrected','mp4')]:
 src=root/'input-check'/f'{kind}.{ext}'; out=root/f'timing-{kind}-8s.avi'
 a=pcm(src,16); b=pcm(out,8); measurements=[]
 for start in [1,3,5]:
  t=b[start*44100:(start+2)*44100]; t-=t.mean(); n=len(t)
  sums=np.r_[0,np.cumsum(a)]; squares=np.r_[0,np.cumsum(a*a)]
  var=squares[n:]-squares[:-n]-(sums[n:]-sums[:-n])**2/n
  score=correlate(a,t,mode='valid',method='fft')/np.sqrt(np.maximum(var,1e-20)*np.dot(t,t))
  at=int(np.argmax(score)); measurements.append({'output_window':[start,start+2],'source_match_sample':at,'origin_seconds':at/44100-start,'correlation':float(score[at])})
 av=frames(src,482); bv=frames(out,240); matches=[]
 for i,row in enumerate(bv):
  lo=max(0,2*i-2); hi=min(len(av),2*i+3); scores=av[lo:hi]@row; order=np.argsort(scores)[::-1]
  best=lo+int(order[0]); matches.append({'output_frame':i,'source_frame':best,'delta_from_2n':best-2*i,'score':float(scores[order[0]]),'runner_up_margin':float(scores[order[0]]-scores[order[1]])})
 first=json.loads(subprocess.check_output([str(ff/'ffprobe.exe'),'-v','error','-select_streams','a:0','-read_intervals','%+#3','-show_frames','-show_entries','frame=pts_time,nb_samples','-of','json',str(src)]))
 histogram={str(d):sum(x['delta_from_2n']==d for x in matches) for d in range(-2,3)}
 case={'kind':kind,'first_audio_frames':first,'audio_windows':measurements,'video_offset_histogram':histogram,'video_matches':matches}
 report['cases'].append(case)
 print(kind,measurements,histogram,'min score',min(x['score'] for x in matches),flush=True)
Path('docs/implements/evidence/editor-normal/lsmash-timing-refinement.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')