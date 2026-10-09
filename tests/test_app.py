"""Drives the real app headlessly against the sample feed."""
import html
import re
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
    """Everything written to the page. Cards and tables are HTML, so undo the escaping."""
    return html.unescape("\n".join(m.value for m in at.markdown))


def matches(at):
    """The count line above the results: (materials shown, materials that fit the project)."""
    found = re.search(r'cp-result"><b>(\d+)</b> of (\d+) materials match, for ([\d.,]+) sq ft finished', text(at))
    assert found, "no match count on the page"
    return int(found.group(1)), int(found.group(2))


def add_buttons(at):
    return [b for b in at.button if b.label == "Add to quote"]


def cards(at):
    return [html.unescape(m.value) for m in at.markdown if 'class="cp-price"' in m.value and "cp-brand" in m.value]


def toasts(at):
    return [t.value for t in at.toast]


def test_loads_and_lists_slabs(app):
    assert matches(app) == (12, 12)
    body = text(app)
    assert '<div class="cp-brand">Caesarstone</div><div class="cp-name">Blizzard</div>' in body
    assert "Cost $" not in body and "margin" not in body.lower()     # staff numbers hidden by default


def test_big_job_uses_two_slabs_and_drops_small_products(app):
    app.number_input(key="sqft").set_value(60.0).run()
    body = text(app)
    assert matches(app) == (2, 2)                    # only Blizzard and Berwyn have 72 sq ft free
    assert "This project needs: <b>2 slabs</b>" in body
    assert "10 more materials in stock are left out: not enough slab to cover 72.0 sq ft." in body


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
    assert matches(app) == (0, 12)
    assert "No materials match these filters." in text(app) and "check the spelling" in text(app)
    app.text_input(key="search").set_value("berwyn").run()
    assert matches(app) == (1, 12)


def test_new_quote_asks_before_clearing(app):
    button(app, "Add to quote").click().run()
    app.text_input(key="customer_name").set_value("Pat").run()
    number = app.session_state["quote_number"]
    button(app, "Start a new quote").click().run()
    # nothing is cleared yet: the app asks first
    assert len(app.session_state["quote"]) == 1 and app.session_state["customer_name"] == "Pat"
    assert {"Keep this quote", "Clear and start new"} <= {b.label for b in app.button}
    button(app, "Keep this quote").click().run()
    assert len(app.session_state["quote"]) == 1 and app.session_state["customer_name"] == "Pat"
    assert app.session_state["quote_number"] == number
    button(app, "Start a new quote").click().run()
    button(app, "Clear and start new").click().run()
    assert app.session_state["quote"] == [] and app.session_state["customer_name"] == ""
    assert app.session_state["sinks"] == {}
    assert toasts(app) == ["Started a new quote."]


def test_new_quote_does_not_ask_when_there_is_nothing_to_lose(app):
    button(app, "Start a new quote").click().run()
    assert "Clear and start new" not in {b.label for b in app.button}
    assert not app.exception


def test_feed_down_shows_plain_error(monkeypatch, tmp_path):
    monkeypatch.setenv("COUNTERPRO_DATA_SOURCES", str(tmp_path / "nope.csv"))
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30).run()
    assert not at.exception
    assert "could not be loaded" in at.error[0].value


def test_budget_slider_follows_project_size(app):
    lo, hi = app.session_state["budget_bounds"]
    assert tuple(app.slider(key="budget").value) == (lo, hi)
    app.slider(key="budget").set_value((lo, lo + 500)).run()
    assert matches(app)[0] < 12                        # the cap hides the dearer slabs
    assert any(b.key and b.key.startswith("chip_budget") for b in app.button)
    app.number_input(key="sqft").set_value(50.0).run() # prices rise, bounds move
    assert not app.exception
    new_lo, new_hi = app.session_state["budget_bounds"]
    a, b = app.slider(key="budget").value
    assert new_lo <= a < b <= new_hi


