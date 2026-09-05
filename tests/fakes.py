"""Shared Sheets fake: multiple spreadsheets keyed by id, tabs keyed by name. Mirrors just enough of the values() surface."""
import re


class FakeValues:
    def __init__(self, stores):
        self.stores = stores  # sid -> {tab: [rows]} (no header rows)
        self.calls = []  # (verb, num_retries) per executed request — pins the retry policy per verb

    def _tab(self, range):
        return range.split("!")[0]

    def get(self, spreadsheetId, range):
        # unknown spreadsheet raises like the real API; unknown tab is lenient
        self._verb = "get"
        self._result = {"values": self.stores[spreadsheetId].get(self._tab(range), [])}
        return self

    def append(self, spreadsheetId, range, valueInputOption, body):
        self._verb = "append"
        self.stores.setdefault(spreadsheetId, {}).setdefault(self._tab(range), []).extend(body["values"])
        self._result = {}
        return self

    def update(self, spreadsheetId, range, valueInputOption, body):
        self._verb = "update"
        tab = self._tab(range)
        cell = range.split("!")[1]
        m = re.match(r"([A-Z]+)(\d+)", cell)
        col = ord(m.group(1)) - ord("A")  # single-letter columns only — fine for A..H
        row = int(m.group(2)) - 2  # store index (row 1 = header)
        rows = self.stores[spreadsheetId][tab]
        while len(rows[row]) <= col:
            rows[row].append("")
        for offset, value in enumerate(body["values"][0]):
            rows[row][col + offset] = value
        self._result = {}
        return self

    def execute(self, num_retries=0):
        self.calls.append((self._verb, num_retries))
        return self._result


class FakeSheets:
    def __init__(self, stores):
        self._values = FakeValues(stores)
        self.stores = self._values.stores

    def spreadsheets(self):
        return self

    def values(self):
        return self._values
