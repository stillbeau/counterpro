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
    store.save(rows, ["inventory.html"], info["filters"])
    monkeypatch.setenv("COUNTERPRO_DATA_SOURCES", str(FIXTURE))
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30).run()
    assert not at.exception
    body = text(at)
    assert "9 slab options for 35.0 sq ft" in body          # 9 products from the page, not 12 from the sheet
    assert "Discontinued colour" in body
    assert any("Moraware page uploaded" in c.value for c in at.sidebar.caption)


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
    assert any("Uploads are off" in c.value for c in app.sidebar.caption)
