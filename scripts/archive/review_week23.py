"""Re-evaluate preserved answers with complete transit evidence; never rewrite attempts."""

import argparse
import asyncio
import json
import time
import uuid
from pathlib import Path

import yaml
from dotenv import load_dotenv

from app import ROOT, build_model
from plugins.astro.tools import AstroPlugin
from scripts.live_week23 import RUBRIC


async def review(run, cases):
    load_dotenv(ROOT / ".env")
    source = run / "live.json"
    if not source.exists():
        source = run / "progress.json"
    data = json.loads(source.read_text(encoding="utf-8"))
    rows = data["results"] if isinstance(data, dict) else data
    config = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    model = build_model(
        config["llm"]["provider"], config["models"]["reviewer"], config, None, "reviewer"
    )
    output = run / ("evidence-rereview-" + uuid.uuid4().hex[:8] + ".json")
    reviews = []
    try:
        for row in rows:
            if cases and row["id"] not in cases:
                continue
            facts = row["calculated_facts"]
            for line in Path(row["trace"]).read_text(encoding="utf-8").splitlines():
                event = json.loads(line)
                if (
                    event["event"] == "tool_result"
                    and event["call"]["name"] == "compute_transits"
                    and event["result"]["ok"]
                    and "events" in event["result"]["data"]
                ):
                    raw = event["result"]["data"]
                    facts["transit_result"]["events"] = raw["events"]
                    facts["transit_result"]["event_count"] = len(raw["events"])
                    facts["transit_result"]["event_projection"] = (
                        "Complete computed events; includes uncited timeline nodes."
                    )
                    facts["transit_result"]["model_available_interpretations"] = (
                        AstroPlugin.project(raw)["interpretations"]
                    )
            started = time.perf_counter()
            result = await model.chat(
                [
                    dict(role="system", content=RUBRIC),
                    dict(
                        role="user",
                        content=json.dumps(
                            dict(
                                question=row["question"],
                                answer=row["answer"],
                                structured=row["structured"],
                                facts=facts,
                            ),
                            ensure_ascii=False,
                        ),
                    ),
                ],
                [],
            )
            verdict = json.loads(result.text.strip().removeprefix("```json").removesuffix("```"))
            item = dict(
                id=row["id"],
                original_run=run.name,
                original_quality_pass=row["quality_pass"],
                review=verdict,
                requested_model=model.model,
                returned_model=result.model,
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
                latency_s=round(time.perf_counter() - started, 3),
                reason="Corrected evidence projection only; answer unchanged, original scores retained.",
            )
            reviews.append(item)
            output.write_text(json.dumps(reviews, ensure_ascii=False, indent=2), encoding="utf-8")
            print(json.dumps(item, ensure_ascii=False), flush=True)
    finally:
        await model.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--cases", nargs="*")
    args = parser.parse_args()
    asyncio.run(review(args.run, args.cases))
