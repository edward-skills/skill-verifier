"""Evaluator-owned filesystem boundaries. Never infer enforcement from attestation."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import stat
import sys


class IsolationError(ValueError):
    pass


def reserved_environment_name(name):
    upper = name.upper()
    return upper in {"HOME", "USERPROFILE", "PATH", "TMPDIR", "TMP", "TEMP", "VIRTUAL_ENV",
                     "__PYVENV_LAUNCHER__", "BASH_ENV", "ENV", "ZDOTDIR", "SHELLOPTS", "BASHOPTS",
                     "NODE_OPTIONS", "NODE_PATH", "RUBYOPT", "RUBYLIB", "PERL5OPT", "PERL5LIB"} or upper.startswith(
                         ("PYTHON", "DYLD_", "LD_", "XDG_", "GIT_CONFIG_"))


def task_environment(adapter, work, parent=None, for_probe=False):
    """Construct child state from fixed defaults and exact, explicit opt-ins only."""
    parent = os.environ if parent is None else parent
    work = Path(work).resolve()
    home = work / ".home"
    temp = work / "tmp"
    paths = {"HOME": home, "TMPDIR": temp, "TMP": temp, "TEMP": temp,
             "XDG_CONFIG_HOME": home / ".config", "XDG_CACHE_HOME": home / ".cache",
             "XDG_DATA_HOME": home / ".local/share", "XDG_STATE_HOME": home / ".local/state"}
    if os.name == "nt":
        paths["USERPROFILE"] = home
    for path in paths.values():
        path.mkdir(parents=True, exist_ok=True)
    config = adapter.get("process_environment", {})
    environment = {key: str(value) for key, value in paths.items()}
    environment.update(PATH=os.pathsep.join(config.get("path", []) + os.defpath.split(os.pathsep)),
                       LANG="C", LC_ALL="C", TZ="UTC", PYTHONUTF8="1", PYTHONNOUSERSITE="1",
                       PYTHONDONTWRITEBYTECODE="1")
    generated = sorted(environment)
    inherited, missing = [], []
    # The boundary probe never receives task-only credentials/settings, even on opt-in.
    for name in [] if for_probe else config.get("inherit", []):
        if reserved_environment_name(name):
            raise IsolationError("Reserved startup/task-local variable cannot be inherited: " + name)
        if name in parent:
            environment[name] = parent[name]
            inherited.append(name)
        else:
            missing.append(name)
    return environment, {"policy": "allowlist-v1", "generated_names": generated,
                         "inherited_names": inherited, "missing_names": missing,
                         "values_recorded": False, "probe": for_probe}


def python_runtime(executable):
    """Grant selected Python's binary/config files, never its project or venv tree."""
    path = Path(executable).absolute()
    if not re.fullmatch(r"python(?:[0-9]+(?:\.[0-9]+)*)?(?:\.exe)?", path.name, re.I):
        return None
    configs = [p.resolve() for p in [path.parent / "pyvenv.cfg", path.parent.parent / "pyvenv.cfg"] if p.is_file()]
    return {"executable": str(path), "resolved_executable": str(path.resolve()),
            "config_files": [str(p) for p in dict.fromkeys(configs)]}


def probe_interpreter(adapter):
    configured = adapter.get("filesystem_isolation", {}).get("probe_python")
    if configured:
        selected = Path(configured).absolute()  # Preserve venv spelling for pyvenv.cfg lookup.
    else:
        selected = Path(getattr(sys, "_base_executable", None) or sys.executable).resolve()
    if not selected.is_file() or not os.access(str(selected), os.X_OK):
        raise IsolationError("Probe Python is missing or not executable: " + str(selected))
    result = python_runtime(selected) or {"executable": str(selected), "resolved_executable": str(selected.resolve()), "config_files": []}
    result["selection"] = "configured" if configured else "verifier-base"
    return result


