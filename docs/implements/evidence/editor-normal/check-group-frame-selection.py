from pathlib import Path
import json
p=Path('docs/implements/evidence/editor-normal/group-pair-frame-matches.json')
d=json.loads(p.read_text());bad=[m for m in d['matches'] if m['output_frame']<120 and m['delta']!=0]
print(f'First 4-second clip: {len(bad)} / 120 frames differ from expected source-frame index')
print('output frame positions:',[m['output_frame'] for m in bad])
assert not bad,'Known validation discrepancy: nonzero source start selects earlier source frames'
