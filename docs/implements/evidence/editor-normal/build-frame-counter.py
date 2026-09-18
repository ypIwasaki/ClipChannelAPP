from pathlib import Path
import subprocess,numpy as np,re,json
root=Path(r'C:\Users\raimu\AppData\Local\Temp\clipchannel-a105-editor-6f349375')
p=Path('docs/implements/evidence/editor-normal')
ff=Path(r'C:\Users\raimu\AppData\Local\ClipChannelAPP-validation\a106\ffmpeg-mirror\ffmpeg-9.0.1-essentials_build\bin\ffmpeg.exe')
video=root/'frame-counter-60.mp4'
if video.exists():raise RuntimeError('fixture exists')
cmd=[str(ff),'-v','error','-f','rawvideo','-pixel_format','gray','-video_size','320x180','-framerate','60','-i','pipe:0','-f','lavfi','-i','anullsrc=r=48000:cl=stereo','-vf','scale=1280:720:flags=neighbor','-c:v','libx264','-preset','veryfast','-crf','18','-pix_fmt','yuv420p','-c:a','aac','-t','8','-shortest',str(video)]
proc=subprocess.Popen(cmd,stdin=subprocess.PIPE,stderr=subprocess.PIPE)
for n in range(480):
 frame=np.zeros((180,320),np.uint8)
 for bit in range(10):frame[:,bit*32:(bit+1)*32]=235 if n&(1<<bit) else 16
 proc.stdin.write(frame.tobytes())
proc.stdin.close();stderr=proc.stderr.read();code=proc.wait()
if code:raise RuntimeError(stderr.decode())
s=(p/'group-pair-ripple-cut.aup2').read_text(encoding='utf-8-sig')
header=s[:s.index('[0]')]
obj=s[s.index('[0]'):s.index('[1]')]
header=re.sub(r'^file=.*$',f'file={root.as_posix()}/frame-counter.aup2',header,flags=re.M)
header=re.sub(r'^output.file=.*$',f'output.file={root.as_posix()}/frame-counter-output.avi',header,flags=re.M)
header=re.sub(r'^cursor.frame=.*$','cursor.frame=0',header,flags=re.M)
obj=re.sub(r'^group=.*\n','',obj,flags=re.M)
obj=re.sub(r'^ファイル=.*$',f'ファイル={video.as_posix()}',obj,flags=re.M)
a=obj.replace('再生位置=4.000,8.000','再生位置=0.000,4.000')
b=re.sub(r'\[0(?=\.|\])','[1',obj).replace('frame=0,119','frame=120,239')
project=header+a+b
(root/'frame-counter.aup2').write_text(project,encoding='utf-8')
(p/'frame-counter-generated.aup2').write_text(project,encoding='utf-8')
print('created',video,video.stat().st_size)
