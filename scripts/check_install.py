#!/usr/bin/env python3
"""Copy-install into isolated temporary projects and verify full package hashes."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
AGENTS = ["codex", "claude-code", "cursor", "opencode", "gemini-cli"]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def package_hashes(path):
    return {str(p.relative_to(path)): digest(p) for p in sorted(path.rglob("*"))
            if p.is_file() and not {"__pycache__", ".DS_Store"}.intersection(p.relative_to(path).parts) and p.suffix != ".pyc"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default=str(ROOT), help="local repository or GitHub owner/repo")
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--cli", type=Path, help="existing skills 1.7.2 cli.mjs; otherwise use npx")
    args = parser.parse_args()
    out = args.out.resolve(); out.mkdir(parents=True, exist_ok=False)
    expected = package_hashes(ROOT / "skill-verifier")
    prefix = [shutil.which("node"), str(args.cli.resolve())] if args.cli else [shutil.which("npx"), "--yes", "skills@1.7.2"]
    if not prefix[0]:
        raise SystemExit("Node.js 22.20+ and npm are required for installer checks")
    rows = []
    for agent in AGENTS:
        project = out / agent / "project"; project.mkdir(parents=True)
        home = out / agent / "home"; home.mkdir()
        env = {"PATH": os.environ.get("PATH", os.defpath), "HOME": str(home), "LANG": "C", "LC_ALL": "C",
               "XDG_CONFIG_HOME": str(home / ".config"), "XDG_CACHE_HOME": str(home / ".cache"),
               "NPM_CONFIG_CACHE": str(out / "npm-cache"), "NPM_CONFIG_USERCONFIG": str(home / ".npmrc"),
               "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull, "GIT_TERMINAL_PROMPT": "0",
               "DO_NOT_TRACK": "1", "DISABLE_TELEMETRY": "1", "CI": "1"}
        argv = prefix + ["add", args.source, "--skill", "skill-verifier", "--agent", agent, "--copy", "--yes"]
        process = subprocess.run(argv, cwd=project, env=env, capture_output=True, text=True, timeout=180)
        (out / agent / "stdout.log").write_text(process.stdout, encoding="utf-8")
        (out / agent / "stderr.log").write_text(process.stderr, encoding="utf-8")
        installed = [p.parent for p in project.rglob("SKILL.md") if p.parent.name == "skill-verifier"]
        row = {"agent": agent, "returncode": process.returncode, "installed": [str(p.relative_to(project)) for p in installed],
               "package_hashes_match": bool(installed) and all(not p.is_symlink() and package_hashes(p) == expected for p in installed)}
        rows.append(row)
    report = {"installer": "skills 1.7.2", "source": args.source, "scope": "copy installation only; no agent launch, model call, or global configuration change",
              "file_count": len(expected), "checks": rows}
    (out / "summary.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if all(row["returncode"] == 0 and row["package_hashes_match"] for row in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
