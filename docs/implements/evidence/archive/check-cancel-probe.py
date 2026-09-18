from pathlib import Path
import json,hashlib,subprocess
p=Path('docs/implements/evidence/archive');r=Path(r'C:/Users/raimu/AppData/Local/Temp/clipchannel-archive-large-f5lbwz8z');source=r/'4GiB超.bin';archive=r/'cancel-probe.7z'
h=hashlib.file_digest(source.open('rb'),'sha256').hexdigest();baseline=json.loads((p/'m10-large-result.json').read_text(encoding='utf-8'))
report={'action':'Ctrl+C sent via exec PTY during mx9 LZMA2 compression, two threads','observed_message':'Break signaled','exec_session_exit_code':1,'note':'Exit code belongs to enclosing PowerShell command; native 7z exit code not captured.','input_bytes':source.stat().st_size,'input_hash_unchanged':h==baseline['source_sha256'],'archive_exists':archive.exists(),'archive_bytes':archive.stat().st_size if archive.exists() else None,'limits':['Console interruption only, not GUI/worker cancellation integration.','Break occurred near end; no claim of cancellation latency bound.','No forced process termination or fault injection.']}
if archive.exists():
 proc=subprocess.run([r'C:/Users/raimu/AppData/Local/ClipChannelAPP-validation/archive-probe/unpacked/7z.exe','t',str(archive)],capture_output=True)
 report['remaining_archive_test_exit_code']=proc.returncode
 (p/'cancel-artifact-test.log').write_bytes(proc.stdout+proc.stderr)
(p/'m10-cancel-result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(report));assert report['input_hash_unchanged']
