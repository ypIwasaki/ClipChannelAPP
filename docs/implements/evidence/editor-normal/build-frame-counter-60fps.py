from pathlib import Path
import re
root=Path(r'C:\Users\raimu\AppData\Local\Temp\clipchannel-a105-editor-6f349375')
p=Path('docs/implements/evidence/editor-normal')
s=(p/'frame-counter-host.aup2').read_text(encoding='utf-8-sig')
s=s.replace('video.rate=30','video.rate=60').replace('frame=0,119','frame=0,239').replace('frame=120,239','frame=240,479')
s=re.sub(r'^file=.*$',lambda _:f'file={root}/frame-counter-60fps.aup2',s,flags=re.M)
s=re.sub(r'^output.file=.*$',lambda _:f'output.file={root}/frame-counter-60fps-output.avi',s,flags=re.M)
for target in [root/'frame-counter-60fps.aup2',p/'frame-counter-60fps-generated.aup2']:
 if target.exists():raise RuntimeError('exists')
 target.write_text(s,encoding='utf-8')
print('60fps fixture prepared, durations retained at 4+4 seconds')
