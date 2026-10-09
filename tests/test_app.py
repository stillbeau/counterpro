"""Drives the real app headlessly against the sample feed."""
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).parent.parent
FIXTURE = Path(__file__).parent / "fixtures" / "sample_inventory.csv"


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setenv("COUNTERPRO_DATA_SOURCES", str(FIXTURE))
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30)
    at.run()
    assert not at.exception
    return at


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    """Never read a real uploaded inventory or staff code during tests."""
    monkeypatch.setenv("COUNTERPRO_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.delenv("COUNTERPRO_STAFF_CODE", raising=False)
    for name in ("COUNTERPRO_STORE_REPO", "COUNTERPRO_STORE_TOKEN"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("COUNTERPRO_LOGO_URL", "")


def button(at, label):
    return next(b for b in at.button if b.label == label)


def text(at):
    return "\n".join(m.value for m in at.markdown)


def test_loads_and_lists_slabs(app):
    assert "12 slab options for 35.0 sq ft" in text(app)
    assert "Caesarstone Blizzard" in text(app)
    assert "Cost $" not in text(app)                 # staff numbers hidden by default


def test_big_job_uses_two_slabs_and_drops_small_products(app):
    app.number_input(key="sqft").set_value(60.0).run()
    body = text(app)
    assert "2 slab options for 60.0 sq ft" in body   # only Blizzard and Berwyn have 72 sq ft free
    assert "this project uses 2" in body
    assert "more in stock are too small" in body


def test_add_to_quote_and_reprice_with_sink(app):
    button(app, "Add to quote").click().run()
    assert len(app.session_state["quote"]) == 1
    before = text(app)
    button(app, "Add sink").click().run()            # first option is the $0 line
    app.selectbox(key="sink_pick").select_index(1).run()
    button(app, "Add sink").click().run()
    assert app.session_state["sinks"] == {"NONE": 1, "83742": 1}
    assert text(app) != before                       # quote option re-priced with the sink
    assert not app.exception


def test_quote_limit(app):
    for _ in range(4):
        button(app, "Add to quote").click().run()
    assert len(app.session_state["quote"]) == 4
    assert all(b.disabled for b in app.button if b.label == "Add to quote")


def test_option_too_small_after_resize_is_flagged(app):
    button(app, "Add to quote").click().run()
    app.number_input(key="sqft").set_value(200.0).run()
    assert "Left off the quote" in text(app)
    assert not app.exception


def test_staff_view_and_filters(app):
    app.toggle(key="staff").set_value(True).run()
    assert "Cost $" in text(app) and "margin" in text(app)
    app.text_input(key="search").set_value("zzzz").run()
    assert "Nothing matches" in text(app)
    app.text_input(key="search").set_value("berwyn").run()
    assert "1 slab option for" in text(app)


def test_new_quote_clears(app):
    button(app, "Add to quote").click().run()
    app.text_input(key="customer_name").set_value("Pat").run()
    button(app, "Start a new quote").click().run()
    assert app.session_state["quote"] == [] and app.session_state["customer_name"] == ""


def test_feed_down_shows_plain_error(monkeypatch, tmp_path):
    monkeypatch.setenv("COUNTERPRO_DATA_SOURCES", str(tmp_path / "nope.csv"))
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30).run()
    assert not at.exception
    assert "could not be loaded" in at.error[0].value


def test_budget_slider_follows_project_size(app):
    lo, hi = app.session_state["budget_bounds"]
    assert tuple(app.slider(key="budget").value) == (lo, hi)
    app.slider(key="budget").set_value((lo, lo + 500)).run()
    narrowed = text(app)
    assert "12 slab options" not in narrowed          # the cap hides the dearer slabs
    app.number_input(key="sqft").set_value(50.0).run() # prices rise, bounds move
    assert not app.exception
    new_lo, new_hi = app.session_state["budget_bounds"]
    a, b = app.slider(key="budget").value
    assert new_lo <= a < b <= new_hi


def test_pdf_download_offered_only_with_a_slab(app):
    assert any(b.label == "Download quote PDF" and b.disabled for b in app.button)
    button(app, "Add to quote").click().run()
    assert not any(b.label == "Download quote PDF" for b in app.button)   # now a real download button
    assert not app.exception


def test_uploaded_moraware_inventory_replaces_the_feed(monkeypatch):
    from counterpro import store
    from counterpro.moraware import parse_inventory_html
    page = (Path(__file__).parent / "fixtures" / "moraware_inventory.html").read_text(encoding="utf-8")
    rows, info = parse_inventory_html(page)
    store.LocalStore().save(rows, ["inventory.html"], info["filters"])
    monkeypatch.setenv("COUNTERPRO_DATA_SOURCES", str(FIXTURE))
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30).run()
    assert not at.exception
    body = text(at)
    assert "9 slab options for 35.0 sq ft" in body          # 9 products from the page, not 12 from the sheet
    assert "Discontinued colour" in body
    assert any("Moraware inventory updated" in c.value for c in at.sidebar.caption)


