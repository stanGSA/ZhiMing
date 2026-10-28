"""Conservative recovery of quotes in prose; never complete or invent JSON fields."""

import json


def parse_arguments(raw: str) -> tuple[dict, bool]:
    try:
        value = json.loads(raw)
        repaired = False
    except json.JSONDecodeError:
        # Only escape a quote which cannot close a JSON string because what follows
        # is prose, not JSON punctuation. Ambiguous damage remains an argument error.
        parts = []
        in_string = escaped = changed = False
        for index, char in enumerate(raw):
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    tail = raw[index + 1 :].lstrip()
                    if tail and "\u3000" <= tail[0] <= "\uffef":
                        parts.append("\\")
                        changed = True
                    else:
                        in_string = False
            elif char == '"':
                in_string = True
            parts.append(char)
        if not changed:
            raise
        value = json.loads("".join(parts))
        repaired = True
    if not isinstance(value, dict):
        raise ValueError("object required")
    return value, repaired
