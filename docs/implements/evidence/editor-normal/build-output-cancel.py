from pathlib import Path
import re
root=Path(r'C:\Users\raimu\AppData\Local\Temp\clipchannel-a105-editor-6f349375');p=Path('docs/implements/evidence/editor-normal')
s=(p/'frame-counter-60fps-host.aup2').read_text(encoding='utf-8-sig').split('[1]',1)[0]
s=s.replace('frame=0,239','frame=0,3599').replace('再生位置=0.000,4.000','再生位置=0.000,60.000').replace('ループ再生=0','ループ再生=1')
s=re.sub(r'^file=.*$',lambda _:f'file={root}/output-cancel.aup2',s,flags=re.M)
s=re.sub(r'^output.file=.*$',lambda _:f'output.file={root}/output-cancel.avi',s,flags=re.M)
for target in [root/'output-cancel.aup2',p/'output-cancel-generated.aup2']:
 if target.exists():raise RuntimeError('exists')
 target.write_text(s,encoding='utf-8')
print('60-second 320x180 60fps cancellation fixture; maximum raw output approximately 634MB')
