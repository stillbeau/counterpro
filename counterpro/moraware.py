"""Read slab inventory straight from a Moraware Systemize inventory page.

The page is the saved inventory view (one row per serialized slab). Columns are
found by their header text, so reordering or adding columns in the Moraware view
does not break this. The HTML is only ever parsed, never rendered or executed.
"""
from __future__ import annotations

import re
from html.parser import HTMLParser

import pandas as pd

# Header text in Moraware -> column name the rest of the app uses.
COLUMN_MAP = {
    "product variant": "Product Variant",
    "serial number": "Serial Number",
    "serialized on hand cost": "Serialized On Hand Cost",
    "measurement": "Measurement",
    "location": "Location",
    "supplier": "Supplier",
    "batch number": "Batch Number",
    "po number": "PO Number",
    "on hand qty": "On Hand Qty",
    "allocated qty": "Allocated Qty",
    "available qty": "Available Qty",
    "image url": "Image URL",
    "image": "Image URL",
    "photo": "Image URL",
    "photo url": "Image URL",
}
NEEDED = ("Product Variant", "Serialized On Hand Cost")
# Any other column whose heading looks like a date says how long a slab has been
# in stock (for example "Received Date"). The first one found is used.
_DATE_HEADING = re.compile(r"\b(received|receipt|receive|date|created|purchased)\b", re.IGNORECASE)


def _map_headers(row: list[str]) -> list[str]:
    headers, dated = [], False
    for cell in row:
        name = COLUMN_MAP.get(cell.lower())
        if name is None and not dated and _DATE_HEADING.search(cell):
            name, dated = "Received Date", True
        headers.append(name or cell)
    return headers

# Length x width in inches. The separator is normally "×"; the replacement character
# covers a page that arrived in the wrong character set, so the size is still read.
_DIMENSIONS = re.compile(r"(\d+(?:\.\d+)?)\s*(?:\"|in\b|″)?\s*[x×\ufffd*]\s*(\d+(?:\.\d+)?)", re.IGNORECASE)


class NotAnInventoryPage(ValueError):
    """The file is not a Moraware inventory page this app can read."""


def _clean(text: str) -> str:
    # Drop Moraware's icon-font glyphs (private-use characters) and squeeze whitespace.
    text = "".join(ch for ch in text if not 0xE000 <= ord(ch) <= 0xF8FF)
    return " ".join(text.replace("\xa0", " ").split())


class _Tables(HTMLParser):
    """Collects every table as rows of cell text, plus the page title and the
    'View / Product / Show only rows containing' filter description."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tables: list[dict] = []
        self._stack: list[dict] = []
        self._row: list[str] | None = None
        self._cell: list[str] | None = None
        self._in_title = False
        self.title = ""

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            table = {"id": dict(attrs).get("id") or "", "class": dict(attrs).get("class") or "", "rows": []}
            self.tables.append(table)
            self._stack.append(table)
        elif tag == "tr" and self._stack:
            self._row = []
        elif tag in ("td", "th") and self._row is not None:
            self._cell = []
        elif tag == "title":
            self._in_title = True

    def handle_endtag(self, tag):
        if tag == "table" and self._stack:
            self._stack.pop()
        elif tag in ("td", "th") and self._cell is not None and self._row is not None:
            self._row.append(_clean("".join(self._cell)))
            self._cell = None
        elif tag == "tr" and self._row is not None and self._stack:
            self._stack[-1]["rows"].append(self._row)
            self._row = None
        elif tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)
        elif self._in_title:
            self.title += data


def sqft_from_measurement(text: object) -> float | None:
    """'120" x 56"' -> 46.67 (square feet). None when it is not a length x width."""
    m = _DIMENSIONS.search(str(text or ""))
    if not m:
        return None
    return float(m.group(1)) * float(m.group(2)) / 144.0


def parse_inventory_html(html: str) -> tuple[pd.DataFrame, dict]:
    """Return (rows, info). `rows` has the same column names as the old sheet feed
    so it goes through the normal clean-up; `info` describes the page."""
    parser = _Tables()
    parser.feed(html)

    best: tuple[list[str], list[list[str]]] | None = None
    for table in parser.tables:
        for i, row in enumerate(table["rows"]):
            headers = _map_headers(row)
            if all(n in headers for n in NEEDED):
                body = [r for r in table["rows"][i + 1:] if len(r) == len(row)]
                if best is None or len(body) > len(best[1]):
                    best = (headers, body)
                break
    if best is None:
        raise NotAnInventoryPage(
            "No inventory table found. Save the Moraware inventory view with the "
            "Product Variant and Serialized On Hand Cost columns showing.")
    headers, body = best

    df = pd.DataFrame(body, columns=headers)
    df = df.loc[:, ~df.columns.duplicated()]
    df = df[df["Product Variant"].str.strip() != ""].reset_index(drop=True)

    if "On Hand Qty" not in df.columns:
        if "Measurement" not in df.columns:
            raise NotAnInventoryPage(
                "The view needs either the Measurement column or On Hand Qty so slab size is known.")
        # A serialized row with no readable size cannot be priced; it is reported, not guessed.
        areas = [sqft_from_measurement(m) for m in df["Measurement"]]
        df["On Hand Qty"] = ["" if a is None else f"{a:.4f}" for a in areas]

    filters = {}
    for table in parser.tables:
        if "pageInfo" in table["class"]:
            for row in table["rows"]:
                if len(row) >= 2 and row[0].endswith(":"):
                    filters[row[0].rstrip(":")] = row[1]
    info = {
        "title": _clean(parser.title),
        "rows": int(len(df)),
        "unsized": int((df["On Hand Qty"] == "").sum()),
        "filters": filters,
        "columns": list(df.columns),
    }
    return df, info
