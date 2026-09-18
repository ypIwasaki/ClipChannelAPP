from pathlib import Path
import subprocess,json
import numpy as np
root=Path(r'C:\Users\raimu\AppData\Local\Temp\clipchannel-a105-editor-6f349375')
ff=Path(r'C:\Users\raimu\AppData\Local\ClipChannelAPP-validation\a106\ffmpeg-mirror\ffmpeg-9.0.1-essentials_build\bin\ffmpeg.exe')
mask=np.ones((90,160),bool);mask[32:58,34:126]=False
def decode(path,count):
 raw=subprocess.check_output([str(ff),'-v','error','-i',str(path),'-map','0:v:0','-vf','scale=160:90','-frames:v',str(count),'-fps_mode','passthrough','-pix_fmt','gray','-f','rawvideo','-'])
 arr=np.frombuffer(raw,np.uint8).reshape(-1,90,160)[:,mask].astype(np.float32)
 arr-=arr.mean(axis=1,keepdims=True);arr/=np.sqrt((arr*arr).sum(axis=1,keepdims=True));return arr
src=decode(root/'input-check/corrected.mp4',482);out=decode(root/'group-pair-output-8s.avi',240)
matches=[]
for n,row in enumerate(out):
 expected=240+2*(n%120);lo=expected-2;hi=expected+3;scores=src[lo:hi]@row;order=np.argsort(scores)[::-1];best=lo+int(order[0])
 matches.append({'output_frame':n,'expected_source_frame':expected,'best_source_frame':best,'delta':best-expected,'score':float(scores[order[0]]),'margin':float(scores[order[0]]-scores[order[1]])})
report={'method':'Grayscale 160x90, central subtitle region excluded, mean/L2 normalization, local cosine +/-2 source frames','offset_histogram':{str(d):sum(m['delta']==d for m in matches) for d in range(-2,3)},'min_score':min(m['score'] for m in matches),'matches':matches}
Path('docs/implements/evidence/editor-normal/group-pair-frame-matches.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(report['offset_histogram'],report['min_score'])
