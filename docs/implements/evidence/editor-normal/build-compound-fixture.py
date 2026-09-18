from pathlib import Path
import re,json
root=Path(r'C:\Users\raimu\AppData\Local\Temp\clipchannel-a105-editor-6f349375')
evidence=Path('docs/implements/evidence/editor-normal')
base=(evidence/'timing-corrected-8s.aup2').read_text(encoding='utf-8-sig')
header=base.split('[0]\n')[0]
target=root/'compound-baseline.aup2'
if target.exists(): raise RuntimeError('already exists')
header=re.sub(r'^file=.*$', 'file='+str(target).replace('\\','\\\\'),header,flags=re.M)
header=header.replace('cursor.frame=0','cursor.frame=45')
def obj(source,id,layer,start,end,replacements):
 s=source.split('[0]\n',1)[1].split('[1]\n')[0]
 s='[0]\n'+s
 s=re.sub(r'\[0(?=[.\]])','['+str(id),s)
 s=re.sub(r'^layer=\d+',f'layer={layer}',s,flags=re.M)
 s=re.sub(r'^frame=\d+,\d+',f'frame={start},{end}',s,flags=re.M)
 s=re.sub(r'^focus=1\n','',s,flags=re.M)
 for a,b in replacements: s=s.replace(a,b)
 return s
parts=[]
for i in range(3):
 parts.append(obj(base,i,0,i*120,i*120+119,[('再生位置=0.000,8.000',f'再生位置={i*4:.3f},{(i+1)*4:.3f}')]))
text=(evidence/'subtitle-duplicate.aup2').read_text(encoding='utf-8-sig')
for i,name in enumerate(['A','B','C']):
 parts.append(obj(text,3+i,1,i*120,i*120+119,[('サイズ=40.00','サイズ=16.00'),('Y=0.00','Y=55.00'),('文字揃え=左寄せ[上]','文字揃え=中央揃え[中]'),('検証用字幕：変幻リメ\\n2行目：保存・再読込み確認',f'検証字幕 {name}')]))
img=(evidence/'image-import.aup2').read_text(encoding='utf-8-sig')
parts.append(obj(img,6,2,0,119,[('X=0.00','X=100.00'),('Y=0.00','Y=-55.00'),('拡大率=100.000','拡大率=25.000')]))
aud=(evidence/'audio-import.aup2').read_text(encoding='utf-8-sig')
parts.append(obj(aud,7,3,60,299,[('音量=100.00','音量=15.00')]))
content=header+''.join(parts)
target.write_text(content,encoding='utf-8')
(evidence/'compound-generated.aup2').write_text(content,encoding='utf-8')
print(target)