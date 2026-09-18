from pathlib import Path
import re,json,hashlib,copy
p=Path('docs/implements/evidence/editor-normal')
def read(name):
 text=(p/name).read_text(encoding='utf-8-sig'); sections={}; section=None
 for line in text.splitlines():
  if re.fullmatch(r'\[[^]]+\]',line):
   section=line[1:-1];sections[section]={}
  elif '=' in line and section:
   key,value=line.split('=',1); sections[section][key]=value
 objects=[]
 for key in sections:
  if key.isdigit():
   obj={'base':{k:v for k,v in sections[key].items() if k!='focus'},'effects':{}}
   for sub in sections:
    if sub.startswith(key+'.'): obj['effects'][sub.split('.',1)[1]]=sections[sub]
   objects.append(obj)
 return objects
names=['compound-generated.aup2','compound-host-saved.aup2','compound-single-duplicate.aup2','compound-duplicated.aup2','compound-undo.aup2','compound-redo.aup2','compound-moved.aup2','compound-move-undo.aup2','compound-move-redo.aup2','compound-reopened.aup2']
d={n:read(n) for n in names}; base=d[names[1]];dup=d[names[3]]
expected=copy.deepcopy(base)
for o in expected:o['base']['layer']=str(int(o['base']['layer'])+4)
moved=copy.deepcopy(dup)
for o in moved:o['base']['frame']=','.join(str(int(n)+60) for n in o['base']['frame'].split(','))
checks={'generated_preserved_by_host':d[names[0]]==base,'base_count_8':len(base)==8,'single_duplicate_count_9':len(d[names[2]])==9,'dup_count_16':len(dup)==16,'originals_unchanged':dup[:8]==base,'copies_match_except_layer_plus4':dup[8:]==expected,'undo_equals_baseline':d[names[4]]==base,'redo_equals_duplicate':d[names[5]]==dup,'all16_move_plus60_only':d[names[6]]==moved,'move_undo_equals_duplicate':d[names[7]]==dup,'move_redo_equals_moved':d[names[8]]==moved}
checks['reopened_matches_moved']=d['compound-reopened.aup2']==moved
report={'ignored_fields':['object focus','project and scene display state'],'checks':checks,'files':[{'file':n,'sha256':hashlib.sha256((p/n).read_bytes()).hexdigest(),'object_count':len(d[n])} for n in names]}
(p/'compound-state-comparison.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(checks,indent=2))