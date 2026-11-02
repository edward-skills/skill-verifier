# Validation and compatibility

## Frozen core evidence

Independent macOS offline QA accepted core 0.3.1 on 2026-11-02: 94 tests passed without skips, plus separately authored hardlink probes. The original reviewed archive SHA-256 was `cbceadc4023db2235b5bbfa2c46ed1cd227459bf313a638428c1ed93c52d8d83`.

It established command/plan handling, artifact checks, evidence states, environment allowlisting, venv layouts, oracle-denial probes, hardlink rejection and post-execution identity checks. It did not establish model uplift, native skill discovery, cross-harness behavior or Linux enforcement. Public summaries omit local paths and private raw logs.

## Distribution 0.3.2

This version adds packaging, rights notices, installation documentation and a synthetic no-account demo. Evaluator algorithms are unchanged from 0.3.1 except the version identifier. Public distribution checks include package lint, offline regression, demo controls and installation using the pinned `skills` CLI; CI is the current record of repository checks. No new independent QA acceptance of 0.3.2 is implied.

| Surface | Supported claim | Unverified |
| --- | --- | --- |
| Codex | Portable entrypoint; CLI adapter recipe; installer target | Native activation and real model tasks |
| Claude Code | Portable entrypoint; CLI adapter recipe; installer target | Native activation and real model tasks |
| Gemini CLI | Portable entrypoint; CLI adapter recipe; installer target | Native activation and real model tasks |
| Cursor | Portable instructions and installer target | Agent execution and native activation |
| OpenCode | Portable instructions and installer target | Agent execution and native activation |
| macOS | Independent offline core QA; sandbox-exec | Arbitrary host/provider setup |
| Linux | Portable Python core and optional bubblewrap implementation | Enforced backend behavior until tested on a compatible host |
| Windows / chat-only hosts | Manual workflow or diagnostic adaptation | Bundled enforced execution |

Installer tests are performed in fresh temporary projects with copied files and isolated home state. They verify discovery and package contents, without launching any agent model or changing global agent configuration.

Author distribution checks on 2026-11-02 reproduced all 94 tests without skips on macOS. The model-free clean/defect/blocked controls returned pass/fail/incomplete respectively. `skills` CLI 1.7.2 copy-installed the local source for all five listed agent targets; all 40 package files matched their source hashes. This is installer evidence, not real agent execution or native activation.

## Run checks

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-test.txt
python scripts/validate_repository.py
python -m unittest discover -s skill-verifier/tests -v
```

Default test discovery may skip native macOS or optional-library checks. Only a log with zero skipped checks supports the full-test claim. On macOS, select a trusted existing interpreter that can create copied venvs:

```bash
SKILL_VERIFIER_TEST_SANDBOX=1 SKILL_VERIFIER_COPY_PYTHON=/absolute/python/bin/python3 python -m unittest discover -s skill-verifier/tests -v
```

The copy interpreter is a test dependency, not permission to read its entire project. The verifier still uses the base probe and narrow grants. CI uses a system-base driver venv for native checks; setup-python provides the copied interpreter separately. Missing backend capability fails/blocks the native job rather than silently dropping the boundary.

## Remaining scope

Ordinary answer copies are outside hardlink identity detection and must be removed during runtime-content review. Privileged concurrent evaluator/runtime tampering is not certified race-free. A local filesystem boundary does not certify remote tools. A rendered or semantic quality claim needs actual artifact review; synthetic rectangles and constant videos establish technical behavior only.
