"""Deterministic gate for LLM-proposed moves — the UNMATCHED sibling. Pure functions, no I/O."""
from collections import Counter
from dataclasses import asdict, dataclass, field


@dataclass
class VerifiedMove:
    person_id: str
    from_site: str
    to_site: str
    reason: str
    valid: bool = True
    issues: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return asdict(self)


def verify_moves(moves: list[dict], crews: list[dict], sites: list[dict], assignments: list[dict]) -> list[VerifiedMove]:
    people = {c["person_id"] for c in crews}
    site_ids = {s["site_id"] for s in sites}
    current = {a["person_id"]: a["site_id"] for a in assignments}
    counts = Counter(m.get("person_id", "") for m in moves)
    out = []
    for move in moves:
        person = move.get("person_id", "")
        from_site = move.get("from_site", "") or ""
        to_site = move.get("to_site", "")
        issues = []
        if person not in people:
            issues.append(f"unknown person {person or '(blank)'}")
        if to_site not in site_ids:
            issues.append(f"unknown site {to_site or '(blank)'}")
        if person in people:
            actual = current.get(person, "")
            if from_site != actual:
                issues.append(f"from_site {from_site or '(unassigned)'} does not match current {actual or '(unassigned)'}")
        if counts[person] > 1:
            issues.append("duplicate move for person in this plan")
        out.append(VerifiedMove(person, from_site, to_site, move.get("reason", ""), not issues, issues))
    return out


def coverage_warnings(crews: list[dict], sites: list[dict], assignments: list[dict], verified: list[VerifiedMove]) -> list[str]:
    post = {a["person_id"]: a["site_id"] for a in assignments}
    for move in verified:
        if move.valid:
            post[move.person_id] = move.to_site
    crafts_by_person = {c["person_id"]: set(c["crafts"]) for c in crews}
    warnings = []
    for site in sites:
        needed = set(site["needed_crafts"])
        if not needed:
            continue
        present: set[str] = set()
        for person, site_id in post.items():
            if site_id == site["site_id"]:
                present |= crafts_by_person.get(person, set())
        missing = needed - present
        if missing:
            warnings.append(f"{site['site_id']}: missing craft(s) {', '.join(sorted(missing))}")
    return warnings
