"""Behavioral regressions for offline execution; native tests require opt-in."""
import argparse
import copy
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

SPEC = importlib.util.spec_from_file_location("verifier_offline_tests", Path(__file__).parents[1] / "scripts/verifier.py")
v = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(v)
o = v.offline_module()

PROGRAM = '''import json,pathlib,sys,time,os
mode = sys.argv[1]
if mode == "timeout":
    time.sleep(20)
if mode == "reject":
    print("invalid input",file=sys.stderr)
    sys.exit(7)
if mode == "bad":
    print(json.dumps({"result":16}))
elif mode == "link":
    pathlib.Path("outputs/result.json").symlink_to(sys.argv[2])
elif mode == "outputs-link":
    pathlib.Path("outputs").rmdir()
    pathlib.Path("outputs").symlink_to(sys.argv[2],target_is_directory=True)
elif mode == "environment":
    print(json.dumps({"secret_absent":"QA_SECRET" not in os.environ,"home_local":os.environ["HOME"].startswith(str(pathlib.Path.cwd()))}))
elif mode == "oracle":
    try:
        pathlib.Path(sys.argv[2]).read_bytes()
        denied=False
    except PermissionError:
        denied=True
    print(json.dumps({"denied":denied}))
else:
    print(json.dumps({"result":8}))
'''


class OfflineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.skill = self.root / "sample-skill"
        (self.skill / "scripts").mkdir(parents=True)
        (self.skill / "SKILL.md").write_text("---\nname: sample-skill\ndescription: Transform local integers.\n---\nUse scripts/run.py.\n")
        (self.skill / "scripts/run.py").write_text(PROGRAM)
        self.plan = self.root / "plan"
        self.plan.mkdir()
        self.suite_path = self.plan / "suite.json"
        self.config_path = self.plan / "config.json"
        self.runtime_path = self.plan / "runtime.json"
        v.write_json(self.runtime_path, {"schema_version":1,"candidate":["scripts/run.py"],"baseline":[]})
        self.case = {"id":"normal","profile":"code","description":"Double four correctly.",
            "contract":{"owner":"script","strength":"required","basis":"The documented result for input 4 is 8."},
            "steps":[{"id":"run","argv":["python","{skill}/scripts/run.py","good"],"stdout_artifact":"result.json"}],
            "checks":[{"id":"value","type":"json-value","path":"result.json","pointer":"/result","expected":8}]}
        self.suite = {"schema_version":1,"kind":"offline","name":"local tests","cases":[self.case]}
        self.config = {"schema_version":1,"name":"test-runtime","tools":{"python":[sys.executable]},"filesystem_isolation":{"mode":"none"}}

    def tearDown(self):
        self.temp.cleanup()

    def execute(self, name="out", repeats=1, manifest=True):
        v.write_json(self.suite_path,self.suite)
        v.write_json(self.config_path,self.config)
        return o.run(argparse.Namespace(skill=str(self.skill),suite=str(self.suite_path),config=str(self.config_path),
            out=str(self.root/name),runtime_manifest=str(self.runtime_path) if manifest else None,repeats=repeats))

    def test_real_stdout_artifact_is_checked_and_diagnostic_is_incomplete(self):
        result=self.execute()
        self.assertEqual(result["runs"][0]["status"],"pass")
        self.assertEqual(result["summary"]["offline_gate"],"incomplete")
        self.assertEqual(result["summary"]["comparison_gate"],"not-run")
        self.assertTrue(result["source_unchanged"])
        self.assertEqual(json.loads((self.root/"out/runs/normal-r1/outputs/result.json").read_text()),{"result":8})

    def test_wrong_content_fails_even_after_exit_zero(self):
        self.case["steps"][0]["argv"][-1]="bad"
        result=self.execute()
        self.assertEqual(result["summary"]["offline_gate"],"fail")
        self.assertIn("16",result["findings"][0]["observations"][0]["evidence"])
        self.assertEqual(result["findings"][0]["root_cause"]["status"],"not-established")

    def test_missing_tool_blocks_without_running(self):
        self.config["tools"]["python"]=[str(self.root/"missing")]
        result=self.execute()
        self.assertEqual(result["runs"][0]["status"],"blocked")
        self.assertEqual(result["summary"]["offline_gate"],"incomplete")
        self.assertEqual(result["runs"][0]["steps"],[])

    def test_missing_runtime_is_blocked_not_target_failure(self):
        result=self.execute(manifest=False)
        self.assertEqual(result["runs"][0]["status"],"blocked")
        self.assertIn("staged",result["runs"][0]["steps"][0]["reason"])

    def test_expected_rejection_retains_stderr_evidence(self):
        self.case["steps"][0].update(argv=["python","{skill}/scripts/run.py","reject"],expected_exit="nonzero",stderr_artifact="reason.txt")
        self.case["checks"]=[{"id":"reason","type":"text-contains","path":"reason.txt","text":"invalid input"}]
        self.assertEqual(self.execute()["runs"][0]["status"],"pass")

    def test_timeout_never_satisfies_expected_nonzero(self):
        self.case["steps"][0].update(argv=["python","{skill}/scripts/run.py","timeout"],expected_exit="nonzero",timeout_seconds=0.05)
        result=self.execute()
        self.assertEqual(result["runs"][0]["status"],"blocked")
        self.assertIn("timeout",result["runs"][0]["steps"][0]["reason"])

    def test_precondition_exit_is_blocked(self):
        self.case["steps"][0].update(argv=["python","{skill}/scripts/run.py","reject"],role="precondition")
        self.assertEqual(self.execute()["runs"][0]["status"],"blocked")

    def test_first_failure_is_preserved_across_repeats(self):
        self.case["steps"][0]["argv"][-1]="bad"
        result=self.execute(repeats=2)
        self.assertEqual(result["summary"]["case_counts"]["fail"],2)
        self.assertEqual(len(result["runs"]),2)

    def test_failed_step_keeps_dependent_steps_blocked(self):
        self.case["steps"][0]["argv"][-1]="reject"
        self.case["steps"].append({"id":"later","argv":["python","{skill}/scripts/run.py","good"]})
        result=self.execute()
        self.assertEqual(result["runs"][0]["grades"][0]["status"],"fail")
        self.assertEqual(result["runs"][0]["grades"][1]["status"],"blocked")

    def test_disabled_draft_is_pending_with_no_commands(self):
        self.case.update(enabled=False,steps=[],checks=[])
        result=self.execute()
        self.assertEqual(result["runs"][0]["status"],"pending")
        self.assertEqual(result["runs"][0]["steps"],[])
        self.assertEqual(result["summary"]["offline_gate"],"incomplete")

    def test_agent_rule_failure_remains_non_gating_recommendation(self):
        self.case["contract"]["owner"]="agent"
        self.case["steps"][0]["argv"][-1]="bad"
        result=self.execute()
        self.assertEqual(result["runs"][0]["status"],"fail")
        self.assertFalse(result["runs"][0]["gating"])
        self.assertEqual(result["summary"]["offline_gate"],"incomplete")
        self.assertEqual(result["findings"][0]["classification"],"recommendation-review")
        self.assertEqual(result["summary"]["advisory_case_counts"]["fail"],1)
        self.assertEqual(result["summary"]["gating_case_counts"]["fail"],0)

    def test_operator_diagnosis_is_labelled_unverified(self):
        self.case["steps"][0]["argv"][-1]="bad"
        self.case["diagnosis"]={"hypothesis":"Could be squaring.","confidence":"medium","repair":"Inspect the transform.","regression":"Retain input 4."}
        finding=self.execute()["findings"][0]
        self.assertEqual(finding["root_cause"]["status"],"not-established")
        self.assertIn("operator",finding["root_cause"]["source"])
        self.assertFalse(finding["repair_verified"])

    def test_clean_child_environment_and_task_home(self):
        from unittest import mock
        self.case["steps"][0]["argv"][-1]="environment"
        self.case["checks"]=[{"id":"env","type":"json-value","path":"result.json","expected":{"secret_absent":True,"home_local":True}}]
        with mock.patch.dict(os.environ,{"QA_SECRET":"not-a-real-secret"}):
            result=self.execute()
        self.assertEqual(result["runs"][0]["status"],"pass")
        self.assertEqual(result["runs"][0]["process_environment"]["inherited_names"],[])
        self.assertFalse((self.root/"out/runs/normal-r1/.home").exists())

    def test_symlink_artifact_cannot_be_graded(self):
        self.case["steps"][0].update(argv=["python","{skill}/scripts/run.py","link",str(self.suite_path)])
        del self.case["steps"][0]["stdout_artifact"]
        self.assertEqual(self.execute()["runs"][0]["status"],"fail")

    def test_outputs_root_link_is_not_dereferenced_by_evaluator(self):
        self.case["steps"][0].update(argv=["python","{skill}/scripts/run.py","outputs-link",str(self.plan)])
        del self.case["steps"][0]["stdout_artifact"]
        with self.assertRaises(v.ContractError):self.execute()
        self.assertFalse((self.root/"out/results.json").exists())

    def test_unavailable_requested_boundary_blocks_without_fallback(self):
        self.config["filesystem_isolation"]={"mode":"macos-sandbox" if sys.platform!="darwin" else "linux-bwrap"}
        result=self.execute()
        self.assertEqual(result["runs"][0]["status"],"blocked")
        self.assertEqual(result["runs"][0]["steps"],[])

    def test_strict_json_and_duplicate_yaml(self):
        output=self.root/"artifacts";output.mkdir()
        for text in ('{"x":1,"x":2}','{"x":NaN}','{bad'):
            (output/"bad.json").write_text(text)
            self.assertEqual(o.check_artifact({"id":"json","type":"json-valid","path":"bad.json"},output)["status"],"fail")
        (output/"good.json").write_text('{"x":1}')
        self.assertEqual(o.check_artifact({"id":"json","type":"json-valid","path":"good.json"},output)["status"],"pass")
        (output/"bad.yaml").write_text('x: 1\nx: 2\n')
        expected="fail" if importlib.util.find_spec("yaml") else "blocked"
        self.assertEqual(o.check_artifact({"id":"yaml","type":"yaml-valid","path":"bad.yaml"},output)["status"],expected)

    @unittest.skipUnless(importlib.util.find_spec("PIL"),"Pillow unavailable")
    def test_image_checks_use_decoded_pixels_and_real_alpha(self):
        from PIL import Image
        output=self.root/"images";output.mkdir()
        Image.new("RGBA",(8,8),(255,0,0,255)).save(output/"one.png")
        Image.new("RGBA",(8,8),(0,255,0,255)).save(output/"two.png")
        Image.new("RGBA",(8,8),(255,0,0,255)).save(output/"same.png")
        base={"id":"pixels","type":"image-compare","path":"one.png","other":"two.png","expected":False}
        self.assertEqual(o.check_artifact(base,output)["status"],"pass")
        base.update(other="same.png",expected=True)
        self.assertEqual(o.check_artifact(base,output)["status"],"pass")
        self.assertEqual(o.check_artifact({"id":"alpha","type":"image-property","path":"one.png","property":"meaningful-alpha","expected":True},output)["status"],"fail")

    def test_invalid_contracts_reject_before_execution(self):
        changes=[lambda c:c.update(unknown=1),lambda c:c["steps"][0].update(timeout_seconds=float("nan")),
                 lambda c:c["steps"][0].update(expected_exit=True),lambda c:c["checks"][0].update(path="../oracle"),
                 lambda c:c["contract"].update(owner="guessed"),lambda c:c["checks"][0].update(type="shell-command")]
        changes.append(lambda c:c["checks"][0].update(id="step-run"))
        for change in changes:
            suite=copy.deepcopy(self.suite)
            change(suite["cases"][0])
            with self.subTest(suite=suite),self.assertRaises(v.ContractError):
                o.validate(suite,self.plan)

    def test_offline_cannot_enable_network(self):
        self.config["filesystem_isolation"]={"mode":"macos-sandbox","allow_network":True}
        with self.assertRaises(v.ContractError):o.config(self.config)

    def test_manual_review_binds_original_artifact_and_keeps_history(self):
        self.case["checks"].append({"id":"review","type":"manual","path":"result.json","rubric":"Independently inspect the JSON contract."})
        result=self.execute()
        self.assertEqual(result["runs"][0]["status"],"pending")
        artifact=self.root/"out/runs/normal-r1/outputs/result.json"
        reviews=[{"case_id":"normal","repeat":1,"check_id":"review","status":"pass","reviewer":"offline unit fixture",
                  "method":"synthetic review binding test","timestamp":"2026-10-31","evidence":"Reviewed frozen fixture.","artifact_sha256":v.digest(artifact)}]
        path=self.root/"review.json";v.write_json(path,reviews)
        reviewed=o.review(argparse.Namespace(workspace=str(self.root/"out"),reviews=str(path)))
        self.assertEqual(reviewed["runs"][0]["status"],"pass")
        self.assertTrue((self.root/"out/results.pre-review.json").exists())

    def test_edited_artifact_cannot_attach_to_old_review(self):
        self.case["checks"]=[{"id":"review","type":"manual","path":"result.json","rubric":"Review raw output."}]
        self.execute()
        artifact=self.root/"out/runs/normal-r1/outputs/result.json";artifact.write_text("changed")
        path=self.root/"review.json"
        v.write_json(path,[{"case_id":"normal","repeat":1,"check_id":"review","status":"pass","reviewer":"test","method":"test","timestamp":"now","evidence":"test","artifact_sha256":v.digest(artifact)}])
        with self.assertRaises(v.ContractError):o.review(argparse.Namespace(workspace=str(self.root/"out"),reviews=str(path)))
        self.assertFalse((self.root/"out/results.pre-review.json").exists())

    def test_init_inventory_does_not_execute_and_drafts_stay_disabled(self):
        (self.skill/"scripts/bad.py").write_text('def broken(:\n')
        result=o.init(argparse.Namespace(skill=str(self.skill),out=str(self.root/"draft"),profile="code"))
        suite=v.read_json(self.root/"draft/suite.json")
        self.assertEqual(result["executed"],0)
        self.assertTrue(all(c["enabled"] is False for c in suite["cases"]))
        inventory=v.read_json(self.root/"draft/inventory.json")
        self.assertEqual(inventory["python_syntax"][0]["status"],"fail")

    @unittest.skipUnless(sys.platform=="darwin" and os.environ.get("SKILL_VERIFIER_TEST_SANDBOX")=="1","Native macOS boundary requires opt-in")
    def test_native_boundary_denies_original_suite(self):
        self.config["filesystem_isolation"]={"mode":"macos-sandbox","allow_network":False}
        self.case["steps"][0]["argv"]=["python","{skill}/scripts/run.py","oracle",str(self.suite_path)]
        self.case["checks"]=[{"id":"denied","type":"json-value","path":"result.json","pointer":"/denied","expected":True}]
        result=self.execute()
        self.assertEqual(result["runs"][0]["filesystem_isolation"]["status"],"enforced")
        self.assertEqual(result["summary"]["offline_gate"],"pass")
        proof=result["runs"][0]["filesystem_isolation"]["private_file_identity"]
        self.assertTrue(proof["verified_after_probe"] and proof["verified_after_task"])

    @unittest.skipUnless(sys.platform=="darwin" and os.environ.get("SKILL_VERIFIER_TEST_SANDBOX")=="1","Native macOS boundary requires opt-in")
    def test_native_presence_only_remains_incomplete(self):
        self.config["filesystem_isolation"]={"mode":"macos-sandbox","allow_network":False}
        self.case["checks"]=[{"id":"present","type":"exists","path":"result.json"}]
        result=self.execute()
        self.assertEqual(result["runs"][0]["filesystem_isolation"]["status"],"enforced")
        self.assertEqual(result["summary"]["offline_gate"],"incomplete")


if __name__=="__main__":unittest.main()
