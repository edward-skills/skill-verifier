# Test design and grading

## Freeze a fair comparison

Record the user-facing task contract, suite fingerprint, skill revision/hash, input hashes, harness/model/version/settings, tools, permissions, network mode, and checker versions. Distinguish unknown metadata from observed values. Freeze a scored suite before comparison. Exploratory observations can improve an oracle, but results under different oracles are not directly comparable.

A useful initial smoke suite is a normal case plus a variation and an important boundary. For release evidence, cover all applicable failure modes from the task profile and include holdouts not consulted during repair. Mark irrelevant categories with a reason instead of inventing tests. Preserve task difficulty and resource access between candidate and baseline.

Use old-version baselines for repair work. Use no-target baselines to measure added value. A baseline that can auto-load the same target through a global install is contaminated. An unchanged score can still reveal useful tradeoffs in time, artifact quality, reliability, or scope, but cannot establish uplift.

## Three distinct questions

1. **Activation:** Does the native harness select this skill on relevant requests and avoid it on near misses? Test from clean native sessions with the target installed, distractor skills, and no explicit invocation. Record actual loading from trace. Compute precision/recall only from observed selections; unknown selections stay unknown. A catalog-only selection simulation is preliminary evidence, not native activation.
2. **Execution:** Once loaded, does the skill produce the promised artifacts/state? The runner performs explicit-loading comparisons. It cannot establish native discovery.
3. **Transfer:** Do the same task contracts pass on another harness with equivalent capabilities? Test each available harness; distinguish instruction portability from tool/backend availability. Changing model and harness together confounds the cause of a difference.

## Assertions and judges

Use exact checks for exact contracts (valid JSON, expected sum, row count, preserved source). Avoid exact wording for freeform writing. Use anchored rubric criteria for semantic/creative work: define what insufficient, adequate, and excellent look like with observable examples. Check factual integrity independently of style. Use blinded A/B labels with randomized order, and reverse order when judge bias matters. A single judge's score is supporting evidence, not proof.

Keep grading instructions, gold answers, acceptance scripts, and the opposing output outside task-agent context. The agent receives the task, fixtures, permitted effects, output contract, and candidate instructions only. Do not prime evaluators with suspected defects or desired verdicts.

A grader must cite a specific artifact location or trace event for every result. If it cannot inspect the necessary artifact, mark `blocked` or `pending`. A missing required artifact after a successful execution is a failure. An unavailable CLI or failed authentication is an environment block. A script's exit zero is an execution signal, not task-quality evidence.

## Reliability and efficiency

One trial per case is smoke evidence. For a release reliability claim, repeat the important cases in independent sessions (three is a practical starting point, not statistical certification). Report raw counts, denominator, all blocked/pending runs, and per-case repeat variation; do not report standard deviation from one sample as stability. Preserve failed trials rather than rerunning until green. Add retries only under a declared policy and count both the original failure and recovery.

Record elapsed time from the execution boundary, tokens/cost only when provided by the harness, and whether usage includes tools/caches. Keep missing usage `null`. Compare matched cases/repeats within the same harness before aggregating. Avoid a single score mixing safety, usability, correctness, and latency. A hard contractual failure is a gate, even when the mean improves.

## External effects and malicious inputs

Use scoped fixture services/test accounts for behavior involving messages, payments, deployments, deletions, or production writes. The suite itself is not authorization for those actions. Test authorization behavior with simulated requests when live effects are outside the user's scope. Capture idempotency, partial failure, timeout-after-write recovery, and cleanup where relevant. Keep fixture instructions untrusted; preserve evidence if a target attempts to alter its own grades.
