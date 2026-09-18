from pathlib import Path
import subprocess,json,hashlib,time
p=Path('docs/implements/evidence/editor-normal');r=Path(r'C:/Users/raimu/AppData/Local/Temp/clipchannel-a105-editor-6f349375')
b=Path(r'C:/Users/raimu/AppData/Local/ClipChannelAPP-validation/a106/ffmpeg-mirror/ffmpeg-9.0.1-essentials_build/bin')
reports=[]
for name in ['output-cancel-observed','output-cancel-real']:
 f=r/(name+'.avi');before=f.stat()
 probe=json.loads(subprocess.check_output([str(b/'ffprobe.exe'),'-v','error','-count_frames','-show_entries','stream=index,codec_name,duration,nb_read_frames','-of','json',str(f)]))
 result=subprocess.run([str(b/'ffmpeg.exe'),'-v','error','-i',str(f),'-f','null','-'],capture_output=True)
 def objects(s):return s[s.index('[0]\n'):]
 old=(p/(name+'-before.aup2')).read_text(encoding='utf-8-sig');new=(p/(name+'-after.aup2')).read_text(encoding='utf-8-sig')
 h=hashlib.file_digest(f.open('rb'),'sha256').hexdigest();after=f.stat()
 report={'fixture':name,'expected_frames':18000,'probe':probe,'bytes':after.st_size,'sha256':h,'size_and_mtime_unchanged_during_analysis':before.st_size==after.st_size and before.st_mtime_ns==after.st_mtime_ns,'decode_returncode':result.returncode,'decode_stderr':result.stderr.decode(errors='replace'),'object_sections_unchanged':objects(old)==objects(new),'dialog_progress_frames':12601 if name.endswith('observed') else 3757}
 reports.append(report)
assert reports[1]['probe']['streams'][0]['nb_read_frames']=='7755'
assert all(x['object_sections_unchanged'] and x['decode_returncode']==0 and x['size_and_mtime_unchanged_during_analysis'] for x in reports)
(p/'output-cancel-followup-result.json').write_text(json.dumps(reports,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(reports,ensure_ascii=False,indent=2))
