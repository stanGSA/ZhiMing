"""Build the bundled location selector from GeoNames snapshots (CC BY 4.0).

Inputs: data/geo/CN.snapshot.zip, admin1CodesASCII.txt, geonamescache-3.0.2.whl.
Only data files are read; no downloaded code is executed.
"""

import gzip
import hashlib
import io
import json
import re
import zipfile
from pathlib import Path

from common.location import ADMIN_ALIASES

ROOT = Path(__file__).resolve().parents[1]
COUNTRIES_ZH = {
    "CN": "中国",
    "HK": "中国香港",
    "MO": "中国澳门",
    "TW": "中国台湾",
    "US": "美国",
    "GB": "英国",
    "CA": "加拿大",
    "AU": "澳大利亚",
    "NZ": "新西兰",
    "JP": "日本",
    "KR": "韩国",
    "SG": "新加坡",
    "MY": "马来西亚",
    "TH": "泰国",
    "VN": "越南",
    "IN": "印度",
    "ID": "印度尼西亚",
    "PH": "菲律宾",
    "FR": "法国",
    "DE": "德国",
    "IT": "意大利",
    "ES": "西班牙",
    "RU": "俄罗斯",
    "NO": "挪威",
    "SE": "瑞典",
    "CH": "瑞士",
    "NL": "荷兰",
    "BR": "巴西",
    "ZA": "南非",
}


def chinese_name(name, aliases):
    candidates = [a for a in aliases if re.fullmatch(r"[\u3400-\u9fff·]+", a) and len(a) > 1]
    suffix = {"Xian": "县", "Qu": "区", "Shi": "市", "Zhou": "州", "Qi": "旗"}.get(name.split()[-1])
    preferred = [a for a in candidates if a.endswith(suffix)] if suffix else []
    preferred = preferred or [
        a for a in candidates if a.endswith(("省", "自治区", "市", "州", "县", "区", "旗", "盟"))
    ]
    return max(preferred or candidates, key=lambda a: (len(a), a)) if candidates else name


def build():
    geo = ROOT / "data/geo"
    paths = [geo / "CN.snapshot.zip", geo / "admin1CodesASCII.txt", geo / "geonamescache-3.0.2.whl"]
    with zipfile.ZipFile(paths[2]) as archive:
        countries = json.loads(archive.read("geonamescache/data/countries.json"))
        cities = json.loads(archive.read("geonamescache/data/cities15000.json"))
    nodes = {}
    available_countries = {c["countrycode"] for c in cities.values()} | {"CN"}
    for code in sorted(available_countries):
        nodes[code] = dict(
            id=code,
            parent=None,
            level="country",
            name=COUNTRIES_ZH.get(code, countries[code]["name"]),
        )
    admins = {}
    for line in paths[1].read_text(encoding="utf-8").splitlines():
        code, name, *_ = line.split("\t")
        admins[code] = name
    for city in cities.values():
        code = city["countrycode"]
        if code == "CN":
            continue
        parent = f"{code}.{city['admin1code'] or '00'}"
        nodes.setdefault(
            parent,
            dict(id=parent, parent=code, level="province", name=admins.get(parent, "其他行政区域")),
        )
        identity = str(city["geonameid"])
        name = (
            chinese_name(city["name"], city["alternatenames"])
            if code in ("HK", "MO", "TW")
            else city["name"]
        )
        nodes[identity] = dict(
            id=identity,
            parent=parent,
            level="city",
            name=name,
            location=dict(
                location_id=identity,
                name=name,
                country=code,
                admin1=city["admin1code"],
                lat=city["latitude"],
                lon=city["longitude"],
                tz=city["timezone"],
                population=city["population"],
                source="GeoNames",
                precision="city centroid",
            ),
        )
    raw = []
    with zipfile.ZipFile(paths[0]) as archive:
        with io.TextIOWrapper(archive.open("CN.txt"), encoding="utf-8") as stream:
            for line in stream:
                row = line.rstrip("\n").split("\t")
                if row[7] in ("ADM1", "ADM2", "ADM3"):
                    raw.append(row)
    province_ids = {r[10]: r[0] for r in raw if r[7] == "ADM1"}
    province_timezones = {r[10]: r[17] for r in raw if r[7] == "ADM1"}
    city_ids = {(r[10], r[11]): r[0] for r in raw if r[7] == "ADM2"}
    for row in sorted(raw, key=lambda r: r[7]):
        identity, name, _, alternate, lat, lon, _, feature, country, _, admin1, admin2, *_ = row
        if admin1 not in province_ids:
            continue
        aliases = set(alternate.split(",")) | {name}
        name_zh = chinese_name(name, aliases)
        if feature == "ADM1":
            known = [alias for alias, code in ADMIN_ALIASES["CN"].items() if code == admin1]
            name_zh = max(known, key=len) if known else name_zh
            parent, level = "CN", "province"
        elif feature == "ADM2":
            parent, level = province_ids[admin1], "city"
        else:
            parent = city_ids.get((admin1, admin2))
            if not parent:
                parent = f"CN.{admin1}.direct"
                nodes.setdefault(
                    parent,
                    dict(
                        id=parent,
                        parent=province_ids[admin1],
                        level="city",
                        name="省直辖县级行政区",
                    ),
                )
            level = "district"
        node = dict(id=identity, parent=parent, level=level, name=name_zh)
        if feature != "ADM1":
            node["location"] = dict(
                location_id=identity,
                name=name_zh,
                country=country,
                admin1=admin1,
                lat=float(lat),
                lon=float(lon),
                tz=row[17] or province_timezones[admin1],
                timezone_source="GeoNames record" if row[17] else "GeoNames parent province",
                population=int(row[14]),
                source="GeoNames",
                precision="administrative centroid",
            )
            node["aliases"] = sorted(a for a in aliases | {name_zh} if a)
        nodes[identity] = node
    for item in nodes.values():
        chain, current = [], item
        while current:
            chain.append(current["name"])
            current = nodes.get(current["parent"])
        item["path"] = " · ".join(reversed(chain))
        if item.get("location"):
            item["location"]["display_name"] = item["path"]
    output = ROOT / "common/region_data/regions.json.gz"
    output.parent.mkdir(exist_ok=True)
    metadata = dict(
        source="https://www.geonames.org/",
        license="CC BY 4.0",
        snapshot_date="2026-10-15",
        scope="CN administrative levels 1–3; worldwide cities15000",
        inputs={p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},
    )
    output.write_bytes(
        gzip.compress(
            json.dumps(
                dict(metadata=metadata, nodes=nodes), ensure_ascii=False, separators=(",", ":")
            ).encode(),
            mtime=0,
        )
    )
    print(f"Built {len(nodes)} nodes, {output.stat().st_size} compressed bytes")
    print(json.dumps(nodes["1803361"], ensure_ascii=False))


if __name__ == "__main__":
    build()
