"""Pydantic models shared by all sources. Every extracted person becomes a PersonMention."""
from pydantic import BaseModel, Field


class PersonMention(BaseModel):
    """One appearance of a person in one source record (e.g. author #3 of paper X).

    This is NOT yet a unique person: the same human can have many mentions.
    Deduplication (a later step) merges mentions into unique candidates.
    """
    mention_id: str                 # unique: <source>:<record id>:<position>
    source: str                     # pubmed | clinicaltrials | sasl
    source_record_id: str           # PMID, NCT ID or SASL study number
    source_url: str
    collected_at: str
    role: str                       # author | principal_investigator | overall_official | ...
    full_name: str                  # name as we display it
    last_name: str | None = None
    fore_name: str | None = None
    initials: str | None = None
    orcid: str | None = None        # bare id like 0000-0002-1825-0097
    affiliations: list[str] = Field(default_factory=list)
    position: int | None = None     # author position in the paper, if relevant
    is_first: bool = False
    is_last: bool = False
    context: dict = Field(default_factory=dict)  # title, year, doi ... for evidence
