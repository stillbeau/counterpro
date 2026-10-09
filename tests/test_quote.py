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
    q = make_quote(2, customer_name="Pat Lee", customer_contact="250-555-0100",
                   project="Kitchen, 12 Lake Rd", prepared_by="Sam")
    text = pdf_text(build_pdf(q))
    assert "FloForm Countertops" in text and "CP-261008-1030" in text
    assert "October 8, 2026" in text and "November 7, 2026" in text          # date and valid until
    for part in ("Pat Lee", "250-555-0100", "Kitchen, 12 Lake Rd", "Prepared by: Sam",
                 "Finished countertop area: 35.0 sq ft", "1 x 50/50 Undermount (16 ga), SKU 83742"):
        assert part in text, part
    for o in q.options:
        for amount in (o.price.material_fab, o.price.install, o.price.slab_subtotal, o.price.per_sqft,
                       o.price.sinks, o.price.subtotal, o.price.tax, o.price.total):
            assert f"${amount:,.2f}" in text
    # nothing internal leaks onto the customer's page
    for o in q.options:
        assert f"{o.price.ib_cost:,.2f}" not in text and f"{o.price.direct_cost:,.2f}" not in text
    assert "margin" not in text.lower() and "IB" not in text and "cost" not in text.lower()


def test_pdf_compares_options_against_the_lowest():
    q = make_quote(3)
    text = pdf_text(build_pdf(q))
    assert "Your 3 countertop options" in text and "Estimated installed price" in text
    assert text.count("Lowest price") == 1
    base = q.options[0].price.slab_subtotal
    for o in q.options[1:]:
        assert f"${o.price.slab_subtotal - base:,.2f} more" in text
    single = pdf_text(build_pdf(make_quote(1)))
    assert "Compared with lowest" not in single and "Your countertop" in single


def test_pdf_says_what_is_and_is_not_included():
    from counterpro.config import BRANDING
    text = " ".join(pdf_text(build_pdf(make_quote(2))).split())
    assert "Included in the price" in text and "Not included" in text
    assert BRANDING.included and BRANDING.excluded and BRANDING.disclaimers
    for line in (*BRANDING.included, *BRANDING.excluded, *BRANDING.disclaimers):
        assert " ".join(line.split()) in text, line
    assert "GST of 5% is shown on its own line and is included in each total." in text
    assert "The sinks listed on this quote" in text and "none were added" not in text
    q = make_quote(1)
    q.sinks = []
    q.options = [QuoteOption("Caesarstone Colour", "3cm", "Vernon", price_job(20, 35, 0))]
    no_sinks = " ".join(pdf_text(build_pdf(q)).split())
    assert "Sinks (none were added to this quote)" in no_sinks and "The sinks listed" not in no_sinks


@pytest.mark.parametrize("n", [1, 2, 3, 4])
def test_everyday_quotes_fit_on_one_page(n):
    pypdf = pytest.importorskip("pypdf")
    import io
    data = build_pdf(make_quote(n, customer_name="Pat Lee", customer_contact="250-555-0100",
                                project="Kitchen, 12 Lake Rd", prepared_by="Sam"))
    assert len(pypdf.PdfReader(io.BytesIO(data)).pages) == 1


def test_long_quotes_run_onto_a_second_page_without_losing_anything():
    pypdf = pytest.importorskip("pypdf")
    import io
    from dataclasses import replace
    q = make_quote(4, customer_name="Pat Lee")
    q.options = [replace(o, name="Natural Stone " + "Very Long Colour Name " * 4 + str(i),
                         spec="3cm Leathered, discontinued colour")
                 for i, o in enumerate(q.options)]
    q.sinks = [SinkLine(str(80000 + i), f"Large Single Bowl Undermount, 15 Degree Radius {i}", 450.0, 2)
               for i in range(6)]
    data = build_pdf(q)
    reader = pypdf.PdfReader(io.BytesIO(data))
    text = " ".join(pdf_text(data).split())
    assert len(reader.pages) == 2 and "Page 2 of 2" in text
    assert "This quote is valid until November 7, 2026." in text
    for o in q.options:
        assert f"${o.price.total:,.2f}" in text


@pytest.fixture
def photo_server():
    """A tiny local web server: one real PNG, one page that is not an image."""
    import io
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (60, 40), (200, 190, 170)).save(buf, "PNG")
    png = buf.getvalue()

    class Handler(BaseHTTPRequestHandler):
        hits = []

        def do_GET(self):
            Handler.hits.append(self.path)
            if self.path == "/slab.png":
                body, kind = png, "image/png"
            elif self.path == "/page.html":
                body, kind = b"<html>not a picture</html>", "text/html"
            else:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}", Handler.hits
    server.shutdown()


def _images_in(data: bytes) -> int:
    pypdf = pytest.importorskip("pypdf")
    import io
    return sum(len(page.images) for page in pypdf.PdfReader(io.BytesIO(data)).pages)


def test_pdf_prints_a_real_photo_and_nothing_in_its_place(photo_server, monkeypatch):
    from dataclasses import replace

    from counterpro import quote as quote_module
    monkeypatch.setenv("NO_PROXY", "127.0.0.1")
    monkeypatch.setenv("no_proxy", "127.0.0.1")
    monkeypatch.setattr(quote_module, "_photo_cache", {})
    base, hits = photo_server
    q = make_quote(3)
    assert _images_in(build_pdf(q)) == 0                          # no photos: no pictures, no placeholders
    q.options[0] = replace(q.options[0], image_url=f"{base}/slab.png")
    q.options[1] = replace(q.options[1], image_url=f"{base}/page.html")      # not an image
    q.options[2] = replace(q.options[2], image_url=f"{base}/gone.png")       # missing
    data = build_pdf(q)
    assert data[:5] == b"%PDF-" and _images_in(data) == 1
    build_pdf(q)
    assert hits.count("/slab.png") == 1                           # fetched once, then remembered


def test_pdf_ignores_photo_addresses_that_are_not_web_links():
    from counterpro.quote import _fetch_image
    for url in ("", "file:///etc/passwd", "/etc/passwd", "javascript:alert(1)", "ftp://example.com/a.png"):
        assert _fetch_image(url) is None


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
    q = make_quote(2)
    assert [r["Installed price (before GST and sinks)"] for r in to_rows(q)] == \
        [round(o.price.slab_subtotal, 2) for o in q.options]
