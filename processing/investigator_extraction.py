"""Step 3b: people from ClinicalTrials.gov and SASL -> PersonMention records.

Trial officials, central contacts and Swiss site contacts come from the registry.
SASL principal investigators come as messy free text, so they are parsed carefully.
"""
import re

from core.schemas import PersonMention

TITLE_WORDS = {"prof", "dr", "med", "pd", "phil", "dre", "md", "msc", "dipl", "pharm"}
# Company job titles, not people ("Gilead Study Director", "Ipsen Clinical Study Enquiries")
GENERIC_MARKERS = ("study director", "medical director", "study enquir", "study information",
                   "information center", "clinical trial", "clinical study")


# ---------- shared name helpers ----------

def strip_titles(words: list[str]) -> tuple[list[str], list[str]]:
    """Remove leading/trailing title words (Prof., Dr., med., PD, MD ...). Returns (name_words, titles)."""
    titles = []
    words = list(words)
    while words and words[0].strip(".").lower() in TITLE_WORDS:
        titles.append(words.pop(0))
    while words and words[-1].strip(".").lower() in TITLE_WORDS:
        titles.append(words.pop())
    return words, titles


def parse_person_name(raw: str) -> dict | None:
    """'B.Helbling' -> B. Helbling | 'Prof. Dr. med. M. Heim' -> M. Heim (title kept separately)."""
    s = re.sub(r"\.(?=[A-Za-z])", ". ", raw.strip())  # 'E.L.Renner' -> 'E. L. Renner'
    words, titles = strip_titles(s.split())
    if not words:
        return None
    last = words[-1]
    fore = " ".join(words[:-1]) or None
    initials = "".join(w[0] for w in fore.replace("-", " ").split()).upper() if fore else None
    return {
        "full_name": " ".join(words),
        "last_name": last,
        "fore_name": fore,
        "initials": initials,
        "title": " ".join(titles) or None,
    }


def is_generic_role(name: str) -> bool:
    n = name.lower()
    return any(m in n for m in GENERIC_MARKERS)


# ---------- ClinicalTrials.gov ----------

def extract_clinicaltrials(payload: dict, country_name: str) -> tuple[list[PersonMention], dict]:
    mentions: list[PersonMention] = []
    skipped_generic = 0

    def add(rec, mention_key, role, raw_name, affiliation, ctx, email=None, phone=None):
        nonlocal skipped_generic
        # CT.gov writes "Andreas Cerny, Prof. Dr. med": name first, title after the comma
        name_part, _, title_part = raw_name.partition(",")
        if is_generic_role(name_part):
            skipped_generic += 1
            return
        parsed = parse_person_name(name_part)
        if not parsed:
            return
        if title_part.strip():
            parsed["title"] = " ".join(filter(None, [parsed["title"], title_part.strip()]))
        mentions.append(PersonMention(
            mention_id=f"clinicaltrials:{rec['source_record_id']}:{mention_key}",
            source="clinicaltrials",
            source_record_id=rec["source_record_id"],
            source_url=rec["source_url"],
            collected_at=rec["collected_at"],
            role=role,
            affiliations=[affiliation] if affiliation else [],
            email=email, phone=phone,
            context=ctx,
            **parsed,
        ))

    for rec in payload["records"]:
        p = rec["study"]["protocolSection"]
        status = p.get("statusModule", {})
        ctx = {
            "nct_id": rec["source_record_id"],
            "title": p["identificationModule"].get("briefTitle"),
            "overall_status": status.get("overallStatus"),
            "start_date": status.get("startDateStruct", {}).get("date"),
            "phases": p.get("designModule", {}).get("phases"),
            "sponsor": p.get("sponsorCollaboratorsModule", {}).get("leadSponsor", {}).get("name"),
            "matched_conditions": rec["matched_conditions"],
        }
        cl = p.get("contactsLocationsModule", {})
        for i, o in enumerate(cl.get("overallOfficials", [])):
            add(rec, f"official{i}", (o.get("role") or "official").lower(), o["name"],
                o.get("affiliation"), ctx)
        for i, c in enumerate(cl.get("centralContacts", [])):
            add(rec, f"central{i}", "central_contact", c["name"], None, ctx,
                email=c.get("email"), phone=c.get("phone"))
        for j, loc in enumerate(cl.get("locations", [])):
            if loc.get("country") != country_name:  # only sites in the target country
                continue
            site = ", ".join(filter(None, [loc.get("facility"), loc.get("city"), loc.get("country")]))
            for k, c in enumerate(loc.get("contacts", [])):
                add(rec, f"site{j}-{k}", "site_contact", c["name"], site,
                    {**ctx, "site": site}, email=c.get("email"), phone=c.get("phone"))

    return mentions, {
        "trials": len(payload["records"]),
        "mentions": len(mentions),
        "skipped_generic_company_roles": skipped_generic,
        "by_role": {r: sum(1 for m in mentions if m.role == r) for r in {m.role for m in mentions}},
    }


