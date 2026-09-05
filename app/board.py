"""The board spreadsheet: Crews/Sites/Assignments/Days reads and Assignment/Days writes."""
import math

from app.google_clients import read_values

CREWS_RANGE = "Crews!A2:D"
SITES_RANGE = "Sites!A2:I"
ASSIGN_TAB = "Assignments"
ASSIGN_RANGE = f"{ASSIGN_TAB}!A2:D"
DAYS_TAB = "Days"
DAYS_RANGE = f"{DAYS_TAB}!A2:C"


def _csv(value: str) -> list[str]:
    return [t.strip() for t in (value or "").split(",") if t.strip()]


def _pad(row: list, width: int) -> list:
    return list(row) + [""] * (width - len(row))


def _coord(value: str):
    try:
        coord = float(value)
    except ValueError:
        return None
    return coord if math.isfinite(coord) else None


def display_name(site: dict) -> str:
    customer = site["customer_name"] if site["customer_name"] not in ("-", "—") else ""
    return site["job_name"] or customer or site["site_id"]


def read_crews(sheets, sid: str) -> list[dict]:
    out = []
    for row in read_values(sheets, sid, CREWS_RANGE):
        p = _pad(row, 4)
        out.append({"person_id": p[0], "name": p[1], "crafts": _csv(p[2]), "crew": p[3]})
    return out


def read_sites(sheets, sid: str) -> list[dict]:
    out = []
    for row in read_values(sheets, sid, SITES_RANGE):
        p = _pad(row, 9)
        out.append({
            "site_id": p[0], "customer_name": p[1], "address": p[2],
            "lat": _coord(p[3]), "lon": _coord(p[4]), "needs": _csv(p[5]) or ["outdoor"],
            "needed_crafts": _csv(p[6]), "notes": p[7], "job_name": p[8],
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


def apply_moves(sheets, sid: str, date: str, moves: list[dict]) -> int:
    current = {a["person_id"]: a for a in read_assignments(sheets, sid, date)}
    applied = 0
    for move in moves:
        person, to_site = move["person_id"], move["to_site"]
        existing = current.get(person)
        if existing:
            sheets.spreadsheets().values().update(
                spreadsheetId=sid, range=f"{ASSIGN_TAB}!C{existing['row']}", valueInputOption="RAW",
                body={"values": [[to_site]]},
            ).execute(num_retries=2)
        else:
            # No retries on appends: a retry after a committed-but-failed response would duplicate the row.
            sheets.spreadsheets().values().append(
                spreadsheetId=sid, range=ASSIGN_RANGE, valueInputOption="RAW",
                body={"values": [[date, person, to_site, ""]]},
            ).execute()
        applied += 1
    return applied


def set_condition(sheets, sid: str, date: str, condition: str) -> None:
    for index, row in enumerate(read_values(sheets, sid, DAYS_RANGE)):
        if _pad(row, 3)[0] == date:
            sheets.spreadsheets().values().update(
                spreadsheetId=sid, range=f"{DAYS_TAB}!B{index + 2}", valueInputOption="RAW",
                body={"values": [[condition]]},
            ).execute(num_retries=2)
            return
    sheets.spreadsheets().values().append(
        spreadsheetId=sid, range=DAYS_RANGE, valueInputOption="RAW", body={"values": [[date, condition, ""]]}
    ).execute()
