"""Operator-reviewed local command suites; facts are separate from diagnosis."""
import ast
import collections
import copy
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time

V = None  # Bound by verifier.offline_module; shares existing validators/isolation.
CORE = {"exists", "json-value", "csv-rows", "text-contains", "sha256", "manual"}
EXTRA = {"json-valid", "yaml-valid", "image-property", "image-compare", "directory-count"}
UNTESTED = ["model-quality-and-uplift", "native-skill-discovery", "cross-harness-transfer",
            "agent-approval-behavior", "external-services"]


def ident(value, label):
    V.require(isinstance(value, str) and V.ID.fullmatch(value), "Invalid " + label)


def validate_check(check):
    kind = check.get("type") if isinstance(check, dict) else None
    if kind in CORE:
        V.validate_suite({"schema_version": 1, "name": "check validation", "cases": [
            {"id": "one", "profile": "offline", "prompt": "validate", "checks": [check]}]}, Path.cwd())
        return
    V.fields(check, ["id", "type", "path", "severity", "property", "other", "expected"],
             ["id", "type", "path"], "offline check")
    ident(check["id"], "check id")
    V.relative_path(check["path"])
    V.require(kind in EXTRA, "Unknown offline checker")
    V.require(check.get("severity", "major") in {"critical", "major", "minor"}, "Unknown severity")
    extras = set(check) - {"id", "type", "path", "severity"}
    if kind in {"json-valid", "yaml-valid"}:
        V.require(not extras, "Syntax checks accept no additional fields")
    elif kind == "image-property":
        V.require(extras == {"property", "expected"}, "Image property needs property/expected only")
        V.require(check["property"] in {"size", "meaningful-alpha"}, "Unknown image property")
        expected = check["expected"]
        if check["property"] == "size":
            V.require(isinstance(expected, list) and len(expected) == 2 and all(type(x) is int and x > 0 for x in expected), "Expected positive image dimensions")
        else:
            V.require(type(expected) is bool, "Alpha expectation must be boolean")
    elif kind == "image-compare":
        V.require(extras == {"other", "expected"} and type(check["expected"]) is bool, "Image compare needs other/boolean expected")
        V.relative_path(check["other"])
    else:
        V.require(extras == {"expected"} and type(check["expected"]) is int and check["expected"] >= 0, "Directory count needs nonnegative integer expected")


