import io
import json
import re
import unicodedata
import zipfile
from pathlib import Path

from pydantic import Field

from harness.models import StrictInput
from harness.registry import Tool

ROOT = Path(__file__).resolve().parents[1]
COUNTRY_ALIASES = {
    "中国": "CN",
    "中國": "CN",
    "China": "CN",
    "美国": "US",
    "美國": "US",
    "United States": "US",
    "USA": "US",
    "英国": "GB",
    "英國": "GB",
    "UK": "GB",
    "United Kingdom": "GB",
    "加拿大": "CA",
    "印度": "IN",
    "挪威": "NO",
    "澳大利亚": "AU",
    "澳洲": "AU",
}
ADMIN_ALIASES = {
    "US": {
        "纽约州": "NY",
        "紐約州": "NY",
        "New York": "NY",
        "California": "CA",
        "加利福尼亚州": "CA",
        "密苏里州": "MO",
        "马萨诸塞州": "MA",
        "伊利诺伊州": "IL",
        "俄勒冈州": "OR",
        "俄亥俄州": "OH",
        "弗吉尼亚州": "VA",
        "宾夕法尼亚州": "PA",
        "田纳西州": "TN",
    },
    "CN": {
        "北京": "22",
        "北京市": "22",
        "上海": "23",
        "上海市": "23",
        "四川": "32",
        "四川省": "32",
        "江苏": "04",
        "江苏省": "04",
    },
}


def country_code(value):
    return COUNTRY_ALIASES.get(value, value).upper() if value else None


def normalize(value):
    return unicodedata.normalize("NFKC", value).strip().casefold()


class LocationInput(StrictInput):
    query: str = Field(min_length=1, max_length=200)
    country: str | None = Field(
        default=None, description="国家ISO两字母代码，如CN/US/GB；也接受明确的中文国名。"
    )
    admin1: str | None = Field(
        default=None, description="GeoNames省州代码；没有用户省州信息则null。"
    )
    candidate_id: str | None = None


class Gazetteer:
    def __init__(self, path: Path = ROOT / "data/geo/geonamescache-3.0.2.whl"):
        self.path = path
        self.records, self.index, self.names = {}, {}, {}

    def load(self):
        if self.records:
            return
        with zipfile.ZipFile(self.path) as archive:
            if "geonamescache/data/cities15000.json" in archive.namelist():
                data = json.loads(archive.read("geonamescache/data/cities15000.json"))
                rows = [
                    (
                        str(c["geonameid"]),
                        c["name"],
                        c["countrycode"],
                        c["admin1code"],
                        c["latitude"],
                        c["longitude"],
                        c["timezone"],
                        c["population"],
                        {c["name"], *c["alternatenames"]},
                    )
                    for c in data.values()
                ]
            else:
                # Retain support for historical GeoNames snapshots and caller fixtures.
                with io.TextIOWrapper(archive.open("cities15000.txt"), encoding="utf-8") as stream:
                    fields = [line.rstrip("\n").split("\t") for line in stream]
                rows = [
                    (
                        f[0],
                        f[1],
                        f[8],
                        f[10],
                        float(f[4]),
                        float(f[5]),
                        f[17],
                        int(f[14]),
                        {f[1], f[2], *f[3].split(",")},
                    )
                    for f in fields
                ]
            for identity, name, country, admin, lat, lon, tz, population, names in rows:
                self.records[identity] = dict(
                    location_id=identity,
                    name=name,
                    country=country,
                    admin1=admin,
                    lat=lat,
                    lon=lon,
                    tz=tz,
                    population=population,
                    source="GeoNames",
                    precision="city centroid",
                )
                for alias in names:
                    if alias:
                        self.index.setdefault(normalize(alias), set()).add(identity)
                        self.names.setdefault(identity, set()).add(alias)
        # Administrative suffixes and traditional spellings of common Chinese cities.
        aliases = {
            "北京": "1816670",
            "上海": "1796236",
            "广州": "1809858",
            "廣州": "1809858",
            "乌鲁木齐": "1529102",
            "烏魯木齊": "1529102",
            "纽约": "5128581",
            "紐約": "5128581",
            "伦敦": "2643743",
            "倫敦": "2643743",
        }
        for name, identity in aliases.items():
            if identity in self.records:
                self.index.setdefault(normalize(name), set()).add(identity)
                self.names.setdefault(identity, set()).add(name)
                if self.records[identity]["country"] == "CN":
                    self.index.setdefault(normalize(name + "市"), set()).add(identity)
                    self.names[identity].add(name + "市")
        for name in ("纽约市", "紐約市", "New York City"):
            self.index.setdefault(normalize(name), set()).add("5128581")
            self.names["5128581"].add(name)

    def resolve(self, args: LocationInput):
        self.load()
        query, inline_country = args.query, None
        for prefix, code in sorted(COUNTRY_ALIASES.items(), key=lambda pair: -len(pair[0])):
            remainder = query[len(prefix) :].lstrip(" ·,，")
            if query.startswith(prefix) and remainder and normalize(remainder) in self.index:
                query, inline_country = remainder, code
                break
        country = country_code(args.country) or inline_country
        admin = ADMIN_ALIASES.get(country, {}).get(args.admin1, args.admin1)
        ids = self.index.get(normalize(query), set())
        if inline_country and country != inline_country:
            ids = set()
        matches = [
            self.records[i]
            for i in ids
            if (not country or self.records[i]["country"] == country)
            and (not admin or self.records[i]["admin1"] == admin)
        ]
        matches.sort(key=lambda x: (-x["population"], x["location_id"]))
        if args.candidate_id:
            matches = [m for m in matches if m["location_id"] == args.candidate_id]
        if len(matches) != 1:
            return dict(
                status="needs_input",
                code="ambiguous_location" if matches else "missing_location",
                question="请确认出生地的国家/省州，或提供准确的城市及经纬度、IANA时区。",
                candidates=matches,
            )
        return dict(status="resolved", location=matches[0])


