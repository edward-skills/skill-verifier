"""Oracle identity regressions; test data and links remain in temporary directories."""
import argparse
import hashlib
import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

SPEC = importlib.util.spec_from_file_location("verifier_hardlink_tests", Path(__file__).parents[1] / "scripts/verifier.py")
v = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(v)


class HardlinkGuardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.oracle = self.root / "suite.json"
        self.oracle.write_text('{"synthetic_expected":431}\n')
        self.runtime = self.root / "runtime"
        self.runtime.mkdir()

    def tearDown(self):
        self.temp.cleanup()

    def boundary(self):
        return {"mode":"macos-sandbox","status":"enforced","private_file_identity":{
            "policy":"single-link-v1","files":v.isolation.private_file_records([self.oracle])}}

    def test_regular_oracle_records_identity_and_content_hash(self):
        records=v.isolation.private_file_records([self.oracle])
        self.assertEqual(records[0]["links"],1)
        self.assertEqual(records[0]["sha256"],hashlib.sha256(self.oracle.read_bytes()).hexdigest())
        v.isolation.verify_private_files(self.boundary())

    def test_preexisting_hardlink_is_rejected_even_under_another_name(self):
        os.link(self.oracle,self.runtime/"unrelated-name.dat")
        with self.assertRaisesRegex(v.isolation.IsolationError,"Hard-linked private oracle"):
            v.isolation.private_file_records([self.oracle])

    def test_nested_alias_is_rejected_without_runtime_tree_scanning(self):
        folder=self.runtime/"sub/deeper";folder.mkdir(parents=True)
        os.link(self.oracle,folder/"cached-resource.bin")
        with self.assertRaises(v.isolation.IsolationError):v.isolation.private_file_records([self.oracle])

    def test_independent_regular_copy_is_not_a_hardlink(self):
        copy=self.runtime/"copy.bin";copy.write_bytes(self.oracle.read_bytes())
        self.assertNotEqual(copy.stat().st_ino,self.oracle.stat().st_ino)
        self.assertEqual(v.isolation.private_file_records([self.oracle])[0]["links"],1)

    def test_unrelated_runtime_hardlinks_do_not_block_a_clean_oracle(self):
        binary=self.runtime/"binary";binary.write_bytes(b"benign-runtime")
        os.link(binary,self.runtime/"binary-alias")
        v.isolation.verify_private_files(self.boundary())

    def test_symlink_cannot_be_an_oracle_identity_proof(self):
        alias=self.root/"oracle-link";alias.symlink_to(self.oracle)
        with self.assertRaises(v.isolation.IsolationError):v.isolation.private_file_records([alias])

    def test_changed_content_invalidates_postcondition(self):
        boundary=self.boundary()
        self.oracle.write_text('{"synthetic_expected":999}\n')
        with self.assertRaises(v.isolation.IsolationError):v.isolation.verify_private_files(boundary)

    def test_replaced_file_with_same_bytes_invalidates_identity(self):
        boundary=self.boundary()
        replacement=self.root/"replacement";replacement.write_bytes(self.oracle.read_bytes())
        os.replace(replacement,self.oracle)
        with self.assertRaises(v.isolation.IsolationError):v.isolation.verify_private_files(boundary)

    def test_link_added_after_probe_invalidates_postcondition(self):
        boundary=self.boundary()
        os.link(self.oracle,self.runtime/"late-alias")
        with self.assertRaises(v.isolation.IsolationError):v.isolation.verify_private_files(boundary)

    def test_enforced_boundary_requires_identity_records(self):
        with self.assertRaises(v.isolation.IsolationError):
            v.isolation.verify_private_files({"mode":"macos-sandbox","status":"enforced"})

    def test_hardlink_rejected_before_probe_process_can_start(self):
        os.link(self.oracle,self.runtime/"alias")
        work=self.root/"work";work.mkdir()
        logs=self.root/"logs";logs.mkdir()
        with mock.patch.object(v.isolation.subprocess,"run") as launch:
            with self.assertRaises(v.isolation.IsolationError):
                v.isolation.probe([], {"mode":"macos-sandbox","status":"unverified"},work,[self.oracle],logs,{}, {"executable":sys.executable})
            launch.assert_not_called()

    def test_diagnostic_mode_does_not_claim_hardlink_isolation(self):
        os.link(self.oracle,self.runtime/"alias")
        result=v.isolation.probe([], {"mode":"none","status":"unverified"},self.root,[self.oracle],self.root,{},None)
        self.assertEqual(result["status"],"unverified")
        self.assertNotIn("private_file_identity",result)


