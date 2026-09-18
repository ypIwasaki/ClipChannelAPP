from pathlib import Path
import json,re,copy
r=Path(__file__).resolve().parent
rows=[json.loads(x) for x in (r/'transaction.jsonl').read_text(encoding='utf-8').splitlines()]
rows=rows[next(i for i,x in enumerate(rows) if x['event']=='initialize' and x['tick_ms']==111359671):]
def events(n):return [x for x in rows if x['event']==n]
def objects(name):
 d={};s=''
 for line in (r/name).read_text(encoding='utf-8-sig').splitlines():
  if line.startswith('['):s=line[1:-1];d[s]={}
  elif '=' in line:
   k,v=line.split('=',1)
   if k!='focus':d[s][k]=v
 return {s:v for s,v in d.items() if re.fullmatch(r'\d+(?:\.\d+)?',s)}
before=objects('transaction-before.aup2');expected=copy.deepcopy(before);expected['5.1']['X']='6.00'
after=objects('transaction-after-undo.aup2');applied=objects('transaction-applied.aup2')
begin=events('modal_begin')[0];end=events('modal_end')[0];cb=events('compound_before')[0];ca=events('compound_after')[0]
checks={
 'undo_restores_all_object_fields_preserving_prior_X6':after==expected,
 'restored_caption_and_video_group':after['4'].get('group')==after['1'].get('group')=='1',
 'compound_changes_snapshot':cb['value']!=ca['value'],
 'pre_apply_samples_unchanged':all(x['value']==cb['value'] for x in events('modal_sample') if x['tick_ms']<cb['tick_ms']),
 'post_apply_samples_unchanged':all(x['value']==ca['value'] for x in events('modal_sample') if x['tick_ms']>ca['tick_ms']),
 'modal_end_matches_applied_state':end['value']==ca['value'],
 'compound_edit_section_succeeded':events('compound_return')[0]['value']=='1',
 'disk_save_marker_armed':events('armed')[0]['value']=='9196-111359671-2',
 'output_entry_state_unavailable':events('output_entry_snapshot')[0]['value']=='UNAVAILABLE',
 'output_rejected_without_receipt_event':events('output_rejected')[0]['value']=='cannot prove exact armed state' and not events('output_receipt'),
}
result={'checks':checks,'modal_samples':len(events('modal_sample')),'modal_duration_ms':end['tick_ms']-begin['tick_ms'],'updates_inside_modal':[x for x in events('update') if begin['tick_ms']<=x['tick_ms']<=end['tick_ms']], 'applied_object_headers':{k:v for k,v in applied.items() if k.isdigit()},'verdicts':{'manual_edit_exclusion':'Observed for modal-owned main window drag and Undo only; not all writers.', 'save_to_output':'Not established: output-entry SDK snapshot unavailable; safely rejected.', 'recovery':'Single host Undo restores compound creation/deletion and prior manual edit; automatic failure rollback not established.'},'receipt_absent_observed':True,'note':'All checks passing validates observations, including limitations; does not close product gates.'}
(r/'transaction-result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(result,ensure_ascii=False,indent=2));assert all(checks.values())
