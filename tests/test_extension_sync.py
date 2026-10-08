"""The sync extension's logic, run in Node against stand-ins for Moraware and
GitHub, then read back through the app's own store. This checks the whole hand-off:
what the extension sends is what the app can price."""
import json
import shutil
import subprocess
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from counterpro import store
from counterpro.inventory import clean_slabs, drop_duplicate_serials, summarize
from counterpro.moraware import parse_inventory_html
from tests.test_github_store import REPO, TOKEN, FakeGitHub, github  # noqa: F401  (fixture)

ROOT = Path(__file__).parent.parent
PAGE = (Path(__file__).parent / "fixtures" / "moraware_inventory.html").read_text(encoding="utf-8")
SECOND = PAGE.replace("(VER)", "(ABB)").replace("15 - ", "17 - ").replace("VER - ", "ABB - ")

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")


class FakeMoraware(BaseHTTPRequestHandler):
    seen: list = []

    def log_message(self, *args):
        pass

    def do_GET(self):
        type(self).seen.append(self.path)
        if "view=1" in self.path:
            body, status = PAGE, 200
        elif "view=2" in self.path:
            body, status = SECOND, 200
        elif "signedout" in self.path:
            body, status = "<html><body><form>Please sign in</form></body></html>", 200
        elif "empty" in self.path:
            body, status = PAGE.split("<tbody>\n<tr class")[0] + "</tbody></table></div></body></html>", 200
        else:
            body, status = "missing", 404
        data = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


@pytest.fixture
def moraware():
    FakeMoraware.seen = []
    server = HTTPServer(("127.0.0.1", 0), FakeMoraware)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()


def run_sync(github, views, token=TOKEN, repo=REPO):
    settings = {"views": views, "repo": repo, "token": token, "apiUrl": github, "path": store.FILE_NAME}
    out = subprocess.run(["node", str(ROOT / "tests" / "ext_sync_runner.mjs"), json.dumps(settings)],
                         capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout.strip().splitlines()[-1])


def test_sync_sends_both_views_and_the_app_reads_them(github, moraware):
    result = run_sync(github, [f"{moraware}/sys/inventory?&view=1", f"{moraware}/sys/inventory?&view=2&pageSize=9999"])
    assert result["ok"] and result["slabs"] == 20
    assert [p["slabs"] for p in result["pages"]] == [10, 10]
    assert result["pages"][0]["name"] == "15 - Stone & Quartz (VER)"
    # the first address had no page size, so the full list was asked for; the second was left alone
    assert FakeMoraware.seen[0].endswith("view=1&pagesize=9999") and FakeMoraware.seen[1].endswith("pageSize=9999")

    snap = store.GitHubStore(REPO, TOKEN, api_url=github).load()
    assert snap.saved_at == datetime(2026, 10, 8, 6, 30) and len(snap.files) == 2
    slabs = drop_duplicate_serials(clean_slabs(snap.rows))
    assert len(slabs) == 20 and set(slabs["location"]) == {"VER", "ABB"}

    # identical to reading the original page directly: trimming loses nothing the app uses
    direct = clean_slabs(parse_inventory_html(PAGE)[0])
    synced = slabs[slabs["location"] == "VER"].reset_index(drop=True)
    for column in ("variant", "serial", "on_hand", "cost", "bin", "dimensions", "supplier"):
        assert list(synced[column]) == list(direct[column]), column
    assert len(summarize(slabs)) == 18


def test_sent_page_carries_only_the_table(github, moraware):
    run_sync(github, [f"{moraware}/sys/inventory?&view=1"])
    import base64
    doc = json.loads(base64.b64decode(FakeGitHub.files[store.FILE_NAME][0]))
    html = doc["pages"][0]["html"]
    assert "<script" not in html and "href=" not in html and "mjtclick" not in html
    assert "Jobs" not in html                      # the navigation menu is not sent
    assert len(html) < len(PAGE) / 2


def test_signed_out_sends_nothing_and_keeps_the_old_inventory(github, moraware):
    assert run_sync(github, [f"{moraware}/sys/inventory?&view=1"])["ok"]
    before = dict(FakeGitHub.files)
    result = run_sync(github, [f"{moraware}/sys/inventory?&view=1", f"{moraware}/signedout"])
    assert not result["ok"] and "Sign in to Moraware" in result["message"]
    assert FakeGitHub.files == before


def test_empty_view_sends_nothing(github, moraware):
    result = run_sync(github, [f"{moraware}/empty"])
    assert not result["ok"] and "no slabs" in result["message"]
    assert FakeGitHub.files == {}


def test_moraware_error_is_reported(github, moraware):
    result = run_sync(github, [f"{moraware}/nothing-here"])
    assert not result["ok"] and "404" in result["message"]


def test_bad_token_is_reported(github, moraware):
    result = run_sync(github, [f"{moraware}/sys/inventory?&view=1"], token="wrong")
    assert not result["ok"] and "rejected the token" in result["message"]
    assert "wrong" not in result["message"]


def test_missing_settings_are_reported(github, moraware):
    assert "not set" in run_sync(github, [f"{moraware}/sys/inventory?&view=1"], token="")["message"]
    assert "No Moraware views" in run_sync(github, [])["message"]


def test_manifest_is_valid_and_narrow():
    manifest = json.loads((ROOT / "extension" / "manifest.json").read_text())
    assert manifest["manifest_version"] == 3
    assert set(manifest["permissions"]) == {"storage", "alarms"}
    assert set(manifest["host_permissions"]) == {"https://*.moraware.net/*", "https://api.github.com/*"}
    for name in ("background.js", "popup.html", "options.html", "sync.js", "ui.css", "popup.js", "options.js"):
        assert (ROOT / "extension" / name).exists()
