"""Session-local aliases at the model boundary; persisted facts keep full identifiers.

Only citable references cross the boundary. When the session holds a reading's
``allowed_refs``, a ``ref_id`` outside that set (a knowledge-base entry, another reading's
fact) is removed from the model's view instead of being numbered, so every R-number the model
sees is one it may submit. Full results, with every source, stay in state and the trace.
"""

from copy import deepcopy


def short(ref: str, session) -> str:
    """The R-number the model knows this reference by; numbered on first use."""
    aliases = session.state.setdefault("ref_alias", {})
    for alias, full in aliases.items():
        if full == ref:
            return alias
    alias = f"R{len(aliases) + 1}"
    aliases[alias] = ref
    return alias


def transform(value, session, *, restore=False):
    aliases = session.state.setdefault("ref_alias", {})
    reverse = {full: alias for alias, full in aliases.items()}
    citable = None if restore else session.state.get("allowed_refs")
    hidden = object()

    def ref(item):
        if not isinstance(item, str):
            return item
        if restore:
            return aliases.get(item, item)
        if citable is not None and item not in citable:
            return hidden
        if item not in reverse:
            alias = f"R{len(aliases) + 1}"
            aliases[alias] = item
            reverse[item] = alias
        return reverse[item]

    def walk(item, key=None):
        if key == "ref_id":
            return ref(item)
        if key == "ref_ids" and isinstance(item, list):
            return [r for r in (ref(v) for v in item) if r is not hidden]
        if isinstance(item, dict):
            walked = {k: walk(v, k) for k, v in item.items()}
            return {k: v for k, v in walked.items() if v is not hidden}
        if isinstance(item, list):
            return [walk(v) for v in item]
        return item

    return walk(value)


def constrain(schema: dict, session) -> dict:
    """List the R-numbers the model has seen and may cite in its ``ref_id``/``ref_ids`` fields.

    The enum guides generation only; Guard and the output validators still decide.
    """
    allowed = session.state.get("allowed_refs")
    aliases = session.state.get("ref_alias", {})
    citable = sorted(
        (alias for alias, full in aliases.items() if allowed and full in allowed),
        key=lambda alias: int(alias[1:]),
    )
    if not citable:
        return schema
    schema = deepcopy(schema)

    def walk(node):
        if isinstance(node, list):
            for value in node:
                walk(value)
            return
        if not isinstance(node, dict):
            return
        properties = node.get("properties") or {}
        single = properties.get("ref_id")
        if isinstance(single, dict) and single.get("type") == "string":
            single["enum"] = citable
        items = (properties.get("ref_ids") or {}).get("items")
        if isinstance(items, dict) and items.get("type") == "string":
            items["enum"] = citable
        for value in node.values():
            walk(value)

    walk(schema)
    return schema
