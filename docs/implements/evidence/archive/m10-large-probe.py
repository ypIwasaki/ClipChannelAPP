"""Bounded >4GiB normal archive roundtrip, synthetic zero-filled file."""
from pathlib import Path
import subprocess,tempfile,time,json,hashlib,shutil
p=Path('docs/implements/evidence/archive');r=Path(tempfile.mkdtemp(prefix='clipchannel-archive-large-'));exe=Path(r'C:/Users/raimu/AppData/Local/ClipChannelAPP-validation/archive-probe/unpacked/7z.exe')
size=2**32+2**20
assert shutil.disk_usage(r).free>size*3
src=r/'4GiB超.bin'
with src.open('wb') as f:f.truncate(size)
archive=r/'large.7z';out=r/'restored';results=[]
for stage,args in [('compress',['a','-t7z','-m0=lzma2','-mx=1','-mmt=2',str(archive),src.name]),('test',['t',str(archive)]),('extract',['x',str(archive),'-o'+str(out),'-y'])]:
 t=time.perf_counter();result=subprocess.run([str(exe),*args],cwd=r,capture_output=True);elapsed=time.perf_counter()-t
 (p/('large-'+stage+'.log')).write_bytes(result.stdout+result.stderr);results.append({'stage':stage,'exit_code':result.returncode,'seconds':elapsed});print(stage,result.returncode,round(elapsed,3),flush=True);assert result.returncode==0
restored=out/src.name
h=lambda f:hashlib.file_digest(f.open('rb'),'sha256').hexdigest()
a=h(src);b=h(restored)
report={'tool':'7-Zip26.03 x64','payload':'synthetic zero bytes, not a video','settings':'7z/LZMA2 mx1 mmt2','source_bytes':size,'restored_bytes':restored.stat().st_size,'archive_bytes':archive.stat().st_size,'source_sha256':a,'restored_sha256':b,'runs':results,'local_root':str(r),'checks':{'over_4GiB':size>2**32,'size_equal':restored.stat().st_size==size,'hash_equal':a==b,'both_retained':src.exists() and archive.exists()},'limits':['Checks individual uncompressed file size >4GiB, not archive size >4GiB.','Zero-filled data does not predict real-media compression or memory/performance.','No ZIP64, external-drive or cancellation validation here.']}
(p/'m10-large-result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(report,ensure_ascii=False));assert all(report['checks'].values())
