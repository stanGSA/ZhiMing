"""Prepare 20 B0 answers for human labeling, then compute per-dimension Cohen kappa."""

import argparse
import hashlib
import json
from pathlib import Path

from scripts.failure_taxonomy import QUALITY
from scripts.model_review_kb import cohen_kappa


def prepare(report_path, target):
    report = json.loads(report_path.read_text(encoding="utf-8"))
    chosen = {}
    for row in report["results"]:
        if row.get("quality_review") and not row["quality_review"].get("error_type"):
            chosen.setdefault(row["id"], row)
    rows = [
        dict(
            id=row["id"],
            repeat=row.get("repeat", 0),
            question=row["question"],
            answer=row["answer"],
            facts=row["calculated_facts"],
            human={key: None for key in QUALITY},
            judge={key: row["quality_review"][key] for key in QUALITY},
        )
        for row in list(chosen.values())[:20]
    ]
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(
            dict(
                source_sha256=hashlib.sha256(report_path.read_bytes()).hexdigest(),
                rubric_version=report.get("rubric_version"),
                judge_model=report.get("judge_model"),
                annotation_status="pending human labels",
                cases=rows,
            ),
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def score(path):
    data = json.loads(path.read_text(encoding="utf-8"))
    if len(data["cases"]) < 20 or any(
        type(row["human"].get(key)) is not bool for row in data["cases"] for key in QUALITY
    ):
        raise ValueError("须由人工完成至少20个回答的四维布尔标注，不能用缺失值计算kappa")
    return {
        key: cohen_kappa(
            [(str(row["human"][key]), str(row["judge"][key])) for row in data["cases"]]
        )
        for key in QUALITY
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    parser.add_argument("--prepare", type=Path, help="生成待人工标注文件；原始回答仅存reports内")
    args = parser.parse_args()
    if args.prepare:
        prepare(args.path, args.prepare)
    else:
        print(json.dumps(score(args.path), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
