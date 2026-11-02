# Repository operating contract

Load `skill-verifier/SKILL.md` to use the skill. This file is repository maintenance guidance.

- Keep the installable package self-contained. Other agents must not depend on this file or OpenAI UI metadata.
- Preserve fail/blocked/pending/incomplete states, every planned repetition and original evidence.
- Keep oracle data outside task access; exact runtime manifests and content review remain required.
- Never import whole HOME/auth trees, bypass permissions or turn diagnostic execution into a passing isolation claim.
- Keep agent obligations/advisories separate from hard helper contracts. Diagnosis stays a hypothesis until supported.
- Do not claim native activation, model uplift or another platform from installation or synthetic tests.
- Keep public docs and fixtures free of local paths, private issue links, account data and raw private logs.
- Existing 0.3.1 validation applies to its frozen core; name the scope of later distribution changes.

Validate with `python3 scripts/validate_repository.py` and the relevant offline tests. The native suite requires macOS sandbox permissions and `SKILL_VERIFIER_TEST_SANDBOX=1`; unavailable execution must not be reported as passing. See `docs/validation.md`.
