"""Normal-path storage feasibility probe; toy schema, not product format."""
from pathlib import Path
import sqlite3,zipfile,tempfile,json,hashlib,shutil,sys
p=Path('docs/implements/evidence/storage');root=Path(tempfile.mkdtemp(prefix='clipchannel-storage-'));src=root/'source';dst=root/'imported';src.mkdir();dst.mkdir()
def digest(f):return hashlib.sha256(f.read_bytes()).hexdigest()
# Deliberately synthetic payloads: not a usable voice model/editor project.
for rel,content in {'people/reference.fixture':b'reference-fixture','people/features.fixture':b'features-fixture','projects/edit.fixture':b'edit-fixture','media/video.fixture':b'media-fixture'}.items():
 f=src/rel;f.parent.mkdir(exist_ok=True);f.write_bytes(content)
c=sqlite3.connect(src/'catalog.sqlite');c.execute('PRAGMA foreign_keys=ON')
c.executescript('CREATE TABLE item(id TEXT PRIMARY KEY,kind TEXT,body TEXT,hidden INTEGER DEFAULT 0); CREATE TABLE link(owner TEXT REFERENCES item(id) ON DELETE RESTRICT,target TEXT REFERENCES item(id) ON DELETE RESTRICT,PRIMARY KEY(owner,target)); CREATE TABLE asset(id TEXT PRIMARY KEY REFERENCES item(id),path TEXT,sha256 TEXT,included INTEGER);')
items=[('P1','person','person'),('R1','reference','reference'),('V1','features','fixed-model-id'),('S1','video','video'),('T1','transcript','original'),('T2','transcript','manual correction'),('L1','intervals','10..20'),('L2','intervals','7..23'),('E1','edit','saved edit')]
c.executemany('INSERT INTO item(id,kind,body) VALUES(?,?,?)',items)
c.executemany('INSERT INTO link VALUES(?,?)',[('R1','P1'),('V1','R1'),('T1','S1'),('T1','P1'),('T2','T1'),('L1','T1'),('L2','T2'),('E1','L2'),('E1','S1')])
for id,rel,inc in [('R1','people/reference.fixture',1),('V1','people/features.fixture',1),('E1','projects/edit.fixture',1),('S1','media/video.fixture',0)]:c.execute('INSERT INTO asset VALUES(?,?,?,?)',(id,rel,digest(src/rel),inc))
c.execute("UPDATE item SET hidden=1 WHERE id='P1'");c.commit()
def snapshot(db):return {t:db.execute(f'SELECT * FROM {t} ORDER BY 1,2').fetchall() for t in ['item','link','asset']}
expected=snapshot(c);before={str(f.relative_to(src)):digest(f) for f in src.rglob('*') if f.is_file()}
backup=root/'snapshot.sqlite';b=sqlite3.connect(backup);c.backup(b);b.close()
manifest={'probe_format':1,'synthetic':True,'files':{'catalog.sqlite':digest(backup)}}
for rel, in c.execute('SELECT path FROM asset WHERE included=1'):manifest['files'][rel]=digest(src/rel)
archive=root/'transfer.zip'
with zipfile.ZipFile(archive,'w',allowZip64=True) as z:
 z.write(backup,'catalog.sqlite')
 for rel in manifest['files']:
  if rel!='catalog.sqlite':z.write(src/rel,rel)
 z.writestr('manifest.json',json.dumps(manifest))
# Trusted, locally generated archive only; not an untrusted archive importer.
with zipfile.ZipFile(archive) as z:z.extractall(dst)
d=sqlite3.connect(dst/'catalog.sqlite');d.execute('PRAGMA foreign_keys=ON')
checks={'backup_relations_equal':snapshot(d)==expected,'sqlite_integrity':d.execute('PRAGMA integrity_check').fetchone()[0]=='ok','foreign_key_integrity':not d.execute('PRAGMA foreign_key_check').fetchall(),'included_hashes_equal':all(digest(dst/rel)==h for rel,h in manifest['files'].items()),'media_not_bundled':not (dst/'media/video.fixture').exists(),'saved_text_read_without_models':d.execute("SELECT body FROM item WHERE id='T2'").fetchone()[0]=='manual correction','hidden_person_preserved':d.execute("SELECT hidden FROM item WHERE id='P1'").fetchone()[0]==1}
# Simulate a user-selected moved-media folder and reconnect only the copied DB.
moved=root/'moved-media';moved.mkdir();shutil.copy2(src/'media/video.fixture',moved/'renamed.fixture')
id,old,sha=d.execute("SELECT id,path,sha256 FROM asset WHERE id='S1'").fetchone();matches=[f for f in moved.iterdir() if digest(f)==sha]
assert len(matches)==1
d.execute('UPDATE asset SET path=? WHERE id=?',(str(matches[0]),id));d.execute("UPDATE item SET hidden=0 WHERE id='P1'");d.commit()
checks['reconnect_identity_and_links_preserved']=d.execute('SELECT * FROM link ORDER BY 1,2').fetchall()==expected['link'] and d.execute("SELECT sha256 FROM asset WHERE id='S1'").fetchone()[0]==sha
checks['source_unchanged']=snapshot(c)==expected and all(digest(src/rel)==h for rel,h in before.items())
d.close();c.close()
report={'python':sys.version.split()[0],'sqlite':sqlite3.sqlite_version,'checks':checks,'archive_bytes':archive.stat().st_size,'archive_sha256':digest(archive),'item_count':len(items),'local_fixture_root':str(root),'limits':['Toy schema and synthetic payloads; not adopted product format.','No real editor/model reopening, cross-PC or external-drive test.','ZIP64 enabled, but no >4GiB entry tested.','No fault injection, deletion, crash recovery or concurrent-write test.','Only trusted generated archive; no untrusted archive safety claim.']}
(p/'m08-normal-result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(report,ensure_ascii=False,indent=2));assert all(checks.values())
