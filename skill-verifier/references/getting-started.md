# First use

The portable entrypoint is `SKILL.md`; copy the entire skill directory. Host-specific UI metadata is optional. Python 3.9+ runs the core; no account or model SDK is required for local QA.

## Ask your agent

```text
Use skill-verifier to audit the skill at <absolute target directory>.
Start offline: inspect its contract and scripts, prepare task-specific cases,
execute only reviewed local operations, and deliver evidence, repair suggestions
and untested scope. Do not call models or external accounts or modify the target.
```

Resolve helper paths relative to the loaded skill, not a guessed global install directory. Run `offline-init` for a target inventory and disabled drafts, review them, then `offline-validate` and `offline-run`. Read [offline QA](offline.md) before configuring tools or isolation. An arbitrary target still needs an appropriate task contract; no generic template guarantees coverage.

If the target has no supported helpers under `scripts/`, auto starts with source-document review. Audit its package, links, templates and written contracts; do not invent CLI tests. Generated website/artifact behavior, native activation and cross-harness results remain untested without actual execution evidence. A local pass keeps `whole_skill_verdict: not-assessed`.

## Model-free example

From the repository root:

```bash
python3 skill-verifier/scripts/demo.py --out /tmp/skill-verifier-clean
python3 skill-verifier/scripts/demo.py --out /tmp/skill-verifier-defect --scenario defect
python3 skill-verifier/scripts/demo.py --out /tmp/skill-verifier-blocked --scenario blocked
```

For an installed skill, substitute its actual directory. Each output directory must be new. The clean case doubles integers, the defect squares them, and the blocked case deliberately has no interpreter. Inspect `evidence/report.md`, `results.json`, `findings.json` and `coverage.json`.

On a host with a usable boundary, clean should exit 0/pass; defect exits 1/fail; unavailable dependencies or boundaries exit 2/incomplete. `--isolation none` is diagnostic and cannot claim a full pass even if all artifact assertions pass. If the host cannot start a requested sandbox, the demo remains blocked rather than falling back. Exit 3 means invalid setup.

The demo config adds only the selected Python's standard-library/shared-library paths. For a real target, explicitly configure its actual runtime and review every readable path and staged file. Do not solve missing access by granting a home/project tree. Optional full YAML checks need PyYAML; pixel checks need Pillow. Missing optional check dependencies stay blocked. Installation does not install those dependencies automatically.

## Scope

The current independently validated core covers macOS offline execution. Generic installation and instruction portability do not establish native activation or task quality in Codex, Claude, Cursor, OpenCode or Gemini. Real-model comparisons, native discovery, Linux enforcement and external services need their own evidence. See [harness adaptation](harnesses.md) and [report policy](report-and-repair.md).
