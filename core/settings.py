"""Central place for paths, API keys and project config loading."""
import json
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[1]
load_dotenv(BASE_DIR / ".env")

DATA_DIR = BASE_DIR / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
CONFIG_DIR = BASE_DIR / "config"

NCBI_API_KEY = os.getenv("NCBI_API_KEY")  # optional, raises the rate limit from 3 to 10 req/s
NCBI_EMAIL = os.getenv("NCBI_EMAIL")      # optional, NCBI likes a contact address
TOOL_NAME = "kol_intelligence_platform"


def load_project(project_id: str) -> dict:
    path = CONFIG_DIR / "projects" / f"{project_id}.json"
    return json.loads(path.read_text(encoding="utf-8"))
