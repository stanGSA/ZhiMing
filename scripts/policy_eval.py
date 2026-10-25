"""Compare regex, model-only and regex+model on labeled policy sentences."""

import argparse
import asyncio
import json
from pathlib import Path

import yaml
from dotenv import load_dotenv

from app import ROOT, build_model
from common.policy_judge import HARD, PROMPT, Decision, candidates, regex_decision


def confusion(rows, predictions, key):
    tp = sum(row[key] and pred[key] for row, pred in zip(rows, predictions, strict=True))
    fp = sum(not row[key] and pred[key] for row, pred in zip(rows, predictions, strict=True))
    fn = sum(row[key] and not pred[key] for row, pred in zip(rows, predictions, strict=True))
    tn = len(rows) - tp - fp - fn
    return dict(
        tp=tp,
        fp=fp,
        fn=fn,
        tn=tn,
        precision=tp / (tp + fp) if tp + fp else None,
        recall=tp / (tp + fn) if tp + fn else None,
    )


async def evaluate(dataset, output, model_name=None):
    data = yaml.safe_load(dataset.read_text(encoding="utf-8"))
    rows = data["cases"]
    variants = {"regex": [regex_decision(row["sentence"]) for row in rows]}
    raw = []
    if model_name:
        load_dotenv(ROOT / ".env")
        config = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
        model = build_model(config["llm"]["provider"], model_name, config, None, "reviewer")
        try:
            for row in rows:
                reply = await model.chat(
                    [
                        {"role": "system", "content": PROMPT},
                        {
                            "role": "user",
                            "content": json.dumps(
                                {"sentence": row["sentence"]}, ensure_ascii=False
                            ),
                        },
                    ],
                    [],
                )
                if reply.tool_calls or not reply.usage_available or reply.finish_reason == "length":
                    raise ValueError("invalid classifier response")
                prediction = Decision.model_validate_json(reply.text).model_dump()
                raw.append(
                    dict(
                        id=row["id"],
                        prediction=prediction,
                        requested_model=model_name,
                        returned_model=reply.model,
                        input_tokens=reply.input_tokens,
                        output_tokens=reply.output_tokens,
                    )
                )
                output.parent.mkdir(parents=True, exist_ok=True)
                output.with_suffix(".progress.json").write_text(
                    json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8"
                )
        finally:
            await model.close()
        variants["model_only"] = [item["prediction"] for item in raw]
        variants["regex_then_model"] = [
            (
                dict(certainty=True, discourage_care=False)
                if HARD.search(row["sentence"])
                else prediction
            )
            if candidates([row["sentence"]]) or HARD.search(row["sentence"])
            else dict(certainty=False, discourage_care=False)
            for row, prediction in zip(rows, variants["model_only"], strict=True)
        ]
    report = dict(
        cases=len(rows),
        annotation_status=data["annotation_status"],
        model=model_name,
        metrics={
            name: {key: confusion(rows, pred, key) for key in ("certainty", "discourage_care")}
            for name, pred in variants.items()
        },
        predictions=raw,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.with_suffix(".json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    lines = [
        "# 表达策略判定对照",
        "",
        f"样本：{len(rows)}；模型：{model_name or '未调用'}。",
        data["annotation_status"],
        "",
        "|方案|维度|TP|FP|FN|TN|precision|recall|",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for name, metrics in report["metrics"].items():
        for key, m in metrics.items():
            lines.append(
                f"|{name}|{key}|{m['tp']}|{m['fp']}|{m['fn']}|{m['tn']}|{m['precision']}|{m['recall']}|"
            )
    lines += ["", "代理标注不等同人工校准；运行时默认保留严格正则。模型裁决失败时不放行。"]
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset",
        type=Path,
        default=ROOT / "evals/cases/policy_sentences.yaml",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "docs/verification/p1/policy-judge.md",
    )
    parser.add_argument("--model", help="设置时真实调用并产生用量；省略只评估正则")
    args = parser.parse_args()
    asyncio.run(evaluate(args.dataset, args.output, args.model))


if __name__ == "__main__":
    main()
