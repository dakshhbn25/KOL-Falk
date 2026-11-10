"""ClinicalTrials.gov API v2. Keeps the full study record untouched."""
import logging
from datetime import datetime, timezone

from connectors.base_connector import BaseConnector

log = logging.getLogger(__name__)
API = "https://clinicaltrials.gov/api/v2/studies"


class ClinicalTrialsConnector(BaseConnector):
    name = "clinicaltrials"

    def fetch(self):
        collected_at = datetime.now(timezone.utc).isoformat()
        studies: dict[str, dict] = {}  # keyed by NCT ID so a trial found by 2 searches is stored once
        counts = {}
        for condition in self.cfg["conditions"]:
            params = {
                "query.cond": condition,
                "query.locn": self.cfg["location"],
                "pageSize": self.cfg.get("page_size", 100),
                "countTotal": "true",
            }
            page_token = None
            while True:
                if page_token:
                    params["pageToken"] = page_token
                data = self._get(API, params).json()
                counts[condition] = data.get("totalCount")
                for study in data.get("studies", []):
                    nct = study["protocolSection"]["identificationModule"]["nctId"]
                    rec = studies.setdefault(nct, {
                        "source": self.name,
                        "source_record_id": nct,
                        "source_url": f"https://clinicaltrials.gov/study/{nct}",
                        "collected_at": collected_at,
                        "matched_conditions": [],
                        "study": study,  # full original record
                    })
                    if condition not in rec["matched_conditions"]:
                        rec["matched_conditions"].append(condition)
                page_token = data.get("nextPageToken")
                if not page_token:
                    break
            log.info("ClinicalTrials.gov: '%s' -> %s studies", condition, counts[condition])
        return list(studies.values()), {
            "conditions": self.cfg["conditions"],
            "location": self.cfg["location"],
            "reported_counts": counts,
        }
