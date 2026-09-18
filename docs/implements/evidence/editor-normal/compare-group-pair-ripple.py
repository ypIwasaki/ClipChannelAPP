from pathlib import Path
import runpy,json,hashlib,copy
p=Path('docs/implements/evidence/editor-normal')
f=runpy.run_path(str(p/'compare-group-pair.py'));read=f['read'];canon=f['canon'];without=f['without_group']
names=['group-pair-reopened.aup2','group-pair-ripple-cut.aup2','group-pair-ripple-undo.aup2','group-pair-ripple-redo.aup2']
a,cut,undo,redo=[read(n) for n in names]
expected=copy.deepcopy([o for o in a if o['base']['frame']=='120,239'])
for o in expected:o['base']['frame']='0,119'
checks={'cut_keeps_only_original_pair_shifted_minus120':canon(without(cut))==canon(without(expected)),'single_undo_restores_all4':canon(undo)==canon(a),'single_redo_restores_cut_state':canon(redo)==canon(cut)}
report={'operation':'Select current-frame objects at 1.66 seconds, Ctrl+Shift+X, save, single Undo/save, single Redo/save','checks':checks,'files':[{'file':n,'sha256':hashlib.sha256((p/n).read_bytes()).hexdigest()} for n in names]}
(p/'group-pair-ripple-comparison.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(checks,indent=2));assert all(checks.values())