# ---------- SASL ----------

def split_sasl_investigators(raw: str, place_words: list[str]) -> list[tuple[str, str | None]]:
    """'Isabelle Pache, Lausanne' -> [('Isabelle Pache', 'Lausanne')]
    'D. Köberle (St.Gallen), M. Montemurro (CHUV Lausanne)' -> two people with city hints.

    Tokens made of place/institution words are NOT people: they become an affiliation
    hint for the previous person.
    """
    place_re = re.compile(r"(?<!\w)(" + "|".join(re.escape(w) for w in place_words) + r")(?!\w)", re.I)
    people: list[list] = []  # [name, hint]
    for token in re.split(r"[;,]", raw):
        token = token.strip()
        if not token:
            continue
        paren = re.search(r"\(([^)]*)\)", token)
        hint = paren.group(1).strip() if paren else None
        name = re.sub(r"\([^)]*\)", "", token).strip()
        if not name:
            continue
        if place_re.search(name) or re.search(r"\d", name):  # institution/address, not a person
            if people:
                people[-1][1] = ", ".join(filter(None, [people[-1][1], name]))
            continue
        people.append([name, hint])
    return [(n, h) for n, h in people]


def extract_sasl(payload: dict, place_words: list[str]) -> tuple[list[PersonMention], dict]:
    mentions: list[PersonMention] = []
    for rec in payload["records"]:
        base = dict(source="sasl", source_url=rec["source_url"], collected_at=rec["collected_at"])
        if rec["record_type"] == "study":
            ctx = {
                "study_number": rec["study_number"],
                "title": rec["title"],
                "enrolment_status": rec["enrolment_status"],
                "publication_status": rec["publication_status"],
                "raw_investigator_string": rec["principal_investigators_raw"],
            }
            for i, (name, hint) in enumerate(split_sasl_investigators(rec["principal_investigators_raw"], place_words)):
                parsed = parse_person_name(name)
                if parsed:
                    mentions.append(PersonMention(
                        mention_id=f"sasl:{rec['source_record_id']}:pi{i}",
                        source_record_id=rec["source_record_id"],
                        role="principal_investigator",
                        affiliations=[hint] if hint else [],
                        context=ctx, **base, **parsed))
        elif rec["record_type"] == "center_contact":
            parsed = parse_person_name(rec["contact_name"])
            if parsed:
                mentions.append(PersonMention(
                    mention_id=f"sasl:{rec['source_record_id']}",
                    source_record_id=rec["source_record_id"],
                    role="center_head",
                    affiliations=[f"{rec['hospital']}"],
                    context={"city": rec["city"], "contact_role": rec["contact_role"],
                             "is_transplant_center": rec["is_transplant_center"],
                             "section": rec["section"], "website": rec["website"]},
                    **base, **parsed))
    return mentions, {
        "records": len(payload["records"]),
        "mentions": len(mentions),
        "pi_mentions": sum(1 for m in mentions if m.role == "principal_investigator"),
        "center_heads": sum(1 for m in mentions if m.role == "center_head"),
    }
