"""PubMed via NCBI E-utilities: esearch (find PMIDs) then efetch (full records)."""
import logging
import re
from datetime import datetime, timezone

from lxml import etree

from connectors.base_connector import BaseConnector
from core import settings

log = logging.getLogger(__name__)
EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"


def _text(el) -> str:
    """All text inside an element, including nested tags like <i> or <sup>."""
    return "".join(el.itertext()).strip() if el is not None else ""


class PubMedConnector(BaseConnector):
    name = "pubmed"

    def __init__(self, project):
        super().__init__(project)
        self.min_interval = 0.11 if settings.NCBI_API_KEY else 0.35

    def _params(self, **extra) -> dict:
        params = {"db": "pubmed", "tool": settings.TOOL_NAME}
        if settings.NCBI_API_KEY:
            params["api_key"] = settings.NCBI_API_KEY
        if settings.NCBI_EMAIL:
            params["email"] = settings.NCBI_EMAIL
        params.update(extra)
        return params

    def build_term(self) -> str:
        return f"({self.cfg['disease_query']}) AND {self.cfg['country_filter']}"

    def search(self, term: str):
        """esearch with the history server: total count plus a handle for paging."""
        r = self._get(f"{EUTILS}/esearch.fcgi",
                      self._params(term=term, usehistory="y", retmax=0, retmode="json"))
        res = r.json()["esearchresult"]
        return int(res["count"]), res["webenv"], res["querykey"]

    def fetch_batch(self, webenv: str, query_key: str, start: int, size: int) -> bytes:
        r = self._get(f"{EUTILS}/efetch.fcgi",
                      self._params(query_key=query_key, WebEnv=webenv, retstart=start,
                                   retmax=size, rettype="abstract", retmode="xml"))
        return r.content

    def parse(self, xml_bytes: bytes, collected_at: str) -> list[dict]:
        root = etree.fromstring(xml_bytes)
        records = []
        for art in root.findall("PubmedArticle"):
            pmid = art.findtext("MedlineCitation/PMID")
            author_els = art.findall(".//AuthorList/Author")
            authors = []
            for i, a in enumerate(author_els, start=1):
                authors.append({
                    "position": i,
                    "is_first": i == 1,
                    "is_last": i == len(author_els),
                    "last_name": a.findtext("LastName"),
                    "fore_name": a.findtext("ForeName"),
                    "initials": a.findtext("Initials"),
                    "collective_name": a.findtext("CollectiveName"),
                    "orcid": next(iter(a.xpath("Identifier[@Source='ORCID']/text()")), None),
                    "affiliations": [_text(x) for x in a.findall("AffiliationInfo/Affiliation")],
                })
            abstract = " ".join(
                (f"{t.get('Label')}: " if t.get("Label") else "") + _text(t)
                for t in art.findall(".//Abstract/AbstractText"))
            year = art.findtext(".//JournalIssue/PubDate/Year")
            if not year:  # some records only have <MedlineDate>2019 Jan-Feb</MedlineDate>
                m = re.search(r"\d{4}", art.findtext(".//JournalIssue/PubDate/MedlineDate") or "")
                year = m.group(0) if m else None
            records.append({
                "source": self.name,
                "source_record_id": pmid,
                "source_url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                "collected_at": collected_at,
                "pmid": pmid,
                "doi": next(iter(art.xpath(".//PubmedData/ArticleIdList/ArticleId[@IdType='doi']/text()")), None),
                "title": _text(art.find(".//ArticleTitle")),
                "abstract": abstract,
                "journal": art.findtext(".//Journal/Title"),
                "year": int(year) if year else None,
                "month": art.findtext(".//JournalIssue/PubDate/Month"),
                "publication_types": [_text(x) for x in art.findall(".//PublicationTypeList/PublicationType")],
                "keywords": [_text(x) for x in art.findall(".//KeywordList/Keyword")],
                "mesh_terms": [_text(x) for x in art.findall(".//MeshHeading/DescriptorName")],
                "author_count": len(authors),
                "authors": authors,
            })
        return records

    def fetch(self):
        term = self.build_term()
        count, webenv, query_key = self.search(term)
        log.info("PubMed: %d records match: %s", count, term)
        size = self.cfg.get("batch_size", 200)
        collected_at = datetime.now(timezone.utc).isoformat()
        records = []
        for start in range(0, count, size):
            xml = self.fetch_batch(webenv, query_key, start, size)
            records.extend(self.parse(xml, collected_at))
            log.info("PubMed: fetched %d/%d", len(records), count)
        return records, {"term": term, "reported_count": count}