def policy(adapter, work, private_paths, logs, runtime_files=()):
    config = adapter.get("filesystem_isolation", {"mode": "none"})
    mode = config["mode"]
    if mode == "none":
        return [], {"mode": mode, "status": "unverified", "reason": "No enforced filesystem boundary"}
    if not private_paths:
        raise IsolationError("Evaluator private roots are required for an enforced boundary")
    work = Path(work).resolve()
    extra = [Path(p).resolve() for p in config.get("readable_paths", [])] + [Path(p).resolve() for p in runtime_files]
    if mode == "macos-sandbox":
        if sys.platform != "darwin" or not Path("/usr/bin/sandbox-exec").is_file():
            raise IsolationError("macOS sandbox-exec is unavailable")
        system = [Path(p) for p in ["/System", "/usr", "/bin", "/sbin", "/Library", "/dev", "/private/var/db/dyld"] if Path(p).exists()]
    elif mode == "linux-bwrap":
        if not sys.platform.startswith("linux") or not shutil.which("bwrap"):
            raise IsolationError("Linux bubblewrap is unavailable")
        system = [Path(p) for p in ["/usr", "/bin", "/sbin", "/lib", "/lib64"] if Path(p).exists()]
    else:
        raise IsolationError("Unsupported filesystem isolation mode")
    readable = []
    for path in system + extra:
        if not path.exists():
            raise IsolationError("Readable runtime path does not exist: " + str(path))
        for private in private_paths:
            private = Path(private).resolve()
            if path == private or private.is_relative_to(path) or path.is_relative_to(private):
                raise IsolationError("Runtime path overlaps evaluator/target source: " + str(path))
        if path == work or work.is_relative_to(path) or path.is_relative_to(work):
            raise IsolationError("Runtime read grant overlaps task directory")
        if not any(path.is_relative_to(parent) for parent in readable):
            readable = [other for other in readable if not other.is_relative_to(path)]
            readable.append(path)
    if mode == "macos-sandbox":
        quote = lambda p: json.dumps(str(p), ensure_ascii=False)
        read_grants = ["({} {})".format("subpath" if p.is_dir() else "literal", quote(p)) for p in readable]
        read_grants.append("(subpath " + quote(work) + ")")
        # dyld/openat need directory descriptors while resolving absolute paths. Grant
        # ancestors literally, so directory traversal does not grant their file contents.
        ancestors = {parent for path in readable + [work] for parent in path.parents}
        read_grants += ["(literal " + quote(p) + ")" for p in sorted(ancestors)]
        write_grants = ["(subpath " + quote(work) + ")", '(literal "/dev/null")']
        # Preserve default runtime operations (dyld/XPC/process bootstrap), while restricting
        # file contents and writes explicitly. A broad process default is not a file grant.
        profile = ["(version 1)", "(allow default)",
                   "(deny file-read-data file-map-executable (require-all " +
                   " ".join("(require-not " + grant + ")" for grant in read_grants) + "))",
                   "(deny file-write* (require-all " +
                   " ".join("(require-not " + grant + ")" for grant in write_grants +
                            ["(literal " + quote(p) + ")" for p in logs]) + "))",
                   # Logs are write-only to the task; the read rule above still denies them.
                   ]
        if not config.get("allow_network", False):
            profile.append("(deny network*)")
        return ["/usr/bin/sandbox-exec", "-p", "\n".join(profile)], {"mode": mode, "status": "unverified"}
    prefix = [shutil.which("bwrap"), "--die-with-parent", "--new-session", "--unshare-all"]
    if config.get("allow_network", False):
        prefix += ["--share-net"]
    prefix += ["--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp"]
    # bubblewrap creates destination parents for bind mounts; host parents are not mounted.
    for path in readable:
        prefix += ["--ro-bind", str(path), str(path)]
    for spelling in runtime_files:
        spelling = Path(spelling).absolute()
        if spelling.is_symlink() and not any(spelling.is_relative_to(parent) for parent in readable):
            prefix += ["--ro-bind", str(spelling.resolve()), str(spelling)]
    prefix += ["--bind", str(work), str(work), "--chdir", str(work)]
    return prefix, {"mode": mode, "status": "unverified"}


PROBE = r'''
import json, pathlib, sys
public = pathlib.Path(sys.argv[1])
ok = public.read_text() == "probe-readable"
blocked = []
for value in sys.argv[2:]:
    try:
        pathlib.Path(value).read_bytes()
    except (PermissionError, FileNotFoundError):
        blocked.append(value)
    else:
        ok = False
print(json.dumps({"ok":ok,"blocked_paths":blocked}))
sys.exit(0 if ok else 9)
'''


