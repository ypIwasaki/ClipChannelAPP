from pathlib import Path
import re,json,subprocess,hashlib,copy
r=Path(__file__).resolve().parent
def objects(name):
 d={};s=''
 for line in (r/name).read_text(encoding='utf-8-sig').splitlines():
  if line.startswith('['):s=line[1:-1];d[s]={}
  elif '=' in line:
   k,v=line.split('=',1)
   if k!='focus':d[s][k]=v
 return {s:v for s,v in d.items() if re.fullmatch(r'\d+(?:\.\d+)?',s)}
base=objects('frozen-after-undo.aup2');batch=objects('batch-registered.aup2');changed=objects('batch-current-x70.aup2');final=objects('batch-final.aup2')
expected=copy.deepcopy(base);expected['5.1']['X']='70.00'
media=Path(r'C:/Users/raimu/AppData/Local/ClipChannelAPP-validation/editor-sdk-observer/batch-frozen-x6')
ff=Path(r'C:/Users/raimu/AppData/Local/ClipChannelAPP-validation/a106/ffmpeg-mirror/ffmpeg-9.0.1-essentials_build/bin')
info=json.loads(subprocess.check_output([str(ff/'ffprobe.exe'),'-v','error','-show_streams','-of','json',str(media)]))
decode=subprocess.run([str(ff/'ffmpeg.exe'),'-v','error','-i',str(media),'-f','null','-'],capture_output=True)
checks={'registered_objects_equal_saved_baseline':batch==base,'later_saved_edit_is_X70_only':changed==expected,'final_objects_restored':final==base,'output_360_frames':info['streams'][0]['nb_frames']=='360','output_12_seconds':info['streams'][0]['duration']=='12.000000','full_decode_without_errors':decode.returncode==0 and not decode.stderr}
result={'checks':checks,'output_sha256':hashlib.sha256(media.read_bytes()).hexdigest(),'output_path':str(media),'output_size':media.stat().st_size,'visual_observations':['Host displayed X=6 while batch output ran and X=70 after completion.','Decoded frame359 shows caption at central X6 position, not right-shifted X70. This is visual verification, not whole-video reference pixel comparison.'],'limits':['UI batch route only; no programmatic SDK entry proved.','Save-to-batch-registration gap not protected.','Normal output completion restoration is not failure rollback.','Referenced media/plugins not frozen; output settings vary by plugin.']}
(r/'batch-result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(result,ensure_ascii=False,indent=2));assert all(checks.values())
