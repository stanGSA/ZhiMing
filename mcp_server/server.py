"""MCP server for the deterministic plugins: charts, draws and meanings, never a language model.

``uv run python -m mcp_server`` serves it over stdio. Every tool calls plugins.direct, the
session-free entry: the inputs are what the MCP client passes, there is no conversation for the
runtime's provenance checks to read, and the runtime and its Guard are neither used nor changed.

A calculation that needs a decision from the person (an ambiguous place, a Xinjiang birth
clock, solar time for an overseas birth) returns ``status: needs_input`` with the question, as
the runtime tools do. Arguments the tools cannot accept come back as an error result whose
structured content is ``{ok: false, code, error, details}``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Annotated, Any, Literal

import yaml
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.types import CallToolResult, TextContent, ToolAnnotations
from pydantic import Field, ValidationError

from common.location import Gazetteer
from common.time_utils import NeedsInput
from knowledge.kb import KnowledgeBase
from plugins.direct import Birth, Calculator, DirectError

# Not app.ROOT: the build copies app.py into site-packages, so a client that starts the server
# outside the repository would import that copy and look for the knowledge base beside it.
ROOT = Path(__file__).resolve().parents[1]
INSTRUCTIONS = (
    "知命的确定性计算：排盘、流期、抽牌、姓名五格、解梦意象匹配、每日运势和释义查询，全部由代码计算，"
    "不调用语言模型，同样的输入得到同样的结果（塔罗传入 seed 才能复现）。出生资料由调用方直接给出，"
    "请只使用用户本人提供的资料，不要猜测出生日期、时辰或地点。返回 needs_input 时请把 question 转问用户。"
    "每条释义带 ref_id 与审核级别（draft 为未经审核、model_reviewed 为经模型交叉审核、未经人工审核），"
    "review.confidence_cap 是据此得出的置信度上限。解读仅供参考与自我反思，不对健康、法律、投资、生死作确定性预测。"
)
SYSTEMS = Literal["tarot", "astro", "bazi", "name", "dream", "daily"]
READ_ONLY = ToolAnnotations(readOnlyHint=True, idempotentHint=True, openWorldHint=False)

BirthArg = Annotated[Birth, Field(description="出生资料：日期时间、时辰是否已知、地点")]
Day = Annotated[str, Field(description="日期 YYYY-MM-DD")]
PeriodTz = Annotated[
    str, Field(description="咨询日期所用的 IANA 时区，如 Asia/Shanghai；不一定是出生地时区")
]
SolarTime = Annotated[
    bool | None,
    Field(
        description="是否用真太阳时。省略时国内钟表按固定UTC+8；海外出生须明确给出，否则返回needs_input"
    ),
]
ZishiRule = Annotated[
    Literal["next_day", "same_day"],
    Field(description="next_day：23点换日（默认）；same_day：0点换日"),
]


def error(code: str, message: str, details: list | None = None) -> CallToolResult:
    payload = dict(ok=False, code=code, error=message, **({"details": details} if details else {}))
    return CallToolResult(
        content=[TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))],
        structuredContent=payload,
        isError=True,
    )


class Server(FastMCP):
    """FastMCP that reports rejected arguments and inputs as structured error results."""

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        try:
            return await super().call_tool(name, arguments)
        except ToolError as exc:
            cause = exc.__cause__
            if isinstance(cause, ValidationError):
                return error(
                    "invalid_arguments",
                    "参数不符合工具定义",
                    [
                        dict(field=".".join(str(part) for part in e["loc"]), message=e["msg"])
                        for e in cause.errors(include_url=False)
                    ],
                )
            if isinstance(cause, DirectError):
                return error(cause.code, str(cause))
            if isinstance(cause, ValueError):
                return error("invalid_arguments", str(cause))
            raise


def answer(calculate, *args, **kwargs) -> dict:
    """A question the person must answer first is a result, not an error."""
    try:
        return calculate(*args, **kwargs)
    except NeedsInput as exc:
        return exc.result()


def build_server(kb_path: Path | None = None, gazetteer: Gazetteer | None = None) -> Server:
    if kb_path is None:
        config = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
        kb_path = ROOT / config["kb"]["path"]
    calculator = Calculator(KnowledgeBase(kb_path), gazetteer)
    # Request logs go to stderr; keep them to warnings so a client's log stays readable.
    server = Server("zhiming", instructions=INSTRUCTIONS, log_level="WARNING")

    @server.tool(annotations=READ_ONLY)
    def resolve_location(
        query: Annotated[
            str,
            Field(min_length=1, max_length=200, description="地名，如 北京、成都市武侯区、London"),
        ],
        country: Annotated[str | None, Field(description="国家 ISO 两字母代码，如 CN、US")] = None,
        admin1: Annotated[str | None, Field(description="GeoNames 省州代码")] = None,
        candidate_id: Annotated[
            str | None, Field(description="同名地点时，从 candidates 里选定的 location_id")
        ] = None,
    ) -> dict[str, Any]:
        """解析出生地：返回 location_id、经纬度与时区；同名地点返回候选供确认。"""
        return answer(calculator.resolve_location, query, country, admin1, candidate_id)

    @server.tool(annotations=READ_ONLY)
    def compute_natal_chart(birth: BirthArg) -> dict[str, Any]:
        """本命盘：行星落座与宫位、四轴、相位（地心视位置、回归黄道，Placidus，无定义时用 Porphyry）。
        时辰未知时宫位与四轴为 null。每个事实附带 ref_id、释义与审核级别。"""
        return answer(calculator.natal_chart, birth)

    @server.tool(annotations=READ_ONLY)
    def compute_transits(
        birth: BirthArg,
        start: Day,
        end: Day,
        tz: PeriodTz,
        orb: Annotated[float, Field(gt=0, le=8, description="相位容许度（度）")] = 1.0,
        bodies: Annotated[
            list[str] | None, Field(description="行运行星英文名，如 Saturn；省略为全部十颗")
        ] = None,
    ) -> dict[str, Any]:
        """行运：日期区间内行运行星对本命行星的精确相位事件（结束日包含，最长 3660 天）。"""
        return answer(calculator.transits, birth, start, end, tz, orb, bodies)

    @server.tool(annotations=READ_ONLY)
    def compute_bazi(
        birth: BirthArg,
        gender: Annotated[
            Literal["male", "female"] | None, Field(description="排大运需要；省略则不排大运")
        ] = None,
        true_solar_time: SolarTime = None,
        zishi_rule: ZishiRule = "next_day",
        calendar: Annotated[
            Literal["solar", "lunar"],
            Field(description="lunar 时填 lunar_date，birth_local 可省略"),
        ] = "solar",
        lunar_date: Annotated[
            str | None, Field(description="农历日期，如 一九九〇年正月初九 10:00")
        ] = None,
        leap_month: Annotated[bool | None, Field(description="农历是否闰月")] = None,
        dayun_time_basis: Annotated[
            Literal["civil", "physical"],
            Field(description="起运口径：civil 修正钟表，physical 物理时刻"),
        ] = "civil",
        accept_uncertain: Annotated[
            bool, Field(description="时辰未知且当天换年换月时，接受年柱月柱以候选列出")
        ] = False,
    ) -> dict[str, Any]:
        """八字：四柱（时辰未知为三柱）、十神、藏干、纳音、五行计数与大运；不计算喜用神。
        立春换年、节气换月按物理时刻。每个事实附带 ref_id、释义与审核级别。"""
        return answer(
            calculator.compute_bazi,
            birth,
            gender=gender,
            true_solar_time=true_solar_time,
            zishi_rule=zishi_rule,
            calendar=calendar,
            lunar_date=lunar_date,
            leap_month=leap_month,
            dayun_time_basis=dayun_time_basis,
            accept_uncertain=accept_uncertain,
        )

    @server.tool(annotations=READ_ONLY)
    def compute_bazi_period(
        birth: BirthArg,
        start: Day,
        end: Day,
        tz: PeriodTz,
        granularity: Annotated[
            Literal["year", "month", "day"], Field(description="流年、节气流月或流日")
        ] = "month",
        true_solar_time: SolarTime = None,
        zishi_rule: ZishiRule = "next_day",
        calendar: Literal["solar", "lunar"] = "solar",
        lunar_date: str | None = None,
        leap_month: bool | None = None,
    ) -> dict[str, Any]:
        """流期：区间内的流年、流月或流日干支，与原局的十神和冲合刑害；按实际立春、节气与日界分段。"""
        return answer(
            calculator.bazi_period,
            birth,
            start,
            end,
            granularity,
            tz,
            true_solar_time=true_solar_time,
            zishi_rule=zishi_rule,
            calendar=calendar,
            lunar_date=lunar_date,
            leap_month=leap_month,
        )

    @server.tool(
        annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=False, openWorldHint=False)
    )
    def draw_tarot(
        question: Annotated[str, Field(min_length=1, max_length=2000)],
        spread: Annotated[
            Literal["single", "three_card", "decision"],
            Field(description="single 单张；three_card 过去现在未来；decision 现状/A/B"),
        ] = "three_card",
        seed: Annotated[
            int | None,
            Field(ge=0, lt=2**64, description="传入同一 seed 得到同样的牌；省略时随机生成并返回"),
        ] = None,
        picks: Annotated[
            list[int] | None,
            Field(description="从背面朝上的 78 张牌中选的位置（0-77），每个牌位一张"),
        ] = None,
    ) -> dict[str, Any]:
        """抽塔罗牌：SHA256 排序（tarot-sha256-v1），不使用 Python random；牌面附释义与审核级别。"""
        return answer(calculator.draw_tarot, spread, question, seed, picks)

    @server.tool(annotations=READ_ONLY)
    def analyze_name(
        surname: Annotated[str, Field(min_length=1, max_length=2, description="姓；复姓两字")],
        given: Annotated[str, Field(min_length=1, max_length=3, description="名")],
        forms: Annotated[
            dict[str, str] | None,
            Field(
                description='确认过的写法，如 {"杰": "傑"}；有歧义的字默认写法见 confirmation_prompts'
            ),
        ] = None,
    ) -> dict[str, Any]:
        """姓名五格：Unihan 康熙笔画、天人地外总五格与 81 数理、三才五行；查不到的字不猜笔画。"""
        return answer(calculator.analyze_name, surname, given, forms)

    @server.tool(annotations=READ_ONLY)
    def lookup_dream_symbols(
        symbols: Annotated[
            list[Annotated[str, Field(min_length=1, max_length=12)]],
            Field(min_length=1, max_length=12, description="梦里的意象，如 掉牙、被追；每项一个"),
        ],
    ) -> dict[str, Any]:
        """解梦意象匹配：同义词表、包含匹配、BM25 候选加相似度门槛；未命中的意象不解读。"""
        return answer(calculator.dream_symbols, symbols)

    @server.tool(annotations=READ_ONLY)
    def daily_fortune(
        birth: BirthArg,
        date: Day,
        tz: PeriodTz,
        true_solar_time: SolarTime = None,
        zishi_rule: ZishiRule = "next_day",
        user_key: Annotated[
            str | None,
            Field(
                min_length=1,
                max_length=64,
                description="决定每日一牌的用户标识；省略时由出生资料生成，同人同日结果相同",
            ),
        ] = None,
    ) -> dict[str, Any]:
        """每日运势：当天月亮与快行星对本命的精确相位、流日干支与日主十神、每日一牌。"""
        return answer(
            calculator.daily_fortune, birth, date, tz, true_solar_time, zishi_rule, user_key
        )

    @server.tool(annotations=READ_ONLY)
    def lookup_meaning(
        system: SYSTEMS,
        kind: Annotated[str, Field(description="条目类型，如 card、planet_sign、ten_god")],
        key: Annotated[str, Field(description="条目键，如 the_fool:upright、Sun:Aries")],
    ) -> dict[str, Any]:
        """按 system/kind/key 精确查释义，返回 ref_id、正文与审核级别；不做模糊匹配。"""
        return answer(calculator.lookup_meaning, system, kind, key)

    return server


def main():
    try:
        server = build_server()
    except FileNotFoundError as exc:
        # stdout belongs to the protocol; explain on stderr.
        print(f"{exc}（MCP server 需要先运行 python -m knowledge.build）", file=sys.stderr)
        raise SystemExit(1) from exc
    server.run("stdio")
