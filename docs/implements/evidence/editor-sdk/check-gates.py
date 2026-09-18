from pathlib import Path
import json, re, hashlib

r = Path(__file__).resolve().parent
rows = [json.loads(s) for s in (r/'gates.jsonl').read_text(encoding='utf-8').splitlines()]
def values(event):
    return [x['value'] for x in rows if x['event'] == event]
def parse(text):
    result = {}; section = ''
    for line in text.splitlines():
        if line.startswith('['):
            section = line[1:-1]; result[section] = {}
        elif '=' in line:
            k, v = line.split('=', 1); result[section][k] = v
    return result
def objects(data):
    return {s:{k:v for k,v in d.items() if k != 'focus'} for s,d in data.items() if re.fullmatch(r'\d+(?:\.\d+)?', s)}
before = parse((r/'gate-before.aup2').read_text(encoding='utf-8-sig'))
saved = parse((r/'gate-after-recovery.aup2').read_text(encoding='utf-8-sig'))
expected = objects(before); expected['3.1']['Y'] = '60.00'
marker = next(d['validation_marker'] for d in saved.values() if d.get('plugin.name') == 'clipchannel_gate_probe')
def scene(data):
    return {k:v for k,v in data['scene.0'].items() if not k.startswith(('cursor.', 'preview.', 'display.'))}
partial = values('partial_state')[0]
original = values('recovery_before')[0]
# Compare the two altered object aliases and all other content, not only the result label.
parts = re.split(r'(?=ITEM \d+ )', original)
parts = [p.replace('X=0.00\r\n', 'X=20.00\r\n', 1) if p.startswith('ITEM 3 ') else p.replace('音量=15.00', '音量=30.00', 1) if p.startswith('ITEM 7 ') else p for p in parts]
probe = json.loads((r/'gate-output-probe.json').read_text(encoding='utf-8-sig'))
video = next(s for s in probe['streams'] if s['codec_type'] == 'video')
checks = {
    'one_deliberate_failure': len(values('injected_failure')) == 1,
    'two_successful_changes_before_failure': values('injected_failure') == ['after two successful changes; third step skipped'],
    'partial_state_only_two_expected_changes': partial == ''.join(parts) and partial != original,
    'recovery_all_captured_objects_equal': values('recovery_after') == [original] and values('recovery_result') == ['restored'],
    'saved_objects_include_prior_Y_and_preserve_other_fields': objects(saved) == expected,
    'scene_content_preserved': scene(before) == scene(saved),
    'save_marker_matches_file_and_reload': values('save_before') == [marker] and values('load_marker')[-1] == marker,
    'reloaded_snapshot_matches_recovery': values('snapshot') == [original],
    'no_save_before_recovery': not any(x['event']=='save_before' for x in rows[:next(i for i,x in enumerate(rows) if x['event']=='recovery_result')]),
    'output_edit_request_rejected': values('output_edit_section_accepted') == ['0'] and not values('output_noop_callback'),
    'output_state_returns_to_edit': values('output_state') == ['0','2','0'] and values('watch_end') == ['output-observed'],
    'output_all_360_frames_decoded': video['nb_read_frames']=='360' and video['duration']=='12.000000',
}
result = {'checks':checks, 'saved_sha256':hashlib.sha256((r/'gate-after-recovery.aup2').read_bytes()).hexdigest(), 'marker':marker,
          'limits':['Only two property setters compensated; not crash, object deletion/creation, or generic rollback.', 'Output no-op edit section rejection only; hand-edit exclusion during applying and save-to-output race not tested.', 'Save content and same-process reload verified; no power-loss durability or save-error injection.', 'Alias capture has eight fixed objects; saved object comparison separately includes group/layer.']}
(r/'gate-result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(result,ensure_ascii=False,indent=2))
assert all(checks.values())
