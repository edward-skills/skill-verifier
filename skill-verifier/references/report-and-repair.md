# QA report and repair

## Verdict policy

The runner reports a **comparison gate**, not a universal quality certificate:

- `fail`: an observed candidate artifact assertion failed, or a known baseline pass regressed.
- `incomplete`: no observed failure, but any expected execution/check is blocked/pending, filesystem isolation has not been enforced and probed, native-baseline isolation is unverified, environment identity is unknown, or a case checks only file presence.
- `pass`: all declared candidate assertions and executions pass, baselines are fully observed, an evaluator-built filesystem boundary denied oracle reads in a live probe, native-baseline isolation is separately attested, environment identity is recorded, and no paired regression exists.

Always show failures even when other work is blocked. A passing baseline is not required for uplift (its task failures are the comparison), but a baseline execution error or ungraded baseline is missing evidence. Candidate versus baseline delta is calculated only for fully graded pairs; the number of excluded pairs is explicit.

An operator's `baseline_isolation: verified` describes native skill loading only. It cannot promote an unsandboxed run to comparison pass. Raw assertion successes/deltas from an incomplete comparison are diagnostic, including a process that copied answers from another reachable location. File existence alone does not establish task correctness. The filesystem probe covers local processes; it does not certify remote tools, MCP servers, native activation, or model quality.

A release recommendation also requires the user's task-specific coverage, repeated important trials, native activation when promised, testing on each claimed harness, no unresolved critical/major defect, and any necessary visual/human review. If those are missing, state **smoke passed / release unverified**. The runner intentionally cannot decide all of these from deterministic assertions alone.

## Report structure

Make evidence levels explicit: executed command/artifact checks, artifact-bound manual reviews, and untested capabilities. Generated reports provide a coverage file alongside raw observations. An offline script run leaves model effect, native discovery, cross-harness transfer and actual agent approval behavior untested. A count is a suite denominator, not a skill quality percentage.

For every suspected defect, cite the requirement's owner and basis. If an instruction is an agent obligation but its helper is not documented to enforce it, report a defensive improvement rather than inventing a hard helper failure. Preserve the raw observation even when triage changes. Mark operator-supplied diagnoses as hypotheses, with confidence and provenance; proposed repairs remain unverified until a separate frozen-suite regression supports them.

Use a short verdict first, then the evidence needed to assess it:

1. Target and revision/fingerprint; request scope and permitted effects; tested environment identities.
2. Coverage table: task/profile/case, candidate, baseline, harness, repetitions, pending/blocked checks, artifact links.
3. Findings: ID, severity, case/run, observed versus expected behavior, exact artifact/trace location, likely cause and confidence, proposed fix, regression check.
4. Comparison: paired raw results and delta; repeated-run spread; time, tokens/cost if measured; excluded pairs and reasons.
5. Portability: native discovery / explicit execution / tools / baseline isolation per harness, with evidence.
6. Repairs: original/candidate hashes, diff, tests rerun, unchanged holdout results, remaining risks and release blockers.
7. Replay: exact command, suite/adapter/fixture/checker revisions, relevant logs. Redact credentials and personal data before distribution.

Use `critical` for unauthorized consequential effects, secret exposure, corrupted source, or invalid evidence leading to a false pass; `major` for a core promised outcome failing; `minor` for a bounded usability/portability problem; `suggestion` for unproven improvements. Severity and release criticality are not the same as confidence in the suspected cause.

## Turn evidence into a repair

Trace backward from the failed outcome. Was the skill loaded? Were tools available? Did instructions select the wrong procedure? Did a script produce bad data? Did the checker reject a legitimate alternative? Record the classification before patching. Do not rewrite a skill to compensate for an unrelated service outage.

An actionable recommendation includes a small proposed diff or precise replacement, the reason it addresses the failure, and a regression test that failed before it. Avoid generic advice such as “add more detail.” Repair in a candidate copy unless the user requested in-place changes. Retain the baseline snapshot and original grades.

Rerun the original failing case, adjacent boundaries, relevant regression cases, and reserved holdouts. Do not use the old evaluator conversation as the task session. Stop at the agreed iteration/resource budget, or after two repair rounds without evidence of improvement; report unresolved causes rather than adding speculative rules. This stopping guideline can be adjusted to the user's scope and the cost of the workflow.

For subjective QA, attach a separate review record with reviewer identity/method, timestamp, rubric/check ID, result, artifact reference, and evidence. The runner accepts these for `manual` checks through `--reviews`; it never turns an agent's self-report into an independent review automatically.
