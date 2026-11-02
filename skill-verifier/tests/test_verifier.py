"""Offline tests use synthetic adapters; they do not claim real LLM quality."""
import argparse
import copy
import importlib.util
import json
import os
from pathlib import Path
import sys
import subprocess
import tempfile
import unittest
import venv
from unittest import mock
from runtime_support import python_runtime_paths

SPEC = importlib.util.spec_from_file_location("verifier", Path(__file__).parents[1] / "scripts" / "verifier.py")
v = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(v)

FAKE = '''import json, pathlib, sys, time
mode, response_file = sys.argv[1:]
prompt = sys.stdin.read()
assert "hidden-oracle-sentinel" not in prompt
assert not pathlib.Path("skill/evals").exists()
assert not pathlib.Path("skill/tests").exists()
if mode == "timeout":
    time.sleep(20)
if mode == "exit-error":
    sys.exit(7)
if mode == "claude-error":
    print(json.dumps({"is_error": True, "result": "authentication error"}))
    sys.exit(0)
if mode == "claude-auth-usage":
    print(json.dumps({"is_error": True, "result": "Not logged in", "usage": {"input_tokens": 10, "output_tokens": 2, "cache_creation_input_tokens": 3, "cache_read_input_tokens": 4}, "total_cost_usd": 0.01}))
    sys.exit(1)
candidate = "<skill>" in prompt
value = {"total": 42 if candidate or mode == "both-pass" else 0}
text = json.dumps(value)
if mode == "invalid-json":
    text = "not JSON"
if mode == "stdout":
    print(text)
elif mode == "claude-json":
    print(json.dumps({"result": text, "is_error": False}))
elif mode == "gemini-json":
    print(json.dumps({"response": text}))
else:
    pathlib.Path(response_file).write_text(text)
'''


class VerifierTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.sources = self.root / "sources"
        self.sources.mkdir()
        self.target = self.root / "sample-skill"
        self.target.mkdir()
        (self.target / "SKILL.md").write_text("---\nname: sample-skill\ndescription: Extract invoice totals from supplied text.\n---\nRead the invoice.\n")
        (self.target / "evals").mkdir()
        (self.target / "evals" / "answers.json").write_text('"hidden-oracle-sentinel"')
        (self.target / "tests").mkdir()
        (self.target / "tests" / "oracle.txt").write_text("hidden-oracle-sentinel")
        (self.sources / "invoice.txt").write_text("Total: 42\n")
        self.fake = self.root / "synthetic_adapter.py"
        self.fake.write_text(FAKE)
        self.suite = {"schema_version": 1, "name": "synthetic smoke", "cases": [{
            "id": "invoice", "profile": "data", "prompt": "Extract total from inputs/invoice.txt as JSON.",
            "inputs": [{"source": "invoice.txt", "dest": "invoice.txt"}],
            "response_artifact": "invoice.json",
            "checks": [{"id": "total", "type": "json-value", "path": "invoice.json", "pointer": "/total", "expected": 42}]}]}
        self.suite_path = self.sources / "suite.json"
        self.adapter = {"schema_version": 1, "name": "synthetic-test-only",
            "argv": [sys.executable, str(self.fake), "paired", "{response_file}"], "response": "file", "timeout_seconds": 5,
            "environment": {"harness_version": "synthetic-1", "model": "deterministic-test-double", "settings": "no network or model"},
            "baseline_isolation": {"status": "verified", "evidence": "Test double has no native skill loader; test inspects staged files and prompt"}}
        self.adapter_path = self.sources / "adapter.json"

    def tearDown(self):
        self.temp.cleanup()

    def execute(self, name="workspace"):
        if self.adapter.get("filesystem_isolation", {}).get("mode", "none") != "none":
            boundary = self.adapter["filesystem_isolation"]
            boundary["readable_paths"] = list(dict.fromkeys(boundary.get("readable_paths", []) + python_runtime_paths()))
        v.write_json(self.suite_path, self.suite)
        v.write_json(self.adapter_path, self.adapter)
        return v.run_suite(argparse.Namespace(skill=str(self.target), suite=str(self.suite_path),
            adapter=str(self.adapter_path), out=str(self.root / name), baseline_skill=None, repeats=1))

    def test_diagnostic_comparison_does_not_attest_isolation(self):
        result = self.execute()
        self.assertEqual(result["summary"]["comparison_gate"], "incomplete")
        self.assertIn("Filesystem oracle isolation", " ".join(result["summary"]["blockers"]))
        self.assertEqual(result["summary"]["paired_delta_mean"], 1)
        self.assertEqual(len(result["runs"]), 2)
        self.assertEqual(result["summary"]["evidence_level"], "smoke")
        self.assertTrue((self.root / "workspace" / "report.md").is_file())
        self.assertTrue((self.root / "workspace" / "coverage.json").is_file())
        self.assertIn({"capability":"native-skill-discovery","status":"not-tested"},result["coverage"])
        self.assertEqual(result["findings"][0]["root_cause"]["status"],"not-established")
        self.assertEqual(result["summary"]["configurations"]["baseline"]["assertions"]["fail"], 1)
        self.assertEqual(result["summary"]["configurations"]["candidate"]["total_tokens"], None)

    def test_unknown_isolation_prevents_pass(self):
        self.adapter["baseline_isolation"] = {"status": "unverified", "evidence": ""}
        self.assertEqual(self.execute()["summary"]["comparison_gate"], "incomplete")

    def test_unknown_model_prevents_pass(self):
        self.adapter["environment"]["model"] = None
        self.assertEqual(self.execute()["summary"]["comparison_gate"], "incomplete")

    def test_nonzero_exit_is_blocked_with_planned_denominator(self):
        self.adapter["argv"][2] = "exit-error"
        result = self.execute()
        self.assertEqual(result["summary"]["comparison_gate"], "incomplete")
        self.assertEqual(result["summary"]["configurations"]["candidate"]["assertions"], {"pass": 0, "fail": 0, "blocked": 1, "pending": 0})
        self.assertEqual(result["summary"]["excluded_pairs"], 1)
        self.assertIsNone(result["summary"]["paired_delta_mean"])

    def test_missing_executable_is_blocked(self):
        self.adapter["argv"] = [str(self.root / "absent-executable")]
        result = self.execute()
        self.assertEqual(result["summary"]["comparison_gate"], "incomplete")
        self.assertIn("adapter-launch", result["runs"][0]["execution"]["reason"])

    def test_timeout_is_recorded(self):
        self.adapter["argv"][2] = "timeout"
        self.adapter["timeout_seconds"] = 0.1
        result = self.execute()
        self.assertEqual(result["summary"]["comparison_gate"], "incomplete")
        self.assertIn("timeout", result["runs"][0]["execution"]["reason"])

    def test_json_error_envelope_cannot_pass_on_exit_zero(self):
        self.adapter["argv"][2] = "claude-error"
        self.adapter["response"] = "claude-json"
        self.assertEqual(self.execute()["summary"]["comparison_gate"], "incomplete")

    def test_all_response_modes(self):
        for mode in ["stdout", "claude-json", "gemini-json"]:
            with self.subTest(mode=mode):
                self.adapter["argv"][2] = mode
                self.adapter["response"] = mode
                self.assertEqual(self.execute(mode)["summary"]["comparison_gate"], "incomplete")

    def test_bad_artifact_fails_even_if_execution_succeeds(self):
        self.adapter["argv"][2] = "invalid-json"
        self.assertEqual(self.execute()["summary"]["comparison_gate"], "fail")

    def test_no_artifact_is_failure(self):
        del self.suite["cases"][0]["response_artifact"]
        self.assertEqual(self.execute()["summary"]["comparison_gate"], "fail")

    def test_fail_not_hidden_by_another_block(self):
        result = self.execute()
        result["runs"][0]["grades"][0]["status"] = "fail"
        result["runs"][0]["status"] = "fail"
        result["runs"][1]["grades"][0]["status"] = "blocked"
        result["runs"][1]["status"] = "blocked"
        self.assertEqual(v.summarize(result["runs"], self.adapter, 1)["comparison_gate"], "fail")

    def test_baseline_failure_plus_pending_is_incomplete(self):
        result = self.execute()
        result["runs"][0]["grades"].append({"id": "review", "status": "pass"})
        result["runs"][1]["grades"].append({"id": "review", "status": "pending"})
        summary = v.summarize(result["runs"], self.adapter, 1)
        self.assertEqual(summary["comparison_gate"], "incomplete")
        self.assertEqual(summary["excluded_pairs"], 1)

    def test_observed_regression_preserved_with_other_pending_checks(self):
        result = self.execute()
        result["runs"][0]["grades"][0]["status"] = "fail"
        result["runs"][1]["grades"][0]["status"] = "pass"
        for run in result["runs"]:
            run["grades"].append({"id": "review", "status": "pending"})
            run["status"] = v.run_status(run["grades"], "completed")
        summary = v.summarize(result["runs"], self.adapter, 1)
        self.assertEqual(len(summary["regressions"]), 1)
        self.assertEqual(summary["comparison_gate"], "fail")

    def test_no_overwriting_evidence(self):
        self.execute()
        with self.assertRaises(v.ContractError):
            self.execute()

    def test_path_escape_and_duplicate_contracts_rejected(self):
        mutations = [
            lambda c: c["inputs"][0].update(source="../synthetic_adapter.py"),
            lambda c: c["inputs"][0].update(dest="../invoice.txt"),
            lambda c: c["checks"][0].update(path="/etc/passwd"),
            lambda c: c["checks"][0].update(path="C:\\Users\\foo"),
            lambda c: c["checks"].append(copy.deepcopy(c["checks"][0])),
            lambda c: c["checks"][0].update(type="command"),
            lambda c: c["checks"][0].update(pointer="/bad~2escape"),
            lambda c: c["checks"][0].update(min_bytes=1),
            lambda c: c.update(unrecognized="typo")]
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                invalid = copy.deepcopy(self.suite)
                mutation(invalid["cases"][0])
                with self.assertRaises(v.ContractError):
                    v.validate_suite(invalid, self.sources)

    def test_empty_suite_and_empty_checks_rejected(self):
        for bad in [{"schema_version": 1, "name": "bad", "cases": []},
                    dict(self.suite, cases=[dict(self.suite["cases"][0], checks=[])])]:
            with self.assertRaises(v.ContractError):
                v.validate_suite(bad, self.sources)

    def test_json_boolean_not_number_and_pointer_escape(self):
        artifact = self.root / "result.json"
        v.write_json(artifact, {"a/b": {"~": [True]}})
        check = {"id": "type", "type": "json-value", "path": "result.json", "pointer": "/a~1b/~0/0", "expected": 1}
        self.assertEqual(v.grade_check(check, self.root)["status"], "fail")
        check["expected"] = True
        self.assertEqual(v.grade_check(check, self.root)["status"], "pass")

    def test_duplicate_json_keys_rejected(self):
        artifact = self.root / "ambiguous.json"
        artifact.write_text('{"total": 0, "total": 42}')
        with self.assertRaises(v.ContractError):
            v.read_json(artifact)

    def test_symlink_outputs_and_fixture_rejected(self):
        real = self.root / "real"
        real.mkdir()
        (real / "result.json").write_text('{"total":42}')
        linked = self.root / "linked"
        linked.symlink_to(real, target_is_directory=True)
        grade = v.grade_check({"id": "total", "type": "json-value", "path": "result.json", "pointer": "/total", "expected": 42}, linked)
        self.assertEqual(grade["status"], "fail")
        (self.sources / "invoice.txt").unlink()
        (self.sources / "invoice.txt").symlink_to(real / "result.json")
        with self.assertRaises(v.ContractError):
            v.validate_suite(self.suite, self.sources)

    def test_csv_structure_and_hash(self):
        artifact = self.root / "table.csv"
        artifact.write_text('name,value\na,2\nb,3\n')
        check = {"id": "rows", "type": "csv-rows", "path": "table.csv", "expected": 2}
        self.assertEqual(v.grade_check(check, self.root)["status"], "pass")
        self.assertEqual(v.grade_check({"id": "bytes", "type": "sha256", "path": "table.csv", "expected": v.digest(artifact)}, self.root)["status"], "pass")
        artifact.write_text('name,value\na,2,extra\n')
        self.assertEqual(v.grade_check(check, self.root)["status"], "fail")

    def test_manual_review_bound_to_artifact(self):
        case = self.suite["cases"][0]
        case["checks"].append({"id": "semantic", "type": "manual", "path": "invoice.json", "rubric": "Numbers faithfully reflect the provided invoice."})
        self.adapter["argv"][2] = "both-pass"
        result = self.execute()
        self.assertEqual(result["summary"]["comparison_gate"], "incomplete")
        reviews = []
        for run in result["runs"]:
            artifact = self.root / "workspace" / run["directory"] / "work" / "outputs" / "invoice.json"
            reviews.append({"case_id": "invoice", "repeat": 1, "configuration": run["configuration"], "check_id": "semantic", "status": "pass",
                "reviewer": "test-independent-review", "method": "synthetic test", "timestamp": "2026-10-29T00:00:00Z",
                "evidence": "Observed total 42 in invoice artifact.", "artifact_sha256": v.digest(artifact)})
        review_path = self.root / "reviews.json"
        invalid = copy.deepcopy(reviews)
        invalid[1]["artifact_sha256"] = "0" * 64
        v.write_json(review_path, invalid)
        with self.assertRaises(v.ContractError):
            v.apply_reviews(self.root / "workspace", review_path)
        self.assertFalse((self.root / "workspace" / "results.pre-review.json").exists())
        v.write_json(review_path, reviews)
        updated = v.apply_reviews(self.root / "workspace", review_path)
        self.assertEqual(updated["summary"]["comparison_gate"], "incomplete")
        self.assertTrue(all(run["status"] == "pass" for run in updated["runs"]))
        self.assertTrue((self.root / "workspace" / "results.pre-review.json").is_file())

    def test_static_lint_catches_broken_references_without_execution(self):
        with (self.target / "SKILL.md").open("a") as stream:
            stream.write("\n[missing guide](references/missing.md)\n")
        result = v.lint(self.target)
        self.assertEqual(result["status"], "fail")
        self.assertIn("missing-reference", {f["code"] for f in result["findings"]})

    def test_static_lint_valid_control_has_no_errors(self):
        result = v.lint(self.target)
        self.assertNotEqual(result["status"], "fail")
        self.assertIn(result["yaml_validation"], {"parsed", "subset-only"})

    def test_adapter_isolation_requires_evidence(self):
        self.adapter["baseline_isolation"]["evidence"] = ""
        with self.assertRaises(v.ContractError):
            v.validate_adapter(self.adapter)

    def test_existing_artifact_qa_without_agent(self):
        v.write_json(self.suite_path, self.suite)
        output = self.root / "artifact-output"
        output.mkdir()
        v.write_json(output / "invoice.json", {"total": 42})
        result = v.grade_artifacts(self.suite_path, "invoice", output)
        self.assertEqual(result["status"], "pass")
        v.write_json(output / "invoice.json", {"total": 0})
        self.assertEqual(v.grade_artifacts(self.suite_path, "invoice", output)["status"], "fail")

    def test_duplicate_yaml_keys_when_parser_available(self):
        try:
            import yaml
        except ImportError:
            self.skipTest("Optional full YAML parser is absent")
        (self.target / "SKILL.md").write_text("---\nname: sample-skill\nname: sample-skill\ndescription: Extract invoices.\n---\nRead input.\n")
        result = v.lint(self.target)
        self.assertEqual(result["status"], "fail")
        self.assertEqual(result["yaml_validation"], "failed")

    def test_review_rejects_replaced_run_artifact(self):
        self.suite["cases"][0]["checks"] = [{"id": "semantic", "type": "manual", "path": "invoice.json", "rubric": "Reflect the invoice."}]
        result = self.execute()
        run = result["runs"][0]
        artifact = self.root / "workspace" / run["directory"] / "work" / "outputs" / "invoice.json"
        artifact.write_text('{"total":999}')
        review = {"case_id": "invoice", "repeat": 1, "configuration": "candidate", "check_id": "semantic", "status": "pass",
                  "reviewer": "test-review", "method": "synthetic", "timestamp": "2026-10-29T00:00:00Z", "evidence": "Read altered output", "artifact_sha256": v.digest(artifact)}
        review_path = self.root / "review-tamper.json"
        v.write_json(review_path, [review])
        with self.assertRaises(v.ContractError):
            v.apply_reviews(self.root / "workspace", review_path)

    def test_oracle_copy_with_operator_attestation_never_passes(self):
        self.fake.write_text('import pathlib,json,sys\nsys.stdin.read()\nsuite=json.loads(pathlib.Path(' + repr(str(self.suite_path)) + ').read_text())\nvalue=suite["cases"][0]["checks"][0]["expected"]\npathlib.Path(sys.argv[2]).write_text(json.dumps({"total":value}))\n')
        result = self.execute()
        self.assertTrue(all(run["status"] == "pass" for run in result["runs"]))
        self.assertEqual(result["summary"]["comparison_gate"], "incomplete")
        self.assertTrue(all(run["execution"]["filesystem_isolation"]["status"] != "enforced" for run in result["runs"]))
        self.assertTrue(all(not Path(run["execution"]["argv"][-1]).is_relative_to(self.root / "workspace") for run in result["runs"]))

    def test_parent_suite_path_is_absent_from_task_tree(self):
        self.fake.write_text('import pathlib,sys\nsys.stdin.read()\nassert not pathlib.Path("../../../../suite.json").is_file()\npathlib.Path(sys.argv[2]).write_text("{\\"total\\":42}")\n')
        result = self.execute()
        self.assertTrue(all(run["status"] == "pass" for run in result["runs"]))
        self.assertEqual(result["summary"]["comparison_gate"], "incomplete")

    def test_unlisted_references_and_examples_are_not_staged(self):
        for relative in ["references/answers.md", "examples/answers.json", "assets/answers.txt"]:
            target = self.target / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("hidden-oracle-sentinel")
        result = self.execute()
        self.assertEqual(set(result["skill"]["files"]), {"SKILL.md"})
        staged = self.root / "workspace" / result["runs"][0]["directory"] / "work" / "skill"
        self.assertEqual([p.name for p in staged.iterdir()], ["SKILL.md"])

    def test_runtime_allowlist_is_explicit_and_keeps_other_files_private(self):
        (self.target / "references").mkdir()
        (self.target / "references" / "method.md").write_text("Useful runtime method")
        (self.target / "references" / "answers.md").write_text("hidden-oracle-sentinel")
        out = self.root / "runtime-snapshot"
        fingerprint = v.snapshot(self.target, out, ["references/method.md"])
        self.assertEqual(set(fingerprint["files"]), {"SKILL.md", "references/method.md"})
        self.assertFalse((out / "references" / "answers.md").exists())
        with self.assertRaises(v.ContractError):
            v.snapshot(self.target, self.root / "bad-snapshot", ["../secret"])

    def test_markdown_code_links_are_not_missing_resources(self):
        body = '\n`![hover](img_key)` and ``[xx]($urlVal)`` and `![x](./a.png)`\n```md\n[example](missing-a.md)\n```\n~~~md\n[example](missing-b.md)\n~~~\n[real missing](scripts/missing-helper.md)\n[external](../lark-shared/SKILL.md)\n'
        with (self.target / "SKILL.md").open("a") as stream:
            stream.write(body)
        result = v.lint(self.target)
        errors = [f for f in result["findings"] if f["code"] == "missing-reference"]
        self.assertEqual(len(errors), 1)
        self.assertIn("scripts/missing-helper.md", errors[0]["message"])
        self.assertEqual(errors[0]["line"], 14)
        self.assertIn("external-file-reference", {f["code"] for f in result["findings"]})

    def test_placeholder_prohibitions_are_not_unfinished_content(self):
        with (self.target / "SKILL.md").open("a") as stream:
            stream.write("\nmust contain no TODO or FIXME.\nNo unresolved TODO/TBD/Lorem placeholders.\nDo not leave TODO markers.\n禁止 TODO 占位符。\nNo TODO markers. TODO: add the actual requirements\n")
        markers = [f for f in v.lint(self.target)["findings"] if f["code"] == "placeholder"]
        self.assertEqual(len(markers), 1)
        self.assertEqual(markers[0]["line"], 11)

    def test_duplicate_yaml_rejected_without_optional_parser(self):
        (self.target / "SKILL.md").write_text('---\nname: sample-skill\n"name": sample-skill\ndescription: Extract invoices.\n---\nRead.\n')
        with mock.patch.dict(sys.modules, {"yaml": None}):
            result = v.lint(self.target)
        self.assertEqual(result["status"], "fail")
        self.assertIn("duplicate-yaml-key", {f["code"] for f in result["findings"]})

    def test_unicode_lowercase_skill_names(self):
        target = self.root / "naïve-skill"
        target.mkdir()
        (target / "SKILL.md").write_text("---\nname: naïve-skill\ndescription: Extract invoice totals.\n---\nRead input.\n")
        self.assertNotIn("name", {f["code"] for f in v.lint(target)["findings"]})
        self.assertFalse(v.valid_skill_name("Naïve-skill"))
        self.assertFalse(v.valid_skill_name("naïve--skill"))

    def test_nonzero_claude_envelope_records_usage_and_log_location(self):
        self.adapter["argv"][2] = "claude-auth-usage"
        self.adapter["response"] = "claude-json"
        result = self.execute()
        execution = result["runs"][0]["execution"]
        self.assertEqual(execution["status"], "blocked")
        self.assertIn("stdout.log", execution["reason"])
        self.assertIn("stderr.log", execution["reason"])
        self.assertEqual(execution["total_tokens"], 19)
        self.assertEqual(execution["cost"]["amount"], 0.01)
        self.assertEqual(result["summary"]["configurations"]["candidate"]["total_tokens"], 19)

    def test_unknown_and_gemini_usage_are_preserved_without_guessing(self):
        self.assertEqual(v.usage_from_envelope({}, "claude-json")["total_tokens"], None)
        self.assertEqual(v.usage_from_envelope({"usage": {"input_tokens": True, "output_tokens": 1}}, "claude-json")["total_tokens"], None)
        gemini = v.usage_from_envelope({"stats": {"tokens": {"total": 12, "input": 8, "output": 4}}}, "gemini-json")
        self.assertEqual(gemini["total_tokens"], 12)
        self.assertIsNone(gemini["cost"])

    def test_requested_unavailable_boundary_blocks_without_running_adapter(self):
        self.adapter["filesystem_isolation"] = {"mode": "linux-bwrap" if sys.platform == "darwin" else "macos-sandbox"}
        result = self.execute()
        self.assertEqual(result["summary"]["comparison_gate"], "incomplete")
        self.assertTrue(all(run["status"] == "blocked" for run in result["runs"]))

    def test_presence_only_comparison_remains_incomplete(self):
        self.suite["cases"][0]["checks"] = [{"id": "file", "type": "exists", "path": "invoice.json"}]
        result = self.execute()
        self.assertTrue(all(run["status"] == "pass" for run in result["runs"]))
        self.assertIn("Only file presence", " ".join(result["summary"]["blockers"]))

    def test_environment_defaults_do_not_copy_parent_values(self):
        parent = {"HOME": "/parent-home", "PATH": "/parent-only-bin", "OPENAI_API_KEY": "fake-parent-secret",
                  "PYTHONPATH": "/parent-python", "VIRTUAL_ENV": "/parent-venv", "UNLISTED": "fake-value"}
        child, record = v.isolation.task_environment({}, self.root / "work", parent)
        self.assertEqual(child["HOME"], str(self.root / "work/.home"))
        self.assertEqual(child["PATH"], os.defpath)
        self.assertNotIn("OPENAI_API_KEY", child)
        self.assertNotIn("PYTHONPATH", child)
        self.assertNotIn("VIRTUAL_ENV", child)
        self.assertNotIn("UNLISTED", child)
        self.assertNotIn("fake-parent-secret", json.dumps(record))
        self.assertFalse(record["values_recorded"])

    def test_exact_environment_opt_in_and_probe_do_not_share_task_settings(self):
        adapter = {"process_environment": {"inherit": ["QA_PUBLIC_SETTING", "QA_MISSING"], "path": [str(self.root / "bin")]}}
        parent = {"QA_PUBLIC_SETTING": "fake-approved-value", "OTHER_SECRET": "fake-private-value"}
        child, record = v.isolation.task_environment(adapter, self.root / "work", parent)
        self.assertEqual(child["QA_PUBLIC_SETTING"], "fake-approved-value")
        self.assertNotIn("OTHER_SECRET", child)
        self.assertEqual(record["missing_names"], ["QA_MISSING"])
        self.assertEqual(child["PATH"].split(os.pathsep)[0], str(self.root / "bin"))
        probe, probe_record = v.isolation.task_environment(adapter, self.root / "work", parent, for_probe=True)
        self.assertNotIn("QA_PUBLIC_SETTING", probe)
        self.assertEqual(probe_record["inherited_names"], [])
        self.assertNotIn("fake-approved-value", json.dumps(record))

    def test_environment_wildcards_reserved_keys_and_unknown_fields_rejected(self):
        for config in [{"inherit": ["*"]}, {"inherit": ["HOME"]}, {"inherit": ["PATH"]},
                       {"inherit": ["PYTHONPATH"]}, {"inherit": ["DYLD_INSERT_LIBRARIES"]},
                       {"inherit": ["NODE_OPTIONS"]}, {"inherit": ["BASH_ENV"]},
                       {"inherit": ["QA", "QA"]}, {"inherit": "QA"}, {"inherit_all": True},
                       {"path": ["relative/bin"]}]:
            with self.subTest(config=config):
                adapter = copy.deepcopy(self.adapter)
                adapter["process_environment"] = config
                with self.assertRaises(v.ContractError):
                    v.validate_adapter(adapter)

    def test_actual_task_sees_clean_environment_and_task_local_home(self):
        self.fake.write_text('''import os,sys,pathlib,json
sys.stdin.read()
root=pathlib.Path.cwd()
home=pathlib.Path(os.environ["HOME"])
keys=["OPENAI_API_KEY","AWS_SECRET_ACCESS_KEY","PYTHONPATH","VIRTUAL_ENV","BASH_ENV","PARENT_SENTINEL"]
clean=all(key not in os.environ for key in keys) and home==root/".home" and os.environ["TMPDIR"]==str(root/"tmp")
clean=clean and all(pathlib.Path(os.environ[k]).is_relative_to(home) for k in ["XDG_CONFIG_HOME","XDG_CACHE_HOME","XDG_DATA_HOME","XDG_STATE_HOME"])
(home/"cache.txt").write_text("task cache")
pathlib.Path(sys.argv[2]).write_text(json.dumps({"clean":clean}))
''')
        self.suite["cases"][0]["checks"][0].update(pointer="/clean", expected=True)
        fake_parent = {"HOME": "/fake-parent-home", "OPENAI_API_KEY": "qa-fake-key", "AWS_SECRET_ACCESS_KEY": "qa-fake-secret",
                       "PYTHONPATH": "/fake-pythonpath", "VIRTUAL_ENV": "/fake-venv", "BASH_ENV": "/fake-hook", "PARENT_SENTINEL": "qa-secret-marker"}
        with mock.patch.dict(os.environ, fake_parent):
            result = self.execute()
        self.assertTrue(all(run["status"] == "pass" for run in result["runs"]))
        for run in result["runs"]:
            self.assertEqual(run["execution"]["process_environment"]["inherited_names"], [])
            self.assertFalse((self.root / "workspace" / run["directory"] / "work/.home").exists())
        self.assertNotIn("qa-secret-marker", json.dumps(result))

    def test_actual_task_receives_only_explicitly_inherited_setting(self):
        self.fake.write_text('''import os,sys,pathlib,json
sys.stdin.read()
pathlib.Path(sys.argv[2]).write_text(json.dumps({"approved":os.environ.get("QA_PUBLIC_SETTING")=="qa-nonsecret-value" and "UNLISTED_SETTING" not in os.environ}))
''')
        self.adapter["process_environment"] = {"inherit": ["QA_PUBLIC_SETTING"]}
        self.suite["cases"][0]["checks"][0].update(pointer="/approved", expected=True)
        with mock.patch.dict(os.environ, {"QA_PUBLIC_SETTING": "qa-nonsecret-value", "UNLISTED_SETTING": "qa-private-value"}):
            result = self.execute()
        self.assertTrue(all(run["status"] == "pass" for run in result["runs"]))
        self.assertEqual(result["runs"][0]["execution"]["process_environment"]["inherited_names"], ["QA_PUBLIC_SETTING"])
        self.assertNotIn("qa-nonsecret-value", json.dumps(result))

    def test_probe_uses_base_interpreter_not_driver_virtualenv(self):
        base = Path(getattr(sys, "_base_executable", None) or sys.executable).resolve()
        with mock.patch.object(sys, "executable", str(self.sources / ".venv/bin/python")), mock.patch.object(sys, "_base_executable", str(base), create=True):
            selected = v.isolation.probe_interpreter({})
        self.assertEqual(selected["executable"], str(base))
        self.assertEqual(selected["selection"], "verifier-base")

    def test_missing_probe_python_blocks_without_fallback(self):
        self.adapter["filesystem_isolation"] = {"mode": "macos-sandbox", "probe_python": str(self.root / "missing-python")}
        result = self.execute()
        self.assertTrue(all(run["status"] == "blocked" for run in result["runs"]))
        self.assertIn("Probe Python is missing", result["runs"][0]["execution"]["reason"])
        self.assertEqual(result["summary"]["comparison_gate"], "incomplete")

    @unittest.skipUnless(os.environ.get("SKILL_VERIFIER_TEST_SANDBOX") == "1" and sys.platform == "darwin", "Opt-in real macOS isolation test")
    def test_virtualenv_driver_inside_evaluator_project_uses_base_probe(self):
        virtual = self.sources / ".venv"
        venv.EnvBuilder(with_pip=False, symlinks=True).create(virtual)
        self.adapter["argv"][0] = str(Path(getattr(sys, "_base_executable", None) or sys.executable).resolve())
        self.adapter["filesystem_isolation"] = {"mode": "macos-sandbox", "readable_paths": [str(self.fake)] + python_runtime_paths(), "allow_network": False}
        v.write_json(self.suite_path, self.suite)
        v.write_json(self.adapter_path, self.adapter)
        env, _ = v.isolation.task_environment({}, self.root / "driver-state")
        command = [str(virtual / "bin/python"), "-I", str(Path(v.__file__)), "run", "--skill", str(self.target),
                   "--suite", str(self.suite_path), "--adapter", str(self.adapter_path), "--out", str(self.root / "venv-driver")]
        completed = subprocess.run(command, env=env, capture_output=True, text=True, timeout=30)
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        result = v.read_json(self.root / "venv-driver/results.json")
        self.assertEqual(result["summary"]["comparison_gate"], "pass")
        for run in result["runs"]:
            probe = run["execution"]["filesystem_isolation"]["probe_python"]
            self.assertEqual(probe["selection"], "verifier-base")
            self.assertFalse(Path(probe["executable"]).is_relative_to(virtual))

    @unittest.skipUnless(os.environ.get("SKILL_VERIFIER_TEST_SANDBOX") == "1" and sys.platform == "darwin", "Opt-in real macOS isolation test")
    def test_explicit_venv_probe_gets_config_without_project_read_grant(self):
        virtual = self.root / "probe-venv"
        venv.EnvBuilder(with_pip=False, symlinks=True).create(virtual)
        private_sibling = self.root / "runtime-sibling-private.txt"
        private_sibling.write_text("qa-private-sibling")
        self.fake.write_text('import json,pathlib,sys\nsys.stdin.read()\ntry: pathlib.Path(' + repr(str(private_sibling)) + ').read_text()\nexcept PermissionError: denied=True\nelse: denied=False\npathlib.Path(sys.argv[2]).write_text(json.dumps({"total":42,"sibling_denied":denied}))\n')
        self.suite["cases"][0]["checks"].append({"id": "private-sibling", "type": "json-value", "path": "invoice.json", "pointer": "/sibling_denied", "expected": True})
        self.adapter["filesystem_isolation"] = {"mode": "macos-sandbox", "readable_paths": [str(self.fake)], "allow_network": False, "probe_python": str(virtual / "bin/python")}
        result = self.execute()
        self.assertEqual(result["summary"]["comparison_gate"], "pass", json.dumps(result["summary"]))
        self.assertIn(str(virtual / "pyvenv.cfg"), result["runs"][0]["execution"]["filesystem_isolation"]["probe_python"]["config_files"])

    @unittest.skipUnless(os.environ.get("SKILL_VERIFIER_TEST_SANDBOX") == "1" and sys.platform == "darwin", "Opt-in real macOS isolation test")
    def test_virtualenv_task_interpreter_symlink(self):
        virtual = self.root / "symlink-venv"
        venv.EnvBuilder(with_pip=False, symlinks=True).create(virtual)
        self.adapter["argv"][0] = str(virtual / "bin/python")
        self.adapter["filesystem_isolation"] = {"mode": "macos-sandbox", "readable_paths": [str(self.fake)], "allow_network": False}
        result = self.execute()
        self.assertEqual(result["summary"]["comparison_gate"], "pass", json.dumps([r["execution"] for r in result["runs"]]))
        self.assertIn(str(virtual / "pyvenv.cfg"), result["runs"][0]["execution"]["task_python"]["config_files"])

    @unittest.skipUnless(os.environ.get("SKILL_VERIFIER_TEST_SANDBOX") == "1" and sys.platform == "darwin", "Opt-in real macOS isolation test")
    def test_virtualenv_task_interpreter_copy(self):
        virtual = self.root / "copy-venv"
        try:
            builder = venv.EnvBuilder(with_pip=False, symlinks=False)
        except Exception:
            # Apple CLT framework Python cannot make copied venvs. An existing trusted
            # standalone runtime may be supplied; nothing is downloaded or installed.
            other = os.environ.get("SKILL_VERIFIER_COPY_PYTHON")
            if not other:
                self.skipTest("This Python requires symlink venvs; set SKILL_VERIFIER_COPY_PYTHON to an existing compatible runtime")
            env, _ = v.isolation.task_environment({}, self.root / "venv-creator")
            completed = subprocess.run([other, "-I", "-c", "import venv,sys;venv.EnvBuilder(with_pip=False,symlinks=False).create(sys.argv[1]);print(sys.base_prefix)", str(virtual)],
                                       env=env, capture_output=True, text=True, timeout=30)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            library = Path(completed.stdout.strip()) / "lib"
        else:
            builder.create(virtual)
            library = Path(sys.base_prefix) / "lib"
        self.adapter["argv"][0] = str(virtual / "bin/python")
        self.adapter["filesystem_isolation"] = {"mode": "macos-sandbox", "readable_paths": [str(self.fake), str(library)], "allow_network": False}
        result = self.execute()
        self.assertEqual(result["summary"]["comparison_gate"], "pass", json.dumps([r["execution"] for r in result["runs"]]))
        self.assertIn(str(virtual / "pyvenv.cfg"), result["runs"][0]["execution"]["task_python"]["config_files"])

    @unittest.skipUnless(os.environ.get("SKILL_VERIFIER_TEST_SANDBOX") == "1" and sys.platform == "darwin", "Opt-in real macOS isolation test")
    def test_probe_venv_overlapping_private_oracle_tree_stays_blocked(self):
        virtual = self.sources / ".venv"
        venv.EnvBuilder(with_pip=False, symlinks=True).create(virtual)
        self.adapter["filesystem_isolation"] = {"mode": "macos-sandbox", "readable_paths": [str(self.fake)], "probe_python": str(virtual / "bin/python")}
        result = self.execute()
        self.assertEqual(result["summary"]["comparison_gate"], "incomplete")
        self.assertTrue(all(run["status"] == "blocked" for run in result["runs"]))
        self.assertIn("overlaps evaluator", result["runs"][0]["execution"]["reason"])

    @unittest.skipUnless(os.environ.get("SKILL_VERIFIER_TEST_SANDBOX") == "1" and sys.platform == "darwin", "Opt-in real macOS isolation test")
    def test_enforced_macos_boundary_allows_clean_task_and_denies_oracle(self):
        self.adapter["filesystem_isolation"] = {"mode": "macos-sandbox", "readable_paths": [str(self.fake)], "allow_network": False}
        clean = self.execute("clean-isolated")
        probes = [p.name + ": " + p.read_text() for p in (self.root / "clean-isolated").rglob("isolation-probe.*.log")]
        self.assertEqual(clean["summary"]["comparison_gate"], "pass", json.dumps([r["execution"] for r in clean["runs"]]) + "\n" + "\n".join(probes))
        self.assertTrue(all(r["execution"]["filesystem_isolation"]["status"] == "enforced" for r in clean["runs"]))
        # A trusted adversarial fixture tries the original suite, report copy, old parent path,
        # and a sibling private file. It cannot obtain any of these under the same boundary.
        suite_copy = self.root / "cheat-isolated" / "suite.json"
        self.fake.write_text('import pathlib,sys,json\nsys.stdin.read()\npaths=' + repr([str(self.suite_path), str(suite_copy), "../../../../suite.json"]) + '\nfor path in paths:\n try: pathlib.Path(path).read_bytes()\n except (PermissionError,FileNotFoundError): pass\n else: raise RuntimeError("oracle readable")\npathlib.Path(sys.argv[2]).write_text("{\\"total\\":-1}")\n')
        cheated = self.execute("cheat-isolated")
        self.assertEqual(cheated["summary"]["comparison_gate"], "fail")
        self.assertTrue(all(r["execution"]["status"] == "completed" for r in cheated["runs"]))

    def test_old_version_baseline_is_staged(self):
        old = self.root / "old-skill"
        old.mkdir()
        (old / "SKILL.md").write_text("---\nname: old-skill\ndescription: Old version.\n---\nRead input.\n")
        v.write_json(self.suite_path, self.suite)
        v.write_json(self.adapter_path, self.adapter)
        result = v.run_suite(argparse.Namespace(skill=str(self.target), suite=str(self.suite_path), adapter=str(self.adapter_path),
            out=str(self.root / "version-workspace"), baseline_skill=str(old), repeats=2))
        self.assertIsNotNone(result["baseline_skill"])
        self.assertEqual(len(result["runs"]), 4)
        self.assertEqual(result["summary"]["evidence_level"], "repeated-trials")
        self.assertEqual(result["summary"]["paired_delta_mean"], 0)


if __name__ == "__main__":
    unittest.main()