def test_staff_code_locks_cost_and_uploads(monkeypatch):
    monkeypatch.setenv("COUNTERPRO_DATA_SOURCES", str(FIXTURE))
    monkeypatch.setenv("COUNTERPRO_STAFF_CODE", "slab-2026")
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30).run()
    assert at.toggle(key="staff").disabled
    assert "Cost $" not in text(at)
    at.sidebar.text_input[0].set_value("wrong")      # a form sends its fields with the button
    at.sidebar.button[0].click().run()
    assert at.toggle(key="staff").disabled and "not right" in at.sidebar.error[0].value
    at.sidebar.text_input[0].set_value("slab-2026")
    at.sidebar.button[0].click().run()
    assert not at.exception and not at.toggle(key="staff").disabled
    at.toggle(key="staff").set_value(True).run()
    assert "Cost $" in text(at)


def test_uploads_off_without_a_staff_code(app):
    assert any("Uploading by hand is off" in c.value for c in app.sidebar.caption)


from tests.test_github_store import REPO, TOKEN, FakeGitHub, github  # noqa: E402,F401  (fixture)


def _github_env(monkeypatch, api):
    monkeypatch.setenv("COUNTERPRO_DATA_SOURCES", str(FIXTURE))
    monkeypatch.setenv("COUNTERPRO_STORE_REPO", REPO)
    monkeypatch.setenv("COUNTERPRO_STORE_TOKEN", TOKEN)
    monkeypatch.setenv("COUNTERPRO_STORE_API", api)


def test_app_reads_inventory_the_extension_sent_to_github(monkeypatch, github):
    import base64
    import json
    page = (Path(__file__).parent / "fixtures" / "moraware_inventory.html").read_text(encoding="utf-8")
    doc = json.dumps({"saved_at": "2026-10-08T08:30:00", "source": "extension",
                      "files": ["15 - Stone & Quartz (VER)"], "pages": [{"name": "VER", "url": "u", "html": page}]})
    FakeGitHub.files["moraware_inventory.json"] = (base64.b64encode(doc.encode()).decode(), "sha1")
    _github_env(monkeypatch, github)
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30).run()
    assert not at.exception
    assert "9 slab options for 35.0 sq ft" in text(at)
    captions = [c.value for c in at.sidebar.caption]
    assert any("Moraware inventory updated Oct 8 at 08:30" in c for c in captions)
    assert any(f"kept in the GitHub repository {REPO}" in c for c in captions)


def test_app_uses_the_feed_until_the_store_has_inventory(monkeypatch, github):
    _github_env(monkeypatch, github)
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30).run()
    assert not at.exception and "12 slab options for 35.0 sq ft" in text(at)


def test_app_survives_the_store_being_unreachable(monkeypatch):
    _github_env(monkeypatch, "http://127.0.0.1:9")
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30).run()
    assert not at.exception
    assert "12 slab options for 35.0 sq ft" in text(at)          # falls back to the feed
    assert any("could not be reached" in w.value for w in at.sidebar.warning)


