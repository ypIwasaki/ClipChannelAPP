from pathlib import Path
import subprocess,re,time,json
p=Path('docs/implements/evidence/editor-normal');r=Path(r'C:/Users/raimu/AppData/Local/Temp/clipchannel-a105-editor-6f349375')
ff=Path(r'C:/Users/raimu/AppData/Local/ClipChannelAPP-validation/a106/ffmpeg-mirror/ffmpeg-9.0.1-essentials_build/bin/ffmpeg.exe')
f=r/'real-trim4.mp4'
assert not f.exists()
t=time.perf_counter()
subprocess.run([str(ff),'-v','error','-i',str(r/'input-check/corrected.mp4'),'-vf','trim=start_frame=240:end_frame=480,setpts=PTS-STARTPTS','-af','atrim=start=4:end=8,asetpts=PTS-STARTPTS','-c:v','libx264','-crf','18','-preset','veryfast','-pix_fmt','yuv420p','-c:a','aac',str(f)],check=True)
elapsed=time.perf_counter()-t
s=(p/'frame-counter-normalized-host.aup2').read_text(encoding='utf-8-sig').split('[1]')[0]
s=re.sub(r'^file=.*$',lambda _:f'file={r}/real-normalized.aup2',s,flags=re.M)
s=re.sub(r'^output.file=.*$',lambda _:f'output.file={r}/real-normalized-output.avi',s,flags=re.M)
s=re.sub(r'^ファイル=.*$',lambda _:f'ファイル={f}',s,flags=re.M)
for target in [r/'real-normalized.aup2',p/'real-normalized-generated.aup2']:target.write_text(s,encoding='utf-8')
report={'source':'input-check/corrected.mp4','source_frames':'240..479','source_audio_seconds':'4..8','encode_seconds':elapsed,'bytes':f.stat().st_size,'settings':'libx264 CRF18 veryfast yuv420p; AAC default bitrate; reset video/audio PTS to zero'}
(p/'real-normalized-build.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(report)
