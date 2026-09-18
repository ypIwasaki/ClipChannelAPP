from pathlib import Path
import contextlib,io,json,tempfile,hashlib
import yt_dlp
from yt_dlp.version import __version__
from yt_dlp.networking import Request
p=Path('docs/implements/evidence/download-contract')
r=Path(tempfile.mkdtemp(prefix='clipchannel-cookie-probe-'))
f=r/'external-dummy.cookies.txt'
f.write_text('# Netscape HTTP Cookie File\n.example.invalid\tTRUE\t/\tFALSE\t2147483647\tdummy\tSYNTHETIC_ONLY\n',encoding='utf-8')
before=f.read_bytes();mtime=f.stat().st_mtime_ns
calls=[]
with yt_dlp.YoutubeDL({'cookiefile':None,'cookiesfrombrowser':None,'cachedir':False,'quiet':True,'no_warnings':True}) as ydl:
 jar=ydl.cookiejar
 jar.load(str(f))
 request=Request('https://example.invalid/')
 # Generate the header locally; no HTTP request is sent.
 header=jar.get_cookie_header('https://example.invalid/')
 present=header is not None and 'SYNTHETIC_ONLY' in header
 filename=jar.filename
 original_save=jar.save
 def record_save(*args,**kwargs):
  calls.append(True);return original_save(*args,**kwargs)
 jar.save=record_save
count=len(list(r.iterdir()))
parsed=yt_dlp.parse_options(['--ignore-config','--no-plugin-dirs','--alias','pick','-f {0}','--pick','bestaudio','--extract-audio','--audio-format','wav'])
a={'format':parsed.ydl_opts.get('format'),'postprocessors':[{'key':x.get('key'),'preferredcodec':x.get('preferredcodec')} for x in parsed.ydl_opts.get('postprocessors',[])]}
cfg=r/'explicit.conf';cfg.write_text('--format worst\n',encoding='utf-8')
explicit=yt_dlp.parse_options(['--ignore-config','--no-plugin-dirs','--config-locations',str(cfg)])
report={'version':__version__,'network_requests':0,'real_credentials_used':False,'cookie':{'loaded_count':len(jar),'local_header_contains_dummy':present,'jar_filename':filename,'close_save_calls':len(calls),'external_bytes_unchanged':f.read_bytes()==before,'external_mtime_unchanged':f.stat().st_mtime_ns==mtime,'directory_files_before_config_creation':count},'alias_effective_options':a,'explicit_config_with_ignore_config_format':explicit.ydl_opts.get('format'),'limitations':['Normal in-process close only; not crash or OS paging proof.','No authenticated download or full CLI compatibility tested.','Do not persist raw parser errors, cookie warning lines or generated headers.']}
assert report['cookie']['external_bytes_unchanged'] and report['cookie']['external_mtime_unchanged'] and present and not calls and filename is None
assert a['format']=='bestaudio' and explicit.ydl_opts['format']=='worst'
(p/'offline-probe-result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=False,indent=2))
