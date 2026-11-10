"""SASL (Swiss Association for the Study of the Liver). No API exists, the pages are
static HTML, so we use requests + BeautifulSoup."""
import logging
from datetime import datetime, timezone

from bs4 import BeautifulSoup

from connectors.base_connector import BaseConnector

log = logging.getLogger(__name__)


def _clean(el) -> str:
    return el.get_text(" ", strip=True) if el else ""


class SaslConnector(BaseConnector):
    name = "sasl"

    def parse_studies(self, html: str, url: str, collected_at: str) -> list[dict]:
        soup = BeautifulSoup(html, "lxml")
        records = []
        for row in soup.select("table#sasl-studies tbody tr"):
            number = _clean(row.select_one("td.number"))
            records.append({
                "source": self.name,
                "source_record_id": number,
                "source_url": url,
                "collected_at": collected_at,
                "record_type": "study",
                "study_number": number,
                "title": _clean(row.select_one("td.title")),
                "principal_investigators_raw": _clean(row.select_one("td.investigator")),
                "enrolment_status": _clean(row.select_one("td.enrolment")),
                "publication_status": _clean(row.select_one("td.publicationstatus")),
                "description": _clean(row.select_one("td.description")),
            })
        return records

    def parse_centers(self, html: str, url: str, collected_at: str) -> list[dict]:
        soup = BeautifulSoup(html, "lxml")
        records = []
        section = None
        for row in soup.select("div.graybox table tr"):
            sub = row.select_one("td.subtitles1")
            if sub:  # section heading row, e.g. "Kantonsspitaeler"
                section = _clean(sub)
                continue
            if not row.select_one("td.hospital"):
                continue
            city = _clean(row.select_one("td.city"))
            name_el = row.select_one("td.contactperson span.contactname")
            link = row.select_one("td.contactinfo a")
            records.append({
                "source": self.name,
                "source_record_id": f"CENTER::{city}::{_clean(name_el)}",
                "source_url": url,
                "collected_at": collected_at,
                "record_type": "center_contact",
                "section": section,
                "city": city.replace("*", "").strip(),
                "is_transplant_center": "*" in city,
                "hospital": _clean(row.select_one("td.hospital")),
                "contact_role": _clean(row.select_one("td.contactperson")).replace(_clean(name_el), "").strip(" :"),
                "contact_name": _clean(name_el),
                "website": link["href"] if link and link.has_attr("href") else None,
            })
        return records

    def fetch(self):
        collected_at = datetime.now(timezone.utc).isoformat()
        s_url, i_url = self.cfg["studies_url"], self.cfg["investigators_url"]
        studies = self.parse_studies(self._get(s_url).text, s_url, collected_at)
        centers = self.parse_centers(self._get(i_url).text, i_url, collected_at)
        log.info("SASL: %d studies, %d center contacts", len(studies), len(centers))
        return studies + centers, {"studies_url": s_url, "investigators_url": i_url}
