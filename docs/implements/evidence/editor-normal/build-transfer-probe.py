from pathlib import Path
import tempfile,shutil,re,json,hashlib
p=Path('docs/implements/evidence/editor-normal');r=Path(tempfile.mkdtemp(prefix='clipchannel-editor-transfer-'));media=r/'素材';media.mkdir()
old=Path(r'C:/Users/raimu/AppData/Local/Temp/clipchannel-a105-editor-6f349375/input-check/corrected.mp4');new=media/'動画.mp4';shutil.copy2(old,new)
s=(p/'group-pair-reopened.aup2').read_text(encoding='utf-8-sig');project=r/'移行検証.aup2'
s=re.sub(r'^file=.*$',lambda _:f'file={project}',s,flags=re.M)
s=re.sub(r'^ファイル=.*$',lambda _:f'ファイル={new}',s,flags=re.M)
project.write_text(s,encoding='utf-8');(p/'transfer-generated.aup2').write_text(s,encoding='utf-8')
report={'project':str(project),'source_media':str(old),'copied_media':str(new),'source_sha256':hashlib.file_digest(old.open('rb'),'sha256').hexdigest(),'copied_sha256':hashlib.file_digest(new.open('rb'),'sha256').hexdigest()}
(p/'transfer-location.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(report,ensure_ascii=False))
