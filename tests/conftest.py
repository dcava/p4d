"""
Load .env.test from the repo root (if present) before any test collects.
This lets you keep FOURD_PWD and friends out of the environment without
hardcoding them in the test files.

Example .env.test (gitignored):
    FOURD_HOST=192.168.1.239
    FOURD_PORT=19812
    FOURD_USER=sqluser
    FOURD_PWD=your_password_here
"""
from pathlib import Path
import os


def _load_env_file(path: Path) -> None:
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        os.environ.setdefault(key.strip(), val.strip())


_env_file = Path(__file__).resolve().parents[1] / ".env.test"
if _env_file.exists():
    _load_env_file(_env_file)
