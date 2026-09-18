from pathlib import Path
import re
p=Path('docs/implements/evidence/editor-normal');r=Path(r'C:/Users/raimu/AppData/Local/Temp/clipchannel-a105-editor-6f349375')
s=(p/'output-cancel-observed-before.aup2').read_text(encoding='utf-8-sig').replace('output-cancel-observed','output-cancel-real').replace('ループ再生=1','ループ再生=0')
s=re.sub(r'^ファイル=.*$',lambda _:f'ファイル={r}/input-check/corrected.mp4',s,flags=re.M)
for f in [r/'output-cancel-real.aup2',p/'output-cancel-real-generated.aup2']:
 assert not f.exists();f.write_text(s,encoding='utf-8')
