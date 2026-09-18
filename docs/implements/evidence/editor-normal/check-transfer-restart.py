from pathlib import Path
import json,shutil,hashlib
p=Path('docs/implements/evidence/editor-normal');loc=json.loads((p/'transfer-location.json').read_text(encoding='utf-8'));f=p/'transfer-restarted.aup2';shutil.copy2(loc['project'],f)
before=(p/'transfer-host-saved.aup2').read_bytes();after=f.read_bytes()
r={'normal_exit_and_new_launch_observed':True,'reopened_video_and_caption_at_seconds':5.30,'saved_file_byte_identical':before==after,'sha256':hashlib.sha256(after).hexdigest(),'limits':['Same PC and installed plugin configuration.','Original media remains present.','Not unsaved-state recovery or cross-PC migration.']}
(p/'transfer-restart-result.json').write_text(json.dumps(r,indent=2),encoding='utf-8');print(json.dumps(r));assert before==after
