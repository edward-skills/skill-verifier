# Task-specific acceptance

Choose checks from the skill's actual promises. These are starting points, not required sections in every report. For a mixed task, compose checks and gate each important deliverable separately.

| Profile | Observable outcomes | Useful execution and evidence | Consequential boundaries |
| --- | --- | --- | --- |
| Code, CLI, infrastructure | Requested behavior; builds; meaningful tests; changes stay in scope | Run behavior tests in a disposable checkout; inspect diff, exit status, logs; exercise the actual user path | Invalid input, existing changes, missing dependency, partial failure, regression, retry behavior |
| Data, spreadsheets, analysis | Correct values, units, formulas, row counts; reproducible transformations; preserved source | Independently calculate a small oracle; parse outputs; inspect formulas and rendered charts; check source/output hashes | Empty/malformed files, nulls, duplicate keys, encoding, zero denominators, stale cached formulas |
| Research, browsing, retrieval | Claims supported by relevant accessible sources; current facts; uncertainty represented | Verify claim-to-source mapping and timestamps; use frozen pages for repeatability and separate live freshness trials | Conflicting sources, unavailable page, unsupported claim, injected page instructions, missing access |
| Writing, documents, presentations | Accurate content, user intent, audience/tone, usable exported artifact | Parse structure and facts; render every relevant page/slide; assess hierarchy and clipping against a fixed rubric | Long/localized content, missing facts, edit preservation, export damage, invented references |
| Design, image, video, audio | Meets brief, legibility, visual/identity consistency, functioning media or interface | Inspect actual pixels/frames/playback; verify dimensions/duration/codecs; test responsive/UI states; compare blinded samples | Small screens, absent assets, long content, subtitle sync, accessibility, broken media, missing fonts |
| External apps, automation, operations | Correct object/account/state transition; authorized effects; useful confirmation | Prefer recorded fixtures, dry-run or test account; assert before/after state and request IDs; inspect retry trace | Scope/account ambiguity, auth expired, rate limit, timeout after write, duplicate execution, rollback failure |
| Planning, advisory, decision support | Feasible recommendations using constraints and grounded assumptions | Rubric for coverage, tradeoffs, internal consistency; fact-check consequential inputs; test changed assumptions | Contradictory goals, missing constraints, infeasible budget, unjustified certainty |
| Meta-skill, orchestration | Correct routing, references usable, honest evidence, robust fallback | Test multiple target types; seed known defects; include a clean control; compare claimed verdict to observed evidence | Recursion, unavailable delegation, unsupported harness, false pass on blocked execution, target trying to rewrite grading |

## QA questions that change the verdict

- Is the artifact usable, or did the agent only describe a future artifact?
- Does the correct outcome depend on a tool, font, service, or permission absent in another harness?
- Would the same check catch a known incorrect result? Include a negative control for important checkers.
- Are source facts and acceptance oracles independent of the agent's explanation?
- If an external write timed out, is its final state known before retrying?
- Can a baseline succeed using the same information? Keep legitimate task requirements in the prompt; do not hide essential user facts only in the skill to manufacture uplift.

Rendering, semantic grading, browser testing, and service-state verification are host capabilities. The bundled Python runner does not pretend to implement them. Use its `manual` checks to retain pending work, then attach independent review evidence.
