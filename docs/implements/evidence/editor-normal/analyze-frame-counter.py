from pathlib import Path
import subprocess,numpy as np,json,hashlib,sys
root=Path(r'C:\Users\raimu\AppData\Local\Temp\clipchannel-a105-editor-6f349375')
evidence=Path('docs/implements/evidence/editor-normal')
ff=Path(r'C:\Users\raimu\AppData\Local\ClipChannelAPP-validation\a106\ffmpeg-mirror\ffmpeg-9.0.1-essentials_build\bin\ffmpeg.exe')
def codes(path):
 proc=subprocess.run([str(ff),'-v','error','-i',str(path),'-map','0:v:0','-vf','scale=320:180','-fps_mode','passthrough','-pix_fmt','gray','-f','rawvideo','-'],capture_output=True,check=True)
 if proc.stderr:raise RuntimeError(proc.stderr.decode())
 arr=np.frombuffer(proc.stdout,np.uint8).reshape(-1,180,320)
 values=np.array([arr[:,50:130,bit*32+8:bit*32+24].mean(axis=(1,2)) for bit in range(10)]).T
 assert np.all((values<40)|(values>210)),'Ambiguous bit intensity'
 return ((values>128)*(1<<np.arange(10))).sum(axis=1).astype(int)
src=codes(root/'frame-counter-60.mp4');assert np.array_equal(src,np.arange(480)),'Source marker mismatch'
name=sys.argv[1] if len(sys.argv)>1 else 'frame-counter-output.avi'
rate=int(sys.argv[2]) if len(sys.argv)>2 else 30
out=codes(root/name);expected=np.arange(8*rate)*(60//rate);assert len(out)==len(expected)
errors=[{'output_frame':int(n),'clip_frame':int(n%(4*rate)),'expected':int(expected[n]),'actual':int(out[n]),'delta':int(out[n]-expected[n])} for n in np.where(out!=expected)[0]]
report={'output':name,'output_rate':rate,'source_frame_markers_all480_valid':True,'output_count':len(out),'clip0_error_count':sum(e['output_frame']<4*rate for e in errors),'clip4_error_count':sum(e['output_frame']>=4*rate for e in errors),'errors':errors,'sha256':hashlib.sha256((root/name).read_bytes()).hexdigest()}
(evidence/(Path(name).stem+'-analysis.json')).write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report,indent=2))
