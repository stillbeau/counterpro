"""Read the slab feed, tidy the product names and work out which slabs a job uses."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Sequence

import pandas as pd

from .config import (BRANCH_LOCATIONS, BRAND_ALIASES, FINISHES, KNOWN_BRANDS,
                     LOCATION_NAMES, MIN_SLAB_SQFT)

REQUIRED_COLUMNS = ("Product Variant", "On Hand Qty", "Serialized On Hand Cost")
SERIAL_COLUMNS = ("Serial Number", "SKU", "Item Code", "Product SKU", "Serialized Inventory")

_BRANCH = re.compile(r"^\s*(\d+)\s*-\s*")
# "(VER)" after the brand. Known codes are also accepted without the closing
# bracket, which is how some Saskatoon products are written ("Cimstone (SKTN Fresh Linens").
_KNOWN_CODES = "|".join(sorted(LOCATION_NAMES, key=len, reverse=True))
_LOCATION = re.compile(rf"\(\s*(?:({_KNOWN_CODES})\b\s*\)?|([A-Z]{{3}})\s*\))")
_PAREN = re.compile(r"\(\s*([^)]*?)\s*\)")
_THICKNESS = re.compile(r"(\d+(?:\.\d+)?)\s*cm\b", re.IGNORECASE)
_COLOR_CODE = re.compile(r"#\s*(\w+)")
_FINISH_ALT = "|".join(FINISHES)
_FINISH_AFTER = re.compile(rf"cm\s+({_FINISH_ALT})\s*$", re.IGNORECASE)
_FINISH_BEFORE = re.compile(rf"\b({_FINISH_ALT})\s+\d+(?:\.\d+)?\s*cm\b", re.IGNORECASE)


@dataclass(frozen=True)
class Variant:
    brand: str
    color: str
    thickness: str = ""       # "3cm"
    finish: str = ""          # "Polished"
    location: str = ""        # "VER"
    color_code: str = ""      # "6313"
    tags: tuple[str, ...] = field(default_factory=tuple)   # other bracketed codes, e.g. "EX"

    @property
    def name(self) -> str:
        return f"{self.brand} {self.color}".strip()

    @property
    def spec(self) -> str:
        return " ".join(b for b in (self.thickness, self.finish) if b)


def parse_variant(raw: object) -> Variant:
    """Turn '15 - Caesarstone (VER) Blizzard #2141 2cm' into its parts."""
    text = "" if raw is None else str(raw).strip()
    if not text:
        return Variant("Unknown", "Unknown")

    branch = ""
    m = _BRANCH.match(text)
    if m:
        branch = m.group(1)
        text = text[m.end():]

    loc = _LOCATION.search(text)
    if loc:
        brand, rest = text[:loc.start()].strip(), text[loc.end():]
        location = loc.group(1) or loc.group(2)
    else:
        location = BRANCH_LOCATIONS.get(branch, "")
        brand = next((b for b in sorted(KNOWN_BRANDS, key=len, reverse=True)
                      if text.lower().startswith(b.lower())), "")
        if brand:
            rest = text[len(brand):]
        else:
            brand, _, rest = text.partition(" ")
    brand = BRAND_ALIASES.get(brand, brand) or "Unknown"

    tags = tuple(dict.fromkeys(
        t for t in _PAREN.findall(rest) if t and t != location))
    rest = _PAREN.sub(" ", rest).rstrip()

    finish = ""
    fm = _FINISH_AFTER.search(rest)
    if fm:
        finish = fm.group(1).title()
        rest = rest[:fm.start(1)]
    else:
        fm = _FINISH_BEFORE.search(rest)
        if fm:
            finish = fm.group(1).title()
            rest = rest[:fm.start(1)] + rest[fm.end(1):]

    thickness = ""
    tm = _THICKNESS.search(rest)
    if tm:
        thickness = f"{tm.group(1)}cm"
        rest = rest[:tm.start()] + " " + rest[tm.end():]

    color_code = ""
    cm = _COLOR_CODE.search(rest)
    if cm:
        color_code = cm.group(1)
        rest = rest[:cm.start()] + " " + rest[cm.end():]

    color = re.sub(r"\s+", " ", rest).strip(" *-") or "Unknown"
    # "Sandgate Matte 3cm Matte": the finish is named twice, keep it once.
    if finish and color.lower().endswith(" " + finish.lower()):
        color = color[: -len(finish)].strip(" *-") or color
    return Variant(brand=brand, color=color, thickness=thickness, finish=finish,
                   location=location, color_code=color_code, tags=tags)


def location_name(code: str) -> str:
    return LOCATION_NAMES.get(code, code) if code else "Unknown"


def thickness_value(thickness: str) -> float:
    try:
        return float(thickness.lower().replace("cm", ""))
    except ValueError:
        return 0.0


def _to_number(series: pd.Series) -> pd.Series:
    cleaned = series.astype(str).str.replace(r"[$,\s]", "", regex=True)
    return pd.to_numeric(cleaned, errors="coerce")


def clean_slabs(raw: pd.DataFrame) -> pd.DataFrame:
    """One row per slab with numeric quantities and parsed names.
    Slabs with nothing on hand are dropped."""
    df = raw.copy()
    df.columns = df.columns.str.strip()
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"feed is missing column(s): {', '.join(missing)}")

    out = pd.DataFrame({"variant": df["Product Variant"].astype(str).str.strip()})
    out["on_hand"] = _to_number(df["On Hand Qty"])
    out["cost"] = _to_number(df["Serialized On Hand Cost"])
    allocated = _to_number(df["Allocated Qty"]) if "Allocated Qty" in df.columns else 0.0
    out["allocated"] = pd.Series(allocated, index=df.index).fillna(0.0)
    out["available"] = (out["on_hand"] - out["allocated"]).clip(lower=0.0)

    serial_col = next((c for c in SERIAL_COLUMNS if c in df.columns), None)
    if serial_col:
        out["serial"] = df[serial_col].astype(str).str.strip().replace({"nan": "", "None": ""})
    else:
        out["serial"] = ""

    # Extra detail the Moraware page carries and the old sheet did not.
    for name, source in (("bin", "Location"), ("dimensions", "Measurement"), ("supplier", "Supplier")):
        out[name] = df[source].fillna("").astype(str).str.strip() if source in df.columns else ""

    # When the feed says when a slab arrived, the app can show the oldest stock first.
    if "Received Date" in df.columns:
        out["received"] = pd.to_datetime(df["Received Date"].astype(str).str.strip().replace("", pd.NA),
                                         errors="coerce", format="mixed")
    else:
        out["received"] = pd.NaT
    out["received"] = pd.to_datetime(out["received"])

    out = out[(out["on_hand"] >= MIN_SLAB_SQFT) & (out["cost"] > 0)].reset_index(drop=True)
    parsed = out["variant"].map(parse_variant)
    for attr in ("brand", "color", "thickness", "finish", "location", "color_code"):
        out[attr] = parsed.map(lambda v, a=attr: getattr(v, a))
    out["tags"] = parsed.map(lambda v: ", ".join(v.tags))
    out["discontinued"] = parsed.map(lambda v: any(t.lower().startswith("discontinu") for t in v.tags))
    return out


@dataclass
class LoadResult:
    slabs: pd.DataFrame | None
    errors: list[str] = field(default_factory=list)


def load_slabs(sources: Iterable[str]) -> LoadResult:
    """Read every source. A source that fails is reported, not fatal."""
    frames, errors = [], []
    for src in sources:
        try:
            frames.append(clean_slabs(read_source(src)))
        except Exception as exc:  # network, parse or missing columns
            errors.append(f"{src}: {exc}")
    if not frames:
        return LoadResult(None, errors)
    return LoadResult(pd.concat(frames, ignore_index=True), errors)


def read_source(src: str) -> pd.DataFrame:
    """A feed is a CSV (file or URL) or a saved Moraware inventory page (.html)."""
    if str(src).lower().split("?")[0].endswith((".html", ".htm")):
        from .moraware import parse_inventory_html
        return parse_inventory_html(Path(src).read_text(encoding="utf-8", errors="replace"))[0]
    return pd.read_csv(src, dtype=str)


def summarize(slabs: pd.DataFrame) -> pd.DataFrame:
    """One row per product: what is available and what it costs per sq ft.

    Cost per sq ft is total cost over total on-hand area for the product,
    so two slabs of the same colour bought at different prices are averaged.
    """
    grouped = slabs.groupby("variant", sort=False)
    out = grouped.agg(
        on_hand=("on_hand", "sum"),
        available=("available", "sum"),
        cost=("cost", "sum"),
        slab_count=("available", lambda s: int((s > 0).sum())),
        largest_slab=("available", "max"),
        brand=("brand", "first"),
        color=("color", "first"),
        thickness=("thickness", "first"),
        finish=("finish", "first"),
        location=("location", "first"),
        color_code=("color_code", "first"),
        tags=("tags", "first"),
        discontinued=("discontinued", "first"),
        received=("received", "min"),          # the oldest slab of this product
    ).reset_index()
    out["unit_cost"] = out["cost"] / out["on_hand"]
    out["name"] = (out["brand"] + " " + out["color"]).str.strip()
    out["spec"] = (out["thickness"] + " " + out["finish"]).str.strip()
    return out


@dataclass(frozen=True)
class SlabPick:
    serial: str
    sqft: float


def drop_duplicate_serials(slabs: pd.DataFrame) -> pd.DataFrame:
    """The same slab can arrive twice when two pages overlap. Keep the first."""
    has_serial = slabs["serial"] != ""
    dupes = has_serial & slabs.duplicated(subset=["serial", "variant"], keep="first")
    return slabs[~dupes].reset_index(drop=True)


def slabs_for_job(slabs: Sequence[tuple[str, float]], needed_sqft: float) -> list[SlabPick] | None:
    """Fewest slabs that cover the job, by area.

    `slabs` is (serial, available sq ft) for one product. Returns None when
    the product cannot cover the job. Largest slabs are taken first; the last
    one is then swapped for the smallest slab that still covers the job, so a
    full slab is not opened when a smaller one will do.
    """
    usable = sorted(((s, float(a)) for s, a in slabs if a and a > 0),
                    key=lambda p: p[1], reverse=True)
    if needed_sqft <= 0:
        return []
    picked, covered = [], 0.0
    for serial, area in usable:
        picked.append((serial, area))
        covered += area
        if covered >= needed_sqft - 1e-9:
            break
    else:
        return None

    covered_before_last = covered - picked[-1][1]
    remaining = usable[len(picked) - 1:]
    for serial, area in reversed(remaining):          # smallest first
        if covered_before_last + area >= needed_sqft - 1e-9:
            picked[-1] = (serial, area)
            break
    return [SlabPick(s, a) for s, a in picked]


def picks_for_variant(slabs: pd.DataFrame, variant: str, needed_sqft: float) -> list[SlabPick] | None:
    rows = slabs[slabs["variant"] == variant]
    return slabs_for_job(list(zip(rows["serial"], rows["available"])), needed_sqft)


def feed_report(slabs: pd.DataFrame) -> dict:
    """Quick health numbers for the staff panel."""
    return {
        "slabs": int(len(slabs)),
        "products": int(slabs["variant"].nunique()),
        "allocated_slabs": int((slabs["allocated"] > 0).sum()),
        "unparsed": sorted(slabs.loc[(slabs["brand"] == "Unknown") | (slabs["color"] == "Unknown")
                                     | (slabs["thickness"] == ""), "variant"].unique()),
        "by_location": slabs.groupby("location")["variant"].count().to_dict(),
    }
