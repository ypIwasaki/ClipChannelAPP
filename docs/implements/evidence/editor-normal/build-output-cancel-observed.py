from pathlib import Path
p=Path('docs/implements/evidence/editor-normal');r=Path(r'C:/Users/raimu/AppData/Local/Temp/clipchannel-a105-editor-6f349375')
s=(p/'output-cancel-generated.aup2').read_text(encoding='utf-8-sig').replace('output-cancel','output-cancel-observed').replace('frame=0,3599','frame=0,17999').replace('0.000,60.000','0.000,300.000')
for f in [r/'output-cancel-observed.aup2',p/'output-cancel-observed-generated.aup2']:
 assert not f.exists();f.write_text(s,encoding='utf-8')
print('Bounded 300 seconds, 18000 frames, maximum raw output about 3.2 GB')
