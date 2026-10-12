"""YAML dump: block style everywhere, except short lists of scalars, which go inline."""
import yaml


class _Dumper(yaml.SafeDumper):
    def ignore_aliases(self, data):
        return True


def _list(dumper, data):
    flow = all(not isinstance(x, (dict, list)) for x in data) and len(data) <= 12
    return dumper.represent_sequence("tag:yaml.org,2002:seq", data, flow_style=flow)


_Dumper.add_representer(list, _list)


def dump(doc, path):
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(doc, f, Dumper=_Dumper, allow_unicode=True, sort_keys=False, width=160, default_flow_style=False)
