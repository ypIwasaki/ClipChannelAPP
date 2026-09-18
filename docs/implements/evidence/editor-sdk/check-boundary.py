from pathlib import Path
import json, re, copy

r=Path(__file__).resolve().parent
rows=[json.loads(x) for x in (r/'boundary.jsonl').read_text(encoding='utf-8').splitlines()]
def events(name): return [x for x in rows if x['event']==name]
def parse(name):
    data={}; section=''
    for line in (r/name).read_text(encoding='utf-8-sig').splitlines():
        if line.startswith('['): section=line[1:-1];data[section]={}
        elif '=' in line:
            k,v=line.split('=',1);data[section][k]=v
    return data
def objects(data):
    return {s:{k:v for k,v in d.items() if k!='focus'} for s,d in data.items() if re.fullmatch(r'\d+(?:\.\d+)?',s)}
def marker(data):
    return next(d['validation_marker'] for d in data.values() if d.get('plugin.name')=='clipchannel_boundary_probe')
before=objects(parse('boundary-before.aup2'))
recreated=objects(parse('boundary-recreated.aup2'))
expected=copy.deepcopy(before);expected['4'].pop('group')
created=objects(parse('boundary-created.aup2'))
extra={k:v for k,v in created.items() if k not in before}
backup=parse('boundary-auto-backup.aup2');disk=parse('boundary-disk-at-rejection.aup2')
holds=[]
for begin,end in zip(events('hold_begin'),events('hold_end')):
    holds.append({'start_tick_ms':begin['tick_ms'],'end_tick_ms':end['tick_ms'],
                  'duration_ms':end['tick_ms']-begin['tick_ms'],
                  'captured_state_equal':begin['value']==end['value'],
                  'updates_inside':sum(begin['tick_ms']<x['tick_ms']<end['tick_ms'] for x in events('update_object'))})
checks={
    'alias_roundtrip_equal_despite_group_loss':events('roundtrip_before')[0]['value']==events('roundtrip_after')[0]['value'],
    'saved_roundtrip_loses_only_caption_group':recreated==expected and recreated!=before,
    'host_undo_restores_all_object_fields':objects(parse('boundary-after-undo.aup2'))==before,
    'created_one_image_on_layer_5':len([k for k in created if k.isdigit()])==9 and extra.get('8',{}).get('layer')=='5' and extra.get('8.0',{}).get('effect.name')=='画像ファイル',
    'creation_keeps_original_objects':all(created.get(k)==v for k,v in before.items()),
    'second_section_removes_temporary_object':events('temporary_removed')[0]['value']=='1' and objects(parse('boundary-removed.aup2'))==before,
    'both_hold_snapshots_equal_no_update_inside':len(holds)==2 and all(h['captured_state_equal'] and h['updates_inside']==0 and h['duration_ms']>=20000 for h in holds),
    'clean_output_receipt_completed':len(events('output_receipt'))==1 and events('output_receipt')[0]['value']=='success' and 'frames=360' in (r/'boundary-clean.ccprobe').read_text(),
    'dirty_output_rejected_at_marker_check':len(events('output_rejected'))==1 and events('output_rejected')[0]['value']=='save marker absent on disk',
    'backup_marker_differs_from_explicit_save':marker(backup)!=marker(disk),
    'backup_contains_unsaved_X_change':objects(backup)['5.1']['X']=='5.00' and objects(disk)['5.1']['X']=='0.00',
    'final_objects_restored':objects(parse('boundary-final.aup2'))==before,
}
result={'checks':checks,'hold_observations':holds,
        'verdicts':{'edit_lock':'Partial: snapshots unchanged; drag request straddled release and left a pending drag. Not proof of all UI input exclusion.',
                    'save_to_output':'Partial: clean receipt succeeds, dirty output rejected. Automatic backup changes the saved marker; notification-only generation is insufficient.',
                    'general_recovery':'FAIL for alias-only restoration: grouped caption loses its group. Host Undo restores this fixture, but no general automatic rollback proved.'},
        'input_timing':{'second_drag_request_utc':'2026-09-18T06:12:03.452Z','clock_sample_utc':'2026-09-18T06:12:14.6396996Z','clock_sample_tick_ms':109861484,'note':'Request began approximately 0.8 seconds before hold end; exact OS input-delivery time not recorded.'},
        'dirty_receipt_absent_observed':True,
        'limits':['Checks verify recorded observations, including counterexamples; all true does not mean all requirements pass.', 'No additional injected-failure case; normal create/delete round trips.', 'Output receipt is not encoded video; no media files changed.']}
(r/'boundary-result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(result,ensure_ascii=False,indent=2));assert all(checks.values())
