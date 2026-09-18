"""Disposable M-07 feasibility harness, not application code."""
from pathlib import Path
from collections import Counter,defaultdict
import json,hashlib,importlib.metadata as md,zipfile
from sudachipy import dictionary,tokenizer
p=Path('docs/implements/evidence/tokenizer');t=dictionary.Dictionary().create();mode=tokenizer.Tokenizer.SplitMode.C
utterances=[{'id':'U1','start':10,'end':12,'text':'ゲーム大会、ゲーム大会。'},{'id':'U2','start':20,'end':22,'text':'ゲーム大会。'}]
def analyze(items,registered=(),excluded=(),verbs=False):
 rows=[]
 for u in items:
  s=u['text'];i=0;pending=0
  def normal(a,b):
   for m in t.tokenize(s[a:b],mode):
    if m.part_of_speech()[0] not in (('名詞','動詞','形容詞') if verbs else ('名詞',)):continue
    start=a+m.begin();end=a+m.end();raw=s[start:end]
    key=m.dictionary_form() if m.part_of_speech()[0] in ('動詞','形容詞') else raw
    rows.append({'id':u['id'],'time':[u['start'],u['end']],'span':[start,end],'raw':raw,'key':key,'registered':False})
  while i<len(s):
   candidates=[w for w in registered if w and s.startswith(w,i)]
   if not candidates:i+=1;continue
   w=max(candidates,key=len);normal(pending,i)
   rows.append({'id':u['id'],'time':[u['start'],u['end']],'span':[i,i+len(w)],'raw':w,'key':w,'registered':True})
   i+=len(w);pending=i
  normal(pending,len(s))
 rows=[r for r in rows if r['key'] not in excluded]
 counts=Counter(r['key'] for r in rows);refs=defaultdict(list)
 for r in rows:
  if r['id'] not in refs[r['key']]:refs[r['key']].append(r['id'])
 return {'counts':dict(counts),'utterance_ids':dict(refs),'rows':rows}
original=json.dumps(utterances,ensure_ascii=False)
a=analyze(utterances,['ゲーム','ゲーム大会']);snapshot=json.dumps(a,ensure_ascii=False)
b=analyze(utterances,['ゲーム','ゲーム大会'],['ゲーム大会']);c=analyze(utterances[:1],['ゲーム','ゲーム大会'])
v=analyze([{'id':'V1','start':0,'end':1,'text':'走った。'},{'id':'V2','start':1,'end':2,'text':'走る。'}],verbs=True)
s='猫 ネコ CAT cat ＣＡＴ';n=analyze([{'id':'N','start':0,'end':3,'text':s}])
x=analyze([{'id':'X','start':0,'end':3,'text':'🐈ゲーム大会で走った。'}],['ゲーム','ゲーム大会'],verbs=True)
checks={'m07_three_occurrences_two_utterances':a['counts']=={'ゲーム大会':3} and a['utterance_ids']=={'ゲーム大会':['U1','U2']},'exclusion_no_shorter_rematch':b['counts']=={},'speaker_exclusion':c['counts']=={'ゲーム大会':2} and c['utterance_ids']=={'ゲーム大会':['U1']},'verb_inflection':v['counts']=={'走る':2},'noun_surface_variants_separate':all(n['counts'].get(k)==1 for k in ['猫','ネコ','CAT','cat','ＣＡＴ']),'source_and_old_result_unchanged':json.dumps(utterances,ensure_ascii=False)==original and json.dumps(a,ensure_ascii=False)==snapshot,'registered_unicode_span':next(r for r in x['rows'] if r['registered'])['span']==[1,6],'utterance_times':all(r['time']==([10,12] if r['id']=='U1' else [20,22]) for r in a['rows'])}
files=[]
for distname in ['SudachiPy','SudachiDict-core']:
 dist=md.distribution(distname)
 for f in dist.files:
  path=Path(dist.locate_file(f))
  if path.name=='system.dic' or 'license' in str(f).lower() or 'notice' in str(f).lower():
   files.append({'distribution':distname,'file':str(f),'bytes':path.stat().st_size,'sha256':hashlib.file_digest(path.open('rb'),'sha256').hexdigest()})
report={'versions':{k:md.version(k) for k in ['SudachiPy','SudachiDict-core']},'mode':'C','checks':checks,'results':{'base':a,'excluded':b,'speaker_excluded':c,'verbs':v,'noun_variants':n,'unicode_offsets':x},'distribution_files':files,'limits':['Fixture-only prototype; no product UI/persistence.','No general guarantee for all inflections or lexical ambiguity.','Spans are Python Unicode code-point offsets, not UTF-16 indices.']}
(p/'m07-result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(checks));assert all(checks.values())