@unittest.skipUnless(sys.platform=="darwin" and os.environ.get("SKILL_VERIFIER_TEST_SANDBOX")=="1","Native macOS integration requires opt-in")
class HardlinkRunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name).resolve()
        self.skill=self.root/"sample-skill";(self.skill/"scripts").mkdir(parents=True)
        (self.skill/"SKILL.md").write_text("---\nname: sample-skill\ndescription: Synthetic offline isolation regression.\n---\nRun the local fixture.\n")
        (self.skill/"scripts/read.py").write_text('import pathlib,json,sys\np=json.loads(pathlib.Path(sys.argv[1]).read_text())\nprint(json.dumps({"copied":p["cases"][0]["checks"][0]["expected"]}))\n')
        self.sources=self.root/"sources";self.sources.mkdir()
        self.runtime=self.root/"runtime";self.runtime.mkdir()
        self.suite_path=self.sources/"suite.json"
        self.alias=self.runtime/"alias.bin"
        self.case={"id":"copy","profile":"code","description":"Known oracle-copy negative control.",
            "contract":{"owner":"script","strength":"required","basis":"Oracle copies cannot establish isolated correctness."},
            "steps":[{"id":"read","argv":["python","{skill}/scripts/read.py",str(self.alias)],"stdout_artifact":"result.json"}],
            "checks":[{"id":"copied","type":"json-value","path":"result.json","pointer":"/copied","expected":431}]}
        v.write_json(self.suite_path,{"schema_version":1,"kind":"offline","name":"hardlink negative control","cases":[self.case]})
        os.link(self.suite_path,self.alias)
        self.manifest=self.root/"runtime-manifest.json"
        v.write_json(self.manifest,{"schema_version":1,"candidate":["scripts/read.py"],"baseline":[]})

    def tearDown(self):self.temp.cleanup()

    def execute(self,name,grant):
        config=self.root/(name+".json")
        v.write_json(config,{"schema_version":1,"name":"hardlink-native","tools":{"python":[sys.executable]},
            "filesystem_isolation":{"mode":"macos-sandbox","allow_network":False,"readable_paths":[str(grant)]}})
        return v.offline_module().run(argparse.Namespace(skill=str(self.skill),suite=str(self.suite_path),config=str(config),
            runtime_manifest=str(self.manifest),out=str(self.root/name),repeats=1))

    def assert_blocked(self,result):
        row=result["runs"][0]
        self.assertEqual(result["summary"]["offline_gate"],"incomplete")
        self.assertEqual(row["status"],"blocked")
        self.assertNotEqual(row["filesystem_isolation"]["status"],"enforced")
        self.assertEqual(row["steps"],[])
        self.assertIn("Hard-linked private oracle",row["grades"][0]["evidence"])

    def test_offline_literal_alias_grant_cannot_pass(self):
        self.assert_blocked(self.execute("literal",self.alias))

    def test_offline_recursive_runtime_alias_cannot_pass(self):
        self.assert_blocked(self.execute("directory",self.runtime))

    def test_post_task_alias_invalidates_previously_enforced_boundary(self):
        self.alias.unlink()
        (self.skill/"scripts/read.py").write_text('import json\nprint(json.dumps({"copied":431}))\n')
        module=v.offline_module()
        execute=module.execute_step
        def mutate_after_step(*args,**kwargs):
            record=execute(*args,**kwargs)
            os.link(self.suite_path,self.alias)
            return record
        config=self.root/"postcondition-config.json"
        v.write_json(config,{"schema_version":1,"name":"postcondition-fixture","tools":{"python":[sys.executable]},
            "filesystem_isolation":{"mode":"macos-sandbox","allow_network":False,"readable_paths":[str(self.runtime)]}})
        with mock.patch.object(module,"execute_step",side_effect=mutate_after_step):
            result=module.run(argparse.Namespace(skill=str(self.skill),suite=str(self.suite_path),config=str(config),
                runtime_manifest=str(self.manifest),out=str(self.root/"postcondition"),repeats=1))
        self.assertEqual(result["summary"]["offline_gate"],"incomplete")
        self.assertEqual(result["runs"][0]["status"],"blocked")
        self.assertEqual(result["runs"][0]["filesystem_isolation"]["status"],"unverified")

    def test_online_comparison_alias_cannot_pass(self):
        self.alias.unlink()
        suite={"schema_version":1,"name":"paired negative control","cases":[{"id":"copy","profile":"data","prompt":"Emit local JSON.",
            "response_artifact":"result.json","checks":[{"id":"copied","type":"json-value","path":"result.json","pointer":"/copied","expected":431}]}]}
        v.write_json(self.suite_path,suite)
        os.link(self.suite_path,self.alias)
        adapter=self.root/"adapter.json"
        v.write_json(adapter,{"schema_version":1,"name":"deterministic-copy-fixture","argv":[sys.executable,str(self.skill/"scripts/read.py"),str(self.alias)],
            "response":"stdout","environment":{"model":"synthetic-only","harness_version":"fixture-1","settings":"no model/network"},
            "baseline_isolation":{"status":"verified","evidence":"Synthetic fixture has no native skill loader."},
            "filesystem_isolation":{"mode":"macos-sandbox","allow_network":False,"readable_paths":[str(self.skill/"scripts/read.py"),str(self.alias)]}})
        # The adapter source grant is intentionally outside the target supplied to the runner.
        target=self.root/"empty-skill";target.mkdir()
        (target/"SKILL.md").write_text("---\nname: empty-skill\ndescription: Deterministic comparison fixture.\n---\nEmit JSON.\n")
        result=v.run_suite(argparse.Namespace(skill=str(target),suite=str(self.suite_path),adapter=str(adapter),out=str(self.root/"paired"),baseline_skill=None,runtime_manifest=None,repeats=1))
        self.assertEqual(result["summary"]["comparison_gate"],"incomplete")
        self.assertTrue(all(r["status"]=="blocked" and r["execution"]["returncode"] is None for r in result["runs"]))


if __name__=="__main__":unittest.main()
