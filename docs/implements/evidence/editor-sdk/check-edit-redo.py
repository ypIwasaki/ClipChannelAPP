from pathlib import Path
import json,re,hashlib
r=Path(__file__).resolve().parent
def parse(name):
 d={};s=''
 for line in (r/name).read_text(encoding='utf-8-sig').splitlines():
  if line.startswith('['):s=line[1:-1];d[s]={}
  elif '=' in line:
   k,v=line.split('=',1);d[s][k]=v
 return d
def objects(d):return {s:{k:v for k,v in o.items() if k!='focus'} for s,o in d.items() if re.fullmatch(r'\d+(?:\.\d+)?',s)}
u=objects(parse('edit-after-undo.aup2'));redo=objects(parse('edit-after-redo.aup2'));final=objects(parse('edit-after-second-undo.aup2'))
expected={s:dict(o) for s,o in u.items()};expected['2.1']['X']='20.00';expected['3.1']['X']='30.00'
checks={'redo_changes_both_X_only':redo==expected,'redo_preserves_prior_Y':redo['2.1']['Y']=='60.00','second_undo_matches_first':final==u}
res={'checks':checks,'limits':['Host UI redo, no new SDK invocation.','Original prior-unsaved Y had been saved after first Undo; this round tests history across that save.','Plugin save markers change on each save; full file byte equality is not expected.']}
(r/'edit-redo-result.json').write_text(json.dumps(res,indent=2),encoding='utf-8');print(json.dumps(res));assert all(checks.values())
