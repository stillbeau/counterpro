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


def as_the_server_might_send_it(page: str) -> bytes:
    """The same inventory the way an older server writes it: one table with a
    different id, upper-case tags, unquoted attributes, and Windows-1252 text.
    The saved page used elsewhere is the browser's tidied-up version."""
    import re
    start = page.index('<div id="ProductsHeadDiv">')
    end = page.index('<div id="ProductsBodyDiv">')
    raw = page[:start] + page[end:]                                  # no separate heading table
    raw = raw.replace('id="ProductsBody"', "id=Products").replace("ProductsBodyDiv", "ProductsDiv")
    raw = raw.replace('<meta charset="utf-8">', "")
    raw = re.sub(r'class="(\w+)"', r"class=\1", raw)
    raw = re.sub(r"<(/?)(table|thead|tbody|tr|td)\b", lambda m: f"<{m.group(1)}{m.group(2).upper()}", raw)
    assert "ProductsBody" not in raw and "<TR class=oddRow>" in raw
    raw = raw.replace("\uf0d8", "")                                  # the icon-font glyph has no Windows-1252 form
    return raw.encode("cp1252")


RAW = as_the_server_might_send_it(PAGE)
SIGN_IN = '<html><head><title>Sign In - Moraware</title></head><body><form><input name="user"><input type="password" name="pwd"></form></body></html>'
SHELL = "<html><head><title>Inventory - Moraware Systemize</title></head><body><div id=app></div><script>/* draws the table later */</script></body></html>"

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")


class FakeMoraware(BaseHTTPRequestHandler):
    seen: list = []

    def log_message(self, *args):
        pass

    def do_GET(self):
        type(self).seen.append(self.path)
        content_type = "text/html; charset=utf-8"
        if "view=1" in self.path:
            body, status = PAGE, 200
        elif "view=2" in self.path:
            body, status = SECOND, 200
        elif "raw" in self.path:
            body, status, content_type = RAW, 200, "text/html; charset=windows-1252"
        elif "rawmeta" in self.path:
            body, status, content_type = RAW, 200, "text/html"
        elif "signedout" in self.path:
            body, status = SIGN_IN, 200
        elif "builtlater" in self.path:
            body, status = (PAGE if "rendered=1" in self.path else SHELL), 200
        elif "tabsignin" in self.path:
            body, status = (SIGN_IN if "rendered=1" in self.path else SHELL), 200
        elif "other" in self.path:
            body, status = '<html><head><title>Jobs - Moraware Systemize</title></head><body><table id="Jobs"><tr><td>Job</td></tr></table></body></html>', 200
        elif "empty" in self.path:
            body, status = PAGE.split("<tbody>\n<tr class")[0] + "</tbody></table></div></body></html>", 200
        else:
            body, status = "missing", 404
        data = body if isinstance(body, bytes) else body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
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


def run_sync(github, views=None, token=TOKEN, repo=REPO, render=False, locations=None):
    settings = {"repo": repo, "token": token, "apiUrl": github, "path": store.FILE_NAME}
    if locations is not None:
        settings["locations"] = locations          # the current settings shape
    else:
        settings["views"] = views                  # the shape used before version 1.2
    if render:
        settings["renderSuffix"] = "&rendered=1"
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
    assert result["message"].startswith("Abbotsford:")         # says which location failed
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
    assert "token is not set" in run_sync(github, [f"{moraware}/sys/inventory?&view=1"], token="")["message"]
    assert "No locations are switched on" in run_sync(github, [])["message"]


def test_manifest_is_valid_and_narrow():
    manifest = json.loads((ROOT / "extension" / "manifest.json").read_text())
    assert manifest["manifest_version"] == 3
    assert set(manifest["permissions"]) == {"storage", "alarms", "scripting"}
    assert set(manifest["host_permissions"]) == {"https://*.moraware.net/*", "https://api.github.com/*"}
    for name in ("background.js", "popup.html", "options.html", "sync.js", "ui.css", "popup.js", "options.js"):
        assert (ROOT / "extension" / name).exists()


def _synced_slabs(github):
    snap = store.GitHubStore(REPO, TOKEN, api_url=github).load()
    return drop_duplicate_serials(clean_slabs(snap.rows))


def test_reads_the_page_the_way_a_server_sends_it(github, moraware):
    """Different table id, upper-case tags, unquoted attributes, Windows-1252."""
    result = run_sync(github, [f"{moraware}/raw?x=1"])
    assert result["ok"] and result["slabs"] == 10 and result["pages"][0]["how"] == "direct"
    direct = clean_slabs(parse_inventory_html(PAGE)[0])
    synced = _synced_slabs(github)
    for column in ("variant", "serial", "on_hand", "cost", "bin", "dimensions", "supplier"):
        assert list(synced[column]) == list(direct[column]), column
    assert "\u00d7" in synced["dimensions"].iloc[0]           # the size separator survived the character set


