"""Replay r4's negated certainty sentence offline with the tested wording policy."""
import json
from pathlib import Path
from common.output_policy import certainty_error

texts = [
    '而不是把它理解成必然的坎坷。',
    '不要把它理解成必然的坎坷。',
    '不必把它理解为必然的坎坷。',
    '它必然遭遇坎坷。',
]
result = [dict(text=text, actual_error=certainty_error([text])) for text in texts]
Path('reports/p2-r4/certainty-false-rejection-replay.json').write_text(
    json.dumps(result, ensure_ascii=False, indent=2), encoding='utf8'
)
print(json.dumps(result, ensure_ascii=False, indent=2))
