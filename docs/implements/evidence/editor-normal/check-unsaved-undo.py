from pathlib import Path
import re,json,hashlib,copy
root=Path(__file__).resolve().parent
def read(name):
 data={};section=None
 for line in (root/name).read_text(encoding='utf-8-sig').splitlines():
  if line.startswith('['): section=line[1:-1];data[section]={}
  elif '=' in line:
   k,v=line.split('=',1);data[section][k]=v
 return data
def objects(d):
 return {s:{k:v for k,v in d[s].items() if k!='focus'} for s in d if re.fullmatch(r'\d+(?:\.\d+)?',s)}
before=read('unsaved-before.aup2');undo=read('unsaved-after-undo.aup2');redo=read('unsaved-after-redo.aup2');final=read('unsaved-final.aup2')
expected=objects(before);expected['2.1']['X']='10.00'
shifted=copy.deepcopy(expected)
for s in ['1','3']: shifted[s]['frame']='240,359'
checks={'undo_preserves_prior_unsaved_X_and_all_other_object_values':objects(undo)==expected,'redo_moves_both_pair_objects_only':objects(redo)==shifted,'second_undo_matches_first':objects(final)==expected,'final_saved_bytes_match_first_undo':(root/'unsaved-final.aup2').read_bytes()==(root/'unsaved-after-undo.aup2').read_bytes(),'scene_content_unchanged':all({k:v for k,v in d['scene.0'].items() if not k.startswith(('cursor.','display.','preview.'))}=={k:v for k,v in before['scene.0'].items() if not k.startswith(('cursor.','display.','preview.'))} for d in [undo,redo,final])}
result={'checks':checks,'hashes':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in root.glob('unsaved-*.aup2')},'observation':'No save occurred between X=10 input, pair movement and initial Undo. Subsequent save materialized the resulting state.','limits':['Normal host Undo only; no failure injection or SDK transaction.','Excludes focus and scene cursor/display/preview UI state.','No auxiliary material, third-party effect state or app IDs in this fixture.','Ctrl+Y and Ctrl+Shift+Z attempts did not visibly redo in this run; menu popup selection did.']}
(root/'unsaved-undo-result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(result,indent=2));assert all(checks.values())
