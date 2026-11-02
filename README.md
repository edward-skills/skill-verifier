# Skill Verifier

Current version: **0.3.4**. Host adaptation separates package inspection, running the verifier and driving another agent. See [release notes](docs/releases/v0.3.4.md). Independent acceptance below applies to the frozen 0.3.2 release; later additions have separate author/CI evidence.

[All Skills](https://github.com/edward-skills) · [简体中文](README.zh-CN.md) · [Validation scope](docs/validation.md)

Test an agent skill against its actual contract, retain evidence, and propose fixes with regression checks. Start with local scripts and artifacts; use model comparisons only when separately configured and authorized.

**Public invocation-only distribution.** Install and invoke for your own or client work and use the resulting reports. Redistribution, resale and publication of modified skill packages are not authorized. [License](LICENSE.md).

## Install and invoke

With Node.js 22.20+:

```bash
npx skills add edward-skills/skill-verifier --skill skill-verifier
```

Choose your agent in the installer. To target one explicitly:

```bash
npx skills add edward-skills/skill-verifier --skill skill-verifier --agent codex
```

Then ask your agent:

```text
Use skill-verifier to audit the skill at <absolute target directory>.
Start offline. Inspect its scripts and contract, run relevant normal/edge/known-bad
cases, and give me the evidence, concrete repair suggestions and untested scope.
Do not call online models or external accounts or modify the target.
```

The complete installable package is [`skill-verifier/`](skill-verifier/). Manual installation copies that whole folder into a skill directory supported by your host. Installation does not install Python libraries or model CLIs.

## Try it without an account

Clone this repository and run with Python 3.9+:

```bash
git clone https://github.com/edward-skills/skill-verifier.git
cd skill-verifier
python3 skill-verifier/scripts/demo.py --out /tmp/skill-verifier-clean
```

Open the printed `evidence/report.md` path. Each run needs a new directory. Exercise a known defect or an unavailable dependency:

```bash
python3 skill-verifier/scripts/demo.py --out /tmp/skill-verifier-defect --scenario defect
python3 skill-verifier/scripts/demo.py --out /tmp/skill-verifier-blocked --scenario blocked
```

The defect deliberately squares 4 instead of doubling it and must fail. The blocked example must remain incomplete. A clean run can pass only with a working, probed filesystem boundary. With `--isolation none`, even successful assertions remain diagnostic/incomplete. A sandbox failure does not fall back to an ordinary process. See [first-use details](skill-verifier/references/getting-started.md).

## What it does

| Capability | Evidence retained |
| --- | --- |
| Static package/metadata/reference checks | Findings and YAML verification state |
| Directory inventory and five domain drafts | Python syntax checks; disabled cases requiring review |
| Declarative local commands and multi-step cases | Exit codes, stdout/stderr, timings, every repetition |
| JSON/YAML/CSV/text/hash/pixel checks | Independent artifact observations and hashes |
| Contract-aware triage and repair planning | Script/artifact requirements versus agent duties and suggestions |
| Human/semantic QA | Pending manual rubrics and artifact-bound review imports |
| Optional candidate/baseline adapters | Explicit CLI execution recipes and incomplete evidence handling |

Profiles cover code, data, media, documents and recorded automation. The full avatar example is a concrete local helper suite; domain drafts still need real inputs and assertions. The workflow also explains research/advisory grading with frozen sources and rubrics. It does not invent a universal quality score.

## Run on your target

```bash
python3 skill-verifier/scripts/verifier.py offline-init --skill /path/to/target --profile auto --out /tmp/target-plan
```

Review the source, contract owner, proposed profile, exact runtime files and command plan. Draft cases are disabled and never count as executed success. Add independent checks, configure trusted tools and a filesystem boundary, then:

```bash
python3 skill-verifier/scripts/verifier.py offline-validate /tmp/target-plan/suite.json
python3 skill-verifier/scripts/verifier.py offline-run --skill /path/to/target --suite /tmp/target-plan/suite.json --config /tmp/target-plan/config.json --runtime-manifest /tmp/target-plan/runtime-proposal.json --out /tmp/target-evidence
```

`runtime-proposal.json` is a proposal, not a safe-content certificate: prune answers and grading material before use. Only `SKILL.md` is staged by default. See the [offline contract](skill-verifier/references/offline.md).

## Requirements and result meanings

- Core: Python 3.9+ standard library.
- Full YAML parsing: optional PyYAML. Pixel inspection: optional Pillow.
- Enforced local boundary: macOS `sandbox-exec`, or a separately validated Linux bubblewrap environment. Windows has no bundled enforcement backend.
- Real model tests: your own configured agent CLI, model, narrow permissions and authorized credentials; none are bundled or imported automatically.

For development checks, install the tested optional dependencies in a virtual environment:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-test.txt
python scripts/validate_repository.py
python -m unittest discover -s skill-verifier/tests -v
```

| State | Meaning |
| --- | --- |
| pass | Declared assertions passed within the recorded scope; an offline gate also requires enforced isolation |
| fail | An observed required assertion failed |
| blocked | Tool, runtime, permissions, execution or evidence is unavailable |
| pending | Draft or manual assessment has not been completed |
| incomplete gate | Evidence is insufficient for a passing execution/comparison claim |

Do not treat file presence, an operator's `verified` declaration, or a target's success statement as quality evidence. Raw advisory failures remain visible but do not turn an agent-only rule into a helper defect.

## Compatibility and validation

Compatibility is based on available tools, not a vendor allowlist. The package includes Codex/Claude Code/Gemini CLI adapter examples; Cursor/OpenCode installer evidence and Aident/WorkBuddy synchronization are different claims. Hermes, pi, SpaceX Grok Bot and Meta Muse have documented adaptation notes, with this Skill's untested installation and task behavior kept explicit. See [harness adaptation](skill-verifier/references/harnesses.md) and the [pending capability worksheet](skill-verifier/examples/harness-review.json).

The 0.3.2 distribution passed independent macOS offline QA for GitHub installation, release integrity and installed-copy execution: five installer targets matched all 42 package files, all 94 author tests passed without skips, and 25 independent probes passed. A separate author retest reproduced fresh GitHub installation and offline execution. See the [0.3.2 QA record](docs/qa/v0.3.2.md), [validation and compatibility](docs/validation.md), and CI for the exact scope; installation is separate from native activation and model-quality evidence.

The local boundary rejects hard-linked declared oracles and checks identity/content after the probe and task. Independent answer copies require runtime-content review. No race-free guarantee against privileged concurrent tampering or remote tools outside the boundary is made. Online model effects, native discovery, cross-harness behavior, Linux enforcement and external-account operations remain unverified.

## Repository layout

```text
skill-verifier/       Installable instructions, helpers, references and examples
scripts/              Repository validation, installation checks and packaging
docs/                 Public, redacted validation scope and release notes
.github/workflows/    Offline checks and release packaging
```

Bug reports should include the version, OS/runtime, minimal redacted fixture, exact command, observed/expected result and relevant evidence. Do not upload credentials, private target skills or raw account logs.
