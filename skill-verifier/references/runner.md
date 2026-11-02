# Runner contract v1 / checker 0.3.2

For local helper scripts without a model, use [offline command QA](offline.md). Existing model-comparison contracts and 0.2.1 environment/isolation protections remain supported.

`scripts/verifier.py` and its sibling `isolation.py` use Python 3.9+ standard library. No model API, vendor SDK, or service account is bundled. The runner executes a trusted adapter with `shell=False`. Optional PyYAML enables full frontmatter parsing; the dependency-free subset still rejects duplicate top-level keys. Do not install dependencies silently.

## Commands and exits

```text
verifier.py lint SKILL_FOLDER [--out lint.json]
verifier.py validate SUITE_JSON
verifier.py grade SUITE_JSON --case CASE_ID --outputs ARTIFACT_FOLDER [--out grading.json]
verifier.py run --skill SKILL_FOLDER --suite SUITE_JSON --adapter ADAPTER_JSON --out NEW_FOLDER [--baseline-skill OLD_FOLDER] [--runtime-manifest RUNTIME_JSON] [--repeats 1]
verifier.py review WORKSPACE --reviews REVIEW_JSON
```

`run`/`review` exits: 0 comparison pass, 1 observed failure, 2 incomplete, 3 invalid contract/setup. `lint` exits: 0 pass, 1 fail, 2 review warnings, 3 contract/setup error. Version 0.2 deliberately stops returning exit zero for `review`; callers should inspect the JSON status as well. Linting checks a static subset, not Python/script syntax or behavior. Inline/fenced/indented code links are not package dependencies; real prose links are checked. Names accept Unicode lowercase letters/digits; case/check IDs remain ASCII.

`run` does not automatically incorporate lint into its comparison gate; include both in the final QA decision.

`grade` independently checks existing artifacts for one case, without launching a model or adapter. It uses the same checkers and exits 0 pass, 1 fail, 2 pending/blocked, 3 contract error. Save grading outside the artifact directory. This establishes artifact QA only; it does not establish how the artifact was produced.

Every run needs a new output folder outside target and suite/fixture trees. The live task directory is separately allocated under the OS temporary directory, rather than beneath evaluator `suite.json`. Only `SKILL.md` is staged by default; every additional runtime file requires an exact entry in the operator-reviewed manifest below. Files under `references/`, `examples/`, `assets/`, or arbitrary names are not copied implicitly. Top-level `evals`/`tests`, `.git`, caches, and symlinks cannot become runtime resources. Fixtures must contain legitimate task inputs, not private oracles. The runner rejects package/input/output symlinks and traversal paths.

An unsandboxed process with the same OS identity can still search the host. Thus moving files or declaring isolation verified never establishes isolation: mode `none` is diagnostic only, with maximum comparison result `incomplete`. A real backend must pass an evaluator-owned probe against the original suite, report copy, and private canary before task launch. Failure blocks execution without fallback. This local filesystem boundary does not certify remote tool servers, permissions to external apps, or an actively compromised evaluator process.

Before an enforced probe, declared private oracle files must be regular non-symlink files with exactly one hard link. The evaluator records device/inode, link count, size, modification/change timestamps and SHA-256, then rechecks after the probe and after the task. Pre-existing hardlinks reject before task launch, even if an alias is named differently or nested in a readable runtime directory. A failed postcondition invalidates enforcement and blocks grading. The policy conservatively rejects any multi-linked declared oracle, even if its alias is not currently readable. Use ordinary evaluator-owned copies and remove oracle aliases from runtime grants; do not bypass the check by replacing the original while retaining an answer copy.

This identity check covers the declared original suite, report suite and canary. It does not detect independent byte copies or certify the content of every runtime file. Operator-reviewed runtime resources and fixtures must still contain no grading answers. These checks do not claim race-free protection against a privileged external process modifying the evaluator or runtime while tasks run; such actors remain outside the supported threat model. Linux backend execution remains unverified.