def test_pdf_download_offered_only_with_a_slab(app):
    assert any(b.label == "Download quote PDF" and b.disabled for b in app.button)
    assert not app.get("download_button")
    button(app, "Add to quote").click().run()
    assert not any(b.label == "Download quote PDF" for b in app.button)   # now a real download button
    downloads = [d.proto.label for d in app.get("download_button")]
    assert downloads == ["Download quote PDF", "Download as spreadsheet (CSV)"]
    assert app.get("download_button")[0].proto.type == "primary"
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
    assert matches(at) == (9, 9)                            # 9 products from the page, not 12 from the sheet
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
    assert matches(at) == (9, 9)
    captions = [c.value for c in at.sidebar.caption]
    assert any("Moraware inventory updated Oct 8 at 08:30" in c for c in captions)
    assert any(f"kept in the GitHub repository {REPO}" in c for c in captions)


def test_app_uses_the_feed_until_the_store_has_inventory(monkeypatch, github):
    _github_env(monkeypatch, github)
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30).run()
    assert not at.exception and matches(at) == (12, 12)


def test_app_survives_the_store_being_unreachable(monkeypatch):
    _github_env(monkeypatch, "http://127.0.0.1:9")
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30).run()
    assert not at.exception
    assert matches(at) == (12, 12)                               # falls back to the feed
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
    body = text(at)
    assert 'In stock: <b>1 slab</b></li><li>Largest slab: <b>128" × 63" (56.0 sq ft)</b>' in body
    assert "In stock: <b>2 slabs</b></li><li>Largest slab: <b>131.9999" in body
    assert "In stock since" not in body                       # this page has no date column
    at.session_state["view_mode"] = "List"
    at.run()
    assert '1 slab in stock, largest 128" × 63" (56.0 sq ft). This project needs 1 slab.' in text(at)
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
    first, second = cards(at)[:2]
    assert '<div class="cp-name">Mont Blanc</div>' in first and "In stock since: <b>Nov 2019</b>" in first
    assert '<div class="cp-name">Titanium</div>' in second and "May 2022" in second


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
    assert not at.exception and matches(at) == (9, 9)
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
    assert not at.exception and matches(at) == (9, 9)
    button(at, "Add sink").click().run()                   # a widget choice made before the deploy
    before = {name: mod for name, mod in sys.modules.items() if name == "counterpro" or name.startswith("counterpro.")}
    try:
        for name in before:
            del sys.modules[name]                          # the deploy: fresh copies on next import
        st.cache_data.clear()                              # the 60-second inventory cache runs out
        at.run()
        assert not at.exception, at.exception
        assert matches(at) == (9, 9)
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
    body = text(app)
    assert "IB for 35.0 sq ft" in body and "$1,707.32" in body            # (20 x 42 + 16 x 35) / 0.82
    assert "Material: 42.0 sq ft at $20.00 (35.0 sq ft plus 20% waste)" in body
    assert any("18% minimum margin" in c.value and "(18.0% of IB)" in c.value for c in app.caption)
    app.number_input(key="ib_cost").set_value(30.0).run()
    app.number_input(key="ib_sqft").set_value(50.0).run()
    body = text(app)
    expected = (30 * 60 + 16 * 50) / 0.82
    assert f"${expected:,.2f}" in body and "IB for 50.0 sq ft" in body
    assert f"${expected * 1.15:,.2f}" in body                              # customer material and fabrication


def test_ib_calculator_rates_can_be_changed(app):
    app.number_input(key="ib_waste").set_value(5.0).run()
    app.number_input(key="ib_fab").set_value(15.0).run()
    app.number_input(key="ib_floor").set_value(0.0).run()
    app.number_input(key="ib_markup").set_value(10.0).run()
    body = text(app)
    expected = 20 * 35 * 1.05 * 1.10 + 15 * 35
    assert f"${expected:,.2f}" in body
    assert any("material markup plus fabrication" in c.value for c in app.caption)
    # the calculator's rates never change the slab list's prices
    assert matches(app) == (12, 12)
    assert app.session_state["budget_bounds"] == AppTest.from_file(str(ROOT / "app.py"), default_timeout=30).run().session_state["budget_bounds"]


