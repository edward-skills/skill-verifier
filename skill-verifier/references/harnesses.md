# Harness adaptation

The skill's workflow requires no vendor-specific tool name. Map these capabilities in the current host: file inspection, artifact creation, command execution, independent sessions, network/browser, secrets, state inspection, and rendering. For each, record available / unavailable / substituted and the effect on the test. A file copy isolates test data, not permissions or network access.

## Portable execution contract

The evaluator stages fixtures and an explicitly allowlisted candidate copy, builds a prompt, then gives a trusted adapter an argv list and file-backed stdin. The adapter executes a fresh session in a disposable task directory separate from the evaluator report tree. The agent writes task artifacts to `outputs/`, or the adapter extracts its final text as an output file. The task can read its prompt/response staging files; assertions, expected answers, original packages, snapshots, and opposing results remain outside its file grants. Captured `runs/.../work/` directories are evidence copies made after execution, not the live working directories. No resume/session reuse belongs in an adapter.

Native auto-discovery is outside this runner. Separately prove installation, actual activation, negative routing, and native-baseline isolation. Inspect global/project skill catalogs and inherited hooks/MCP/configuration. If they cannot be controlled or observed, keep `baseline_isolation.status: "unverified"`. This attestation cannot substitute for filesystem isolation: `filesystem_isolation` must select an available evaluator-built backend and pass a live probe. Mode `none` is diagnostic and cannot produce comparison pass. Backend failure blocks execution without a plain-process fallback.

The macOS backend uses sandbox-exec file-content/write restrictions; Linux uses a bubblewrap mount namespace. Both require runtime-readable paths to be declared narrowly and reject grants overlapping evaluator/target sources. Network is disabled unless explicitly enabled in the trusted adapter. Kernel-enforced local file isolation does not constrain tools already running outside it (such as remote MCP/browser services); remove such capabilities or verify their own access boundaries before making a broader claim. Never add credential paths without the user's existing authorization, and never grant an entire home directory to make a test green.

Version 0.2.1 also rebuilds child environments instead of inheriting the host environment: task-local home/cache/temp state and an exact pass-through allowlist replace host HOME, startup hooks and implicit credentials. The probe uses a base Python by default, with narrow interpreter/pyvenv.cfg grants for configured venvs. Custom library roots require explicit read permissions. Fresh HOME may change CLI authentication/config discovery; resolve those requirements only within an authorized future online test, not by importing the whole host environment.

## CLI recipes

Examples in `examples/adapters/` use CLI flags checked against local help on 2026-10-29. Always inspect current `--help`, executable version, authentication, and sandbox availability before executing them. They keep permission checks enabled and do not select a model. Models/settings are supplied by the operator's environment and must be recorded for real comparisons.

| Harness | Explicit execution recipe | Result handling | What remains to verify |
| --- | --- | --- | --- |
| Codex | `codex exec --skip-git-repo-check --ephemeral --ignore-user-config --sandbox workspace-write --json --output-last-message {response_file} -` | JSONL trace plus final response file | Loaded native skill catalog, inherited plugins, tool/network policy, model/settings |
| Claude Code | `claude -p --no-session-persistence --output-format json --permission-mode default` | JSON stdout; runner extracts `result` and detects `is_error` | Settings/hooks/MCP/native skills, trust, available tool permissions, model/settings |
| Gemini CLI | `gemini --prompt ... --output-format json --approval-mode default` | JSON stdout; runner extracts `response` and detects `error` | Native skills, extensions, trust/permissions, clean settings, model/settings |
| Other CLI or SDK | Operator supplies a small executable adapter implementing the same protocol | File or text/JSON response; trace retained | Session isolation and host-specific permissions |
| Chat UI / no shell | New host session per case with staged fixtures and explicit skill instructions | Save actual artifacts and a trace/export; grade with the same rubric | Fresh context, upload fidelity, native activation; script checks require another permitted execution surface |

Do not add blanket permission bypass flags for convenience. If default permissions prevent headless operations, pre-authorize only the required capabilities through the harness's supported mechanism, or report a block. For text-only tasks, final-response extraction avoids requiring file-write tools. Do not use it for tasks whose promise is to edit a file or operate an external app.

## Adapter scope claims

An argv recipe that starts is **adapter-compatible**. Passing actual target tasks is **behavior-tested**. Passing from native discovery is **native-activation-tested**. Use these labels per harness/version; do not promote a recipe to a behavioral claim. The bundled vendor examples use diagnostic mode `none`, unverified native-baseline isolation, and unknown model. They cannot silently produce a comparison or release pass. The 0.2 revision has offline macOS boundary evidence; Linux and real model/harness execution remain unverified until tested in the intended environment.