def validate(data, base):
    V.fields(data, ["schema_version", "kind", "name", "cases"], ["schema_version", "kind", "name", "cases"], "offline suite")
    V.require(type(data["schema_version"]) is int and data["schema_version"] == 1 and data["kind"] == "offline", "Unsupported offline suite")
    V.string(data["name"], "suite.name")
    V.require(isinstance(data["cases"], list) and data["cases"], "Offline suite needs cases")
    ids = set()
    for case in data["cases"]:
        V.fields(case, ["id", "profile", "description", "contract", "enabled", "inputs", "steps", "checks", "requires_tools", "diagnosis"],
                 ["id", "profile", "description", "contract", "steps", "checks"], "offline case")
        ident(case["id"], "case id")
        V.require(case["id"] not in ids, "Duplicate case id")
        ids.add(case["id"])
        for key in ["profile", "description"]:
            V.string(case[key], key)
        V.require(type(case.get("enabled", True)) is bool, "enabled must be boolean")
        contract = case["contract"]
        V.fields(contract, ["owner", "strength", "basis"], ["owner", "strength", "basis"], "contract")
        V.require(contract["owner"] in {"script", "artifact", "agent", "environment"}, "Unknown contract owner")
        V.require(contract["strength"] in {"required", "recommendation"}, "Unknown contract strength")
        V.string(contract["basis"], "contract.basis")
        requirements = case.get("requires_tools", [])
        V.require(isinstance(requirements, list) and len(requirements) == len(set(requirements)), "requires_tools must be unique")
        for name in requirements:
            ident(name, "required tool")
        fixtures = case.get("inputs", [])
        V.validate_suite({"schema_version": 1, "name": "fixtures", "cases": [{"id": "one", "profile": "offline", "prompt": "fixtures", "inputs": fixtures,
            "checks": [{"id": "dummy", "type": "exists", "path": "dummy"}]}]}, base)
        V.require(isinstance(case["steps"], list), "steps must be a list")
        V.require(not case.get("enabled", True) or case["steps"], "Enabled cases need steps")
        step_ids = set()
        for step in case["steps"]:
            V.fields(step, ["id", "argv", "expected_exit", "stdout_artifact", "stderr_artifact", "timeout_seconds", "role"], ["id", "argv"], "step")
            ident(step["id"], "step id")
            V.require(step["id"] not in step_ids, "Duplicate step id")
            step_ids.add(step["id"])
            V.require(isinstance(step["argv"], list) and step["argv"] and all(isinstance(a, str) and a for a in step["argv"]), "Step argv must be nonempty strings")
            ident(step["argv"][0], "tool alias")
            # Only known names are replaced; ordinary JSON/code braces stay literal.
            for arg in step["argv"][1:]:
                V.require(not re.search(r"\{(?:work|outputs|inputs|skill)[^}]*\}", arg.replace("{work}", "").replace("{outputs}", "").replace("{inputs}", "").replace("{skill}", "")), "Unknown path placeholder")
            expected = step.get("expected_exit", [0])
            V.require(expected == "nonzero" or isinstance(expected, list) and expected and all(type(x) is int and 0 <= x <= 255 for x in expected), "expected_exit needs integer list or nonzero")
            V.require(step.get("role", "task") in {"task", "precondition"}, "Unknown step role")
            timeout = step.get("timeout_seconds", 60)
            V.require(type(timeout) in (int, float) and math.isfinite(timeout) and 0 < timeout <= 3600, "Invalid step timeout")
            for key in ["stdout_artifact", "stderr_artifact"]:
                if key in step:
                    V.relative_path(step[key])
        V.require(isinstance(case["checks"], list), "checks must be a list")
        check_ids = set()
        for check in case["checks"]:
            validate_check(check)
            V.require(check["id"] not in check_ids, "Duplicate check id")
            V.require(check["id"] not in {"step-" + name for name in step_ids}, "Check id collides with a step observation")
            check_ids.add(check["id"])
        if "diagnosis" in case:
            d = case["diagnosis"]
            V.fields(d, ["hypothesis", "confidence", "repair", "regression"], ["hypothesis", "confidence", "repair", "regression"], "diagnosis")
            V.require(d["confidence"] in {"low", "medium", "high"}, "Unknown confidence")
            for key in ["hypothesis", "repair", "regression"]:
                V.string(d[key], key)
    return data


def config(data):
    V.fields(data, ["schema_version", "name", "tools", "filesystem_isolation", "process_environment"],
             ["schema_version", "name", "tools", "filesystem_isolation"], "offline config")
    V.require(type(data["schema_version"]) is int and data["schema_version"] == 1, "Unsupported config schema")
    V.string(data["name"], "config.name")
    V.require(isinstance(data["tools"], dict), "tools must be an object")
    for name, argv in data["tools"].items():
        ident(name, "tool alias")
        V.require(isinstance(argv, list) and argv and all(isinstance(a, str) and a for a in argv), "Tool prefix must be nonempty strings")
    adapter = {"schema_version": 1, "name": data["name"], "argv": [sys.executable], "response": "stdout",
               "environment": {"model": None, "harness_version": None, "settings": "offline commands"},
               "baseline_isolation": {"status": "unverified", "evidence": "No model comparison"},
               "filesystem_isolation": data["filesystem_isolation"], "process_environment": data.get("process_environment", {})}
    V.validate_adapter(adapter)
    V.require(not data["filesystem_isolation"].get("allow_network", False), "Offline config cannot enable network")
    return adapter


