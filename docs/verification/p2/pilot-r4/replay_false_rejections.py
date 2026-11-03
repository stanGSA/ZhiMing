"""Offline replay of r4 drafts using the actual fact sheet and a read-only KB."""
import json
import sqlite3
from pathlib import Path

from plugins.dream.match import DreamMatcher
from plugins.dream.validation import phrase_aliases, phrase_hits, text_error

root = Path.cwd()
directory = sorted(p for p in (root/'reports/p2-r4/Dream-pipeline').iterdir() if p.is_dir())[-1]
report_path = directory/'live.json'
rows = json.loads(report_path.read_text(encoding='utf8'))['results'] if report_path.exists() else json.loads((directory/'progress.json').read_text(encoding='utf8'))
connection = sqlite3.connect((directory/'workspace/data/kb.sqlite').resolve().as_uri()+'?mode=ro',uri=True)
matcher = DreamMatcher(connection,'r4-offline-replay')
examples = [
 ('dream_teeth_falling',0,'梦里牙齿一颗颗掉下来，醒来心慌，可能和最近担心失去掌控、形象受损或表达受阻有关。','本轮被拒草稿原句'),
 ('dream_teeth_falling',0,'梦里牙齿一颗颗掉下来。','移除解释后，只保留同义复述'),
 ('dream_teeth_falling',0,'梦里牙齿一颗一颗掉下来。','使用事实表原话的对照'),
 ('dream_teeth_falling',0,'梦里牙齿掉下来。','既有NORMALISATIONS能识别的另一种掉牙说法，但不是本条绑定原话'),
]
results=[]
for case,repeat,text,explanation in examples:
 row=next(r for r in rows if r['id']==case and r['repeat']==repeat)
 facts=next(v for k,v in row['calculated_facts'].items() if k.startswith('dream_result:'))
 results.append(dict(answer=f'{case}#{repeat+1}',text=text,explanation=explanation,hits=facts['hits'],misses=facts['misses'],phrase_hits=phrase_hits(facts['hits']),actual_error=text_error(text,matcher,{h['key'] for h in facts['hits']},set(facts['misses']),aliases=phrase_aliases(matcher,facts['hits']),phrases=phrase_hits(facts['hits']))))
connection.close()
output=root/'reports/p2-r4/false-rejection-replay.json'
output.write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps(results,ensure_ascii=False,indent=2))
