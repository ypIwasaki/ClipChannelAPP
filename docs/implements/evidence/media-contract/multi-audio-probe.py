import json, subprocess, tempfile, hashlib, wave, array
from pathlib import Path
E=Path(__file__).resolve().parent
F=Path('C:/Users/raimu/AppData/Local/ClipChannelAPP-validation/a106/ffmpeg-mirror/ffmpeg-9.0.1-essentials_build/bin')
R=Path(tempfile.mkdtemp(prefix='clipchannel-multiaudio-'))
runs=[]
def run(name,args,probe=False):
 p=subprocess.run([str(F/('ffprobe.exe' if probe else 'ffmpeg.exe')),*args],capture_output=True,text=True,encoding='utf-8',errors='replace')
 (E/(name+'.log')).write_text(p.stdout+p.stderr,encoding='utf-8');runs.append({'stage':name,'exit_code':p.returncode});p.check_returncode();return p.stdout
filters=run('filters',['-hide_banner','-filters'])
encoders=run('encoders',['-hide_banner','-encoders'])
src=R/'two-tracks.mkv'
run('create',['-hide_banner','-nostdin','-f','lavfi','-i','testsrc2=size=160x90:rate=30:duration=2','-f','lavfi','-i','sine=frequency=440:sample_rate=48000:duration=2','-f','lavfi','-i','sine=frequency=880:sample_rate=48000:duration=2','-map','0:v:0','-map','1:a:0','-map','2:a:0','-c:v','libx264','-preset','ultrafast','-pix_fmt','yuv420p','-c:a','pcm_s16le','-metadata:s:a:0','title=reference-440Hz','-metadata:s:a:1','title=finished-880Hz',str(src)])
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
before=sha(src)
asr=R/'asr.wav';out=R/'finished.mp4';decoded=R/'finished.wav'
run('select-asr',['-hide_banner','-nostdin','-i',str(src),'-map','0:a:0','-vn','-ac','1','-ar','16000','-c:a','pcm_s16le',str(asr)])
run('select-finished',['-hide_banner','-nostdin','-i',str(src),'-map','0:v:0','-map','0:a:1','-c:v','copy','-c:a','aac','-profile:a','aac_low','-ar','48000',str(out)])
run('decode-finished',['-hide_banner','-nostdin','-i',str(out),'-map','0:a:0','-ac','1','-c:a','pcm_s16le',str(decoded)])
def tone(p):
 with wave.open(str(p),'rb') as w:
  rate=w.getframerate();values=array.array('h',w.readframes(w.getnframes()));duration=len(values)/rate
 # Ignore codec start/end padding and count rising zero crossings in the interior.
 values=values[rate//4:rate*7//4]
 crossings=sum(a<=0<b for a,b in zip(values,values[1:]))
 return {'rate':rate,'duration':duration,'measured_Hz':crossings/(len(values)/rate)}
a,b=tone(asr),tone(decoded)
meta=json.loads(run('probe-finished',['-v','error','-show_streams','-show_format','-of','json',str(out)],True))
audio=[s for s in meta['streams'] if s['codec_type']=='audio']
checks={'zscale_available':' zscale ' in filters,'tonemap_available':' tonemap ' in filters,'libx264_available':' libx264 ' in encoders,'aac_available':' aac ' in encoders,'asr_first_track':abs(a['measured_Hz']-440)<2 and a['rate']==16000,'finished_second_track':abs(b['measured_Hz']-880)<2 and b['rate']==48000,'one_AAC_LC_track':len(audio)==1 and audio[0]['codec_name']=='aac' and audio[0]['profile']=='LC','source_unchanged':sha(src)==before}
result={'local_root':str(R),'source_sha256':before,'asr':a,'finished':b,'checks':checks,'runs':runs,'limits':['Synthetic tones, not speaker recognition.','Both tracks start at zero; offset tracks not tested.','No GUI choice/persistence or AviUtl2 track routing tested.','HDR filters listed only; PQ/HLG color conversion not validated.']}
(E/'multi-audio-result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(result,ensure_ascii=False,indent=2));assert all(checks.values())
