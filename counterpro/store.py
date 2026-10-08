"""Where an uploaded Moraware inventory is kept between visits.

Two places are supported:

* a private GitHub repository (use this on Streamlit Community Cloud, whose
  disk is wiped whenever the app restarts), or
* a folder beside the app (fine on a machine you run yourself).

The inventory holds slab costs. It is never committed to this repository.
"""
from __future__ import annotations

import base64
import json
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pandas as pd
import requests

FILE_NAME = "moraware_inventory.json"


class StoreError(RuntimeError):
    """The inventory could not be read from or written to its store."""


@dataclass(frozen=True)
class Snapshot:
    rows: pd.DataFrame          # raw rows, sheet-style column names
    saved_at: datetime
    files: tuple[str, ...]
    filters: dict


def _encode(rows: pd.DataFrame, files: list[str], filters: dict, now: datetime | None) -> str:
    return json.dumps({
        "saved_at": (now or datetime.now()).isoformat(timespec="seconds"),
        "files": list(files),
        "filters": filters,
        "columns": list(rows.columns),
        "rows": rows.fillna("").astype(str).values.tolist(),
    }, ensure_ascii=False, indent=0)


def _decode(text: str) -> Snapshot:
    """Two shapes are accepted: rows already read from a page (what the app
    saves after an upload), or the pages themselves (what the browser sync
    extension sends, so there is only one place that knows how to read them)."""
    doc = json.loads(text)
    saved_at = datetime.fromisoformat(doc["saved_at"]).replace(tzinfo=None)
    if "pages" in doc:
        from .moraware import parse_inventory_html
        frames, filters, names = [], {}, []
        for page in doc["pages"]:
            rows, info = parse_inventory_html(page["html"])
            frames.append(rows)
            names.append(page.get("name") or page.get("url") or "page")
            for key, value in info["filters"].items():
                filters[key] = f"{filters[key]}; {value}" if key in filters and value not in filters[key] else value
        if not frames:
            raise ValueError("no pages in the saved inventory")
        return Snapshot(rows=pd.concat(frames, ignore_index=True).fillna(""), saved_at=saved_at,
                        files=tuple(names), filters=filters)
    return Snapshot(rows=pd.DataFrame(doc["rows"], columns=doc["columns"], dtype=str),
                    saved_at=saved_at, files=tuple(doc.get("files", [])), filters=doc.get("filters", {}))


