"""Skipta's Amendments sheet is the integration bus: read-only, matched to sites by customer name."""
import math
from datetime import date as date_type

from app.google_clients import read_values

AMENDMENTS_RANGE = "Amendments!A2:P"


def read_amendment_flags(sheets, skipta_sid: str, sites: list[dict], today: date_type, lookback_days: int) -> dict:
    site_by_customer = {s["customer_name"].lower(): s["site_id"] for s in sites}
    flags: dict[str, list[dict]] = {}
    for row in read_values(sheets, skipta_sid, AMENDMENTS_RANGE):
        padded = list(row) + [""] * (16 - len(row))
        if padded[7] != "signed" or (padded[10] or "new") != "amend":
            continue
        signed_prefix = padded[9][:10]
        if not signed_prefix:
            continue
        try:
            signed_on = date_type.fromisoformat(signed_prefix)
        except ValueError:
            continue
        if (today - signed_on).days > lookback_days:
            continue
        try:
            total = float(padded[6] or 0)
        except ValueError:
            continue
        if not math.isfinite(total):
            continue
        site_id = site_by_customer.get(padded[2].lower())
        if site_id:
            flags.setdefault(site_id, []).append({"proposal_name": padded[12], "total": total})
    return flags
