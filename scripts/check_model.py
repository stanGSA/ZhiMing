"""Opt-in connectivity probe: no credential, endpoint, or request headers in output."""

import asyncio
import json
import time
from pathlib import Path

import yaml
from dotenv import load_dotenv

from app import ROOT
from harness.llm import OpenAIModel


async def main():
    load_dotenv(ROOT / ".env")
    config = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    model = OpenAIModel("gpt-6.1-sol", 90, config["llm"].get("system_role", "system"))
    started = time.perf_counter()
    try:
        response = await model.chat([dict(role="user", content="连接测试，请仅回复OK。")], [])
        record = dict(
            requested_model=model.model,
            returned_model=response.model,
            input_tokens=response.input_tokens if response.usage_available else None,
            output_tokens=response.output_tokens if response.usage_available else None,
            usage_available=response.usage_available,
            answer=response.text,
            latency_s=round(time.perf_counter() - started, 3),
            model_calls=model.request_attempts,
            note="Returned model name is service metadata, not independent identity evidence.",
        )
    except Exception as exc:
        record = dict(error_type=type(exc).__name__, requested_model=model.model)
    finally:
        await model.close()
    path = Path("reports/pr1-remediation/connectivity.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(record, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
