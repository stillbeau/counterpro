from datetime import datetime
from pathlib import Path

import pandas as pd
import pytest

from counterpro import store
from counterpro.inventory import clean_slabs, load_slabs, parse_variant, summarize
from counterpro.moraware import (NotAnInventoryPage, parse_inventory_html,
                                 sqft_from_measurement)

PAGE = Path(__file__).parent / "fixtures" / "moraware_inventory.html"


@pytest.fixture(scope="module")
def page():
    return PAGE.read_text(encoding="utf-8")


@pytest.mark.parametrize("text,sqft", [
    ('120" × 56"', 120 * 56 / 144),
    ('131.9999" × 65.4546"', 131.9999 * 65.4546 / 144),
    ("126 x 63", 55.125),
    ('131" X 64.5"', 131 * 64.5 / 144),
])
def test_sqft_from_measurement(text, sqft):
    assert sqft_from_measurement(text) == pytest.approx(sqft)


@pytest.mark.parametrize("text", ["", None, "n/a", "120"])
def test_sqft_from_measurement_unreadable(text):
    assert sqft_from_measurement(text) is None


def test_parses_the_inventory_table(page):
    rows, info = parse_inventory_html(page)
    assert info["rows"] == 10 and info["unsized"] == 0
    assert info["title"] == "Inventory - Moraware Systemize"
    assert info["filters"]["Product"] == "15 - Stone & Quartz (VER)"
    first = rows.iloc[0]
    assert first["Product Variant"] == "15 - Caesarstone (VER) Snowy Cliffs 6607 (Discontinued) 2cm"
    assert first["Serial Number"] == "T100 (VER)"
    assert first["Serialized On Hand Cost"] == "$700.00"
    assert first["Location"] == "VER - Row 3"
    assert float(first["On Hand Qty"]) == pytest.approx(46.6667, abs=1e-4)
    assert "Supplier" in rows.columns            # the sort icon glyph is stripped from the header


def test_page_becomes_priced_slabs(page):
    slabs = clean_slabs(parse_inventory_html(page)[0])
    assert len(slabs) == 10
    row = slabs[slabs["serial"] == "S200"].iloc[0]
    assert (row["brand"], row["color"], row["thickness"], row["finish"]) == ("Natural Stone", "Basalt - Lynn Blue", "2cm", "Honed")
    assert row["bin"] == "VER - Orphan E2" and row["dimensions"] == '128" × 63"'
    assert row["supplier"] == "15 - Margranite (VER)"
    assert row["available"] == pytest.approx(56.0)

    products = summarize(slabs).set_index("name")
    sandgate = products.loc["Cambria Sandgate"]
    assert sandgate["slab_count"] == 2 and sandgate["spec"] == "3cm Matte"
    assert sandgate["unit_cost"] == pytest.approx(4800 / (2 * 131.9999 * 65.4546 / 144))
    assert bool(products.loc["Cambria Halstead", "discontinued"]) is True
    assert bool(products.loc["Caesarstone Mont Blanc", "discontinued"]) is False


@pytest.mark.parametrize("raw,color,finish,tags", [
    ("15 - Cambria (VER) Sandgate Matte 3cm Matte", "Sandgate", "Matte", ()),
    ("15 - Silestone (VER) Seaport Suede (DISCONTINUED) 3cm", "Seaport", "Suede", ("DISCONTINUED",)),
    ("15 - Caesarstone (VER) Oyster #9601 (Discontinued) 3cm", "Oyster", "", ("Discontinued",)),
    ("15 - Cambria (VER) Southampton (VER) (DISCONTINUED) 3cm Polished", "Southampton", "Polished", ("DISCONTINUED",)),
])
def test_names_seen_on_the_moraware_page(raw, color, finish, tags):
    v = parse_variant(raw)
    assert (v.color, v.finish, v.tags) == (color, finish, tags)


def test_columns_can_move_and_extra_columns_are_fine(page):
    rows, _ = parse_inventory_html(page)
    shuffled = rows[["Serialized On Hand Cost", "Measurement", "Product Variant", "Serial Number"]]
    html = shuffled.assign(Extra="x").to_html(index=False)
    again, _ = parse_inventory_html(html)
    assert list(again["Product Variant"]) == list(rows["Product Variant"])
    assert [float(a) for a in again["On Hand Qty"]] == pytest.approx([float(a) for a in rows["On Hand Qty"]])


def test_on_hand_qty_column_is_used_when_present():
    html = pd.DataFrame({"Product Variant": ["15 - Viatera (VER) Aura 3cm"], "On Hand Qty": ["56.875"],
                         "Serialized On Hand Cost": ["$1,900.00"]}).to_html(index=False)
    rows, _ = parse_inventory_html(html)
    assert clean_slabs(rows)["on_hand"].item() == pytest.approx(56.875)


def test_unsized_slab_is_reported_and_left_out():
    html = pd.DataFrame({"Product Variant": ["15 - Viatera (VER) Aura 3cm", "15 - Viatera (VER) Soprano 3cm"],
                         "Measurement": ['126" x 65"', ""],
                         "Serialized On Hand Cost": ["$1,900.00", "$1,500.00"]}).to_html(index=False)
    rows, info = parse_inventory_html(html)
    assert info["unsized"] == 1
    assert len(clean_slabs(rows)) == 1


