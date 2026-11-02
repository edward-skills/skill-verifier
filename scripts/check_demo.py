#!/usr/bin/env python3
"""Check the real demo entrypoint's clean/fail/blocked controls."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--isolation", choices=["none", "auto"], default="none")
    parser.add_argument("--require-enforced", action="store_true")
    args = parser.parse_args()
    out = args.out.resolve(); out.mkdir(parents=True, exist_ok=False)
    rows = []
    for scenario in ["clean", "defect", "blocked"]:
        destination = out / scenario
        command = [sys.executable, str(ROOT / "skill-verifier/scripts/demo.py"), "--out", str(destination), "--scenario", scenario, "--isolation", args.isolation]
        process = subprocess.run(command, capture_output=True, text=True, timeout=120)
        (out / (scenario + ".stdout.log")).write_text(process.stdout, encoding="utf-8")
        (out / (scenario + ".stderr.log")).write_text(process.stderr, encoding="utf-8")
        result = json.loads((destination / "evidence/results.json").read_text(encoding="utf-8"))
        summary = result["summary"]
        row = {"scenario": scenario, "returncode": process.returncode, "gate": summary["offline_gate"], "case_counts": summary["case_counts"]}
        rows.append(row)
        if scenario == "clean":
            assert summary["case_counts"]["pass"] == 2, row
            assert row["gate"] == ("pass" if args.require_enforced else "incomplete" if args.isolation == "none" else row["gate"]), row
            assert row["returncode"] in ([0] if args.require_enforced else [0, 2]), row
        elif scenario == "defect":
            assert row["returncode"] == 1 and row["gate"] == "fail" and summary["case_counts"]["fail"] == 1, row
        else:
            assert row["returncode"] == 2 and row["gate"] == "incomplete" and summary["case_counts"]["blocked"] == 2, row
    report = {"scope": "synthetic demo controls; no agent/model execution", "checks": rows}
    (out / "summary.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
