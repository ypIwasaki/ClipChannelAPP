from pathlib import Path
import json,re,copy,hashlib
r=Path(__file__).resolve().parent
rows=[json.loads(x) for x in (r/'edit-probe.jsonl').read_text(encoding='utf-8').splitlines()]
def parse(t):
 d={};s=''
 for line in t.splitlines():
  if line.startswith('['):s=line[1:-1];d[s]={}
  elif '=' in line:
   k,v=line.split('=',1);d[s][k]=v
 return d
def event(k):return next(x['value'] for x in rows if x['event']==k)
before=parse((r/'edit-before.aup2').read_text(encoding='utf-8-sig'));final=parse((r/'edit-after-undo.aup2').read_text(encoding='utf-8-sig'))
a,b,c,d=[parse(event(k)) for k in ['before_a','before_b','after_a','after_b']]
ea,eb=copy.deepcopy(a),copy.deepcopy(b);ea['Object.1']['X']='20.00';eb['Object.1']['X']='30.00'
def objects(x):return {k:{p:v for p,v in obj.items() if p!='focus'} for k,obj in x.items() if re.fullmatch(r'\d+(?:\.\d+)?',k)}
expected=objects(before);expected['2.1']['Y']='60.00'
begin=next(i for i,x in enumerate(rows) if x['event']=='request_begin');ret=next(i for i,x in enumerate(rows) if x['event']=='request_return')
updates=[{'index':i,**x} for i,x in enumerate(rows) if x['event']=='update_object']
checks={'one_sdk_request':sum(x['event']=='request_begin' for x in rows)==1,'both_setters_success':event('set_results')=='1,1','edit_section_return_success':event('request_return')=='1','aliases_only_intended_X_changes':c==ea and d==eb,'prior_unsaved_Y_seen_by_sdk':a['Object.1']['Y']=='60.00','single_undo_saved_objects_match_prior_unsaved_state':objects(final)==expected,'no_save_before_sdk_return':not any(x['event']=='save_before' for x in rows[:ret+1])}
result={'checks':checks,'updates':updates,'request_begin_index':begin,'request_return_index':ret,'first_alias_base':a['Object'],'original_object_base':before['2'],'pre_save_disk_sha256_observed':'c713741d176ebdffcfa357f15194fdfc0dc53d7b2cd167880f13845b759879b8','final_sha256':hashlib.sha256((r/'edit-after-undo.aup2').read_bytes()).hexdigest(),'limitations':['Normal two-setter edit, not injected failure or automatic rollback.','Undo initiated through host UI, not an SDK Undo function.','Alias base omits layer/group present in this project object.','No actor ID in notification; ordering in this log is not a universal guarantee.']}
(r/'edit-result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(result,ensure_ascii=False,indent=2));assert all(checks.values())
