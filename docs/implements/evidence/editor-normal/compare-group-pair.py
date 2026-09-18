from pathlib import Path
import re,json,copy,hashlib
p=Path('docs/implements/evidence/editor-normal')
def read(name):
 sections={}; key=None
 for line in (p/name).read_text(encoding='utf-8-sig').splitlines():
  if re.fullmatch(r'\[[^]]+\]',line):key=line[1:-1];sections[key]={}
  elif '=' in line and key:
   k,v=line.split('=',1);sections[key][k]=v
 return [{'base':{k:v for k,v in sections[n].items() if k!='focus'},'effects':{s.split('.',1)[1]:v for s,v in sections.items() if s.startswith(n+'.')}} for n in sections if n.isdigit()]
def canon(objects):
 return sorted(json.dumps(o,ensure_ascii=False,sort_keys=True) for o in objects)
def without_group(objects):
 result=copy.deepcopy(objects)
 for o in result:o['base'].pop('group',None)
 return result
names=['highlight-generated.aup2','highlight-shifted.aup2','highlight-single-selection.aup2','group-pair.aup2','group-pair-duplicated.aup2','group-pair-moved.aup2','group-pair-edited.aup2','group-pair-reopened.aup2']
d={n:read(n) for n in names}
g,shift,single,base,dup,moved,edited,reopened=[d[n] for n in names]
expected=copy.deepcopy(g)
for o in expected:o['base']['frame']=','.join(str(int(v)+120) for v in o['base']['frame'].split(','))
expected_dup=copy.deepcopy(base)
for o in expected_dup:o['base']['layer']=str(int(o['base']['layer'])+2)
expected_move=copy.deepcopy(base)
for o in expected_move:o['base']['frame']='0,119'
expected_edit=copy.deepcopy(moved)
for o in expected_edit:
 if o['base']['frame']=='0,119':
  for effect in o['effects'].values():
   if 'テキスト' in effect:effect['テキスト']='ハイライト B'
checks={
 'all8_shift_120_frames_only':canon(shift)==canon(expected),
 'plain_selection_duplicates_only_video_count9':len(single)==9 and sum(o['effects'].get('0',{}).get('effect.name')=='動画ファイル' for o in single)==4,
 'pair_base_two_same_group':len(base)==2 and len({o['base'].get('group') for o in base})==1,
 'pair_dup_preserves_all_properties_except_layer_group':canon(without_group(dup))==canon(without_group(base+expected_dup)),
 'pair_move_preserves_all_except_time_layer_group':canon(without_group(moved))==canon(without_group(base+expected_move)),
 'moved_pair_groups_separate':len({o['base'].get('group') for o in moved if o['base']['frame']=='0,119'})==1 and len({o['base'].get('group') for o in moved if o['base']['frame']=='120,239'})==1 and len({o['base'].get('group') for o in moved})==2,
 'only_copy_text_changed':canon(edited)==canon(expected_edit),
 'fresh_process_reopen_objects_equal':canon(reopened)==canon(edited)
}
report={'checks':checks,'notes':['Object focus and project/scene state excluded.','Group IDs can be renumbered; compare pair partitions separately.','Highlight B-ABC insertion not completed by these operations.'], 'files':[{'file':n,'sha256':hashlib.sha256((p/n).read_bytes()).hexdigest(),'objects':len(d[n])} for n in names]}
(p/'group-pair-comparison.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(checks,ensure_ascii=False,indent=2))
assert all(checks.values())