## Runtime manifest

```json
{
  "schema_version": 1,
  "candidate": ["scripts/extract.py", "references/format.md"],
  "baseline": ["scripts/extract.py", "references/format.md"]
}
```

`SKILL.md` is implicit. Paths are exact files relative to the corresponding target, with no globs/directories. Missing or excluded paths reject setup. The manifest is evaluator-owned and its hash/file hashes are recorded. Review each included file for grading material; explicitly listing an answer file would intentionally disclose it. This is a content review requirement, not an inference from filenames. Omit the flag for self-contained single-file skills. An example for this verifier's own runtime resources is bundled under `examples/`.

The runner's automated scope is local artifact production. Prompts authorize only staged inputs and local outputs. Test real external operations or native skill selection through the host protocol, with the appropriate test environment and authorization. Task-specific tests, rendering tools, or semantic judges can run outside the task workspace and enter as independent manual reviews.

## Suite

```json
{
  "schema_version": 1,
  "name": "invoice extraction smoke",
  "cases": [{
    "id": "normal-invoice",
    "profile": "data",
    "tags": ["happy"],
    "prompt": "Read inputs/invoice.txt and return JSON with currency and total. Preserve stated currency and amount.",
    "inputs": [{"source": "files/invoice.txt", "dest": "invoice.txt"}],
    "response_artifact": "invoice.json",
    "checks": [{"id": "total", "type": "json-value", "path": "invoice.json", "pointer": "/total", "expected": 42}]
  }]
}
```

Sources resolve relative to the suite folder and must be existing files confined to it. Destinations resolve under the live task's `inputs/`; checks later inspect captured `work/outputs/`. IDs use ASCII lowercase letters/digits and single hyphens. Duplicate IDs, unknown fields, invalid counts, and checker-field mismatches are rejected before launch.

`response_artifact` saves final text as an artifact. Use it only for response-text/JSON tasks; omit it when the agent must create/edit files. The prompt does not include `checks`, expected values, the suite path, or opposing output. It includes the task, staged fixtures, output contract, and candidate entrypoint; explicitly allowlisted references reside under `skill/`. Filesystem enforcement is separately necessary to prevent reading evaluator data by path.

| Checker | Required extra fields | Meaning |
| --- | --- | --- |
| `exists` | optional `min_bytes` (default 1) | Regular file with at least N bytes; not a quality/content check |
| `json-value` | `expected`; optional `pointer` | Parse strict JSON, follow JSON Pointer (`""` = whole document), compare value/types; booleans are not 0/1 |
| `csv-rows` | integer `expected` | Data rows excluding one required header; require consistent column widths |
| `text-contains` | nonempty `text` | Case-sensitive exact substring; reserve for exact contractual text |
| `sha256` | lowercase 64-char `expected` | Exact byte integrity |
| `manual` | nonempty `rubric` | Require artifact and retain `pending` until an independent review is imported |

Each check accepts `severity`: `critical`, `major` (default), or `minor`; every declared check is an acceptance condition. Use advisory prose for non-gating suggestions. A case containing only `exists` checks withholds comparison pass because presence does not establish task correctness. Correctness checks alone cannot establish visual/semantic quality. Missing artifacts after successful execution fail; execution failures block checks. Strong assertions still cannot reveal cases absent from the suite; release coverage is a separate decision.

## Trusted adapter

```json
{
  "schema_version": 1,
  "name": "my-harness",
  "argv": ["my-agent", "--prompt-file", "{prompt_file}", "--response-file", "{response_file}"],
  "response": "file",
  "timeout_seconds": 180,
  "environment": {"harness_version": null, "model": null, "settings": null},
  "baseline_isolation": {"status": "unverified", "evidence": ""},
  "filesystem_isolation": {"mode": "none"},
  "process_environment": {"inherit": []}
}
```

