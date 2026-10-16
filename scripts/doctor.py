from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import sqlite3
import sys
from importlib.metadata import version
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]


def diagnose(root: Path = ROOT, data_root: Path | None = None) -> dict:
    load_dotenv(root / ".env")
    checks = [
        {
            "name": "python_3_11",
            "ok": sys.version_info[:2] == (3, 11),
            "detail": sys.version.split()[0],
            "required": True,
        }
    ]
    db = sqlite3.connect(":memory:")
    try:
        db.execute("CREATE VIRTUAL TABLE check_fts USING fts5(text)")
        fts = True
    except sqlite3.OperationalError:
        fts = False
    finally:
        db.close()
    checks.append(
        {
            "name": "sqlite_fts5",
            "ok": fts,
            "required": True,
            "sqlite_version": sqlite3.sqlite_version,
        }
    )
    try:
        ZoneInfo("Asia/Shanghai")
        timezone_ok = True
    except ZoneInfoNotFoundError:
        timezone_ok = False
    checks.append(
        {
            "name": "iana_timezone",
            "ok": timezone_ok,
            "required": True,
            "detail": "系统IANA数据或锁定tzdata；出生时间通过历史规则解析",
        }
    )
    checks.append(
        {
            "name": "swisseph",
            "ok": importlib.util.find_spec("swisseph") is not None,
            "required": True,
            "detail": "第二周星盘插件依赖",
        }
    )
    kb_path = root / "data/kb.sqlite"
    try:
        from knowledge.kb import KnowledgeBase

        kb = KnowledgeBase(kb_path)
        coverage = json.loads(
            kb.db.execute("SELECT value FROM meta WHERE key='coverage'").fetchone()[0]
        )
        checks.append(
            {
                "name": "tarot_kb",
                "ok": coverage["coverage"] == 1,
                "detail": coverage,
                "required": True,
            }
        )
        kb.close()
    except (FileNotFoundError, sqlite3.Error):
        checks.append(
            {
                "name": "tarot_kb",
                "ok": False,
                "detail": "先运行 python -m knowledge.build",
                "required": True,
            }
        )
    for package in (
        "pydantic",
        "yaml",
        "httpx",
        "typer",
        "openai",
        "anthropic",
        "skyfield",
        "lunar_python",
    ):
        checks.append(
            {
                "name": package,
                "ok": importlib.util.find_spec(package) is not None,
                "required": package not in ("openai", "anthropic"),
            }
        )
    for key in ("DEEPSEEK_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY"):
        checks.append(
            {
                "name": key,
                "ok": bool(os.getenv(key)),
                "required": False,
                "detail": "只报告是否配置，不输出密钥；离线演示无需密钥",
            }
        )
    for path in ("data/ephe", "data/geo", "data/unihan", "data/models"):
        checks.append(
            {
                "name": path,
                "ok": (root / path).exists(),
                "required": False,
                "detail": "ephe/geo为第二周数据，unihan为第六周姓名笔画数据（三者由清单哈希强制核验）；"
                "models（embedding）尚未使用，缺少不阻断验收",
            }
        )
    import yaml

    manifest = yaml.safe_load((ROOT / "scripts/data_manifest.yaml").read_text(encoding="utf-8"))
    for asset in manifest["assets"]:
        file = (data_root or root / "data") / asset["path"]
        checksum = None
        if file.is_file():
            with file.open("rb") as stream:
                checksum = hashlib.file_digest(stream, "sha256").hexdigest()
        checks.append(
            dict(
                name="data:" + asset["path"],
                ok=checksum == asset["sha256"],
                required=True,
                version=asset["version"],
                license=asset["license"],
            )
        )
    checks.append(dict(name="tzdata_version", ok=True, required=True, version=version("tzdata")))
    return {"ok": all(c["ok"] for c in checks if c["required"]), "checks": checks}


def probe_api(root: Path = ROOT) -> dict:
    import httpx
    import yaml

    load_dotenv(root / ".env")
    config = yaml.safe_load((root / "config.yaml").read_text(encoding="utf-8"))
    model = (config.get("models") or {}).get("orchestrator") or config["llm"]["model"]
    provider = config["llm"].get("provider", "openai")
    if provider not in ("deepseek", "openai"):
        return {"ok": False, "supported": False, "provider": provider}
    key = os.getenv("DEEPSEEK_API_KEY" if provider == "deepseek" else "OPENAI_API_KEY")
    if not key:
        return {"ok": False, "configured": False}
    try:
        base = (
            (os.getenv("DEEPSEEK_BASE_URL") or "https://api.deepseek.com")
            if provider == "deepseek"
            else (os.getenv("OPENAI_BASE_URL") or "https://api.openai.com/v1")
        ).rstrip("/")
        with httpx.Client(timeout=20) as client:
            response = client.get(base + "/models", headers={"Authorization": "Bearer " + key})
            available = response.status_code == 200 and any(
                item.get("id") == model for item in response.json().get("data", [])
            )
            return {
                "ok": available,
                "configured": True,
                "http_status": response.status_code,
                "requested_model": model,
                "model_available": available,
            }
    except Exception as exc:
        return {"ok": False, "configured": True, "error_type": type(exc).__name__}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", action="store_true", help="显式探测模型列表，绝不输出凭据")
    args = parser.parse_args()
    report = diagnose()
    if args.api:
        report["api_probe"] = probe_api()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(0 if report["ok"] else 1)


if __name__ == "__main__":
    main()
