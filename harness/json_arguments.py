"""Conservative recovery of quotes in prose; never complete or invent JSON fields."""

import json


def _is_cjk(char: str) -> bool:
    return "\u3000" <= char <= "\uffef"


def _closes_string(raw: str, index: int, *, allow_colon: bool) -> bool:
    """Whether the quote at ``index`` can structurally close the current JSON string."""
    tail = raw[index + 1 :].lstrip()
    if not tail:
        return False
    allowed = (":", ",", "}", "]") if allow_colon else (",", "}", "]")
    if tail[0] not in allowed:
        return False
    # In '{"body": "重点看"Offer""}', index of Offer's closing quote is followed by '"}',
    # so tail[0] is '"' (handled above). If tail[0] is ',', verify it is not prose like
    # '{"body": "选"A", 还是"B"}' where what follows ',' cannot start a JSON token/key.
    if tail[0] == ",":
        after_comma = tail[1:].lstrip()
        if after_comma and _is_cjk(after_comma[0]):
            return False
    return True


def _repair_prose_quotes(raw: str) -> dict:
    parts: list[str] = []
    changed = False
    i = 0
    n = len(raw)
    expecting_key = False
    stack: list[str] = []

    while i < n:
        ch = raw[i]
        if ch == "{":
            stack.append("{")
            expecting_key = True
            parts.append(ch)
            i += 1
            continue
        if ch == "[":
            stack.append("[")
            expecting_key = False
            parts.append(ch)
            i += 1
            continue
        if ch in ("}", "]"):
            if stack:
                stack.pop()
            expecting_key = False
            parts.append(ch)
            i += 1
            continue
        if ch == ":":
            expecting_key = False
            parts.append(ch)
            i += 1
            continue
        if ch == ",":
            expecting_key = bool(stack and stack[-1] == "{")
            parts.append(ch)
            i += 1
            continue
        if ch != '"':
            parts.append(ch)
            i += 1
            continue

        # Scan one JSON string starting at i.
        is_key = expecting_key
        parts.append('"')
        i += 1
        seg_chars: list[str] = []
        inner_positions: list[int] = []
        escaped = False
        closed = False
        while i < n:
            c = raw[i]
            if escaped:
                escaped = False
                seg_chars.append(c)
                i += 1
                continue
            if c == "\\":
                escaped = True
                seg_chars.append(c)
                i += 1
                continue
            if c == '"':
                if _closes_string(raw, i, allow_colon=is_key):
                    closed = True
                    break
                # If we are in a value and hit '":' (e.g. '{"body":"a" "other":1}'), do not repair.
                tail = raw[i + 1 :].lstrip()
                if not is_key and tail.startswith(":"):
                    raise json.JSONDecodeError("Expecting ',' delimiter", raw, i)
                inner_positions.append(len(seg_chars))
                seg_chars.append(c)
                i += 1
                continue
            seg_chars.append(c)
            i += 1

        if not closed:
            raise json.JSONDecodeError("Unterminated string", raw, i)

        segment = "".join(seg_chars)
        if inner_positions:
            has_cjk = any(_is_cjk(c) for c in segment)
            balanced_prose = (not is_key) and has_cjk and len(inner_positions) % 2 == 0
            escape_set: set[int] = set()
            if balanced_prose:
                escape_set.update(inner_positions)
            else:
                for pos in inner_positions:
                    rest = segment[pos + 1 :].lstrip()
                    if rest and _is_cjk(rest[0]):
                        escape_set.add(pos)
            if len(escape_set) != len(inner_positions):
                raise json.JSONDecodeError("Expecting ',' delimiter", raw, i)
            for idx, sc in enumerate(seg_chars):
                if idx in escape_set:
                    parts.append("\\")
                    changed = True
                parts.append(sc)
        else:
            parts.append(segment)

        parts.append('"')
        i += 1

    if not changed:
        raise json.JSONDecodeError("Unable to repair JSON", raw, 0)
    return json.loads("".join(parts))


def parse_arguments(raw: str) -> tuple[dict, bool]:
    try:
        value = json.loads(raw)
        repaired = False
    except json.JSONDecodeError:
        value = _repair_prose_quotes(raw)
        repaired = True
    if not isinstance(value, dict):
        raise ValueError("object required")
    return value, repaired
