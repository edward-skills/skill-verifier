# Offline command and artifact QA

Use this mode for a target's local helpers or existing artifacts, without agent CLIs or model-gain claims. The runner executes only configured commands and does not set up model sessions. Read target scripts before enabling steps; suites and tool configuration are evaluator-owned executable material. Avoid network-dependent tools and external accounts in this mode.

## Start with a directory

```text
verifier.py offline-init --skill TARGET --profile auto --out NEW_PLAN
verifier.py offline-validate PLAN/suite.json
verifier.py offline-run --skill TARGET --suite PLAN/suite.json --config PLAN/config.json --runtime-manifest PLAN/runtime-proposal.json --out NEW_EVIDENCE --repeats 1
verifier.py offline-review EVIDENCE --reviews REVIEWS_JSON
```

Initialization inventories scripts, parses Python syntax without executing it, proposes a task profile, and writes disabled CLI-help and domain cases. Review `inventory.json` syntax findings as well as `lint`; these are not silently folded into an execution score. Confirm the profile; auto selection is only a text heuristic. Add real inputs, steps and independent assertions; enable applicable cases and remove explicitly inapplicable proposals with an explanation in the QA report. A disabled draft stays pending and prevents a passing offline gate.

Review every file in `runtime-proposal.json` before using it. It proposes the package files except excluded eval/test/cache files; this is not evidence that their content is safe or free of answers. Prune evaluation material wherever it is named. Only the explicit manifest stages files beyond `SKILL.md`; omitting it stages no helper scripts. Do not place expected answers in inputs, tool prefixes or staged runtime resources.

The profile catalog covers code, data, media, documents, and recorded automation. Profiles are starting points, not universal assertions. For research/advisory skills use frozen inputs and a task-specific semantic rubric; browsing freshness remains outside offline coverage. `examples/offline/code-suite.json` illustrates a concrete data assertion but remains disabled until adapted to the actual target CLI.

The concrete `examples/offline/avatar-suite.json` exercises local `produce-avatar-ip-system` 1.2.0 helpers using synthetic files. Its `avatar-runtime.json` contains the exact reviewed scripts/templates; inspect before reusing against a different revision. `avatar-config.json` is a portable diagnostic starter: select an existing Python with Pillow, configure child PATH for FFmpeg and narrow sandbox read grants as applicable. It is not a claim that those dependencies exist on another host. Dependency preconditions prevent missing imports from masquerading as a successful rejection. The suite deliberately catches known defects in the unmodified target; it is not expected to be all green. No character artwork, image model or Figma operation is involved.

## Suite contract

```json
{
  "schema_version": 1, "kind": "offline", "name": "real CLI test",
  "cases": [{
    "id": "normal", "profile": "data", "description": "Check a documented transform.",
    "contract": {"owner":"script", "strength":"required", "basis":"State the actual CLI requirement and its source."},
    "inputs": [{"source":"files/input.json", "dest":"input.json"}],
    "steps": [{"id":"run", "argv":["python", "{skill}/scripts/transform.py", "{inputs}/input.json"], "stdout_artifact":"result.json"}],
    "checks": [{"id":"value", "type":"json-value", "path":"result.json", "pointer":"/result", "expected":8}]
  }]
}
```

Each step's first argv item is an operator-configured tool alias. Further arguments replace only `{work}`, `{skill}`, `{inputs}`, `{outputs}`. No shell expansion occurs. Unknown tools block. Helpers share one disposable cwd within a case; each case/repetition gets a fresh cwd. All compared artifacts must be under outputs; stdout/stderr can be copied there using `stdout_artifact`/`stderr_artifact`. Original logs live outside task-readable evidence in enforced mode.

`expected_exit` defaults to `[0]`; specify an integer list or `"nonzero"` for a documented rejection. A timeout, signal, unavailable tool or failed isolation never satisfies expected nonzero. Unexpected task exit fails the observed step; failed `role:"precondition"` blocks the case. Declare `requires_tools` for dependencies that must exist before execution. Failures stop dependent steps, preserve the first failure, and retain remaining checks as blocked. All planned cases/repetitions remain in results.

