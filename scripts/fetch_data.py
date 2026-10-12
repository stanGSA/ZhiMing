from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

import httpx
import yaml

ROOT = Path(__file__).resolve().parents[1]


def fetch_asset(asset: dict, root: Path, client: httpx.Client) -> dict:
    checksum = asset.get("sha256", "")
    if not re.fullmatch(r"[0-9a-f]{64}", checksum):
        raise ValueError("必须提供经核实的 SHA256")
    if not asset["url"].startswith("https://"):
        raise ValueError("下载地址必须使用 HTTPS")
    root = root.resolve()
    destination = (root / asset["path"]).resolve()
    if not destination.is_relative_to(root) or destination == root:
        raise ValueError("下载路径必须在 data 目录内")
    if destination.is_file() and hashlib.sha256(destination.read_bytes()).hexdigest() == checksum:
        return {"path": asset["path"], "status": "cached"}
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".download")
    digest = hashlib.sha256()
    try:
        with client.stream("GET", asset["url"]) as response:
            response.raise_for_status()
            if not str(response.url).startswith("https://"):
                raise ValueError("重定向后地址必须使用 HTTPS")
            with temporary.open("wb") as stream:
                for block in response.iter_bytes():
                    digest.update(block)
                    stream.write(block)
        if digest.hexdigest() != checksum:
            raise ValueError("SHA256 不匹配，拒绝使用下载数据")
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
    return {"path": asset["path"], "status": "downloaded"}


def main():
    parser = argparse.ArgumentParser(description="下载并核验数据；第一周清单为空，无需外部数据")
    parser.add_argument("--manifest", type=Path, default=ROOT / "scripts/data_manifest.yaml")
    args = parser.parse_args()
    manifest = yaml.safe_load(args.manifest.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != 1:
        raise ValueError("不支持的数据清单版本")
    with httpx.Client(timeout=30, follow_redirects=True) as client:
        report = [fetch_asset(asset, ROOT / "data", client) for asset in manifest["assets"]]
    print(
        json.dumps(
            {"assets": report, "note": "第一周塔罗不依赖星历、地名、Unihan 或 embedding。"},
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
