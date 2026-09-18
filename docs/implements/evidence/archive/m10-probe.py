from pathlib import Path
import subprocess,json,hashlib,time,shutil,tempfile
p=Path('docs/implements/evidence/archive');base=Path(r'C:/Users/raimu/AppData/Local/ClipChannelAPP-validation/archive-probe');exe=base/'unpacked/7z.exe'
r=Path(tempfile.mkdtemp(prefix='clipchannel-archive-'));src=Path(r'C:/Users/raimu/AppData/Local/Temp/clipchannel-a105-editor-6f349375/input-check/corrected.mp4');copy=r/'検証動画.mp4';shutil.copy2(src,copy)
def hash(f):return hashlib.file_digest(f.open('rb'),'sha256').hexdigest()
before=hash(src);archive=r/'保管.7z';out=r/'restored';results=[]
for stage,args in [('compress',['a','-t7z','-m0=lzma2','-mx=5','-mmt=2',str(archive),copy.name]),('test',['t',str(archive)]),('extract',['x',str(archive),'-o'+str(out),'-y'])]:
 t=time.perf_counter();proc=subprocess.run([str(exe),*args],cwd=r,capture_output=True);elapsed=time.perf_counter()-t
 (p/(stage+'.log')).write_bytes(proc.stdout+proc.stderr);results.append({'stage':stage,'exit_code':proc.returncode,'seconds':elapsed});assert proc.returncode==0
restored=out/copy.name
report={'tool':'7-Zip 26.03 x64','settings':'7z/LZMA2 mx5 mmt2','source_bytes':copy.stat().st_size,'archive_bytes':archive.stat().st_size,'ratio':archive.stat().st_size/copy.stat().st_size,'saved_bytes':copy.stat().st_size-archive.stat().st_size,'source_sha256':before,'restored_sha256':hash(restored),'checks':{'roundtrip_exact':hash(restored)==before,'source_unchanged':hash(src)==before,'input_copy_retained':copy.exists() and hash(copy)==before,'archive_retained':archive.exists()},'runs':results,'binaries':{name:hash(base/'unpacked'/name) for name in ['7z.exe','7z.dll']},'local_root':str(r),'limits':['Single 300-second MP4, same PC/local volume.','Not video re-encoding; restored bytes must match.','No GUI, cancellation, >4GiB file or failure injection tested.']}
(p/'m10-result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(report,ensure_ascii=False,indent=2));assert all(report['checks'].values())
