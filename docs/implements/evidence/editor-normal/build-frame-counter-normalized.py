from pathlib import Path
import subprocess,re
root=Path(r'C:\Users\raimu\AppData\Local\Temp\clipchannel-a105-editor-6f349375');p=Path('docs/implements/evidence/editor-normal')
ff=Path(r'C:\Users\raimu\AppData\Local\ClipChannelAPP-validation\a106\ffmpeg-mirror\ffmpeg-9.0.1-essentials_build\bin\ffmpeg.exe')
clip=root/'frame-counter-trim4.mp4'
if clip.exists():raise RuntimeError('exists')
subprocess.run([str(ff),'-v','error','-i',str(root/'frame-counter-60.mp4'),'-vf','trim=start_frame=240:end_frame=480,setpts=PTS-STARTPTS','-af','atrim=start=4:end=8,asetpts=PTS-STARTPTS','-c:v','libx264','-crf','18','-preset','veryfast','-pix_fmt','yuv420p','-c:a','aac',str(clip)],check=True)
s=(p/'frame-counter-60fps-host.aup2').read_text(encoding='utf-8-sig')
a,b=s.split('[1]',1)
b=b.replace('再生位置=4.000,8.000','再生位置=0.000,4.000')
b=re.sub(r'^ファイル=.*$',lambda _:f'ファイル={clip}',b,flags=re.M)
s=a+'[1]'+b
s=re.sub(r'^file=.*$',lambda _:f'file={root}/frame-counter-normalized.aup2',s,flags=re.M)
s=re.sub(r'^output.file=.*$',lambda _:f'output.file={root}/frame-counter-normalized-output.avi',s,flags=re.M)
for target in [root/'frame-counter-normalized.aup2',p/'frame-counter-normalized-generated.aup2']:
 if target.exists():raise RuntimeError('exists')
 target.write_text(s,encoding='utf-8')
print('Only second clip source changed to normalized 0-second file; source marker values remain 240..479')
