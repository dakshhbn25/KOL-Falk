"""Small helpers to read the newest raw snapshot and write JSON outputs."""
import json
from pathlib import Path

from core import settings


def latest_raw(source: str) -> tuple[Path, dict]:
    """Return (path, payload) of the newest snapshot in data/raw/<source>/.

    File names are UTC timestamps (20261110T114041Z.json) so sorting by name = sorting by time.
    """
    files = sorted((settings.RAW_DIR / source).glob("*.json"))
    if not files:
        raise FileNotFoundError(f"No raw files for '{source}'. Run: python main.py {source}")
    path = files[-1]
    return path, json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, obj) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
