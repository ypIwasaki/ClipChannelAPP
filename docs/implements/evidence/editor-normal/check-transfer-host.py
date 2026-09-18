from pathlib import Path
import json,re,hashlib,shutil
p=Path('docs/implements/evidence/editor-normal');loc=json.loads((p/'transfer-location.json').read_text(encoding='utf-8'));shutil.copy2(loc['project'],p/'transfer-host-saved.aup2')
def sections(path):
 out={};key=None
 for line in path.read_text(encoding='utf-8-sig').splitlines():
  if re.fullmatch(r'\[[^]]+\]',line):key=line[1:-1];out[key]={}
  elif key and '=' in line:
   k,v=line.split('=',1)
   if k!='focus':out[key][k]=v
 return out
before=sections(p/'transfer-generated.aup2');after=sections(p/'transfer-host-saved.aup2')
objects=lambda s:{k:v for k,v in s.items() if k not in ['project','scene.0']}
checks={'four_objects_preserved':objects(before)==objects(after) and sum(k.isdigit() for k in after)==4,'scene_media_settings_preserved':all(before['scene.0'][k]==after['scene.0'][k] for k in ['video.width','video.height','video.rate','video.scale','audio.rate']),'new_media_references_retained':sum(v.get('ファイル')==loc['copied_media'] for v in after.values())==2,'source_media_unchanged':hashlib.file_digest(Path(loc['source_media']).open('rb'),'sha256').hexdigest()==loc['source_sha256'],'copy_media_unchanged':hashlib.file_digest(Path(loc['copied_media']).open('rb'),'sha256').hexdigest()==loc['copied_sha256']}
report={'checks':checks,'observed':['Opened relocated Japanese-path project in AviUtl2 2.1.9 with existing L-SMASH plugin','Video and highlight caption at 1.66 seconds','Video and original caption at 5.30 seconds','Saved relocated project'],'limits':['Same process and same PC; no fresh-process reopen yet','Original media remains available; missing-media resolution not tested','Only two videos and two standard captions; no auxiliary/external-plugin state tested']}
(p/'transfer-host-result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(report));assert all(checks.values())
