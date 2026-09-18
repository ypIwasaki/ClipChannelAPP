from pathlib import Path
import subprocess,json,hashlib
import numpy as np

root=Path(r'C:\Users\raimu\AppData\Local\Temp\clipchannel-a105-editor-6f349375')
evidence=Path('docs/implements/evidence/editor-normal')
bin=Path(r'C:\Users\raimu\AppData\Local\ClipChannelAPP-validation\a106\ffmpeg-mirror\ffmpeg-9.0.1-essentials_build\bin')
source=root/'group-pair-output-8s.avi'
probe=json.loads(subprocess.check_output([str(bin/'ffprobe.exe'),'-v','error','-show_streams','-show_format','-of','json',str(source)]))
(evidence/'group-pair-output-probe.json').write_text(json.dumps(probe,indent=2),encoding='utf-8')
decode=subprocess.run([str(bin/'ffmpeg.exe'),'-v','error','-i',str(source),'-f','null','-'],capture_output=True)
def frames(path):
 raw=subprocess.check_output([str(bin/'ffmpeg.exe'),'-v','error','-i',str(path),'-map','0:v:0','-f','rawvideo','-pix_fmt','rgb24','-'])
 return np.frombuffer(raw,np.uint8).reshape(-1,180,320,3)
a=frames(source);ref=frames(root/'timing-corrected-8s.avi')
mask=np.ones((180,320),bool);mask[65:115,70:250]=False
expected=np.concatenate([ref[120:240],ref[120:240]])
diff=np.abs(a.astype(np.int16)-expected.astype(np.int16))
# Outside the central subtitle region, compare against the same host's prior uncaptioned output.
mae=diff[:,mask,:].mean(axis=(1,2))
audio=np.frombuffer(subprocess.check_output([str(bin/'ffmpeg.exe'),'-v','error','-i',str(source),'-map','0:a:0','-f','s16le','-acodec','pcm_s16le','-']),np.int16).reshape(-1,2)
report={'sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'decode_returncode':decode.returncode,'decode_stderr':decode.stderr.decode(errors='replace'),'video_frames':len(a),'audio_samples_per_channel':len(audio),'comparison':'Against timing-corrected-8s AVI frames 120..239 repeated twice; central subtitle area excluded','outside_subtitle_mae_max':float(mae.max()),'outside_subtitle_mae_mean':float(mae.mean()),'boundary_frame_mae':{str(n):float(mae[n]) for n in [0,119,120,239]},'two_audio_halves_equal':bool(np.array_equal(audio[:176400],audio[176400:])),'subtitle_region_nonzero_diff_frames':int(np.count_nonzero(np.any(diff[:,65:115,70:250,:]>0,axis=(1,2,3))))}
report['nonzero_outside_subtitle_frames']=[int(n) for n in np.where(mae>0)[0]]
report['two_video_halves_outside_subtitle_equal']=bool(np.array_equal(a[:120,mask,:],a[120:,mask,:]))
report['local_best_reference_offsets']={str(int(n)):min(range(max(0,120+int(n)%120-2),min(len(ref),120+int(n)%120+3)),key=lambda k:float(np.abs(a[n,mask,:].astype(np.int16)-ref[k,mask,:].astype(np.int16)).mean()))-(120+int(n)%120) for n in np.where(mae>0)[0]}
(evidence/'group-pair-output-analysis.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report,indent=2))
