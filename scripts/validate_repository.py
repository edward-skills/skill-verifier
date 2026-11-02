#!/usr/bin/env python3
"""Validate public package structure and executable contracts without models."""
import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "skill-verifier"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-yaml-review", action="store_true")
    args = parser.parse_args()
    for relative in ["README.md", "README.zh-CN.md", "LICENSE.md", "AGENTS.md", "requirements-test.txt", "skill-verifier/SKILL.md", "skill-verifier/LICENSE.md"]:
        if not (ROOT / relative).is_file():
            raise SystemExit("Missing release file: " + relative)
    if (ROOT / "LICENSE.md").read_bytes() != (PACKAGE / "LICENSE.md").read_bytes():
        raise SystemExit("Repository and installable-package licenses differ")
    for path in ROOT.rglob("*.md"):
        if {".git", ".venv", ".ci-venv", "node_modules", "dist"}.intersection(path.relative_to(ROOT).parts):
            continue
        text = path.read_text(encoding="utf-8")
        if re.search(r"/Users/|/private/var/folders/|linear\.app/", text):
            raise SystemExit("Private/local reference in public prose: " + str(path.relative_to(ROOT)))
        for link in re.findall(r"\]\(([^)\s]+)\)", text):
            if link.startswith(("https:", "http:", "mailto:", "#")):
                continue
            target = (path.parent / unquote(link.split("#")[0])).resolve()
            if not target.is_relative_to(ROOT) or not target.exists():
                raise SystemExit("Broken/outside local link in " + str(path.relative_to(ROOT)) + ": " + link)
    verifier = PACKAGE / "scripts/verifier.py"
    lint = subprocess.run([sys.executable, str(verifier), "lint", str(PACKAGE)], capture_output=True, text=True)
    data = json.loads(lint.stdout)
    if data["status"] != "pass" and not (args.allow_yaml_review and data["status"] == "review" and all(x["code"] == "yaml-unverified" for x in data["findings"])):
        print(lint.stdout)
        return 1
    for example in ["avatar-suite.json", "code-suite.json"]:
        subprocess.run([sys.executable, str(verifier), "offline-validate", str(PACKAGE / "examples/offline" / example)], check=True)
    version = subprocess.check_output([sys.executable, str(verifier), "--version"], text=True).strip()
    entry = (PACKAGE / "SKILL.md").read_text(encoding="utf-8")
    if 'version: "' + version + '"' not in entry:
        raise SystemExit("Entrypoint/runtime versions differ")
    print(json.dumps({"version": version, "package_lint": data["status"], "local_doc_links": "pass", "model_calls": 0}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
