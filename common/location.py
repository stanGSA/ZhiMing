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
# GeoNames admin1 codes (not Chinese GB/T province codes).
for _code, _short, _full in [
    ("01", "安徽", "安徽省"),
    ("02", "浙江", "浙江省"),
    ("03", "江西", "江西省"),
    ("05", "吉林", "吉林省"),
    ("06", "青海", "青海省"),
    ("07", "福建", "福建省"),
    ("08", "黑龙江", "黑龙江省"),
    ("09", "河南", "河南省"),
    ("10", "河北", "河北省"),
    ("11", "湖南", "湖南省"),
    ("12", "湖北", "湖北省"),
    ("13", "新疆", "新疆维吾尔自治区"),
    ("14", "西藏", "西藏自治区"),
    ("15", "甘肃", "甘肃省"),
    ("16", "广西", "广西壮族自治区"),
    ("18", "贵州", "贵州省"),
    ("19", "辽宁", "辽宁省"),
    ("20", "内蒙古", "内蒙古自治区"),
    ("21", "宁夏", "宁夏回族自治区"),
    ("24", "山西", "山西省"),
    ("25", "山东", "山东省"),
    ("26", "陕西", "陕西省"),
    ("28", "天津", "天津市"),
    ("29", "云南", "云南省"),
    ("30", "广东", "广东省"),
    ("31", "海南", "海南省"),
    ("33", "重庆", "重庆市"),
]:
    ADMIN_ALIASES["CN"].update({_short: _code, _full: _code})


def _consultation_timezone_mention(text, start, end):
    """A birth clock label is not a request to change the consultation clock."""
    before = re.split(r"[，,。；;！!？?\n]", text[:start])[-1]
    after = re.split(r"[，,。；;！!？?\n]", text[end:])[0]
    if re.search(r"(?:不(?:要|再)?(?:按|用|使用|采用)?|不是|别(?:按|用)?)\s*$", before):
        return False
    birth = list(re.finditer(r"出生|生于|生辰|生日|钟表", before))
    consultation = list(
        re.finditer(r"本次|这次|咨询|现在|目前|现居|现住|我住在", before + text[start:end])
    )
    requested_after = re.match(
        r"(?:的)?(?:当地)?(?:时间)?(?:来)?(?:看|算|计算|咨询).{0,12}(?:运势|行运|流期)", after
    )
    if birth and not requested_after:
        if not consultation or consultation[-1].end() <= birth[-1].end():
            return False
    if re.search(r"出生|生于|生辰|生日|钟表", after) and not consultation and not requested_after:
        return False
    return True


def consultation_timezone_evidence(text, session, birth_tz=None):
    """Only current residence/consultation statements bind a resolved city to a timezone."""
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

    zones = set()
    for match in re.finditer(r"[A-Za-z_]+/[A-Za-z_+0-9/-]+", text):
        zone = match[0]
        if not _consultation_timezone_mention(text, match.start(), match.end()):
            continue
        try:
            ZoneInfo(zone)
            zones.add(zone)
        except (ValueError, OSError, ZoneInfoNotFoundError):  # e.g. a region directory name
            pass
    if any(
        _consultation_timezone_mention(text, m.start(), m.end())
        for m in re.finditer("北京时间", text)
    ):
        zones.add("Asia/Shanghai")
    if birth_tz and any(
        _consultation_timezone_mention(text, m.start(), m.end())
        for m in re.finditer(r"(?:按|使用|采用)\s*(?:出生地(?:当地)?(?:时间)?|当地(?:时间)?)", text)
    ):
        zones.add(birth_tz)
    for identity, location in session.state.get("locations", {}).items():
        aliases = session.state.get("location_aliases", {}).get(identity, [])
        for alias in {*aliases, location["name"]}:
            if len(alias) < 2:
                continue
            name = re.escape(alias)
            matches = re.finditer(
                rf"(?:现在住在|目前住在|现在在|目前在|现居|现住|我住在)\s*{name}(?![A-Za-z])|"
                rf"(?:按|使用|采用|咨询(?:时区|时间)?[是为：:]?)\s*{name}(?:的)?(?:当地)?时间",
                text,
                re.I,
            )
            if any(_consultation_timezone_mention(text, m.start(), m.end()) for m in matches):
                zones.add(location["tz"])
    return next(iter(zones)) if len(zones) == 1 else None


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
        if self.path == ROOT / "data/geo/geonamescache-3.0.2.whl":
            # Extend the city-only snapshot with real county coordinates and full paths.
            # Keep existing city aliases stable; an explicit administrative name/path
            # or ID identifies the finer location without substituting a nearby city.
            from common.regions import region_data

            for node in region_data()["nodes"].values():
                location = node.get("location")
                if not location or location["country"] != "CN":
                    continue
                identity = location["location_id"]
                self.records.setdefault(identity, location)
                aliases = {*node.get("aliases", []), node["path"], node["path"].replace(" · ", "")}
                for alias in aliases:
                    key = normalize(alias)
                    if (
                        key not in self.index
                        or (node["level"] == "district" and alias == node["name"])
                        or alias == node["path"]
                    ):
                        self.index.setdefault(key, set()).add(identity)
                        self.names.setdefault(identity, set()).add(alias)
                self.names.setdefault(identity, set()).add(node["name"])

    def resolve(self, args: LocationInput):
        self.load()
        query, inline_country = args.query, None
        for prefix, code in sorted(COUNTRY_ALIASES.items(), key=lambda pair: -len(pair[0])):
            remainder = query[len(prefix) :].lstrip(" ·,，")
            if query.startswith(prefix) and remainder and normalize(remainder) in self.index:
                query, inline_country = remainder, code
                break
        country = country_code(args.country) or inline_country
        ids = self.index.get(normalize(query), set())
        countries = {self.records[i]["country"] for i in ids}
        inferred_country = country or (next(iter(countries)) if len(countries) == 1 else None)
        admin = ADMIN_ALIASES.get(inferred_country, {}).get(args.admin1, args.admin1)
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
            session.state.setdefault("location_aliases", {})[location["location_id"]] = sorted(
                gazetteer.names[location["location_id"]] | {args.query}
            )
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
            countries = {c["country"] for c in original.get("candidates", [])}
            country = country_code(args.country) or (unique or {}).get("country")
            if not country and len(countries) == 1:
                country = next(iter(countries))
            aliases = ADMIN_ALIASES.get(country, {})
            admin = aliases.get(args.admin1, args.admin1)
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