def location_tool(gazetteer: Gazetteer):
    def resolve(args, session):
        result = gazetteer.resolve(args)
        for candidate in result.get("candidates", []):
            session.state.setdefault("location_candidates", {})[candidate["location_id"]] = (
                candidate
            )
        if result["status"] == "resolved":
            location = result["location"]
            session.state.setdefault("locations", {})[location["location_id"]] = location
        return result

    def validate(args, session):
        text = " ".join(session.user_messages)
        source_place = session.profile.get("birth_place", "")
        original = gazetteer.resolve(LocationInput(query=args.query))
        unique = original.get("location")
        if normalize(args.query) not in normalize(text) and normalize(args.query) != normalize(
            source_place
        ):
            # Chinese/English alias translation is allowed only for the same stored city.
            source = gazetteer.resolve(LocationInput(query=source_place)) if source_place else {}
            proposed = gazetteer.resolve(LocationInput(query=args.query))
            alias_evidence = unique and any(
                len(alias) >= 2 and normalize(alias) in normalize(text)
                for alias in gazetteer.names[unique["location_id"]]
            )
            if not alias_evidence and (
                not source.get("location") or source.get("location") != proposed.get("location")
            ):
                return "地名必须来自用户原话或画像，不能自行换出生地"
        country_names = {
            "CN": ("中国", "中國"),
            "US": ("美国", "美國"),
            "GB": ("英国", "英國"),
            "CA": ("加拿大",),
            "IN": ("印度",),
            "AU": ("澳大利亚", "澳洲"),
            "NO": ("挪威",),
        }
        if args.country and not any(
            x.casefold() in text.casefold()
            for x in (args.country, *country_names.get(country_code(args.country), ()))
        ):
            original = gazetteer.resolve(LocationInput(query=args.query))
            locations = (
                [original["location"]]
                if original.get("location")
                else original.get("candidates", [])
            )
            if not locations or any(m["country"] != country_code(args.country) for m in locations):
                return "国家限制必须由用户明确提供，不能自行消歧"
        if args.admin1 and args.admin1 not in text:
            admin = ADMIN_ALIASES.get(country_code(args.country), {}).get(args.admin1, args.admin1)
            aliases = ADMIN_ALIASES.get(country_code(args.country), {})
            if not any(alias in text and code == admin for alias, code in aliases.items()) and (
                not unique or unique["admin1"] != admin
            ):
                return "省州限制须有用户确认"
        if args.candidate_id:
            candidate = session.state.get("location_candidates", {}).get(args.candidate_id)
            if candidate is None:
                if unique and unique["location_id"] == args.candidate_id:
                    candidate = unique
                else:
                    return "请先查询候选地名"
            if not unique and args.candidate_id not in text:
                candidates = original.get("candidates", [])
                country_evidence = any(
                    x in text for x in country_names.get(candidate["country"], ())
                ) or bool(re.search(rf"\b{candidate['country']}\b", text))
                aliases = ADMIN_ALIASES.get(candidate["country"], {})
                admin_evidence = any(
                    alias in text and code == candidate["admin1"] for alias, code in aliases.items()
                ) or bool(re.search(rf"(?<![A-Za-z0-9]){candidate['admin1']}(?![A-Za-z0-9])", text))
                narrowed = [
                    c
                    for c in candidates
                    if (not country_evidence or c["country"] == candidate["country"])
                    and (
                        not admin_evidence
                        or (c["country"], c["admin1"])
                        == (candidate["country"], candidate["admin1"])
                    )
                ]
                if len(narrowed) != 1 or narrowed[0]["location_id"] != args.candidate_id:
                    return "国家或省州仍未唯一确定同名城市，请确认真实候选location_id，不能自行选择"
        return None

    return Tool(
        "resolve_location",
        "离线解析地名、中文别名和IANA时区。同名地点必须ask_user确认候选编号/国家省州。",
        LocationInput,
        resolve,
        validator=validate,
        idempotent=False,
        roles=frozenset({"orchestrator", "astro", "bazi"}),
    )