def test_ib_calculator_uses_a_picked_slabs_cost(app):
    options = app.selectbox(key="ib_slab").options
    assert options[0] == "Type in a cost myself" and any("Caesarstone Blizzard, 2cm, Vernon, $20.51/sq ft" == o for o in options)
    # the test harness cannot pick from a list that shows custom labels, so set the choice directly
    app.session_state["ib_slab"] = "15 - Caesarstone (VER) Blizzard #2141 2cm"
    app.run()
    assert not app.exception
    body = text(app)
    unit = (1120.00 + 1222.67) / 114.2222
    assert f"Slab cost ${unit:,.2f} per sq ft" in body.replace("\\$", "$")
    assert f"${(unit * 42 + 560) / 0.82:,.2f}" in body


def test_location_choices_show_how_many_options_fit(app):
    assert app.pills(key="locations").options == ["Vernon (6)", "Abbotsford (6)"]
    app.number_input(key="sqft").set_value(60.0).run()            # only two products can cover 72 sq ft
    assert app.pills(key="locations").options == ["Vernon (1)", "Abbotsford (1)"]


# --- The redesigned screen --------------------------------------------------
def test_project_setup_shows_finished_area_allowance_and_material(app):
    body = text(app)
    assert "<span>Finished area</span><b>35.0 sq ft</b>" in body
    assert "<span>Cutting allowance</span><b>20%</b>" in body
    assert "<span>Slab material required</span><b>42.0 sq ft</b>" in body
    app.number_input(key="sqft").set_value(300.0).run()
    assert "<span>Slab material required</span><b>360.0 sq ft</b>" in text(app)


def test_cards_show_what_the_brief_asks_for(app):
    first = cards(app)[0]
    for part in ("cp-brand", "cp-name", "cp-tag", "In stock:", "Largest slab:", "This project needs:",
                 "Estimated installed price", "per finished sq ft, before GST and sinks"):
        assert part in first, part
    assert len(cards(app)) == 12
    labels = [b.label for b in app.button]
    assert labels.count("View details") == 12 and labels.count("Add to quote") == 12


def test_no_photo_means_a_plain_placeholder_never_a_picture(app):
    body = text(app)
    assert "No photo yet" in body and "<img" not in body       # the sample feed has no photos


def test_a_real_photo_is_shown_when_the_feed_has_one(monkeypatch, tmp_path):
    import pandas as pd
    feed = pd.read_csv(FIXTURE)
    feed["Image URL"] = ""
    feed.loc[feed["Product Variant"].str.contains("Blizzard"), "Image URL"] = "https://example.com/blizzard.jpg"
    path = tmp_path / "with_photo.csv"
    feed.to_csv(path, index=False)
    monkeypatch.setenv("COUNTERPRO_DATA_SOURCES", str(path))
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30).run()
    assert not at.exception
    blizzard = next(c for c in cards(at) if ">Blizzard<" in c)
    assert '<img src="https://example.com/blizzard.jpg" alt="Photo of Blizzard"' in blizzard
    assert "No photo yet" not in blizzard
    assert sum("No photo yet" in c for c in cards(at)) == 11


def test_grid_and_list_views_show_the_same_slabs_and_prices(app):
    def price_list(at):
        return re.findall(r'cp-name">(.*?)</div>.*?cp-price"><small>Estimated installed price</small><b>(.*?)</b>',
                          "\n".join(cards(at)))
    grid = price_list(app)
    assert len(grid) == 12 and 'class="cp-row"' not in text(app)
    app.session_state["view_mode"] = "List"
    app.run()
    assert not app.exception
    assert text(app).count('class="cp-row"') == 12
    assert price_list(app) == grid
    assert [b.label for b in app.button].count("Add to quote") == 12


def test_filters_show_as_chips_that_can_be_removed(app):
    app.session_state["locations"] = ["VER"]
    app.session_state["thickness"] = ["3cm"]
    app.run()
    chips = {b.label: b for b in app.button if b.key and b.key.startswith("chip_")}
    assert set(chips) == {"Vernon", "3cm"}
    both = matches(app)[0]
    assert 0 < both < 12
    chips["3cm"].click().run()
    assert app.session_state["thickness"] == [] and app.session_state["locations"] == ["VER"]
    assert matches(app)[0] > both
    assert {b.label for b in app.button if b.key and b.key.startswith("chip_")} == {"Vernon"}


