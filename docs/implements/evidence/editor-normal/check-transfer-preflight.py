from pathlib import Path
import json,re,hashlib
p=Path('docs/implements/evidence/editor-normal');loc=json.loads((p/'transfer-location.json').read_text(encoding='utf-8'))
a=(p/'group-pair-reopened.aup2').read_text(encoding='utf-8-sig');b=(p/'transfer-generated.aup2').read_text(encoding='utf-8-sig')
def normalize(s):return re.sub(r'^(file|ファイル)=.*$',r'\1=<PATH>',s,flags=re.M)
checks={'all_nonpath_text_preserved':normalize(a)==normalize(b),'two_video_references_relocated':b.count('ファイル='+loc['copied_media'])==2,'copied_media_equal':loc['source_sha256']==loc['copied_sha256'],'source_media_unchanged':hashlib.file_digest(Path(loc['source_media']).open('rb'),'sha256').hexdigest()==loc['source_sha256']}
r={'checks':checks,'host_reopen':'pending: concurrent user input detected; stopped UI before opening transferred project','limits':['Path rewrite is a fixture preparation technique, not an adopted project-format API.','Original source remains present; cannot claim absence/fallback handling tested.']}
(p/'transfer-preflight-result.json').write_text(json.dumps(r,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(r));assert all(checks.values())
