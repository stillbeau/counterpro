"""Where an uploaded Moraware inventory is kept between visits.

It is a small folder on the machine running the app (set COUNTERPRO_DATA_DIR to
move it). It holds slab costs, so it is never committed to git.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pandas as pd

_ROWS = "moraware_inventory.csv"
_META = "moraware_inventory.json"


def data_dir() -> Path:
    return Path(os.environ.get("COUNTERPRO_DATA_DIR", "") or Path(__file__).resolve().parent.parent / ".counterpro")


@dataclass(frozen=True)
class Snapshot:
    rows: pd.DataFrame          # raw rows, sheet-style column names
    saved_at: datetime
    files: tuple[str, ...]
    filters: dict


def stamp() -> float:
    """Changes whenever the stored inventory changes; used to refresh caches."""
    path = data_dir() / _META
    return path.stat().st_mtime if path.exists() else 0.0


def save(rows: pd.DataFrame, files: list[str], filters: dict, now: datetime | None = None) -> None:
    folder = data_dir()
    folder.mkdir(parents=True, exist_ok=True)
    tmp = folder / (_ROWS + ".tmp")
    rows.to_csv(tmp, index=False)
    tmp.replace(folder / _ROWS)
    meta = {"saved_at": (now or datetime.now()).isoformat(timespec="seconds"),
            "files": list(files), "filters": filters, "rows": int(len(rows))}
    tmp = folder / (_META + ".tmp")
    tmp.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    tmp.replace(folder / _META)      # written last: its timestamp is the change signal


def load() -> Snapshot | None:
    folder = data_dir()
    try:
        meta = json.loads((folder / _META).read_text(encoding="utf-8"))
        rows = pd.read_csv(folder / _ROWS, dtype=str, keep_default_na=False)
    except (OSError, ValueError):
        return None
    return Snapshot(rows=rows, saved_at=datetime.fromisoformat(meta["saved_at"]),
                    files=tuple(meta.get("files", [])), filters=meta.get("filters", {}))


def clear() -> None:
    for name in (_ROWS, _META):
        try:
            (data_dir() / name).unlink()
        except OSError:
            pass
