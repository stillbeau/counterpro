from datetime import datetime

import pytest

from counterpro.pricing import price_job
from counterpro.quote import (Quote, QuoteOption, SinkLine, build_pdf,
                              new_quote_number, pdf_safe, to_rows)


def make_quote(n_options=1, **kw):
    options = [
        QuoteOption(f"Caesarstone Colour {i}", "3cm Polished", "Vernon",
                    price_job(20 + 7 * i, 35, 300), slabs_used=1, serials=(f"S{i}",))
        for i in range(n_options)
    ]
    return Quote(number="CP-261008-1030", created=datetime(2026, 10, 8, 10, 30), sqft=35,
                 options=options, sinks=[SinkLine("83742", "50/50 Undermount (16 ga)", 300.0, 1)], **kw)


def pdf_text(data: bytes) -> str:
    pypdf = pytest.importorskip("pypdf")
    import io
    return "\n".join(p.extract_text() for p in pypdf.PdfReader(io.BytesIO(data)).pages)


def test_quote_number_and_validity():
    assert new_quote_number(datetime(2026, 10, 8, 9, 5)) == "CP-261008-0905"
    q = make_quote()
    assert q.valid_until.isoformat() == "2026-11-07"
    assert make_quote(customer_name="Pat O'Neil & Co.").file_stem == "CP-261008-1030-Pat-O-Neil-Co"


@pytest.mark.parametrize("n", [1, 2, 4])
def test_pdf_builds(n):
    data = build_pdf(make_quote(n, customer_name="Pat Lee", customer_contact="250-555-0100",
                                project="Kitchen, 12 Lake Rd", prepared_by="Sam"))
    assert data[:5] == b"%PDF-"


def test_pdf_contents():
    q = make_quote(2, customer_name="Pat Lee", prepared_by="Sam")
    text = pdf_text(build_pdf(q))
    assert "CP-261008-1030" in text and "Pat Lee" in text
    assert "November 7, 2026" in text
    for o in q.options:
        assert f"${o.price.total:,.2f}" in text
    # nothing internal leaks onto the customer's page
    for o in q.options:
        assert f"{o.price.ib_cost:,.2f}" not in text
    assert "margin" not in text.lower() and "IB" not in text


def test_pdf_handles_odd_characters():
    q = make_quote(customer_name="Zoë — “the” café \U0001f6b0")
    assert build_pdf(q)[:5] == b"%PDF-"
    assert pdf_safe("15° Radius – ok \U0001f963") == "15° Radius - ok "


def test_pdf_needs_an_option():
    q = make_quote()
    q.options = []
    with pytest.raises(ValueError):
        build_pdf(q)


def test_csv_rows_are_customer_safe():
    rows = to_rows(make_quote(2, customer_name="Pat Lee"))
    assert len(rows) == 2 and rows[1]["Option"] == 2
    assert not any("cost" in k.lower() or "margin" in k.lower() for k in rows[0])