def test_reset_filters_clears_everything(app):
    assert button(app, "Reset filters").disabled               # nothing to reset yet
    app.session_state["locations"] = ["ABB"]
    app.text_input(key="search").set_value("white").run()
    app.selectbox(key="sort").set_value("Name, A to Z").run()
    assert matches(app)[0] < 12
    assert any(b.label == 'Search: "white"' for b in app.button)
    button(app, "Reset filters").click().run()
    assert matches(app) == (12, 12)
    assert app.session_state["search"] == "" and app.session_state["locations"] == []
    assert app.selectbox(key="sort").value == "Price, low to high"
    assert not [b for b in app.button if b.key and b.key.startswith("chip_")]


def test_search_finds_a_product_code(app):
    app.text_input(key="search").set_value("2141").run()        # Caesarstone's colour number for Blizzard
    assert matches(app) == (1, 12) and ">Blizzard<" in cards(app)[0]


def test_sort_orders(app):
    def names(at):
        return re.findall(r'cp-name">(.*?)</div>', "\n".join(cards(at)))

    def amounts(at):
        return [int(a.replace(",", "")) for a in re.findall(r'cp-price"><small>.*?</small><b>\$([\d,]+)</b>',
                                                               "\n".join(cards(at)))]
    assert amounts(app) == sorted(amounts(app))
    app.selectbox(key="sort").set_value("Price, high to low").run()
    assert amounts(app) == sorted(amounts(app), reverse=True)
    app.selectbox(key="sort").set_value("Name, A to Z").run()
    assert len(names(app)) == 12
    app.selectbox(key="sort").set_value("Most in stock").run()
    assert ">Blizzard<" in cards(app)[0] or ">Berwyn<" in cards(app)[0]   # the two with two slabs each


def test_excluded_materials_are_explained_when_nothing_fits(app):
    app.number_input(key="sqft").set_value(400.0).run()
    body = text(app)
    assert matches(app) == (0, 0)
    assert "No material in stock can cover 480.0 sq ft of slab." in body
    assert "12 more materials in stock are left out" in body


def test_adding_confirms_and_marks_the_card(app):
    add_buttons(app)[0].click().run()
    assert toasts(app) == ["Added Natural Stone HD Ashen White to the quote (1 of 4)."]
    assert '<span class="cp-tag is-on">In quote</span>' in cards(app)[0]
    assert "<b>No materials yet</b>" not in text(app)
    assert '<div class="cp-qname">1. Natural Stone HD Ashen White</div>' in text(app)
    button(app, "In quote").click().run()                       # pressing it again takes the material off
    assert app.session_state["quote"] == [] and "Removed" in toasts(app)[0]


def test_replace_swaps_a_material_in_place(app):
    for _ in range(2):
        add_buttons(app)[0].click().run()
    first, second = app.session_state["quote"]
    app.button(key=f"swap_{first}").click().run()
    assert app.session_state["replacing"] == first
    assert "Choose a replacement for <b>Natural Stone HD Ashen White</b>" in text(app)
    labels = [b.label for b in app.button]
    assert labels.count("Replace with this") == 10 and "Add to quote" not in labels
    new = next(b for b in app.button if b.label == "Replace with this")
    chosen = new.key.removeprefix("add_")
    new.click().run()
    assert app.session_state["quote"] == [chosen, second]       # same position, nothing else moved
    assert app.session_state["replacing"] is None and toasts(app)[0].startswith("Replaced ")
    assert "Add to quote" in [b.label for b in app.button]


def test_replace_can_be_called_off(app):
    add_buttons(app)[0].click().run()
    only = app.session_state["quote"][0]
    app.button(key=f"swap_{only}").click().run()
    button(app, "Keep it instead").click().run()
    assert app.session_state["quote"] == [only] and app.session_state["replacing"] is None
    assert "Choose a replacement" not in text(app)


