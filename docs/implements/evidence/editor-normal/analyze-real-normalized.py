from pathlib import Path
import subprocess,json,hashlib
import numpy as np
from scipy.signal import correlate
r=Path(r'C:/Users/raimu/AppData/Local/Temp/clipchannel-a105-editor-6f349375');p=Path('docs/implements/evidence/editor-normal')
ff=Path(r'C:/Users/raimu/AppData/Local/ClipChannelAPP-validation/a106/ffmpeg-mirror/ffmpeg-9.0.1-essentials_build/bin/ffmpeg.exe')
def video(f,count):
 raw=subprocess.check_output([str(ff),'-v','error','-i',str(f),'-vf','scale=160:90','-frames:v',str(count),'-fps_mode','passthrough','-pix_fmt','gray','-f','rawvideo','-'])
 a=np.frombuffer(raw,np.uint8).reshape(-1,90*160).astype(np.float32);a-=a.mean(axis=1,keepdims=True);a/=np.linalg.norm(a,axis=1,keepdims=True);return a
src=video(r/'input-check/corrected.mp4',483);mid=video(r/'real-trim4.mp4',241);out=video(r/'real-normalized-output.avi',241)
rows=[]
for i,a in enumerate(out):
 e=240+i;lo=e-2;sc=src[lo:e+3]@a;order=np.argsort(sc)[::-1]
 rows.append({'frame':i,'expected':e,'best':lo+int(order[0]),'margin':float(sc[order[0]]-sc[order[1]]),'score':float(sc[order[0]])})
def audio(f,seconds):
 raw=subprocess.check_output([str(ff),'-v','error','-i',str(f),'-t',str(seconds),'-vn','-ac','1','-ar','48000','-f','f32le','-']);return np.frombuffer(raw,np.float32)
srca=audio(r/'input-check/corrected.mp4',9);mida=audio(r/'real-trim4.mp4',4);outa=audio(r/'real-normalized-output.avi',4)
checks=[]
for label,reference,origin in [('source',srca,4),('intermediate',mida,0)]:
 for t in [0.25,1.5,2.75]:
  pos=round(t*48000);q=outa[pos:pos+24000].astype(np.float64);q-=q.mean();start=round((origin+t)*48000)-2400
  ref=reference[start:start+len(q)+4800].astype(np.float64)
  scores=correlate(ref,q,mode='valid',method='fft');k=int(np.argmax(scores));candidate=ref[k:k+len(q)];candidate-=candidate.mean()
  checks.append({'reference':label,'output_window_start':t,'offset_samples_from_expected':start+k-round((origin+t)*48000),'correlation':float(np.dot(candidate,q)/(np.linalg.norm(candidate)*np.linalg.norm(q)))})
report={'frames':len(out),'intermediate_frames':len(mid),'frame_mismatch_count':sum(x['expected']!=x['best'] for x in rows),'min_frame_score':min(x['score'] for x in rows),'min_frame_margin':min(x['margin'] for x in rows),'audio_samples_48k':len(outa),'audio_windows':checks,'matches':rows,'output_sha256':hashlib.sha256((r/'real-normalized-output.avi').read_bytes()).hexdigest()}
(p/'real-normalized-analysis.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps({k:v for k,v in report.items() if k!='matches'},indent=2))
assert len(out)==240 and report['frame_mismatch_count']==0
assert all(abs(x['offset_samples_from_expected'])<=1 for x in checks)
