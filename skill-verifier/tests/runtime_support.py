"""Use the same explicit runtime discovery as the public demo."""
import importlib.util
from pathlib import Path

SPEC = importlib.util.spec_from_file_location("demo_runtime_paths", Path(__file__).parents[1] / "scripts/runtime_paths.py")
runtime = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runtime)
python_runtime_paths = runtime.python_runtime_paths
