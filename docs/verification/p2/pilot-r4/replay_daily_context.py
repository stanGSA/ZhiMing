"""Offline check of a daily summary's transit/natal context using the actual record."""
import json
from pathlib import Path
from common.schemas import Reading
from plugins.astro.validation import validate_output

root=Path.cwd()
path=sorted((root/'reports/p2-r4/Daily-single').glob('*/live.json'))[-1]
rows=json.loads(path.read_text(encoding='utf8'))['results']
row=next(r for r in rows if r['id']=='daily_investment_risk' and r['repeat']==0)
draft=None
for line in Path(row['trace']).read_text(encoding='utf8').splitlines():
 e=json.loads(line)
 if e.get('event')=='tool_result' and e.get('call',{}).get('name')=='submit_reading' and not e['result']['ok']:
  draft=e['call']['arguments'];break
reading=Reading.model_validate(draft)
state=dict(row['calculated_facts'])
state['daily_result']['interpretations']=state['daily_result']['cited_interpretations']
out=[]
for summary in [reading.summary,reading.summary.replace('火星四分本命太阳','行运火星四分本命太阳')]:
 sample=reading.model_copy(update={'summary':summary,'sections':[],'timeline':[],'advice':[],'resonances':[],'tensions':[],'closing':'','followups':[]})
 out.append(dict(summary=summary,actual_error=validate_output(sample,state)))
(root/'reports/p2-r4/daily-context-replay.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps(out,ensure_ascii=False,indent=2))