def check_artifact(check, outputs):
    if check["type"] in CORE:
        return V.grade_check(check, outputs)
    result = {key: check[key] for key in ["id", "type", "path"]}
    result["severity"] = check.get("severity", "major")
    try:
        path = V.within(outputs, check["path"])
        kind = check["type"]
        if kind == "directory-count":
            V.require(path.is_dir(), "Required directory missing")
            files = [p for p in path.rglob("*") if p.is_file() or p.is_symlink()]
            V.require(not any(p.is_symlink() or any(q.is_symlink() for q in p.parents) for p in files), "Symlink in counted directory")
            observed = len(files)
        else:
            V.require(path.is_file(), "Required artifact missing")
            result["artifact_sha256"] = V.digest(path)
            if kind == "json-valid":
                V.read_json(path)
                observed = True
            elif kind == "yaml-valid":
                try:
                    import yaml
                except ImportError:
                    return dict(result, status="blocked", evidence="Optional PyYAML unavailable; YAML syntax was not verified")
                class UniqueLoader(yaml.SafeLoader):
                    pass
                def unique(loader, node):
                    mapping = {}
                    for key_node, value_node in node.value:
                        key = loader.construct_object(key_node)
                        V.require(key not in mapping, "Duplicate YAML key: " + str(key))
                        mapping[key] = loader.construct_object(value_node)
                    return mapping
                UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, unique)
                try:
                    yaml.load(path.read_text(encoding="utf-8"), Loader=UniqueLoader)
                except yaml.YAMLError as exc:
                    raise ValueError(str(exc)) from exc
                observed = True
            else:
                try:
                    from PIL import Image
                except ImportError:
                    return dict(result, status="blocked", evidence="Optional Pillow unavailable; pixels were not inspected")
                with Image.open(path) as source:
                    image = source.convert("RGBA")
                if kind == "image-property":
                    if check["property"] == "size":
                        observed = list(image.size)
                    else:
                        low, high = image.getchannel("A").getextrema()
                        observed = low < 255 and high > 0
                else:
                    other = V.within(outputs, check["other"])
                    V.require(other.is_file(), "Comparison image missing")
                    with Image.open(other) as source:
                        second = source.convert("RGBA")
                    result["other_artifact_sha256"] = V.digest(other)
                    observed = image.size == second.size and image.tobytes() == second.tobytes()
        expected = check.get("expected", True)
        return dict(result, status="pass" if V.json_equal(observed, expected) else "fail",
                    evidence="Observed " + json.dumps(observed) + "; expected " + json.dumps(expected))
    except (OSError, UnicodeError, ValueError, KeyError, TypeError) as exc:
        return dict(result, status="fail", evidence="Artifact check failed: " + str(exc)[:1500])