The command receives a file-backed prompt on stdin and runs from the disposable `{work_dir}`. Supported argv placeholders: `{prompt_file}`, `{work_dir}`, `{response_file}`; prompt/response files are task-local. Inspect adapter configuration as executable code and never trust it merely because a target supplied it. No shell expansion, global configuration editing, model override, or automatic installation is performed.

## Environment allowlist

The task and probe never copy the parent environment wholesale, including in diagnostic mode `none`. Defaults synthesize task-local HOME, TMP/TEMP/TMPDIR and XDG config/cache/data/state directories, a system-default PATH, C locale, UTC timezone and safe Python UTF-8/no-user-site/no-bytecode flags. The temporary home is excluded from captured report files. The configured top-level executable is resolved before using the clean child PATH; helper executable directories must be supplied explicitly if necessary.

The optional operator-controlled setting below forwards exact names, not patterns, and adds explicit PATH directories:

```json
"process_environment": {
  "inherit": ["QA_PUBLIC_SETTING"],
  "path": ["/absolute/path/to/trusted/bin"]
}
```

Defaults inherit nothing. Missing requested names remain absent and are recorded. HOME/PATH/temp/XDG overrides, Python/loader startup variables, shell startup hooks, and similar reserved settings are rejected rather than silently overriding local state. Wildcards, duplicate names, unknown fields, and relative PATH entries are invalid. The boundary probe receives none of the task-only pass-through values. Execution metadata records generated/inherited/missing names and never serializes their values; it is not a general redactor for content a task chooses to print.

Inherited credentials require existing user authorization. This option does not authorize network access, account login, or external writes. A normally logged-in CLI may require explicit authorized configuration under the fresh HOME; host account state is not imported automatically.

## Python virtualenvs and probe selection

The boundary probe defaults to the running verifier's base interpreter (`sys._base_executable`, or the resolved executable), rather than the project venv path. It starts with `-I -S` and the clean probe environment. Thus a verifier launched from a project `.venv` need not expose that project's `pyvenv.cfg` merely to run the probe.

For an explicitly selected trusted interpreter, add an absolute `probe_python` path to `filesystem_isolation`:

```json
"filesystem_isolation": {
  "mode": "macos-sandbox",
  "readable_paths": ["/absolute/path/to/required/runtime/lib"],
  "probe_python": "/absolute/path/to/trusted/venv/bin/python",
  "allow_network": false
}
```

Selected Python executables and adjacent/parent `pyvenv.cfg` files receive narrow read grants. The same discovery supports a Python task executable in a symlink or copied venv. This does not grant the venv or enclosing project recursively. Non-system standard libraries, shared libraries, and task packages still need narrowly declared runtime read paths; no dependencies are installed. Missing interpreters, unavailable runtime dependencies, or grants overlapping private evaluator/target sources block execution without fallback. In particular, explicitly selecting a probe venv inside an oracle directory remains invalid; the default base probe avoids needing such a grant.

Per-run metadata records the selected probe/interpreter, selection source and config paths, without environment values. macOS system-Python project venvs, explicit probes, symlink task venvs and a standalone-Python copied task venv have offline regression evidence. Linux behavior and real harness execution remain unverified.

To request enforcement, replace diagnostic mode with a platform backend:

```json
"filesystem_isolation": {
  "mode": "macos-sandbox",
  "readable_paths": ["/absolute/path/to/required/runtime"],
  "allow_network": false
}
```

Modes: `none`, `macos-sandbox` (sandbox-exec), `linux-bwrap` (bubblewrap). Read grants must be narrow existing files/directories; grants overlapping evaluator or target sources are rejected. System runtime directories and task files are available. macOS grants ancestor directories literally for path resolution, with no recursive file-content grant. Writes are limited to task files and write-only stdout/stderr logs. Linux exposes read-only runtime mounts plus the task directory. Network is off by default; enabling it requires the task's existing authorization. This package does not install sandbox tools. The evaluator selects/builds the backend and verifies it; adapters cannot assert `enforced` themselves. The macOS backend has offline local regression evidence; Linux needs validation on a compatible host.

