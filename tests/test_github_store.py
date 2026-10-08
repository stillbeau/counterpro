"""GitHubStore against a small stand-in for the GitHub contents API."""
import base64
import hashlib
import json
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pandas as pd
import pytest

from counterpro import store
from counterpro.inventory import clean_slabs
from counterpro.moraware import parse_inventory_html

PAGE = Path(__file__).parent / "fixtures" / "moraware_inventory.html"
TOKEN = "test-token"
REPO = "someone/counterpro-data"


class FakeGitHub(BaseHTTPRequestHandler):
    files: dict = {}          # path -> (content_b64, sha)
    calls: list = []
    fail_with: int | None = None

    def log_message(self, *args):
        pass

    def _send(self, status, body=None, headers=None):
        data = json.dumps(body or {}).encode()
        self.send_response(status)
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(data) if status != 304 else 0))
        self.end_headers()
        if status != 304:
            self.wfile.write(data)

    def _route(self):
        type(self).calls.append((self.command, self.path.split("?")[0]))
        if self.headers.get("Authorization") != f"Bearer {TOKEN}":
            return self._send(401, {"message": "Bad credentials"})
        if type(self).fail_with:
            return self._send(type(self).fail_with, {"message": "nope"})
        path = self.path.split("?")[0]
        if path == f"/repos/{REPO}":
            return self._send(200, {"full_name": REPO})
        prefix = f"/repos/{REPO}/contents/"
        if not path.startswith(prefix):
            return self._send(404, {"message": "Not Found"})
        name = path[len(prefix):]
        length = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(length) or b"{}") if length else {}
        current = type(self).files.get(name)
        if self.command == "GET":
            if not current:
                return self._send(404, {"message": "Not Found"})
            etag = f'"{current[1]}"'
            if self.headers.get("If-None-Match") == etag:
                return self._send(304, headers={"ETag": etag})
            return self._send(200, {"content": current[0], "sha": current[1]}, {"ETag": etag})
        if self.command == "PUT":
            if current and body.get("sha") != current[1]:
                return self._send(409, {"message": "sha mismatch"})
            if not current and body.get("sha"):
                return self._send(422, {"message": "sha given for new file"})
            sha = hashlib.sha1(body["content"].encode()).hexdigest()
            type(self).files[name] = (body["content"], sha)
            return self._send(200 if current else 201, {"content": {"sha": sha}})
        if self.command == "DELETE":
            if not current or body.get("sha") != current[1]:
                return self._send(409, {"message": "sha mismatch"})
            del type(self).files[name]
            return self._send(200, {})

    do_GET = do_PUT = do_DELETE = _route


@pytest.fixture
def github():
    FakeGitHub.files, FakeGitHub.calls, FakeGitHub.fail_with = {}, [], None
    server = HTTPServer(("127.0.0.1", 0), FakeGitHub)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()


@pytest.fixture
def rows():
    return parse_inventory_html(PAGE.read_text(encoding="utf-8"))


def make(api, token=TOKEN, repo=REPO):
    return store.GitHubStore(repo, token, api_url=api, timeout=5)


def test_empty_repo_has_no_inventory(github):
    assert make(github).load() is None


def test_save_then_load_from_a_fresh_app(github, rows):
    raw, info = rows
    make(github).save(raw, ["inventory.html"], info["filters"], now=datetime(2026, 10, 8, 11, 2))
    stored = json.loads(base64.b64decode(FakeGitHub.files[store.FILE_NAME][0]))
    assert stored["saved_at"] == "2026-10-08T11:02:00" and len(stored["rows"]) == 10

    snap = make(github).load()                      # a restarted app: new object, nothing in memory
    assert snap.saved_at == datetime(2026, 10, 8, 11, 2) and snap.files == ("inventory.html",)
    pd.testing.assert_frame_equal(clean_slabs(snap.rows), clean_slabs(raw))


def test_second_save_replaces_the_first(github, rows):
    raw, info = rows
    gh = make(github)
    gh.save(raw, ["a.html"], {})
    gh.save(raw.head(3), ["b.html"], {})
    snap = make(github).load()
    assert len(snap.rows) == 3 and snap.files == ("b.html",)


def test_unchanged_file_is_not_downloaded_twice(github, rows):
    raw, _ = rows
    gh = make(github)
    gh.save(raw, ["a.html"], {})
    first = gh.load()
    second = gh.load()                              # server answers 304; cached copy is reused
    assert second is first


def test_picks_up_a_change_made_elsewhere(github, rows):
    raw, _ = rows
    reader = make(github)
    make(github).save(raw, ["a.html"], {})
    assert len(reader.load().rows) == 10
    make(github).save(raw.head(4), ["pushed-by-extension.html"], {})
    assert len(reader.load().rows) == 4


def test_clear(github, rows):
    raw, _ = rows
    gh = make(github)
    gh.save(raw, ["a.html"], {})
    gh.clear()
    assert gh.load() is None and store.FILE_NAME not in FakeGitHub.files
    gh.clear()                                      # nothing there: no error


def test_bad_token_is_explained(github, rows):
    raw, _ = rows
    with pytest.raises(store.StoreError, match="token was rejected"):
        make(github, token="wrong").load()
    with pytest.raises(store.StoreError, match="token was rejected"):
        make(github, token="wrong").save(raw, ["a.html"], {})
    assert FakeGitHub.files == {}


def test_missing_repo_is_explained(github):
    with pytest.raises(store.StoreError, match="was not found"):
        make(github, repo="someone/typo").load()


def test_forbidden_write_is_explained(github, rows):
    raw, _ = rows
    gh = make(github)
    assert gh.load() is None
    FakeGitHub.fail_with = 403
    with pytest.raises(store.StoreError, match="Contents read and write"):
        gh.save(raw, ["a.html"], {})


def test_unreachable_is_explained(rows):
    raw, _ = rows
    gh = store.GitHubStore(REPO, TOKEN, api_url="http://127.0.0.1:9", timeout=1)
    with pytest.raises(store.StoreError, match="could not be reached"):
        gh.load()


def test_token_never_appears_in_errors(github):
    try:
        make(github, token="super-secret-token").load()
    except store.StoreError as exc:
        assert "super-secret-token" not in str(exc)


def test_from_settings_picks_the_store(monkeypatch, tmp_path):
    for name in ("COUNTERPRO_STORE_REPO", "COUNTERPRO_STORE_TOKEN"):
        monkeypatch.delenv(name, raising=False)
    assert isinstance(store.from_settings({}), store.LocalStore)
    assert isinstance(store.from_settings({"repo": REPO}), store.LocalStore)       # no token: not usable
    gh = store.from_settings({"repo": REPO, "token": TOKEN})
    assert isinstance(gh, store.GitHubStore) and gh.durable and REPO in gh.where
    monkeypatch.setenv("COUNTERPRO_STORE_REPO", REPO)
    monkeypatch.setenv("COUNTERPRO_STORE_TOKEN", TOKEN)
    assert isinstance(store.from_settings(None), store.GitHubStore)