@pytest.mark.parametrize("html", [
    "", "<html><body><p>Please sign in</p></body></html>",
    "<table><tr><td>Product Variant</td><td>Something else</td></tr></table>",
    "<script>var x = '<td>Product Variant</td><td>Serialized On Hand Cost</td>';</script>",
])
def test_rejects_pages_that_are_not_inventory(html):
    with pytest.raises(NotAnInventoryPage):
        parse_inventory_html(html)


def test_needs_a_size_column():
    html = pd.DataFrame({"Product Variant": ["x"], "Serialized On Hand Cost": ["$1"]}).to_html(index=False)
    with pytest.raises(NotAnInventoryPage, match="Measurement"):
        parse_inventory_html(html)


def test_html_file_works_as_a_feed():
    result = load_slabs([str(PAGE)])
    assert result.errors == [] and len(result.slabs) == 10


def test_local_store_round_trip(tmp_path, page):
    local = store.LocalStore(tmp_path)
    assert local.load() is None and local.stamp() == 0.0
    rows, info = parse_inventory_html(page)
    local.save(rows, ["inventory.html"], info["filters"], now=datetime(2026, 10, 8, 10, 55))
    snap = local.load()
    assert local.stamp() > 0
    assert snap.saved_at == datetime(2026, 10, 8, 10, 55) and snap.files == ("inventory.html",)
    assert snap.filters["Product"] == "15 - Stone & Quartz (VER)"
    pd.testing.assert_frame_equal(clean_slabs(snap.rows), clean_slabs(rows))
    local.clear()
    assert local.load() is None and local.stamp() == 0.0


def test_local_store_reports_damage(tmp_path):
    (tmp_path / store.FILE_NAME).write_text("{not json", encoding="utf-8")
    with pytest.raises(store.StoreError, match="damaged"):
        store.LocalStore(tmp_path).load()


def with_dates(page: str) -> str:
    """The stand-in page with a Received Date column added, oldest slab last."""
    dates = ["10/1/2026", "3/15/2024", "2024-03-20", "Jan 5, 2023", "", "6/30/2025", "7/1/2025", "11/2/2019", "5/5/2022", "not a date"]
    out, rows = [], iter(dates)
    for line in page.splitlines(keepends=True):
        if line.startswith('<tr class="'):
            line = line.replace("</tr>", f"<td>{next(rows)}</td></tr>")
        out.append(line)
    text = "".join(out)
    head = '<td class="headerSortableCol" mjtclick="promptToSortPageWithUrl(event)">PO Number&nbsp;&nbsp;&nbsp;</td>'
    assert head in text
    return text.replace(head, head + '<td class="headerSortableCol">Received Date&nbsp;&nbsp;&nbsp;</td>')


def test_received_date_column_gives_slab_age(page):
    rows, _ = parse_inventory_html(with_dates(page))
    assert "Received Date" in rows.columns
    slabs = clean_slabs(rows)
    by_serial = slabs.set_index("serial")["received"]
    assert by_serial["29000 (VRN)"] == pd.Timestamp(2019, 11, 2)
    assert by_serial["FG0000003 (VER)"] == pd.Timestamp(2023, 1, 5)
    assert pd.isna(by_serial["S200"]) and pd.isna(by_serial["S301"])     # blank and unreadable dates
    products = summarize(slabs).set_index("name")
    assert products.loc["Cambria Sandgate", "received"] == pd.Timestamp(2024, 3, 15)   # oldest of its two slabs
    oldest = summarize(slabs).sort_values("received", na_position="last")["name"].tolist()
    assert oldest[0] == "Caesarstone Mont Blanc"


@pytest.mark.parametrize("heading", ["Date Received", "Receipt Date", "Created", "Purchased Date", "received"])
def test_other_date_headings_are_recognised(heading):
    html = pd.DataFrame({"Product Variant": ["15 - Viatera (VER) Aura 3cm"], "Measurement": ['126" x 65"'],
                         "Serialized On Hand Cost": ["$1,900.00"], heading: ["2/3/2021"]}).to_html(index=False)
    assert clean_slabs(parse_inventory_html(html)[0])["received"].item() == pd.Timestamp(2021, 2, 3)


def test_no_date_column_means_no_age(page):
    slabs = clean_slabs(parse_inventory_html(page)[0])
    assert slabs["received"].isna().all()
    assert summarize(slabs)["received"].isna().all()


def test_placeholder_rows_are_left_out():
    """Moraware lists some serials as 1" x 1" with no cost. They cannot be priced."""
    html = pd.DataFrame({
        "Product Variant": ["17 - Caesarstone (ABB) Alpine Mist #5110 3cm"] * 3 + ["17 - Hanstone (ABB) Tofino 2cm"],
        "Serial Number": ["A1", "A2", "A3", "B1"],
        "Measurement": ['120" × 56"', '1" × 1"', '1" × 1"', '1" × 1"'],
        "Serialized On Hand Cost": ["$900.00", "$0.00", "$0.00", "$0.00"],
    }).to_html(index=False)
    slabs = clean_slabs(parse_inventory_html(html)[0])
    assert list(slabs["serial"]) == ["A1"]
    product = summarize(slabs).iloc[0]
    assert product["slab_count"] == 1 and product["unit_cost"] == pytest.approx(900 / (120 * 56 / 144))


def test_real_slab_with_no_cost_is_left_out_too():
    html = pd.DataFrame({"Product Variant": ["15 - Viatera (VER) Aura 3cm"], "Measurement": ['126" x 65"'],
                         "Serialized On Hand Cost": ["$0.00"]}).to_html(index=False)
    assert clean_slabs(parse_inventory_html(html)[0]).empty
