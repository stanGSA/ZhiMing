"""Session-local aliases at the model boundary; persisted facts keep full identifiers."""


def transform(value, session, *, restore=False):
    aliases = session.state.setdefault("ref_alias", {})
    reverse = {full: short for short, full in aliases.items()}

    def ref(item):
        if not isinstance(item, str):
            return item
        if restore:
            return aliases.get(item, item)
        if item not in reverse:
            short = f"R{len(aliases) + 1}"
            aliases[short] = item
            reverse[item] = short
        return reverse[item]

    def walk(item, key=None):
        if key == "ref_id":
            return ref(item)
        if key == "ref_ids" and isinstance(item, list):
            return [ref(v) for v in item]
        if isinstance(item, dict):
            return {k: walk(v, k) for k, v in item.items()}
        if isinstance(item, list):
            return [walk(v) for v in item]
        return item

    return walk(value)
