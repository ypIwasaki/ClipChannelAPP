from pathlib import Path
import time
p=Path(r'C:/Users/raimu/AppData/Local/Temp/clipchannel-frozen-file-_0ouce5u')
f=(p/'frozen.aup2').open('rb')
import ctypes as c
from ctypes import wintypes as w
k=c.WinDLL('kernel32',use_last_error=True);k.CreateFileW.argtypes=[w.LPCWSTR,w.DWORD,w.DWORD,c.c_void_p,w.DWORD,w.DWORD,w.HANDLE];k.CreateFileW.restype=w.HANDLE;k.CloseHandle.argtypes=[w.HANDLE]
h=k.CreateFileW(str(p/'frozen.aup2'),0x80000000,1,None,3,0,None)
assert h!=c.c_void_p(-1).value,c.get_last_error()
print('FROZEN LOCK ACTIVE',flush=True)
try:
 end=time.monotonic()+300
 while time.monotonic()<end and not (p/'release').exists():time.sleep(.2)
finally:k.CloseHandle(h);f.close();print('LOCK RELEASED',flush=True)
