"""Read-only, versioned GeoNames hierarchy used by the browser and location tool."""

import gzip
import json
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def region_data():
    path = Path(__file__).with_name("region_data") / "regions.json.gz"
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        return json.load(stream)


@lru_cache(maxsize=1)
def children_index():
    result = {}
    for node in region_data()["nodes"].values():
        result.setdefault(node["parent"], []).append(node)
    return result


def region_options(parent=None):
    children = children_index().get(parent, [])
    return [
        dict(
            id=n["id"],
            name=n["name"],
            level=n["level"],
            has_children=n["id"] in children_index(),
            selectable="location" in n,
        )
        for n in sorted(children, key=lambda n: (n["id"] != "CN", n["name"]))
    ]


def selected_region(identity):
    node = region_data()["nodes"].get(identity)
    if not node or "location" not in node:
        raise ValueError("请逐级选择有效的出生城市或区县。")
    chain, current = [], node
    while current:
        chain.append(dict(id=current["id"], name=current["name"], level=current["level"]))
        current = region_data()["nodes"].get(current["parent"])
    return {**node["location"], "path": list(reversed(chain))}