def test_falls_back_to_the_page_as_the_browser_draws_it(github, moraware):
    without = run_sync(github, [f"{moraware}/builtlater?x=1"])
    assert not without["ok"] and "no inventory table" in without["message"]
    result = run_sync(github, [f"{moraware}/builtlater?x=1"], render=True)
    assert result["ok"] and result["slabs"] == 10 and result["pages"][0]["how"] == "tab"
    assert len(_synced_slabs(github)) == 10


def test_sign_in_seen_in_the_tab_is_reported_as_sign_in(github, moraware):
    result = run_sync(github, [f"{moraware}/tabsignin?x=1"], render=True)
    assert not result["ok"] and "Sign in to Moraware" in result["message"]
    assert FakeGitHub.files == {}


def test_unexpected_page_says_what_came_back(github, moraware):
    result = run_sync(github, [f"{moraware}/other?x=1"], render=True)
    assert not result["ok"]
    message = result["message"]
    assert "no inventory table" in message and 'page "Jobs - Moraware Systemize"' in message
    assert "at /other" in message and "1 tables (Jobs)" in message and "headings missing" in message
    assert "$" not in message                                  # the description never carries page content


def place(key, url, enabled=True):
    return {"key": key, "enabled": enabled, "url": url}


def test_each_location_has_its_own_switch_and_address(github, moraware):
    result = run_sync(github, locations=[
        place("vernon", f"{moraware}/sys/inventory?&view=1"),
        place("abbotsford", f"{moraware}/sys/inventory?&view=2", enabled=False),
        place("edmonton", "", enabled=False),
        place("saskatoon", "", enabled=False),
    ])
    assert result["ok"] and result["slabs"] == 10
    assert [(p["location"], p["slabs"], p["holds"]) for p in result["pages"]] == [("Vernon", 10, "Vernon")]
    assert not any("view=2" in path for path in FakeMoraware.seen)      # a switched-off location is not read
    assert set(_synced_slabs(github)["location"]) == {"VER"}


def test_switching_a_location_on_adds_it(github, moraware):
    result = run_sync(github, locations=[place("vernon", f"{moraware}/sys/inventory?&view=1"),
                                         place("abbotsford", f"{moraware}/sys/inventory?&view=2")])
    assert [(p["location"], p["holds"]) for p in result["pages"]] == [("Vernon", "Vernon"), ("Abbotsford", "Abbotsford")]
    assert set(_synced_slabs(github)["location"]) == {"VER", "ABB"}


def test_wrong_address_in_a_slot_is_noticed(github, moraware):
    result = run_sync(github, locations=[place("edmonton", f"{moraware}/sys/inventory?&view=2")])
    assert result["ok"]
    assert result["pages"][0]["location"] == "Edmonton" and result["pages"][0]["holds"] == "Abbotsford"


def test_location_switched_on_without_an_address(github, moraware):
    result = run_sync(github, locations=[place("vernon", f"{moraware}/sys/inventory?&view=1"), place("saskatoon", "")])
    assert not result["ok"] and "Saskatoon is switched on but has no Moraware address" in result["message"]
    assert FakeGitHub.files == {}


def test_all_locations_off(github, moraware):
    result = run_sync(github, locations=[place("vernon", f"{moraware}/sys/inventory?&view=1", enabled=False)])
    assert not result["ok"] and "No locations are switched on" in result["message"]


def test_old_address_list_is_sorted_into_locations():
    """Settings saved by versions before 1.2 are carried over, each address in its own location."""
    script = """
import { normalizeSettings } from "./extension/sync.js";
const base = "https://floformcountertops.moraware.net/sys/inventory?&view=0&sort=a0&pageSize=9999&mrv=14938&prod=";
const out = [
  normalizeSettings({ views: [base + "F1017", base + "F1023"], token: "t", time: "07:15" }),
  normalizeSettings({ views: ["https://floformcountertops.moraware.net/sys/inventory?&view=14938", base + "F1017"] }),
  normalizeSettings({ views: [base + "F9999"] }),
  normalizeSettings(undefined),
].map((s) => ({ time: s.time, token: s.token, hasViews: "views" in s,
                places: s.locations.map((l) => [l.name, l.enabled, (l.url.match(/prod=(\\w+)|view=(14938)/) || []).slice(1).find(Boolean) || ""]) }));
console.log(JSON.stringify(out));
"""
    out = subprocess.run(["node", "--input-type=module", "-e", script], capture_output=True, text=True, timeout=60, cwd=ROOT)
    assert out.returncode == 0, out.stderr
    swapped, saved_view, unknown, fresh = json.loads(out.stdout)
    assert swapped["places"] == [["Vernon", True, "F1023"], ["Abbotsford", True, "F1017"], ["Edmonton", False, ""], ["Saskatoon", False, ""]]
    assert swapped["token"] == "t" and swapped["time"] == "07:15" and swapped["hasViews"] is False
    assert saved_view["places"][:2] == [["Vernon", True, "14938"], ["Abbotsford", True, "F1017"]]
    assert unknown["places"][0] == ["Vernon", True, "F9999"]              # no clue in the address: next free location
    assert [p[:2] for p in fresh["places"]] == [["Vernon", True], ["Abbotsford", True], ["Edmonton", False], ["Saskatoon", False]]
