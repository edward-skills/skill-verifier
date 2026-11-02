#!/usr/bin/env python3
"""Run a small offline Skill Verifier example without a model or an account."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import sysconfig


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True, help="new directory for the fixture, plan and evidence")
    parser.add_argument("--scenario", choices=["clean", "defect", "blocked"], default="clean")
    parser.add_argument("--isolation", choices=["auto", "none", "macos-sandbox", "linux-bwrap"], default="auto")
    args = parser.parse_args()
    root = args.out.resolve()
    if root.exists():
        parser.error("--out must be new; keep earlier evidence")
    root.mkdir(parents=True)
    target = root / "demo-skill"
    (target / "scripts").mkdir(parents=True)
    (target / "SKILL.md").write_text("---\nname: demo-skill\ndescription: Double an integer and return JSON.\n---\nRun scripts/double.py with one integer.\n", encoding="utf-8")
    expression = "number ** 2" if args.scenario == "defect" else "number * 2"
    (target / "scripts/double.py").write_text("import json, sys\nnumber = int(sys.argv[1])\nprint(json.dumps({'result': " + expression + "}))\n", encoding="utf-8")
    plan = root / "plan"
    cases = []
    for name, number, expected in [("normal", 4, 8), ("zero", 0, 0)]:
        cases.append({"id": name, "profile": "code", "description": "Double the supplied integer.",
            "contract": {"owner": "script", "strength": "required", "basis": "The demo CLI promises twice its input."},
            "steps": [{"id": "double", "argv": ["python", "{skill}/scripts/double.py", str(number)], "stdout_artifact": "result.json"}],
            "checks": [{"id": "value", "type": "json-value", "path": "result.json", "pointer": "/result", "expected": expected}]})
    write(plan / "suite.json", {"schema_version": 1, "kind": "offline", "name": "Integer-doubling example", "cases": cases})
    write(plan / "runtime.json", {"schema_version": 1, "candidate": ["scripts/double.py"], "baseline": []})
    mode = args.isolation
    if mode == "auto":
        mode = "macos-sandbox" if sys.platform == "darwin" and Path("/usr/bin/sandbox-exec").is_file() else "linux-bwrap" if sys.platform.startswith("linux") and shutil.which("bwrap") else "none"
    boundary = {"mode": mode}
    if mode != "none":
        runtime = [sysconfig.get_path("stdlib"), sysconfig.get_config_var("LIBDIR")]
        boundary.update(allow_network=False, readable_paths=list(dict.fromkeys(str(Path(p).resolve()) for p in runtime if p and Path(p).exists())))
    executable = str(Path(sys.executable).absolute())
    if args.scenario == "blocked":
        executable = str(root / "deliberately-unavailable-python")
    write(plan / "config.json", {"schema_version": 1, "name": "model-free-demo", "tools": {"python": [executable]},
        "filesystem_isolation": boundary, "process_environment": {"inherit": []}})
    verifier = Path(__file__).with_name("verifier.py")
    argv = [sys.executable, str(verifier), "offline-run", "--skill", str(target), "--suite", str(plan / "suite.json"),
            "--config", str(plan / "config.json"), "--runtime-manifest", str(plan / "runtime.json"), "--out", str(root / "evidence")]
    result = subprocess.run(argv)
    print("Report: " + str(root / "evidence/report.md"))
    if mode == "none":
        print("Diagnostic mode: successful assertions still have an incomplete gate.")
    print("This is a synthetic execution example, not evidence of model uplift.")
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
