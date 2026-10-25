"""Serial P1 experiments from frozen sources, with durable per-job checkpoints.

Exit code 1 from an evaluation means failed assertions, not a lost experiment.
The runner records it and proceeds only when a complete live.json exists.
"""

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from scripts.p1_report import publish


def stamp():
    return datetime.now(UTC).isoformat()


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def completed(root):
    return sorted(root.glob("*/live.json"))


def valid_report(path, expected):
    report = json.loads(path.read_text(encoding="utf-8"))
    return len(report.get("results", [])) == expected


def run(root, snapshot, baseline, output, timeout_hours=12):
    root = root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    if (snapshot / "scripts/live_test.py").read_bytes() != (
        baseline / "scripts/live_test.py"
    ).read_bytes():
        raise ValueError("B0/final heldout assertions differ; synchronize scripts before running")
    lock = root / "campaign.lock"
    # An exclusive file prevents accidental concurrent latency experiments.
    fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    os.write(fd, str(os.getpid()).encode())
    state_path = root / "campaign.json"
    state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
    state.update(status="waiting_for_baseline", pid=os.getpid(), updated=stamp())
    save(state_path, state)
    jobs = [
        ("Final-single", ["--natural", "--mode", "single"], 60),
        ("Final-multi", ["--natural", "--mode", "multi"], 60),
        ("Compare-single", ["--dataset", "evals/cases/p1_multi.yaml", "--mode", "single"], 36),
        ("Compare-multi", ["--dataset", "evals/cases/p1_multi.yaml", "--mode", "multi"], 36),
        (
            "Compare-multi-lite",
            ["--dataset", "evals/cases/p1_multi.yaml", "--mode", "multi-lite"],
            36,
        ),
        ("Final-heldout", None, 17),
    ]
    deadline = time.monotonic() + timeout_hours * 3600
    try:
        while not all(completed(root / name) for name in ("B0-single", "B0-multi", "B0-heldout")):
            if time.monotonic() > deadline:
                raise TimeoutError("baseline wait expired")
            # No model requests are sent while an earlier experiment is active.
            time.sleep(5)
        for name, count in (("B0-single", 60), ("B0-multi", 60), ("B0-heldout", 17)):
            if not valid_report(completed(root / name)[-1], count):
                raise ValueError(f"{name}: baseline is incomplete")
        state["status"] = "running"
        publish(root, output, output / "pricing.yaml")
        state.setdefault("jobs", {})
        env = os.environ.copy()
        env["PYTHONPATH"] = str(snapshot)
        for name, args, count in jobs:
            existing = completed(root / name)
            if existing and valid_report(existing[-1], count):
                state["jobs"][name] = {"status": "complete", "report": str(existing[-1])}
                continue
            module = "scripts.live_test" if args is None else "scripts.live_week23"
            command = [sys.executable, "-X", "utf8", "-m", module]
            if args is not None:
                command += [*args, "--judge", "pro", "--repeats", "3"]
            command += ["--output", str(root / name)]
            state.update(active_job=name, updated=stamp())
            state["jobs"][name] = {"status": "running", "started": stamp()}
            save(state_path, state)
            with (root / f"{name}.log").open("a", encoding="utf-8") as log:
                result = subprocess.run(
                    command,
                    cwd=snapshot,
                    env=env,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    check=False,
                )
            reports = completed(root / name)
            if not reports or not valid_report(reports[-1], count):
                raise RuntimeError(f"{name}: incomplete evaluation; inspect the log before retry")
            state["jobs"][name].update(
                status="complete",
                exit_code=result.returncode,
                report=str(reports[-1]),
                finished=stamp(),
            )
            save(state_path, state)
            publish(root, output, output / "pricing.yaml")
        policy = root / "policy-model.md"
        if not policy.exists():
            state.update(active_job="policy-model", updated=stamp())
            save(state_path, state)
            with (root / "policy-model.log").open("a", encoding="utf-8") as log:
                subprocess.run(
                    [
                        sys.executable,
                        "-X",
                        "utf8",
                        "-m",
                        "scripts.policy_eval",
                        "--model",
                        "deepseek-flash",
                        "--output",
                        str(policy),
                    ],
                    cwd=snapshot,
                    env=env,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    check=True,
                )
        state.update(status="complete", active_job=None, finished=stamp())
        publish(root, output, output / "pricing.yaml")
        for suffix in (".md", ".json"):
            (output / ("policy-judge" + suffix)).write_bytes(
                policy.with_suffix(suffix).read_bytes()
            )
        save(state_path, state)
    except BaseException as exc:
        state.update(status="interrupted", error_type=type(exc).__name__, updated=stamp())
        save(state_path, state)
        raise
    finally:
        os.close(fd)
        lock.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--publish", type=Path, required=True)
    parser.add_argument("--timeout-hours", type=float, default=12)
    args = parser.parse_args()
    run(
        args.root,
        args.snapshot.resolve(),
        args.baseline.resolve(),
        args.publish.resolve(),
        timeout_hours=args.timeout_hours,
    )


if __name__ == "__main__":
    main()
