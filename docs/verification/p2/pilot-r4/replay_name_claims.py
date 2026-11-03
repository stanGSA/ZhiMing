"""Replay name validation fragments with r4's actual facts; no model requests."""
import json
from pathlib import Path
from plugins.name.validation import check_claims

root=Path.cwd()
path=sorted((root/'reports/p2-r4/Name-single').glob('*/live.json'))[-1]
rows=json.loads(path.read_text(encoding='utf8'))['results']
examples=[
 ('name_three_character',1,'整体五格数理四吉一凶。','类别计数被识别为数理4'),
 ('name_ambiguous_form',2,'人格是五格里最被看重的“自我与做事方式”那一格。','五格的五被识别为人格5'),
 ('name_compare_two',2,'李娜的人格、地格、总格三项都在传统所谓“吉”数里。','三项被识别为总格3'),
 ('name_career_grid',2,'三才是看天格、人格、地格三个位置尾数对应的五行关系。','三个位置被识别为地格3'),
]
out=[]
for case,repeat,text,note in examples:
 row=next(r for r in rows if r['id']==case and r['repeat']==repeat)
 facts={v['name_id']:v for k,v in row['calculated_facts'].items() if k.startswith('name_result:')}
 bound=next(iter(facts.values())) if len(facts)==1 else None
 out.append(dict(answer=f'{case}#{repeat+1}',text=text,note=note,actual_error=check_claims(text,bound,facts),facts={v['full_name']:v['grids'] for v in facts.values()}))
pipe_path=sorted((root/'reports/p2-r4/Name-pipeline').glob('*/live.json'))[-1]
pipe_rows=json.loads(pipe_path.read_text(encoding='utf8'))['results']
row=next(r for r in pipe_rows if r['id']=='name_three_character' and r['repeat']==2)
facts={v['name_id']:v for k,v in row['calculated_facts'].items() if k.startswith('name_result:')}
for text,note in [('只有外格一项提示波折。','一项误读为外格1'),('名字的数理是一份自我观察的线索。','一份误读为数理1')]:
 out.append(dict(answer='Name-pipeline/name_three_character#3',text=text,note=note,actual_error=check_claims(text,next(iter(facts.values())),facts),facts={v['full_name']:v['grids'] for v in facts.values()}))
(root/'reports/p2-r4/name-false-rejection-replay.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps(out,ensure_ascii=False,indent=2))
