from pathlib import Path
import re
root=Path(r'C:\Users\raimu\AppData\Local\Temp\clipchannel-a105-editor-6f349375')
p=Path('docs/implements/evidence/editor-normal')
s=(p/'compound-generated.aup2').read_text(encoding='utf-8-sig').replace('compound-baseline.aup2','highlight-insertion.aup2')
for n in [1,4]:
 s=s.replace(f'[{n}]\n',f'[{n}]\ngroup=1\n')
target=root/'highlight-insertion.aup2'
if target.exists():raise RuntimeError('exists')
target.write_text(s,encoding='utf-8')
(p/'highlight-generated.aup2').write_text(s,encoding='utf-8')