def test_compare_table_marks_the_lowest_and_shows_differences(app):
    assert "Nothing to compare yet" in text(app)
    for _ in range(3):
        add_buttons(app)[0].click().run()                       # the three least expensive, in price order
    body = text(app)
    table = body[body.index('<table class="cp-compare">'):]
    table = table[:table.index("</table>")]
    for label in ("Brand", "Thickness", "Largest slab", "Inventory location", "In stock", "Slabs required",
                  "Estimated installed price", "Per finished sq ft", "Compared with lowest", "GST (5%)",
                  "Total with GST"):
        assert f'<td class="cp-rowlabel">{label}</td>' in table, label
    assert table.count('<span class="cp-lowtag">Lowest</span>') == 1
    assert table.count("Lowest price") == 1 and table.count(" more</td>") == 2
    installed = [float(a.replace(",", "")) for a in re.findall(
        r"\$([\d,]+\.\d\d)", re.search(r"is-price.*?</tr>", table).group(0))]
    more = [float(a.replace(",", "")) for a in re.findall(r"\$([\d,]+\.\d\d) more", table)]
    assert more == [pytest.approx(installed[1] - installed[0], abs=0.011),
                    pytest.approx(installed[2] - installed[0], abs=0.011)]
    # remove from the comparison
    third = app.session_state["quote"][2]
    app.button(key=f"cmp_rm_{third}").click().run()
    assert len(app.session_state["quote"]) == 2
    # replace from the comparison goes back to the slabs
    first = app.session_state["quote"][0]
    app.button(key=f"cmp_swap_{first}").click().run()
    assert app.session_state["view"] == "Slabs and quote" and app.session_state["replacing"] == first


def test_one_price_on_the_card_the_quote_the_comparison_and_the_pdf(app, monkeypatch):
    """The installed price is worked out once. Every place that shows it must agree."""
    from counterpro import quote as quote_module
    from tests.test_quote import pdf_text
    seen = {}
    real = quote_module.build_pdf

    def spy(q, *args, **kwargs):
        seen["quote"] = q
        seen["pdf"] = real(q, *args, **kwargs)
        return seen["pdf"]
    monkeypatch.setattr(quote_module, "build_pdf", spy)

    app.number_input(key="sqft").set_value(48.5).run()
    app.session_state["sinks"] = {"83742": 2}
    app.run()
    card_prices = re.findall(r'cp-price"><small>Estimated installed price</small><b>(.*?)</b><span>(.*?)</span>',
                             "\n".join(cards(app)))[:2]
    for _ in range(2):
        add_buttons(app)[0].click().run()
    assert not app.exception
    body = text(app)
    q = seen["quote"]
    pdf = pdf_text(seen["pdf"])
    table = body[body.index('<table class="cp-compare">'):]
    for option, (card_price, card_note) in zip(q.options, card_prices):
        p = option.price
        whole, exact = f"${p.slab_subtotal:,.0f}", f"${p.slab_subtotal:,.2f}"
        assert card_price == whole                                           # card
        assert card_note == f"${p.per_sqft:,.0f} per finished sq ft, before GST and sinks"
        assert f'<div class="cp-qprice">{whole}</div>' in body               # quote panel
        assert f"{exact}" in table and f"${p.total:,.2f}" in table           # comparison
        assert exact in pdf and f"${p.total:,.2f}" in pdf                    # PDF
        assert f"${p.tax:,.2f}" in pdf and f"${p.tax:,.2f}" in table
        # and the figures are the pricing module's own, for this size and these sinks
        assert p.sqft == 48.5 and p.sinks == 600.0
        assert p.slab_subtotal == pytest.approx(p.material_fab + p.install)
        assert p.total == pytest.approx((p.slab_subtotal + 600.0) * 1.05)


def test_phone_bar_appears_once_there_is_a_quote(app):
    def bar(at):
        return [h.proto.body for h in at.get("html") if "cp-mobilebar" in h.proto.body and "<a " in h.proto.body]
    assert not bar(app)
    add_buttons(app)[0].click().run()
    assert len(bar(app)) == 1 and 'href="#quote"' in bar(app)[0] and "Quote: 1 material, from $" in bar(app)[0]


def test_quote_panel_lists_project_and_sinks(app):
    app.session_state["sinks"] = {"83742": 1}
    app.run()
    add_buttons(app)[0].click().run()
    body = text(app)
    assert '<div class="cp-kv"><span>Finished area</span><span>35.0 sq ft</span></div>' in body
    assert '<div class="cp-kv"><span>Slab material required</span><span>42.0 sq ft</span></div>' in body
    assert '<div class="cp-kv"><span>Sinks</span><span>$300.00</span></div>' in body
    assert "with sinks and GST" in body
    assert any(c.value == f"No. {app.session_state['quote_number']}" for c in app.caption)