def _save_page(html):
    from counterpro import store
    from counterpro.moraware import parse_inventory_html
    rows, info = parse_inventory_html(html)
    store.LocalStore().save(rows, ["inventory.html"], info["filters"])


def test_rows_show_slab_size_and_staff_see_slab_cost(monkeypatch):
    page = (Path(__file__).parent / "fixtures" / "moraware_inventory.html").read_text(encoding="utf-8")
    _save_page(page)
    monkeypatch.setenv("COUNTERPRO_DATA_SOURCES", str(FIXTURE))
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30).run()
    import html
    body = html.unescape(text(at))                             # the list is written as escaped HTML
    assert '1 slab in stock, 128" × 63" (56.0 sq ft)' in body
    assert "2 slabs in stock, largest 131.9999" in body
    assert "In stock since" not in body                       # this page has no date column
    assert "Oldest stock first" not in at.selectbox(key="sort").options
    at.toggle(key="staff").set_value(True).run()
    assert "Slab cost $1,400.00 ($25.00/sq ft)" in text(at)


def test_oldest_first_when_moraware_gives_dates(monkeypatch):
    from tests.test_moraware import with_dates
    page = (Path(__file__).parent / "fixtures" / "moraware_inventory.html").read_text(encoding="utf-8")
    _save_page(with_dates(page))
    monkeypatch.setenv("COUNTERPRO_DATA_SOURCES", str(FIXTURE))
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30).run()
    assert not at.exception
    assert at.selectbox(key="sort").options[0] == "Oldest stock first"
    assert at.selectbox(key="sort").value == "Oldest stock first"
    names = [m.value for m in at.markdown if 'class="cp-name"' in m.value]
    assert "Caesarstone Mont Blanc" in names[0] and "In stock since Nov 2019" in names[0]
    assert "Natural Stone Titanium" in names[1] and "May 2022" in names[1]


def test_abbotsford_is_named(app):
    assert "Abbotsford" in text(app) and ", ABB." not in text(app)


def test_no_google_sheet_is_read_any_more(monkeypatch):
    from counterpro import config
    monkeypatch.delenv("COUNTERPRO_DATA_SOURCES", raising=False)
    assert config.data_sources() == ()
    assert "docs.google.com" not in (ROOT / "counterpro" / "config.py").read_text()
    assert "docs.google.com" not in (ROOT / "app.py").read_text()


def test_empty_store_tells_staff_to_sync(monkeypatch):
    monkeypatch.delenv("COUNTERPRO_DATA_SOURCES", raising=False)
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30).run()
    assert not at.exception
    assert "no slab inventory yet" in at.error[0].value and "Sync now" in at.error[0].value


def test_old_inventory_warns_that_the_sync_stopped(monkeypatch):
    from datetime import datetime, timedelta
    from counterpro import config, store
    from counterpro.moraware import parse_inventory_html
    monkeypatch.delenv("COUNTERPRO_DATA_SOURCES", raising=False)
    page = (Path(__file__).parent / "fixtures" / "moraware_inventory.html").read_text(encoding="utf-8")
    rows, info = parse_inventory_html(page)
    store.LocalStore().save(rows, ["inventory.html"], info["filters"], now=config.now() - timedelta(days=5))
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30).run()
    assert not at.exception and "9 slab options" in text(at)
    assert any("5 days old" in w.value and "sync has stopped" in w.value for w in at.sidebar.warning)


