"""Step 3a: turn raw source records into PersonMention records (people, not papers).

Run from the repo root:  python -m processing.data_extraction
"""
import logging
import re
from collections import Counter

from core import settings
from core.schemas import PersonMention
from core.storage import latest_raw, save_json

log = logging.getLogger(__name__)

ORCID_RE = re.compile(r"\d{4}-\d{4}-\d{4}-\d{3}[\dX]")


def clean_orcid(value: str | None) -> str | None:
    """PubMed gives ORCID as a URL or bare id. Keep only the bare id."""
    if not value:
        return None
    m = ORCID_RE.search(value)
    return m.group(0) if m else None


def extract_pubmed(payload: dict) -> tuple[list[PersonMention], dict]:
    """One mention per author per paper. Complete author lists are kept because
    co-authorship (who wrote with whom) is evidence for the network."""
    mentions: list[PersonMention] = []
    skipped_collective = 0
    for rec in payload["records"]:
        for a in rec["authors"]:
            if not a["last_name"]:  # consortium names like "Swiss PSC Study Group" are not people
                skipped_collective += 1
                continue
            given = a["fore_name"] or a["initials"] or ""
            mentions.append(PersonMention(
                mention_id=f"pubmed:{rec['pmid']}:{a['position']}",
                source="pubmed",
                source_record_id=rec["pmid"],
                source_url=rec["source_url"],
                collected_at=rec["collected_at"],
                role="author",
                full_name=f"{given} {a['last_name']}".strip(),
                last_name=a["last_name"],
                fore_name=a["fore_name"],
                initials=a["initials"],
                orcid=clean_orcid(a["orcid"]),
                affiliations=a["affiliations"],
                position=a["position"],
                is_first=a["is_first"],
                is_last=a["is_last"],
                context={
                    "title": rec["title"],
                    "year": rec["year"],
                    "doi": rec["doi"],
                    "author_count": rec["author_count"],
                },
            ))
    stats = {
        "papers": len(payload["records"]),
        "mentions": len(mentions),
        "skipped_collective_names": skipped_collective,
        "mentions_with_orcid": sum(1 for m in mentions if m.orcid),
        "mentions_with_affiliation": sum(1 for m in mentions if m.affiliations),
        "distinct_full_names": len({m.full_name.lower() for m in mentions}),
    }
    return mentions, stats


def run_pubmed():
    path, payload = latest_raw("pubmed")
    mentions, stats = extract_pubmed(payload)
    out = settings.PROCESSED_DIR / "extracted_researchers.json"
    save_json(out, {
        "source": "pubmed",
        "input_file": path.name,
        "stats": stats,
        "mentions": [m.model_dump() for m in mentions],
    })
    log.info("PubMed extraction: %s -> %s", stats, out)
    return mentions, stats


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    mentions, stats = run_pubmed()
    top = Counter(m.full_name for m in mentions).most_common(10)
    print("Most frequent author names:", top)
