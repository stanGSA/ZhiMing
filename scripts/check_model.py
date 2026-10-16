"""Opt-in connectivity probe: no credential, endpoint, or request headers in output."""

import asyncio
import json
import time
from pathlib import Path

import yaml
from dotenv import load_dotenv

from app import ROOT, build_model


async def main():
    load_dotenv(ROOT / ".env")
    config = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    model = build_model(
        config["llm"]["provider"],
        (config.get("models") or {}).get("orchestrator") or config["llm"]["model"],
        config,
        None,
    )
    started = time.perf_counter()
    try:
        response = await model.chat([dict(role="user", content="连接测试，请仅回复OK。")], [])
        record = dict(
            requested_model=model.model,
            returned_model=response.model,
            input_tokens=response.input_tokens if response.usage_available else None,
            output_tokens=response.output_tokens if response.usage_available else None,
            usage_available=response.usage_available,
            finish_reason=response.finish_reason,
            reasoning_tokens=response.reasoning_tokens,
            answer=response.text,
            latency_s=round(time.perf_counter() - started, 3),
            model_calls=model.request_attempts,
            note="Returned model name is service metadata, not independent identity evidence.",
        )
    except Exception as exc:
        record = dict(
            error_type=type(exc).__name__,
            status_code=getattr(exc, "status_code", None),
            requested_model=model.model,
        )
    finally:
        await model.close()
    path = Path("reports/connectivity/current.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(record, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
