"""Throwaway Windows file-boundary probe. Never opens source evidence for writing.
This tests file handles only, not AviUtl2 output or automatic recovery.
"""
from pathlib import Path
import ctypes as c
from ctypes import wintypes as w
import hashlib,json,subprocess,sys,tempfile
k=c.WinDLL('kernel32',use_last_error=True)
k.CreateFileW.argtypes=[w.LPCWSTR,w.DWORD,w.DWORD,c.c_void_p,w.DWORD,w.DWORD,w.HANDLE]
k.CreateFileW.restype=w.HANDLE
k.CloseHandle.argtypes=[w.HANDLE]
BAD=c.c_void_p(-1).value
READ=0x80000000;WRITE=0x40000000;DELETE=0x10000

def acquire(path,access,share):
 h=k.CreateFileW(str(path),access,share,None,3,0,None)
 return (None,c.get_last_error()) if h==BAD else (h,0)

def attempt(path,access,share):
 h,e=acquire(path,access,share)
 if h is not None:k.CloseHandle(h)
 return {'opened':h is not None,'error':e}

if len(sys.argv)>1 and sys.argv[1]=='child':
 print(json.dumps(attempt(Path(sys.argv[2]),int(sys.argv[3]),int(sys.argv[4]))));sys.exit()

def child(path,access,share):
 return json.loads(subprocess.check_output([sys.executable,__file__,'child',str(path),str(access),str(share)],text=True))
r=Path(__file__).resolve().parent
work=Path(tempfile.mkdtemp(prefix='clipchannel-frozen-file-'))
p=work/'frozen.aup2';source=(r/'transaction-after-undo.aup2').read_bytes();p.write_bytes(source)
checks={};observations={}
observations['unlocked_write']=child(p,WRITE,7)
h,e=acquire(p,READ,1)
assert h is not None,e
try:
 for name,access in [('read',READ),('write',WRITE),('delete_or_replace_access',DELETE)]:observations['locked_'+name]=child(p,access,7)
 checks['bytes_unchanged_while_locked']=p.read_bytes()==source
finally:k.CloseHandle(h)
observations['released_write']=child(p,WRITE,7)
writer,e=acquire(p,WRITE,7);assert writer is not None,e
try:observations['existing_writer_blocks_freeze']=attempt(p,READ,1)
finally:k.CloseHandle(writer)
checks.update({'unlocked_write_possible':observations['unlocked_write']['opened'],
 'reader_allowed':observations['locked_read']['opened'],
 'write_denied':observations['locked_write']=={'opened':False,'error':32},
 'delete_access_denied':observations['locked_delete_or_replace_access']=={'opened':False,'error':32},
 'release_restores_write_access':observations['released_write']['opened'],
 'preexisting_writer_rejected':observations['existing_writer_blocks_freeze']=={'opened':False,'error':32}})
# Durable recovery bytes can retain all serialized sections, unlike aliases.
restored=work/'restored.aup2';restored.write_bytes(p.read_bytes())
checks['whole_file_copy_preserves_all_serialized_bytes']=restored.read_bytes()==source
out={'checks':checks,'observations':observations,'work_directory':str(work),'sha256':hashlib.sha256(source).hexdigest(),
 'limits':['File layer only. Does not prove host in-memory equality, save completion, loading, render, or automatic recovery.',
 'External media and plugin/model files are not frozen by locking the project.',
 'No target file contents were deliberately corrupted; access probes opened handles only.',
 'All source evidence remains unchanged. No extra application failure was injected.']}
(r/'frozen-file-result.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(out,ensure_ascii=False,indent=2));assert all(checks.values())
