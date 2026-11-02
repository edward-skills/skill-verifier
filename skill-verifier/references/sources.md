# Sources and implementation scope

Originally reviewed 2026-10-29; public distribution reviewed 2026-11-02.

- Project brief: evaluate existing skills across task types, support portable execution and evidence-based repair/QA, and distinguish proven behavior from untested scope.
- [Agent Skills evaluation guide](https://agentskills.io/skill-creation/evaluating-skills): upstream basis for artifact-based comparison and iterative evaluation. This package implements its own suite and report contract; it does not claim drop-in compatibility with other skill-creator JSON files.
- [Agent Skills specification](https://agentskills.io/specification): portable `SKILL.md` package format. The bundled linter covers a documented subset plus heuristics; it is not an official conformance implementation.
- CLI recipes checked using locally installed `codex exec --help`, `claude --help`, and `gemini --help`. Help-level verification does not establish authentication or behavioral portability. Actual execution evidence belongs in the adjacent validation workspace.

Task profiles, gate policy, isolation attestation, and runner schemas are this skill's design choices. There is no claim that upstream standards require these particular thresholds or formats. Full syntax validation uses optional PyYAML rather than executing target code.

Packaging compatibility observed locally: the current Codex `quick_validate.py` rejects the specification's optional `compatibility` field. This package therefore keeps environment requirements in the body and uses the shared `name`, `description`, and `metadata` fields in frontmatter.

Revision 0.2, 2026-10-30: independent QA reproduced answer-file access and Markdown-example false positives in 0.1. Runtime resources now require an explicit allowlist, live tasks are separate from evaluator evidence, and comparison pass requires an evaluator-built/probed filesystem boundary. Markdown code is excluded from reference/placeholder checks; dependency-free duplicate-key checks, Unicode names, and observed Claude/Gemini usage handling were improved. Offline macOS sandbox tests and deterministic QA fixture replays validate these changes. They do not establish real-model uplift, native activation, Linux behavior, or cross-harness portability.

Revision 0.2.1 addresses the remaining environment and venv findings: child environments use fixed task-local defaults plus exact opt-ins; probe selection uses the base interpreter or an explicit path; selected Python binaries and pyvenv.cfg files receive narrow read permissions. Offline tests cover both environment filtering and real virtualenv layouts. No new online/model/harness validation is claimed.

Revision 0.3.0 adds local command plans, directory inventory and domain drafts, independent structured-file/pixel checks, artifact-bound offline review, and explicit coverage/contract/diagnosis fields. A real local avatar skill is exercised through declarative steps and synthetic fixtures. The source remains unchanged; observed target defects and defensive recommendations are separated. Verification is author-run macOS offline evidence; independent QA of 0.3.0, online models, native discovery, cross-harness behavior and Linux remain pending. No generated draft or operator-authored diagnosis is automatically certified.

On 2026-11-01 the user supplied independent macOS offline acceptance of 0.3.0 (78 tests, no skips, plus independent CLI probes). QA retained a pre-existing hardlink alias gap in readable runtime grants. Revision 0.3.1 rejects multi-linked declared oracles before launch and checks their identity/content after probe/task. Author-run before/after macOS fixtures reproduce the old false pass and new block. This is a focused fix; 0.3.1 independent acceptance, online/model/native-discovery/cross-harness and Linux execution remain pending.

On 2026-11-02 independent QA accepted the 0.3.1 hardlink fix and reproduced all 94 tests without skips. Independent byte copies remain outside the identity check and require runtime-content review. Version 0.3.2 prepares the public distribution: installation/usage documentation, licensing, a model-free demo and release checks. Its evaluator algorithms are unchanged from the independently accepted 0.3.1 core; public distribution checks do not establish model quality or native activation.
