#!/usr/bin/env python3
"""Build a self-contained deterministic ZIP and its public content manifest."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import zipfile

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "skill-verifier"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    out = args.out.resolve(); out.mkdir(parents=True, exist_ok=True)
    if out.is_relative_to(PACKAGE):
        raise SystemExit("Release output must be outside the installable package")
    version = re.search(r'^VERSION = "([^"]+)"', (PACKAGE / "scripts/verifier.py").read_text(), re.M).group(1)
    files = [p for p in sorted(PACKAGE.rglob("*")) if p.is_file() and not {"__pycache__", ".DS_Store"}.intersection(p.relative_to(PACKAGE).parts) and p.suffix != ".pyc"]
    if any(p.is_symlink() for p in PACKAGE.rglob("*")):
        raise SystemExit("Package symlinks are not accepted")
    hashes = {str(p.relative_to(PACKAGE)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    manifest = (json.dumps({"version": version, "files": hashes}, indent=2) + "\n").encode()
    archive = out / ("skill-verifier-" + version + ".zip")
    if archive.exists():
        raise SystemExit("Release already exists; use a new output directory")
    with zipfile.ZipFile(archive, "x", compression=zipfile.ZIP_STORED) as bundle:
        for name, body in [("skill-verifier/" + str(p.relative_to(PACKAGE)), p.read_bytes()) for p in files] + [("skill-verifier/PACKAGE-MANIFEST.json", manifest)]:
            info = zipfile.ZipInfo(name, date_time=(2026, 11, 2, 0, 0, 0))
            info.create_system = 3; info.external_attr = 0o100644 << 16
            bundle.writestr(info, body)
    (out / "package-manifest.json").write_bytes(manifest)
    checksum = hashlib.sha256(archive.read_bytes()).hexdigest()
    (out / "SHA256SUMS").write_text(checksum + "  " + archive.name + "\n" + hashlib.sha256(manifest).hexdigest() + "  package-manifest.json\n")
    with zipfile.ZipFile(archive) as bundle:
        assert bundle.testzip() is None
        assert all(hashlib.sha256(bundle.read("skill-verifier/" + name)).hexdigest() == digest for name, digest in hashes.items())
    print(json.dumps({"version": version, "archive": str(archive), "sha256": checksum, "files": len(files)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
