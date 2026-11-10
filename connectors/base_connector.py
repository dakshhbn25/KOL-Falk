"""Common behaviour for every source: polite HTTP, retries, saving raw snapshots."""
import json
import logging
import time
from abc import ABC, abstractmethod
from datetime import datetime, timezone

import requests
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from core import settings

log = logging.getLogger(__name__)


class RetryableError(Exception):
    """Raised for errors worth retrying: timeouts, 429 (rate limit), 5xx."""


class BaseConnector(ABC):
    name: str = "base"          # must match the key under "sources" in the project config
    min_interval: float = 0.4   # minimum seconds between two requests

    def __init__(self, project: dict):
        self.project = project
        self.cfg = project["sources"][self.name]
        self.session = requests.Session()
        self.session.headers["User-Agent"] = f"{settings.TOOL_NAME}/0.1"
        self._last_request = 0.0

    @retry(
        retry=retry_if_exception_type(RetryableError),
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=1, max=20),
        reraise=True,
    )
    def _get(self, url: str, params: dict | None = None) -> requests.Response:
        # simple rate limiter: wait until min_interval has passed since the last call
        wait = self.min_interval - (time.monotonic() - self._last_request)
        if wait > 0:
            time.sleep(wait)
        try:
            resp = self.session.get(url, params=params, timeout=30)
        except (requests.ConnectionError, requests.Timeout) as exc:
            raise RetryableError(str(exc)) from exc
        self._last_request = time.monotonic()
        if resp.status_code == 429 or resp.status_code >= 500:
            log.warning("%s returned %s, will retry", url, resp.status_code)
            raise RetryableError(f"HTTP {resp.status_code}")
        resp.raise_for_status()  # other 4xx = our mistake, fail immediately
        return resp

    @abstractmethod
    def fetch(self) -> tuple[list[dict], dict]:
        """Return (records, query_info). Each record carries source,
        source_record_id, source_url and collected_at."""

    def save_raw(self, records: list[dict], query_info: dict):
        """Write a NEW timestamped file every run; never overwrite old ones."""
        run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        out_dir = settings.RAW_DIR / self.name
        out_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "source": self.name,
            "project_id": self.project["project_id"],
            "collected_at": datetime.now(timezone.utc).isoformat(),
            "query": query_info,
            "record_count": len(records),
            "records": records,
        }
        path = out_dir / f"{run_id}.json"
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        log.info("saved %d records to %s", len(records), path)
        return path

    def run(self):
        records, query_info = self.fetch()
        return self.save_raw(records, query_info)
