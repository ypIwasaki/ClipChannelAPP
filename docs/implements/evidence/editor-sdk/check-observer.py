from pathlib import Path
import json,re,hashlib
r=Path(__file__).resolve().parent
rows=[json.loads(s) for s in (r/'observer.jsonl').read_text().splitlines()]
def parse(name):
 d={};section=''
 for line in (r/name).read_text(encoding='utf-8-sig').splitlines():
  if line.startswith('['): section=line[1:-1];d[section]={}
  elif '=' in line:
   k,v=line.split('=',1);d[section][k]=v
 return d
before,saved,after=(parse(n) for n in ['before.aup2','saved.aup2','after-undo.aup2'])
def objects(d):return {s:{k:v for k,v in v.items() if k!='focus'} for s,v in d.items() if re.fullmatch(r'\d+(?:\.\d+)?',s)}
saves=[x for x in rows if x['event']=='save_before'];loads=[x for x in rows if x['event']=='load_marker'];updates=[x for x in rows if x['event']=='update_object']
checks={'plugin_registered':any(x['event']=='registered' for x in rows),'first_marker_in_file':saves[0]['value']==saved['plugin.0']['validation_marker'],'first_marker_read_back':any(x['value']==saves[0]['value'] and x['tick_ms']>saves[0]['tick_ms'] for x in loads),'second_save_new_marker':len(saves)==2 and saves[1]['value']!=saves[0]['value'] and saves[1]['value']==after['plugin.0']['validation_marker'],'objects_unchanged_after_normal_undo':objects(before)==objects(saved)==objects(after),'two_update_events_observed':len(updates)==2,'event_thread_differs_from_save_thread':all(x['thread']!=saves[0]['thread'] for x in updates)}
base=Path('C:/Users/raimu/AppData/Local/ClipChannelAPP-validation/editor-sdk-observer')
files=[base/'clipchannel_observer.aux2',base/'plugin2.h',base/'sdk-packages/microsoft.windows.sdk.cpp.zip',base/'sdk-packages/microsoft.windows.sdk.cpp.x64.zip']
result={'checks':checks,'saves':saves,'loads':loads,'updates':updates,'build':'MSVC 14.51.36231 x64 /std:c++17 /MT; Windows SDK NuGet 10.0.28000.2705; include tree 10.0.28000.0','hashes':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in files},'limits':['Normal save and readback only; save-before is not success notification.','No actor or operation ID in update events; no app-origin update exercised.','No automated save trigger, output lock, SDK mutation or failure restoration.','State menu compiled but not invoked.']}
(r/'observer-result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(checks));assert all(checks.values())
