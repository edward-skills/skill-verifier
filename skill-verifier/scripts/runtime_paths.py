"""Narrow library grants for the currently selected Python, for demos/tests only."""
from pathlib import Path
import sys
import sysconfig


def python_runtime_paths():
    candidates = [sysconfig.get_path("stdlib"), sysconfig.get_config_var("LIBDIR")]
    names = {"Python", "Python3", sysconfig.get_config_var("LDLIBRARY"), sysconfig.get_config_var("PYTHONFRAMEWORK")}
    candidates += [str(Path(sys.base_prefix) / name) for name in names if name]
    return sorted({str(Path(path).resolve()) for path in candidates if path and Path(path).exists()})