def execute_step(step, tools, work, run_dir, environment, prefix):
    run_dir.mkdir(parents=True)
    result = {"id": step["id"], "status": "blocked", "returncode": None, "reason": None,
              "expected_exit": step.get("expected_exit", [0]), "duration_ms": 0}
    alias = step["argv"][0]
    if alias not in tools or not tools[alias]:
        return dict(result, reason="Unavailable operator tool: " + alias)
    argv = list(tools[alias])
    values = {"work": str(work), "outputs": str(work / "outputs"), "inputs": str(work / "inputs"), "skill": str(work / "skill")}
    for value in step["argv"][1:]:
        for root_name in ["skill", "inputs"]:
            start_marker = "{" + root_name + "}/"
            if value.startswith(start_marker):
                staged = V.within(work / root_name, value[len(start_marker):])
                if not staged.exists():
                    return dict(result, reason="Required staged runtime/input missing: " + value)
        for name, path in values.items():
            value = value.replace("{" + name + "}", path)
        argv.append(value)
    result["argv"] = argv
    start = time.monotonic()
    stdout_path, stderr_path = run_dir / "stdout.log", run_dir / "stderr.log"
    with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
        try:
            proc = subprocess.Popen(prefix + argv, cwd=str(work), env=environment, stdin=subprocess.DEVNULL,
                                    stdout=stdout, stderr=stderr, start_new_session=os.name == "posix")
            try:
                proc.communicate(timeout=step.get("timeout_seconds", 60))
            except subprocess.TimeoutExpired:
                if os.name == "posix":
                    try:
                        os.killpg(proc.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                else:
                    proc.kill()
                proc.communicate()
                result["reason"] = "timeout; not evidence of a successful rejection"
            result["returncode"] = proc.returncode
        except OSError as exc:
            result["reason"] = "launch failed: " + str(exc)
    result["duration_ms"] = round((time.monotonic() - start) * 1000)
    if result["reason"]:
        return result
    if result["returncode"] < 0:
        return dict(result, reason="Process terminated by signal; diagnosis required")
    expected = result["expected_exit"]
    good = result["returncode"] != 0 if expected == "nonzero" else result["returncode"] in expected
    result["status"] = "pass" if good else "blocked" if step.get("role") == "precondition" else "fail"
    result["reason"] = "Observed exit {}; expected {}".format(result["returncode"], expected)
    for key, source in [("stdout_artifact", stdout_path), ("stderr_artifact", stderr_path)]:
        if key in step:
            destination = V.within(work / "outputs", step[key])
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
    return result


def gating(case):
    return case["contract"]["owner"] in {"script", "artifact"} and case["contract"]["strength"] == "required"


def summarize(result):
    rows = result["runs"]
    counts = {state: sum(r["status"] == state for r in rows) for state in V.STATES}
    blocking = [r for r in rows if r["gating"]]
    reasons = []
    if any(r["status"] in {"blocked", "pending"} for r in blocking):
        reasons.append("Gating execution/checks are blocked or pending")
    if not blocking:
        reasons.append("No required script/artifact cases")
    if any(r["filesystem_isolation"].get("status") != "enforced" for r in rows if r["enabled"]):
        reasons.append("Filesystem isolation unverified; successes remain diagnostic")
    if any(not r["correctness_check"] for r in blocking):
        reasons.append("Independent correctness evidence is missing for some cases (exit/presence only or unresolved manual review)")
    if any(not r["enabled"] for r in rows):
        reasons.append("Draft cases remain unexecuted")
    failed = any(r["status"] == "fail" for r in blocking)
    gate = "fail" if failed else "incomplete" if reasons else "pass"
    return {"offline_gate": gate, "whole_skill_verdict": "not-assessed", "case_counts": counts, "planned_runs": len(rows),
            "gating_case_counts": {state: sum(r["status"] == state for r in blocking) for state in V.STATES},
            "advisory_case_counts": {state: sum(r["status"] == state for r in rows if not r["gating"]) for state in V.STATES},
            "assertion_counts": dict(collections.Counter(g["status"] for r in rows for g in r["grades"])),
            "blockers": reasons, "comparison_gate": "not-run", "model": None, "tokens": None, "cost": None,
            "scope": "Declared local commands and artifacts only; not a whole-skill certificate",
            "source_unchanged": result["source_unchanged"]}


def save_report(out, result):
    result["summary"] = summarize(result)
    findings = []
    for row in result["runs"]:
        if row["status"] == "pass":
            continue
        case = next(c for c in result["suite"]["cases"] if c["id"] == row["case_id"])
        diagnosis = case.get("diagnosis")
        findings.append({"case_id": row["case_id"], "repeat": row["repeat"], "status": row["status"],
            "severity": (max((g.get("severity", "major") for g in row["grades"] if g["status"] == "fail"),
                             key=lambda x: {"minor": 0, "major": 1, "critical": 2}[x], default=None)
                         if row["gating"] else "suggestion"),
            "classification": "observed-contract-failure" if row["gating"] and row["status"] == "fail" else "recommendation-review" if not row["gating"] else "missing-evidence",
            "contract": row["contract"], "gating": row["gating"], "evidence_directory": row["directory"],
            "observations": [g for g in row["grades"] if g["status"] != "pass"],
            "root_cause": {"status": "not-established", "hypothesis": diagnosis.get("hypothesis") if diagnosis else None,
                           "confidence": diagnosis.get("confidence") if diagnosis else None,
                           "source": "operator-authored hypothesis, not verified by the runner" if diagnosis else "no root cause inferred"},
            "repair": diagnosis["repair"] if diagnosis else "Inspect the linked command/artifact and its declared contract; patch only the supported cause.",
            "regression": diagnosis["regression"] if diagnosis else "Rerun frozen case " + row["case_id"] + " and neighboring controls; retain original failures.",
            "repair_verified": False})
    result["findings"] = findings
    coverage = [{"case_id": r["case_id"], "repeat": r["repeat"], "profile": r["profile"], "owner": r["contract"]["owner"],
                 "method": "local-script-and-artifact", "status": r["status"], "gating": r["gating"], "evidence": r["directory"],
                 "manual_reviews": [{"id":g["id"],"status":g["status"],"review_imported":"review" in g} for g in r["grades"] if g["type"]=="manual"]} for r in result["runs"]]
    coverage += [{"capability": x, "status": "not-tested", "method": None} for x in UNTESTED]
    result["coverage"] = coverage
    V.write_json(out / "results.json", result)
    V.write_json(out / "findings.json", findings)
    V.write_json(out / "coverage.json", coverage)
    summary = result["summary"]
    lines = ["# Offline Skill QA", "", "Offline gate: **" + summary["offline_gate"] + "**", "",
             "Whole-skill verdict: **not assessed**. Task/model quality, native activation and cross-harness behavior require separate evidence.", "",
             summary["scope"], "", "Counts: " + json.dumps(summary["case_counts"]) + ". Native/model comparison: not-run.", "",
             "Required cases: " + json.dumps(summary["gating_case_counts"]) + "; recommendations: " + json.dumps(summary["advisory_case_counts"]) + ".", "",
             "## Observed evidence", "", "| Case / repeat | Contract owner | Result | Gating | Evidence |",
             "| --- | --- | --- | --- | --- |"]
    for row in rows_sorted(result):
        lines.append("| {} / {} | {} | {} | {} | [run]({}/run.json) |".format(row["case_id"], row["repeat"], row["contract"]["owner"], row["status"], row["gating"], row["directory"]))
    lines += ["", "## Findings: facts, then interpretation", ""]
    for finding in findings:
        lines += ["### " + finding["case_id"] + " / " + str(finding["repeat"]), "",
                  "Classification: " + finding["classification"] + "; gating: " + str(finding["gating"]),
                  "Contract (operator declared): " + finding["contract"]["basis"], ""]
        lines += ["- " + g["id"] + ": " + g["status"] + "; " + g["evidence"].replace("\n", " ") for g in finding["observations"]]
        cause = finding["root_cause"]
        lines += ["", "Root cause: not established. " + (cause["hypothesis"] or "No hypothesis supplied.") + " (" + cause["source"] + ").",
                  "Proposed repair: " + finding["repair"], "Regression: " + finding["regression"], "Repair verification: not performed.", ""]
    lines += ["## Coverage boundaries", "", "Manual checks remain pending until artifact-bound review is imported. Recommendations and agent-only requirements cannot fail the offline script gate.", ""]
    lines += ["- " + x + ": not tested" for x in UNTESTED]
    lines += ["", "## Blockers", ""] + ["- " + x for x in summary["blockers"]]
    lines += ["", "Runtime files were explicitly listed; target/fixture hashes and every planned repetition are retained. "
              "A passing diagnostic run does not certify filesystem isolation. Contract interpretation and suggested causes require review.", ""]
    (out / "report.md").write_text("\n".join(lines), encoding="utf-8")


def rows_sorted(result):
    return sorted(result["runs"], key=lambda row: (row["case_id"], row["repeat"]))


def run(args):
    suite_path, config_path = Path(args.suite).resolve(), Path(args.config).resolve()
    suite = validate(V.read_json(suite_path), suite_path.parent)
    settings = V.read_json(config_path)
    adapter = config(settings)
    V.require(type(args.repeats) is int and 1 <= args.repeats <= 20, "repeats must be 1-20")
    skill = Path(args.skill).resolve()
    original = V.fingerprint(V.package_files(skill, True))
    out = Path(args.out).resolve()
    V.require(not out.exists(), "Output must be new; preserve prior evidence")
    for source in [skill, suite_path.parent]:
        V.require(not out.is_relative_to(source), "Evidence must be outside target and suite trees")
    runtime_path = Path(args.runtime_manifest).resolve() if args.runtime_manifest else None
    runtime = V.runtime_manifest(runtime_path)
    out.mkdir(parents=True)
    snapshot = V.snapshot(skill, out / "snapshot", runtime.get("candidate", []))
    V.write_json(out / "suite.json", suite)
    V.write_json(out / "config.json", settings)
    V.write_json(out / "runtime-manifest.json", runtime)
    (out / ".isolation-canary").write_text(os.urandom(24).hex())
    tools = {}
    for name, prefix in settings["tools"].items():
        executable = prefix[0] if Path(prefix[0]).is_absolute() else shutil.which(prefix[0])
        tools[name] = [executable] + prefix[1:] if executable and Path(executable).is_file() and os.access(executable, os.X_OK) else None
    fixture_hashes = {item["source"]: V.digest(V.within(suite_path.parent, item["source"])) for c in suite["cases"] for item in c.get("inputs", [])}
    result = {"schema_version": 1, "checker_version": V.VERSION, "mode": "offline", "suite": suite,
              "environment": {"verifier_python": sys.version, "verifier_executable": sys.executable, "platform": sys.platform,
                              "resolved_tool_prefixes": tools, "task_runtime_versions": None,
                              "runtime_version_scope": "Command argv/prefixes observed; task runtime version strings not inferred"},
              "suite_sha256": V.digest(suite_path), "config_sha256": V.digest(config_path), "runtime_manifest_sha256": V.digest(runtime_path) if runtime_path else None,
              "target": original, "staged_target": snapshot, "fixture_hashes": fixture_hashes, "source_unchanged": True,
              "replay_argv": sys.argv, "runs": []}
    V.write_json(out / "manifest.json", {k: x for k, x in result.items() if k not in {"runs", "suite"}})
    private_paths = [skill, suite_path.parent, out, config_path] + ([runtime_path] if runtime_path else [])
    private_files = [suite_path, out / "suite.json", out / ".isolation-canary"]
    planned = len(suite["cases"]) * args.repeats
    for case in suite["cases"]:
        for repeat in range(1, args.repeats + 1):
            directory = "runs/{}-r{}".format(case["id"], repeat)
            run_dir = out / directory
            run_dir.mkdir(parents=True)
            grades, steps = [], []
            boundary = {"mode": adapter["filesystem_isolation"]["mode"], "status": "unverified"}
            enabled = case.get("enabled", True)
            env_meta = None
            with tempfile.TemporaryDirectory(prefix="skill-verifier-offline-") as temporary:
                work = Path(temporary).resolve()
                V.require(not any(work.is_relative_to(p) for p in private_paths), "Temp work overlaps evaluator sources")
                (work / "outputs").mkdir()
                (work / "inputs").mkdir()
                shutil.copytree(out / "snapshot", work / "skill")
                for item in case.get("inputs", []):
                    dest = V.within(work / "inputs", item["dest"])
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(V.within(suite_path.parent, item["source"]), dest)
                    V.require(V.digest(dest) == fixture_hashes[item["source"]], "Fixture changed during staging")
                reason = "Draft case not executed" if not enabled else None
                environment, env_meta = V.isolation.task_environment(adapter, work)
                prefix = []
                if enabled:
                    aliases = set(case.get("requires_tools", [])) | {s["argv"][0] for s in case["steps"]}
                    unavailable = [name for name in aliases if not tools.get(name)]
                    if unavailable:
                        reason = "Unavailable operator tools: " + ", ".join(sorted(unavailable))
                    else:
                        try:
                            probe_python = V.isolation.probe_interpreter(adapter) if boundary["mode"] != "none" else None
                            runtime_files = []
                            for python in [probe_python] + [V.isolation.python_runtime(tools[a][0]) for a in aliases]:
                                if python:
                                    runtime_files += [python["executable"]] + python["config_files"]
                            # Policy must permit each step's own write-only log files.
                            logs = [run_dir / "stdout.log", run_dir / "stderr.log"]
                            logs += [run_dir / "steps" / s["id"] / name for s in case["steps"] for name in ["stdout.log", "stderr.log"]]
                            prefix, boundary = V.isolation.policy(adapter, work, private_paths, logs, runtime_files)
                            probe_env, probe_meta = V.isolation.task_environment(adapter, work, for_probe=True)
                            boundary = V.isolation.probe(prefix, boundary, work, private_files, run_dir, probe_env, probe_python)
                        except V.isolation.IsolationError as exc:
                            reason = "filesystem-isolation: " + str(exc)
                if not reason:
                    for step in case["steps"]:
                        record = execute_step(step, tools, work, run_dir / "steps" / step["id"], environment, prefix)
                        steps.append(record)
                        V.write_json(run_dir / "steps" / step["id"] / "execution.json", record)
                        if record["status"] != "pass":
                            reason = record["reason"]
                            break
                if boundary.get("status") == "enforced":
                    try:
                        V.isolation.verify_private_files(boundary)
                        boundary["private_file_identity"]["verified_after_task"] = True
                    except V.isolation.IsolationError as exc:
                        reason = "filesystem-isolation postcondition: " + str(exc)
                        boundary.update(status="unverified", reason=str(exc))
                        grades.append({"id":"private-file-integrity", "type":"isolation", "path":"", "severity":"critical", "status":"blocked", "evidence":reason})
                V.require(not work.is_symlink(), "Task replaced work directory")
                V.require(not (work / "outputs").is_symlink(), "Task replaced outputs root with a link; refuse evaluator-side dereference")
                shutil.copytree(work / "outputs", run_dir / "outputs", symlinks=True)
            for step in steps:
                grades.append({"id": "step-" + step["id"], "type": "exit-code", "path": "steps/" + step["id"] + "/execution.json",
                               "severity": "major", "status": step["status"], "evidence": step["reason"]})
            for step in case["steps"][len(steps):]:
                grades.append({"id": "step-" + step["id"], "type": "exit-code", "path": "", "severity": "major",
                               "status": "pending" if not enabled else "blocked", "evidence": reason})
            for check in case["checks"]:
                if reason:
                    grades.append(dict(check, status="pending" if not enabled else "blocked", evidence=reason))
                else:
                    grades.append(check_artifact(check, run_dir / "outputs"))
            status = "pending" if not enabled else V.run_status(grades, "completed")
            row = {"case_id": case["id"], "profile": case["profile"], "repeat": repeat, "directory": directory,
                   "contract": case["contract"], "gating": gating(case), "enabled": enabled,
                   "correctness_check": any(c["type"] not in {"exists", "manual"} for c in case["checks"]),
                   "filesystem_isolation": boundary, "process_environment": env_meta,
                   "steps": steps, "grades": grades, "status": status}
            V.write_json(run_dir / "run.json", row)
            result["runs"].append(row)
            V.write_json(out / "progress.json", {"completed_runs": len(result["runs"]), "planned_runs": planned})
    result["source_unchanged"] = original == V.fingerprint(V.package_files(skill, True))
    V.require(result["source_unchanged"], "Target source changed during testing; evidence cannot be accepted")
    for source, expected in fixture_hashes.items():
        V.require(V.digest(V.within(suite_path.parent, source)) == expected, "Original fixture changed during testing")
    save_report(out, result)
    return result


def init(args):
    skill = Path(args.skill).resolve()
    files = V.package_files(skill, True)
    out = Path(args.out).resolve()
    V.require(not out.exists() and not out.is_relative_to(skill), "Choose a new plan directory outside target")
    out.mkdir(parents=True)
    scripts = [rel for rel, p in files if rel.startswith("scripts/") and p.suffix in {".py", ".js", ".mjs", ".sh"}]
    syntax = []
    for rel in scripts:
        if rel.endswith(".py"):
            try:
                ast.parse((skill / rel).read_text(encoding="utf-8"))
                syntax.append({"path": rel, "status": "pass"})
            except (SyntaxError, UnicodeError) as exc:
                syntax.append({"path": rel, "status": "fail", "observation": str(exc)})
    cases = []
    for index, rel in enumerate(scripts, 1):
        tool = "python" if rel.endswith(".py") else "node" if rel.endswith((".js", ".mjs")) else "shell"
        cases.append({"id": "help-" + str(index), "profile": "code", "description": "Review source first, then check documented CLI help for " + rel,
            "enabled": False, "contract": {"owner": "script", "strength": "recommendation", "basis": "Confirm --help is part of the actual CLI contract before enabling."},
            "steps": [{"id": "help", "argv": [tool, "{skill}/" + rel, "--help"], "expected_exit": [0]}],
            "checks": []})
    template_path = Path(__file__).parents[1] / "examples/offline/profiles.json"
    catalog = V.read_json(template_path)
    profile = args.profile
    if profile == "auto":
        text = (skill / "SKILL.md").read_text(encoding="utf-8").lower()
        profile = "documents" if not scripts else "media" if any(x in text for x in ["pillow", "ffmpeg", "image", "video"]) else "data" if any(x in text for x in ["csv", "spreadsheet", "invoice"]) else "code"
    execution_scope = "source-review-only" if not scripts else "helper-commands-and-artifacts"
    for item in catalog[profile]:
        cases.append({"id": item["id"], "profile": profile, "description": item["description"], "enabled": False,
            "contract": {"owner": item["owner"], "strength": "recommendation", "basis": item["basis"]}, "steps": [], "checks": []})
    suite = {"schema_version": 1, "kind": "offline", "name": skill.name + " offline draft", "cases": cases}
    V.write_json(out / "suite.json", suite)
    V.write_json(out / "inventory.json", {"target": str(skill), "fingerprint": V.fingerprint(files), "suggested_profile": profile,
        "profile_selection": "heuristic suggestion; operator review required", "execution_scope": execution_scope,
        "python_syntax": syntax, "scripts": scripts})
    V.write_json(out / "runtime-proposal.json", {"schema_version": 1, "candidate": [rel for rel, p in files if rel != "SKILL.md"], "baseline": []})
    V.write_json(out / "config.json", {"schema_version": 1, "name": "local-offline", "tools": {"python": [sys.executable]},
        "filesystem_isolation": {"mode": "none"}, "process_environment": {"inherit": []}})
    source_note = ("No supported helper scripts were discovered under scripts/. Auto selects documents for source review; do not invent a CLI or count written instructions as successful task execution. "
                   "Actual website/artifact generation, native activation and cross-harness behavior remain untested.\n\n") if not scripts else ""
    (out / "REVIEW.md").write_text("# Review before execution\n\n" + source_note + "All cases are disabled drafts. Inspect target scripts; confirm CLI flags, contract ownership, legitimate fixtures and independent assertions. "
        "Review/prune every exact runtime-proposal file for grading answers before passing it as --runtime-manifest. No file is staged merely because it is proposed. "
        "Configure trusted tools/runtime dependencies and an enforced boundary where available; none mode remains diagnostic. "
        "Enable applicable cases only after adding concrete steps/checks. Disabled drafts remain pending. Agent responsibilities and recommendations do not fail a script gate.\n", encoding="utf-8")
    return {"status": "draft", "profile": profile, "execution_scope": execution_scope, "cases": len(cases), "out": str(out), "executed": 0}


def review(args):
    out = Path(args.workspace).resolve()
    result = V.read_json(out / "results.json")
    V.require(result.get("mode") == "offline", "Not an offline workspace")
    reviews = V.read_json(args.reviews)
    V.require(isinstance(reviews, list), "Reviews must be a list")
    seen = set()
    for item in reviews:
        V.fields(item, ["case_id", "repeat", "check_id", "status", "reviewer", "method", "timestamp", "evidence", "artifact_sha256"],
                 ["case_id", "repeat", "check_id", "status", "reviewer", "method", "timestamp", "evidence", "artifact_sha256"], "offline review")
        key = (item["case_id"], item["repeat"], item["check_id"])
        V.require(key not in seen, "Duplicate review")
        seen.add(key)
        V.require(item["status"] in {"pass", "fail", "blocked"}, "Invalid review status")
        for name in ["reviewer", "method", "timestamp", "evidence"]:
            V.string(item[name], name)
        rows = [r for r in result["runs"] if (r["case_id"], r["repeat"]) == key[:2]]
        V.require(len(rows) == 1, "Unknown run")
        row = rows[0]
        matches = [g for g in row["grades"] if g["id"] == item["check_id"]]
        V.require(len(matches) == 1 and matches[0]["type"] == "manual" and matches[0]["status"] == "pending", "Only pending manual checks can be reviewed")
        grade = matches[0]
        artifact = V.within(out / row["directory"] / "outputs", grade["path"])
        V.require(artifact.is_file() and V.digest(artifact) == grade.get("artifact_sha256") == item["artifact_sha256"], "Artifact changed or review hash mismatched")
        grade.update(status=item["status"], evidence=item["evidence"], review=item)
        row["status"] = V.run_status(row["grades"], "completed")
        row["correctness_check"] = row["correctness_check"] or any(
            g["type"] == "manual" and g["status"] == "pass" and "review" in g for g in row["grades"])
    V.require(not (out / "results.pre-review.json").exists(), "One atomic review import per workspace")
    shutil.copyfile(out / "results.json", out / "results.pre-review.json")
    shutil.copyfile(out / "report.md", out / "report.pre-review.md")
    V.write_json(out / "reviews.json", reviews)
    for row in result["runs"]:
        V.write_json(out / row["directory"] / "run.json", row)
    save_report(out, result)
    return result


def dispatch(args):
    if args.command == "offline-init":
        print(json.dumps(init(args), ensure_ascii=False))
        return 0
    if args.command == "offline-validate":
        path = Path(args.suite).resolve()
        validate(V.read_json(path), path.parent)
        print("Offline suite valid")
        return 0
    result = run(args) if args.command == "offline-run" else review(args)
    gate = result["summary"]["offline_gate"]
    print(json.dumps({"offline_gate": gate, "counts": result["summary"]["case_counts"]}))
    return {"pass": 0, "fail": 1, "incomplete": 2}[gate]