def test_survives_a_code_update_without_a_restart(monkeypatch):
    """After a deploy Streamlit drops the changed modules and imports them fresh
    while the app keeps running. Anything cached from before (the store object,
    a remembered widget choice) then belongs to the old copy of the code and
    must not break the next page load."""
    import sys

    import streamlit as st
    from counterpro import store
    from counterpro.moraware import parse_inventory_html
    monkeypatch.delenv("COUNTERPRO_DATA_SOURCES", raising=False)
    page = (Path(__file__).parent / "fixtures" / "moraware_inventory.html").read_text(encoding="utf-8")
    rows, info = parse_inventory_html(page)
    store.LocalStore().save(rows, ["inventory.html"], info["filters"])

    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30).run()
    assert not at.exception and "9 slab options" in text(at)
    button(at, "Add sink").click().run()                   # a widget choice made before the deploy
    before = {name: mod for name, mod in sys.modules.items() if name == "counterpro" or name.startswith("counterpro.")}
    try:
        for name in before:
            del sys.modules[name]                          # the deploy: fresh copies on next import
        st.cache_data.clear()                              # the 60-second inventory cache runs out
        at.run()
        assert not at.exception, at.exception
        assert "9 slab options" in text(at)
        button(at, "Add sink").click().run()
        assert not at.exception, at.exception
        assert sys.modules["counterpro.store"] is not before["counterpro.store"]   # really was a fresh copy
    finally:
        for name in [n for n in sys.modules if n == "counterpro" or n.startswith("counterpro.")]:
            del sys.modules[name]
        sys.modules.update(before)
        st.cache_data.clear()
        st.cache_resource.clear()


def test_ib_calculator_with_a_typed_cost(app):
    import html as html_lib
    body = html_lib.unescape(text(app))
    assert "IB for 35.0 sq ft" in body and "$1,707.32" in body            # (20 x 42 + 16 x 35) / 0.82
    assert "Material: 42.0 sq ft at $20.00 (35.0 sq ft plus 20% waste)" in body
    assert any("18% minimum margin" in c.value and "(18.0% of IB)" in c.value for c in app.caption)
    app.number_input(key="ib_cost").set_value(30.0).run()
    app.number_input(key="ib_sqft").set_value(50.0).run()
    body = html_lib.unescape(text(app))
    expected = (30 * 60 + 16 * 50) / 0.82
    assert f"${expected:,.2f}" in body and "IB for 50.0 sq ft" in body
    assert f"${expected * 1.15:,.2f}" in body                              # customer material and fabrication


def test_ib_calculator_rates_can_be_changed(app):
    import html as html_lib
    app.number_input(key="ib_waste").set_value(5.0).run()
    app.number_input(key="ib_fab").set_value(15.0).run()
    app.number_input(key="ib_floor").set_value(0.0).run()
    app.number_input(key="ib_markup").set_value(10.0).run()
    body = html_lib.unescape(text(app))
    expected = 20 * 35 * 1.05 * 1.10 + 15 * 35
    assert f"${expected:,.2f}" in body
    assert any("material markup plus fabrication" in c.value for c in app.caption)
    # the calculator's rates never change the slab list's prices
    assert "12 slab options for 35.0 sq ft" in body
    assert app.session_state["budget_bounds"] == AppTest.from_file(str(ROOT / "app.py"), default_timeout=30).run().session_state["budget_bounds"]


def test_ib_calculator_uses_a_picked_slabs_cost(app):
    import html as html_lib
    options = app.selectbox(key="ib_slab").options
    assert options[0] == "Type in a cost myself" and any("Caesarstone Blizzard, 2cm, Vernon, $20.51/sq ft" == o for o in options)
    # the test harness cannot pick from a list that shows custom labels, so set the choice directly
    app.session_state["ib_slab"] = "15 - Caesarstone (VER) Blizzard #2141 2cm"
    app.run()
    assert not app.exception
    body = html_lib.unescape(text(app))
    unit = (1120.00 + 1222.67) / 114.2222
    assert f"Slab cost ${unit:,.2f} per sq ft" in body.replace("\\$", "$")
    assert f"${(unit * 42 + 560) / 0.82:,.2f}" in body


def test_location_choices_show_how_many_options_fit(app):
    assert app.pills(key="locations").options == ["Vernon (6)", "Abbotsford (6)"]
    app.number_input(key="sqft").set_value(60.0).run()            # only two products can cover 72 sq ft
    assert app.pills(key="locations").options == ["Vernon (1)", "Abbotsford (1)"]
