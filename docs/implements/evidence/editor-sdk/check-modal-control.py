"""Summarize recorded modal probe; UI observations are not automated assertions."""
import json
from pathlib import Path

root = Path(__file__).resolve().parent
rows = [json.loads(line) for line in (root / 'modal-control.jsonl').read_text(encoding='utf-8-sig').splitlines() if line.strip()]
start = max(i for i, row in enumerate(rows) if row['event'] == 'modal_begin')
end = next(i for i in range(start + 1, len(rows)) if rows[i]['event'] == 'modal_end')
segment = rows[start:end + 1]
samples = [row for row in segment if row['event'] == 'modal_sample']
result = {
    'scope': 'Latest recorded modal only; bounded alias snapshot, not complete project state',
    'duration_ms': rows[end]['tick_ms'] - rows[start]['tick_ms'],
    'sample_count': len(samples),
    'events': sorted(set(row['event'] for row in segment)),
    'recorded_checks': {
        'samples_present': bool(samples),
        'all_sample_and_end_values_equal_begin': all(row['value'] == rows[start]['value'] for row in samples + [rows[end]]),
        'no_save_load_update_or_compound_event': not any(row['event'].startswith(('save', 'load', 'update', 'compound')) for row in segment),
    },
    'ui_observations': {
        'save_as_request_utc': '2026-09-18T07:21:04.618Z',
        'open_request_utc': '2026-09-18T07:21:11.624Z',
        'during_modal': 'Host disabled; Ctrl+Shift+S and Ctrl+O did not open their dialogs',
        'controls': 'Open succeeded before modal; Save As opened after modal and was cancelled without saving',
    },
    'observed_fixture_sha256_before_and_after': 'D2231369D203AC961D811FE59E7CFA5A83C5E0D31C5561CCA40211A175295B3F',
    'verdict': 'Modal plus injected keyboard control fails the entry condition; protected automatic recovery and save-to-batch remain unproven',
    'limits': ['No UIA Invoke test', 'No failure injection or compound Apply', 'No proof that every possible controller route is unavailable'],
}
(root / 'modal-control-result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps(result, ensure_ascii=False, indent=2))
