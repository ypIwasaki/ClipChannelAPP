"""Read-only inventory of the SDK actually used by the probes."""
from pathlib import Path
import re,json,hashlib
sdk=Path(r'C:/Users/raimu/AppData/Local/ClipChannelAPP-validation/editor-sdk-observer/plugin2.h')
b=sdk.read_bytes();t=b.decode('utf-8-sig');functions=[]
for n,line in enumerate(t.splitlines(),1):
 for name in re.findall(r'\(\*(\w+)\)\(',line):
  if not name.startswith('func_'):functions.append({'name':name,'line':n})
terms=['project','save','load','undo','redo','batch','rendering','event','menu','edit_state']
result={'file':str(sdk),'sha256':hashlib.sha256(b).hexdigest(),'function_pointer_declarations':len(functions),'relevant_declarations':{term:[x for x in functions if term in x['name'].lower()] for term in terms},'scope':'Name inventory supports manual header review; absence of a matching name alone is not proof of impossibility.'}
r=Path(__file__).resolve().parent
(r/'sdk-control-inventory.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(result,ensure_ascii=False,indent=2))
