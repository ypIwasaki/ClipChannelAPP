import json, soundfile as sf, numpy as np
from scipy.signal import correlate
from pathlib import Path
r=Path('C:/Users/raimu/AppData/Local/ClipChannelAPP-validation/a106')
rows=[]
for name,old in [('first','RWM4SdTZ1t8-180-480'),('second','lxYJTSK0y50-420-720')]:
 x,s=sf.read(r/(old+'.wav')); y,t=sf.read(r/('accurate-'+name+'.wav')); assert s==t==16000
 x=x[:40*s]; y=y[:min(len(y),18*s)]
 c=correlate(x,y,mode='valid',method='fft'); energies=np.convolve(x*x,np.ones(1),'valid')
 sums=np.r_[0,np.cumsum(x*x)]; den=np.sqrt((sums[len(y):]-sums[:-len(y)])*np.sum(y*y))
 scores=c/np.maximum(den,1e-12); k=int(np.argmax(scores))
 rows.append(dict(input=old,accurate_samples=len(sf.read(r/('accurate-'+name+'.wav'))[0]),lag_samples=k,lag_seconds=k/s,normalized_correlation=float(scores[k])))
(r/'alignment.json').write_text(json.dumps(rows,indent=2)); print(json.dumps(rows,indent=2))