Response modes: `file`, `stdout`, `claude-json` (`result`), `gemini-json` (`response`). JSON error envelopes or missing response fields block execution even after exit zero. Envelopes on nonzero exits are also inspected, so Claude authentication details and usage in stdout are retained. Error messages point to both log files. Tools producing files still need a final response. Timeout kills the POSIX process group; Windows cleanup covers only the immediate process (no bundled Windows isolation backend).

Claude token totals use reported total, or known disjoint input/output/cache counters when present; reported USD cost is retained, including zero. Gemini retains reported token counters and its explicit total. Missing/unsupported usage remains `null`. Configuration totals aggregate only complete measured coverage and disclose observed-run counts. Provider counters are not assumed comparable across vendors; no cost is inferred from a price table.

Record `environment.harness_version`, `model`, and `settings` after verification. Empty identity prevents comparison pass. Optional `capabilities` describes tools/permissions/rendering. Metadata does not configure the process. `baseline_isolation` is only an attestation about native skill loading; it cannot establish filesystem isolation. Vendor example adapters remain diagnostic, with unknown identity and unverified baseline loading.

The runner counterbalances candidate/baseline order across cases/repeats. It does not guarantee cache or provider-state isolation. It preserves adapter failures as blocked runs without retry. A failed batch can leave `progress.json` and individual `run.json`; `results.json` is only produced for a completed planned batch.

## Result artifacts

```text
workspace/
  manifest.json, suite.json, adapter.json, runtime-manifest.json
  snapshots/candidate/          # baseline/ when comparing revisions
  runs/<case>-r<N>/<configuration>/
    prompt.txt, stdout.log, stderr.log, response.txt
    isolation-probe.json, isolation-probe.stdout.log, isolation-probe.stderr.log
    run.json
    work/inputs/, work/skill/, work/outputs/   # captured after execution, not the live cwd
  progress.json
  results.json, report.md
```

The manifest records runtime snapshot/fixture/manifest hashes, checker version, environment, baseline attestation and replay argv. `run.json` records actual filesystem enforcement/probe, selected Python/config files, environment variable names (not values), execution and artifact grades. Captures exclude task temporary directories and the generated home. Results retain planned counts, pairs, exclusions, regressions, repeat variation, and measured usage coverage. Baseline task failures are valid comparisons; blocked/pending baselines are incomplete evidence. Raw pairs/deltas from incomplete gates are diagnostic, not validated uplift. Generated reports contain observed evidence; the evaluator adds root-cause analysis and concrete repair recommendations.

## Independent review import

Use `review` once per completed workspace, after all relevant reviews are ready. The importer accepts only existing `manual` checks with completed execution and an artifact whose hash matches the review. It retains pre-review results/report, validates the whole import before changing files, then recomputes the gate. It cannot override deterministic failures or blocked executions.

The artifact must also match its hash recorded immediately after execution. Edited artifacts require a new run; a review cannot attach a new artifact to an old execution.

```json
[{
  "case_id": "normal-invoice", "repeat": 1, "configuration": "candidate",
  "check_id": "readability", "status": "pass",
  "reviewer": "independent reviewer identifier", "method": "rendered artifact against rubric",
  "timestamp": "2026-10-29T10:00:00Z",
  "evidence": "Artifact invoice.json uses the requested fields; supporting review at review/notes.md.",
  "artifact_sha256": "replace-with-observed-64-character-sha256"
}]
```

Use `pass`, `fail`, or `blocked`. Evidence is supplied by the reviewer; the importer verifies binding to the artifact, not whether the human/judge's interpretation is truthful. Keep the original review artifacts and method. Do not put a gold answer or grading record inside the task workspace.

## Demo scope

`examples/invoice-evals.json` contains three simple extraction cases: normal data, missing currency, and an injected vendor note. Its legitimate output requirements are present in both configurations. It is a plumbing example, not evidence that this small skill adds value beyond a competent model. Use representative harder tasks and holdouts to assess a production skill.
