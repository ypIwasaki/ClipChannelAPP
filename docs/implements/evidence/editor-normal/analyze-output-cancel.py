from pathlib import Path
import json,hashlib,subprocess,re
p=Path('docs/implements/evidence/editor-normal')
r=Path(r'C:/Users/raimu/AppData/Local/Temp/clipchannel-a105-editor-6f349375')
ff=Path(r'C:/Users/raimu/AppData/Local/ClipChannelAPP-validation/a106/ffmpeg-mirror/ffmpeg-9.0.1-essentials_build/bin/ffprobe.exe')
f=r/'output-cancel.avi'
probe=json.loads(subprocess.check_output([str(ff),'-v','error','-count_frames','-show_entries','stream=index,codec_name,duration,nb_read_frames','-of','json',str(f)]))
def objects(name):
 s=(p/name).read_text(encoding='utf-8-sig');return s[s.index('[0]\n'):]
a=objects('output-cancel-before.aup2');b=objects('output-cancel-after.aup2')
report={'action':'Requested Escape after starting standard AVI output; observed editor again afterward.','result':'Full 3600-frame 60-second output exists. Cancellation NOT demonstrated; completion/cancel timing is unknown.','probe':probe,'output_bytes':f.stat().st_size,'sha256':hashlib.sha256(f.read_bytes()).hexdigest(),'saved_object_sections_unchanged':a==b,'log_directory_files':len(list((r/'data/Log').glob('*')))}
(p/'output-cancel-result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=False,indent=2))
assert a==b