def private_file_records(paths):
    """Reject aliases of declared oracles without scanning broad runtime trees."""
    records = []
    for value in paths:
        path = Path(value)
        try:
            flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
            descriptor = os.open(str(path), flags)
            with os.fdopen(descriptor, "rb") as stream:
                before = os.fstat(stream.fileno())
                if not stat.S_ISREG(before.st_mode) or path.is_symlink():
                    raise IsolationError("Private oracle must be a regular non-symlink file: " + str(path))
                if before.st_nlink != 1:
                    raise IsolationError("Hard-linked private oracle is not accepted: {} (links={})".format(path, before.st_nlink))
                digest = hashlib.sha256()
                for chunk in iter(lambda: stream.read(65536), b""):
                    digest.update(chunk)
                after = os.fstat(stream.fileno())
                named = path.lstat()
                identity = lambda s: (s.st_dev, s.st_ino, s.st_nlink, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
                if identity(before) != identity(after) or identity(after) != identity(named) or not stat.S_ISREG(named.st_mode):
                    raise IsolationError("Private oracle changed while checking identity: " + str(path))
                records.append({"path": str(path), "device": after.st_dev, "inode": after.st_ino,
                                "links": after.st_nlink, "size": after.st_size,
                                "mtime_ns": after.st_mtime_ns, "ctime_ns": after.st_ctime_ns,
                                "sha256": digest.hexdigest()})
        except OSError as exc:
            raise IsolationError("Cannot verify private oracle identity: " + str(path) + ": " + str(exc)) from exc
    if not records:
        raise IsolationError("Private oracle identity records are required")
    return records


def verify_private_files(boundary):
    if boundary.get("mode") == "none":
        return
    proof = boundary.get("private_file_identity", {})
    records = proof.get("files", [])
    if not records or proof.get("policy") != "single-link-v1":
        raise IsolationError("Private oracle identity proof is missing")
    if private_file_records([record["path"] for record in records]) != records:
        raise IsolationError("Private oracle identity or content changed after the boundary check")


def probe(prefix, boundary, work, private_files, evidence_dir, environment, interpreter=None):
    if boundary["mode"] == "none":
        return boundary
    if not private_files or not all(Path(p).is_file() for p in private_files):
        raise IsolationError("Existing private oracle files are required for the boundary probe")
    if not interpreter:
        raise IsolationError("Probe interpreter was not selected")
    proof = {"policy": "single-link-v1", "files": private_file_records(private_files),
             "verified_after_probe": False, "verified_after_task": False}
    boundary = dict(boundary, private_file_identity=proof)
    public = Path(work) / ".read-probe"
    public.write_text("probe-readable", encoding="utf-8")
    try:
        # Use the same permitted log descriptors as the real task. Anonymous pipes have
        # no allowed filesystem path under the macOS content-read/write predicates.
        stdout_path, stderr_path = evidence_dir / "stdout.log", evidence_dir / "stderr.log"
        with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
            process = subprocess.run(prefix + [interpreter["executable"], "-I", "-S", "-c", PROBE, str(public)] +
                                     [str(p) for p in private_files], cwd=str(work), env=environment,
                                     stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr, timeout=10)
        stdout_data, stderr_data = stdout_path.read_bytes(), stderr_path.read_bytes()
        (evidence_dir / "isolation-probe.stdout.log").write_bytes(stdout_data)
        (evidence_dir / "isolation-probe.stderr.log").write_bytes(stderr_data)
        (evidence_dir / "isolation-probe.json").write_text(json.dumps({"returncode": process.returncode,
            "stdout": "isolation-probe.stdout.log", "stderr": "isolation-probe.stderr.log"}) + "\n", encoding="utf-8")
        data = json.loads(stdout_data) if process.returncode == 0 else {}
        if data.get("ok") is not True or len(data.get("blocked_paths", [])) != len(private_files):
            raise IsolationError("Boundary probe failed (exit " + str(process.returncode) + "); inspect isolation-probe stdout/stderr logs")
        verify_private_files(boundary)
        proof["verified_after_probe"] = True
        return dict(boundary, status="enforced", probe=data,
                    probe_python=interpreter,
                    scope="Task reads confined to its directory and declared runtime paths; declared oracle files are single-link and denied by the live probe")
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        raise IsolationError("Filesystem boundary was not verified: " + str(exc)) from exc
    finally:
        public.unlink(missing_ok=True)