`contract.owner`: script, artifact, agent, or environment. `strength`: required or recommendation. Only required script/artifact cases gate local correctness. For example, a reference rule addressed to the agent may motivate a helper validation recommendation; it does not prove a script violated its own contract. Contract basis and ownership are operator interpretations, recorded for review rather than certified automatically.

Optional `diagnosis` has `hypothesis`, low/medium/high `confidence`, `repair`, and `regression`. Reports label it as an operator-authored hypothesis and leave root cause unestablished and repair unverified. The runner supplies linked observations even without diagnosis; it does not invent causal certainty.

## Checks and evidence

All existing artifact checks are supported. Additional independent checks:

| Type | Extra fields | Outcome |
| --- | --- | --- |
| json-valid | none | Strict JSON parse; duplicate keys and non-finite numbers reject |
| yaml-valid | none | Full YAML parse with duplicate-key rejection; missing optional PyYAML blocks |
| image-property | property: size or meaningful-alpha; expected | Inspect pixels with optional Pillow; missing Pillow blocks |
| image-compare | other; expected boolean | Equality of decoded RGBA dimensions/pixels, not file metadata |
| directory-count | expected integer | Count regular files recursively; reject symlinks |

Check paths are relative to outputs. `manual` remains pending until a review bound to the original artifact hash is imported. Offline review fields match online reviews except there is no configuration field; include case_id, repeat, check_id, status, reviewer, method, timestamp, evidence, artifact_sha256. An import cannot override deterministic failures, resolve blocked executions, replace artifacts or erase earlier results. Only one atomic import per workspace is supported.

Image alpha is a technical property; it cannot establish clean edges, identity, readable text or aesthetics. Add actual rendered review. Syntax validity cannot establish factual correctness. A required case with only exit codes/file existence cannot produce a passing offline gate. Independent manual review can establish a declared semantic check, within its rubric and actual reviewer evidence.

## Trusted tools and isolation

Config contains schema_version, name, tools, filesystem_isolation, and optional process_environment. Tools map aliases to argv prefixes, e.g. `"python":["/absolute/venv/bin/python"]`. Prefixes are executable code under operator control; no target-provided or automatically guessed wrapper is trusted. Record any interpreter bootstrap or dependency paths explicitly. Prefer a configured existing venv to broad project-directory grants; never import host login state.

The runner reuses 0.2.1's clean environment, task-local HOME/cache/temp, narrow Python/venv grants, and live oracle-denial probe. Explicitly configure required runtime directories, executables and child PATH directories. Offline config rejects allow_network=true. Under mode none, no filesystem/network enforcement is claimed; all successes remain diagnostic and the offline gate is incomplete. A requested sandbox that cannot start blocks without fallback. Linux backend availability still requires Linux-host validation.

Version 0.3.1 additionally rejects hard-linked declared oracle files before the probe, and verifies their identity/content after the probe and task. A runtime hardlink alias must not yield an enforced/pass result. If this check fails, remove oracle aliases and use clean evaluator-owned files; do not relax runtime grants or fall back to mode none as a passing result. See the [runner boundary contract](runner.md) for the precise scope: independent answer copies and concurrent privileged changes are not certified by this check.

`offline-run` exits: 0 local offline gate pass, 1 observed gating failure, 2 incomplete, 3 invalid setup. A passing offline gate additionally requires an enforced/probed boundary, complete required correctness checks and no disabled drafts. It does not establish universal skill quality, native activation, model effect, other harnesses, remote tool isolation or authorization behavior.

## Report files

`manifest.json` records target/staged fingerprints, suite/config/runtime hashes, fixtures and replay argv. `runs/CASE-rN/` retains original step logs, execution records, post-run outputs, probe evidence, grades and environment variable names only. Task home and temporary state are not archived. `results.json`, `findings.json`, `coverage.json` and `report.md` keep observations, contract interpretation, hypotheses and proposed repair separate. Original sources/fixtures are checked for mutation. Counts measure this suite, not a universal percentage of skill quality. `lint` remains a separate check.
