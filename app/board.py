"""The board spreadsheet: Crews/Sites/Assignments/Days reads and Assignment/Days writes."""
from app.google_clients import read_values

CREWS_RANGE = "Crews!A2:D"
SITES_RANGE = "Sites!A2:H"
ASSIGN_TAB = "Assignments"
ASSIGN_RANGE = f"{ASSIGN_TAB}!A2:D"
DAYS_TAB = "Days"
DAYS_RANGE = f"{DAYS_TAB}!A2:C"


def _csv(value: str) -> list[str]:
    return [t.strip() for t in (value or "").split(",") if t.strip()]


def _pad(row: list, width: int) -> list:
    return list(row) + [""] * (width - len(row))


def _coord(value: str):
    return float(value) if value else None


def read_crews(sheets, sid: str) -> list[dict]:
    out = []
    for row in read_values(sheets, sid, CREWS_RANGE):
        p = _pad(row, 4)
        out.append({"person_id": p[0], "name": p[1], "crafts": _csv(p[2]), "crew": p[3]})
    return out


def read_sites(sheets, sid: str) -> list[dict]:
    out = []
    for row in read_values(sheets, sid, SITES_RANGE):
        p = _pad(row, 8)
        out.append({
            "site_id": p[0], "customer_name": p[1], "address": p[2],
            "lat": _coord(p[3]), "lon": _coord(p[4]), "work_type": p[5] or "outdoor",
            "needed_crafts": _csv(p[6]), "notes": p[7],
        })
    return out


def read_assignments(sheets, sid: str, date: str) -> list[dict]:
    out = []
    for index, row in enumerate(read_values(sheets, sid, ASSIGN_RANGE)):
        p = _pad(row, 4)
        if p[0] == date:
            out.append({"row": index + 2, "person_id": p[1], "site_id": p[2], "note": p[3]})
    return out


def read_condition_override(sheets, sid: str, date: str) -> str:
    for row in read_values(sheets, sid, DAYS_RANGE):
        p = _pad(row, 3)
        if p[0] == date:
            return p[1]
    return ""