class LocalStore:
    """A folder on the machine running the app."""
    durable = False

    def __init__(self, folder: str | Path | None = None):
        self.last_good: Snapshot | None = None
        self.folder = Path(folder or os.environ.get("COUNTERPRO_DATA_DIR", "")
                           or Path(__file__).resolve().parent.parent / ".counterpro")

    @property
    def where(self) -> str:
        return "on this server only"

    def stamp(self) -> float:
        """Changes whenever the stored inventory changes; used to refresh caches."""
        path = self.folder / FILE_NAME
        return path.stat().st_mtime if path.exists() else 0.0

    def load(self) -> Snapshot | None:
        try:
            return _decode((self.folder / FILE_NAME).read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise StoreError(f"the saved inventory file is damaged ({exc})") from exc

    def save(self, rows: pd.DataFrame, files: list[str], filters: dict, now: datetime | None = None) -> None:
        self.folder.mkdir(parents=True, exist_ok=True)
        tmp = self.folder / (FILE_NAME + ".tmp")
        tmp.write_text(_encode(rows, files, filters, now), encoding="utf-8")
        tmp.replace(self.folder / FILE_NAME)

    def clear(self) -> None:
        try:
            (self.folder / FILE_NAME).unlink()
        except FileNotFoundError:
            pass


class GitHubStore:
    """One JSON file in a private GitHub repository, read and written through
    the GitHub API with a token that can reach only that repository."""
    durable = True

    def __init__(self, repo: str, token: str, path: str = FILE_NAME, branch: str = "",
                 api_url: str = "https://api.github.com", timeout: float = 15):
        self.repo, self.path, self.branch = repo.strip().strip("/"), path.strip("/"), branch.strip()
        self._url = f"{api_url.rstrip('/')}/repos/{self.repo}/contents/{self.path}"
        self._headers = {"Authorization": f"Bearer {token.strip()}",
                         "Accept": "application/vnd.github+json",
                         "X-GitHub-Api-Version": "2022-11-28"}
        self._timeout = timeout
        self.last_good: Snapshot | None = None
        self._etag: str | None = None
        self._cached: tuple[Snapshot, str] | None = None     # (snapshot, file sha)

    @property
    def where(self) -> str:
        return f"in the GitHub repository {self.repo}"

    def stamp(self) -> float:
        return 1.0          # always worth asking; fetch() is time-cached by the app

    def _call(self, method: str, **kwargs) -> requests.Response:
        params = {"ref": self.branch} if self.branch and method == "GET" else None
        try:
            return requests.request(method, self._url, headers={**self._headers, **kwargs.pop("headers", {})},
                                    params=params, timeout=self._timeout, **kwargs)
        except requests.RequestException as exc:
            raise StoreError(f"GitHub could not be reached ({type(exc).__name__})") from exc

    def _explain(self, resp: requests.Response, doing: str) -> StoreError:
        hints = {401: "the token was rejected; it may have expired",
                 403: "the token is not allowed to do this; it needs Contents read and write on this repository",
                 404: f"the repository {self.repo} was not found, or the token cannot see it",
                 409: "the file changed at the same moment; try again",
                 422: "GitHub refused the change; try again"}
        return StoreError(f"Could not {doing}: {hints.get(resp.status_code, f'GitHub answered {resp.status_code}')}.")

    def _fetch(self) -> tuple[Snapshot, str] | None:
        headers = {"If-None-Match": self._etag} if self._etag and self._cached else {}
        resp = self._call("GET", headers=headers)
        if resp.status_code == 304 and self._cached:
            return self._cached
        if resp.status_code == 404:
            # Missing file is normal before the first upload; a missing repo is a setup error.
            if "not found" in resp.text.lower() and self._repo_missing():
                raise self._explain(resp, "read the saved inventory")
            self._cached, self._etag = None, None
            return None
        if resp.status_code != 200:
            raise self._explain(resp, "read the saved inventory")
        try:
            doc = resp.json()
            if doc.get("content"):
                text = base64.b64decode(doc["content"]).decode("utf-8")
            else:       # GitHub leaves the content out of this answer for files over 1 MB
                raw = self._call("GET", headers={"Accept": "application/vnd.github.raw+json"})
                if raw.status_code != 200:
                    raise self._explain(raw, "read the saved inventory")
                text = raw.content.decode("utf-8")
            snapshot = _decode(text)
        except StoreError:
            raise
        except (ValueError, KeyError, TypeError) as exc:
            raise StoreError(f"the saved inventory in {self.repo} is damaged ({type(exc).__name__})") from exc
        self._cached, self._etag = (snapshot, doc["sha"]), resp.headers.get("ETag")
        return self._cached

    def _repo_missing(self) -> bool:
        repo_url = self._url.split("/contents/")[0]
        try:
            return requests.get(repo_url, headers=self._headers, timeout=self._timeout).status_code != 200
        except requests.RequestException:
            return False

    def load(self) -> Snapshot | None:
        found = self._fetch()
        return found[0] if found else None

    def check(self) -> None:
        """Raise StoreError when the repository or token is not usable."""
        self._fetch()

    def save(self, rows: pd.DataFrame, files: list[str], filters: dict, now: datetime | None = None) -> None:
        text = _encode(rows, files, filters, now)
        existing = self._fetch()
        body = {"message": f"Update slab inventory ({len(rows)} slabs)",
                "content": base64.b64encode(text.encode("utf-8")).decode("ascii")}
        if existing:
            body["sha"] = existing[1]
        if self.branch:
            body["branch"] = self.branch
        resp = self._call("PUT", json=body)
        if resp.status_code not in (200, 201):
            raise self._explain(resp, "save the inventory")
        self._cached, self._etag = None, None

    def clear(self) -> None:
        existing = self._fetch()
        if not existing:
            return
        body = {"message": "Remove uploaded slab inventory", "sha": existing[1]}
        if self.branch:
            body["branch"] = self.branch
        resp = self._call("DELETE", json=body)
        if resp.status_code not in (200, 204, 404):
            raise self._explain(resp, "remove the saved inventory")
        self._cached, self._etag = None, None


def from_settings(settings: dict | None = None):
    """Pick the store. `settings` is the [inventory_store] block from Streamlit
    secrets; COUNTERPRO_STORE_REPO / COUNTERPRO_STORE_TOKEN do the same job."""
    settings = dict(settings or {})
    repo = os.environ.get("COUNTERPRO_STORE_REPO") or settings.get("repo", "")
    token = os.environ.get("COUNTERPRO_STORE_TOKEN") or settings.get("token", "")
    if repo and token:
        return GitHubStore(repo, token,
                           path=os.environ.get("COUNTERPRO_STORE_PATH") or settings.get("path", FILE_NAME),
                           branch=os.environ.get("COUNTERPRO_STORE_BRANCH") or settings.get("branch", ""),
                           api_url=os.environ.get("COUNTERPRO_STORE_API") or settings.get("api_url", "https://api.github.com"))
    return LocalStore()
