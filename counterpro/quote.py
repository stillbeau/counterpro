"""The customer quote: data model, PDF and CSV export."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from fpdf import FPDF
from fpdf.enums import TableCellFillMode
from fpdf.fonts import FontFace

from .config import BRANDING, RULES, Branding, PricingRules
from .pricing import Price, money

# Same palette as the app: ink, a dark teal, and a light teal tint for the total.
INK = (20, 32, 31)
MUTED = (88, 102, 100)
LINE = (225, 230, 227)
TEAL = (23, 73, 77)
TEAL_TINT = (237, 244, 243)
_MAX_IMAGE_BYTES = 3 * 1024 * 1024


@dataclass(frozen=True)
class SinkLine:
    sku: str
    label: str
    unit_price: float
    quantity: int

    @property
    def total(self) -> float:
        return self.unit_price * self.quantity


@dataclass(frozen=True)
class QuoteOption:
    name: str            # "Caesarstone Blizzard"
    spec: str            # "2cm Polished"
    location: str        # "Vernon"
    price: Price
    slabs_used: int = 1
    serials: tuple[str, ...] = ()
    image_url: str = ""  # a real photo of this colour, when there is one


@dataclass
class Quote:
    number: str
    created: datetime
    sqft: float
    options: list[QuoteOption]
    sinks: list[SinkLine] = field(default_factory=list)
    customer_name: str = ""
    customer_contact: str = ""
    project: str = ""
    prepared_by: str = ""
    valid_days: int = BRANDING.quote_valid_days

    @property
    def valid_until(self) -> date:
        return (self.created + timedelta(days=self.valid_days)).date()

    @property
    def file_stem(self) -> str:
        who = re.sub(r"[^A-Za-z0-9]+", "-", self.customer_name).strip("-")
        return f"{self.number}-{who}" if who else self.number


def new_quote_number(now: datetime | None = None, branding: Branding = BRANDING) -> str:
    now = now or datetime.now()
    return f"{branding.quote_prefix}-{now:%y%m%d}-{now:%H%M}"


def pdf_safe(text: object) -> str:
    """The built-in PDF fonts only cover latin-1. Swap the common typographic
    characters for plain ones and drop anything else that cannot be encoded."""
    text = str(text)
    for orig, repl in {"—": "-", "–": "-", "’": "'", "‘": "'",
                       "“": '"', "”": '"', "…": "..."}.items():
        text = text.replace(orig, repl)
    return text.encode("latin-1", errors="ignore").decode("latin-1")


def _long_date(d: date | datetime) -> str:
    return f"{d:%B} {d.day}, {d.year}"


_photo_cache: dict[str, bytes] = {}     # photos already fetched, so a quote is not held up twice


def _fetch_image(url: str):
    """A slab photo for the PDF, or None. Only real photos are ever printed;
    a quote without one simply has no picture."""
    import io
    if not url or not url.lower().startswith(("https://", "http://")):
        return None
    if url in _photo_cache:
        return io.BytesIO(_photo_cache[url])
    try:
        import requests
        resp = requests.get(url, timeout=4, stream=True)
        if resp.status_code != 200 or not resp.headers.get("content-type", "").lower().startswith("image/"):
            return None
        data = resp.raw.read(_MAX_IMAGE_BYTES + 1, decode_content=True)
        if not 0 < len(data) <= _MAX_IMAGE_BYTES:
            return None
        if len(_photo_cache) >= 64:
            _photo_cache.clear()
        _photo_cache[url] = data
        return io.BytesIO(data)
    except Exception:
        return None


class _QuotePDF(FPDF):
    footer_text = ""

    def footer(self):
        self.set_y(-10)
        self.set_font("Helvetica", "", 8)
        self.set_text_color(*MUTED)
        self.cell(0, 5, pdf_safe(self.footer_text), align="L")
        self.cell(0, 5, f"Page {self.page_no()} of {{nb}}", align="R")


def build_pdf(quote: Quote, branding: Branding = BRANDING, rules: PricingRules = RULES) -> bytes:
    """Customer-facing quote. Never includes cost, IB or margin. Every figure is
    read from the option's Price as it stands; nothing is worked out here."""
    if not quote.options:
        raise ValueError("a quote needs at least one slab option")
    n = len(quote.options)

    pdf = _QuotePDF(format="Letter")
    pdf.footer_text = f"{branding.company}   Quote {quote.number}"
    pdf.alias_nb_pages()
    pdf.set_margins(16, 14, 16)
    pdf.set_auto_page_break(True, margin=14)
    pdf.add_page()
    width = pdf.epw
    pdf.set_title(pdf_safe(f"Quote {quote.number}"))
    pdf.set_author(pdf_safe(branding.company))

    # Letterhead
    top = pdf.get_y()
    pdf.set_text_color(*TEAL)
    pdf.set_font("Helvetica", "B", 19)
    pdf.cell(width * 0.6, 9, pdf_safe(branding.company), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9.5)
    pdf.set_text_color(*MUTED)
    for line in (branding.branch, *branding.contact_lines):
        if line:
            pdf.cell(width * 0.6, 4.6, pdf_safe(line), new_x="LMARGIN", new_y="NEXT")
    left_bottom = pdf.get_y()

    pdf.set_xy(pdf.l_margin + width * 0.6, top)
    pdf.set_text_color(*INK)
    pdf.set_font("Helvetica", "B", 19)
    pdf.cell(width * 0.4, 9, "Quote", align="R", new_x="LEFT", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9.5)
    pdf.set_text_color(*MUTED)
    for line in (f"No. {quote.number}",
                 f"Date: {_long_date(quote.created)}",
                 f"Valid until: {_long_date(quote.valid_until)}"):
        pdf.cell(width * 0.4, 4.6, pdf_safe(line), align="R", new_x="LEFT", new_y="NEXT")

    pdf.set_y(max(left_bottom, pdf.get_y()) + 3.5)
    pdf.set_draw_color(*TEAL)
    pdf.set_line_width(0.8)
    pdf.line(pdf.l_margin, pdf.get_y(), pdf.l_margin + width, pdf.get_y())
    pdf.ln(5)

    # Who and what
    def block(x: float, y: float, w: float, heading: str, lines: list[str]) -> float:
        pdf.set_xy(x, y)
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_text_color(*TEAL)
        pdf.cell(w, 5, heading, new_x="LEFT", new_y="NEXT")
        pdf.set_font("Helvetica", "", 10.5)
        pdf.set_text_color(*INK)
        for line in lines:
            pdf.set_x(x)
            pdf.multi_cell(w, 5.2, pdf_safe(line), align="L", new_x="LEFT", new_y="NEXT")
        return pdf.get_y()

    y0 = pdf.get_y()
    half = width / 2 - 4
    who = [l for l in (quote.customer_name, quote.customer_contact, quote.project) if l.strip()]
    job = [f"Finished countertop area: {quote.sqft:,.1f} sq ft"]
    if quote.sinks:
        job += [f"{s.quantity} x {s.label}" + (f", SKU {s.sku}" if s.sku.isdigit() else "")
                for s in quote.sinks]
    else:
        job.append("No sinks included")
    if quote.prepared_by.strip():
        job.append(f"Prepared by: {quote.prepared_by.strip()}")
    y1 = block(pdf.l_margin, y0, half, "Prepared for", who or ["Customer"])
    y2 = block(pdf.l_margin + half + 8, y0, half, "Project", job)
    pdf.set_y(max(y1, y2) + 5.5)

    # Options
    pdf.set_font("Helvetica", "B", 13)
    pdf.set_text_color(*INK)
    heading = "Your countertop" if n == 1 else f"Your {n} countertop options"
    pdf.cell(width, 7, heading, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(1)

    label_w = 50 if n > 1 else 74
    col_w = (width - label_w) / n
    lowest = min(range(n), key=lambda i: quote.options[i].price.slab_subtotal)
    base = quote.options[lowest].price.slab_subtotal

    def difference(o: QuoteOption) -> str:
        more = o.price.slab_subtotal - base
        return "Lowest price" if abs(more) < 0.005 else f"{money(more)} more"

    installed_label = "Estimated installed price"
    rows = [
        ("Material and fabrication", [money(o.price.material_fab) for o in quote.options], ""),
        ("Installation", [money(o.price.install) for o in quote.options], ""),
        (installed_label, [money(o.price.slab_subtotal) for o in quote.options], "strong"),
        ("Per finished sq ft", [money(o.price.per_sqft) for o in quote.options], "quiet"),
    ]
    if n > 1:
        rows.append(("Compared with lowest", [difference(o) for o in quote.options], "quiet"))
    rows += [
        ("Sinks", [money(o.price.sinks) for o in quote.options], ""),
        ("Subtotal", [money(o.price.subtotal) for o in quote.options], ""),
        (f"GST ({rules.tax_rate * 100:g}%)", [money(o.price.tax) for o in quote.options], ""),
    ]
    images = [_fetch_image(o.image_url) for o in quote.options]

    pdf.set_draw_color(*LINE)
    pdf.set_line_width(0.2)
    pdf.set_font("Helvetica", "", 10)
    head_style = FontFace(emphasis="BOLD", color=INK, fill_color=(255, 255, 255))
    strong_style = FontFace(emphasis="BOLD", color=INK, size_pt=11)
    quiet_style = FontFace(color=MUTED, size_pt=9)
    total_style = FontFace(emphasis="BOLD", color=INK, fill_color=TEAL_TINT, size_pt=12)
    with pdf.table(
        col_widths=(label_w, *([col_w] * n)),
        text_align=("LEFT", *(["RIGHT"] * n)),
        borders_layout="HORIZONTAL_LINES",
        cell_fill_mode=TableCellFillMode.NONE,
        headings_style=head_style,
        line_height=5.4,
        padding=(1.35, 2, 1.35, 2),
        width=width,
        align="LEFT",
        num_heading_rows=2 if any(images) else 1,
    ) as table:
        if any(images):
            pictures = table.row()
            pictures.cell("")
            for img in images:
                if img is not None:
                    pictures.cell(img=img, img_fill_width=True)
                else:
                    pictures.cell("")
        header = table.row()
        header.cell("")
        for i, o in enumerate(quote.options, 1):
            title = o.name if n == 1 else f"Option {i}\n{o.name}"
            detail = ", ".join(b for b in (o.spec, o.location) if b)
            header.cell(pdf_safe(f"{title}\n{detail}" if detail else title))
        for label, values, kind in rows:
            style = strong_style if kind == "strong" else quiet_style if kind == "quiet" else None
            row = table.row()
            row.cell(label, style=style)
            for v in values:
                row.cell(v, style=style)
        total = table.row()
        total.cell("Total with GST", style=total_style)
        for o in quote.options:
            total.cell(money(o.price.total), style=total_style)

    # What the price covers
    pdf.ln(5.5)
    y0 = pdf.get_y()

    def bullets(x: float, w: float, heading: str, items: tuple[str, ...]) -> float:
        pdf.set_xy(x, y0)
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_text_color(*TEAL)
        pdf.cell(w, 5, heading, new_x="LEFT", new_y="NEXT")
        pdf.set_font("Helvetica", "", 9.5)
        pdf.set_text_color(*INK)
        for item in items:
            pdf.set_x(x)
            pdf.cell(3.5, 4.6, "-")
            pdf.multi_cell(w - 3.5, 4.6, pdf_safe(item), align="L", new_x="LEFT", new_y="NEXT")
        return pdf.get_y()

    included, excluded = tuple(branding.included), tuple(branding.excluded)
    if quote.sinks:
        included += ("The sinks listed on this quote",)
    else:
        excluded = ("Sinks (none were added to this quote)",) + excluded
    b1 = bullets(pdf.l_margin, half, "Included in the price", included)
    b2 = bullets(pdf.l_margin + half + 8, half, "Not included", excluded)
    pdf.set_y(max(b1, b2) + 4.5)

    # The small print
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(*MUTED)
    notes = []
    if n > 1:
        notes.append("Each option is a complete price for the same project. Choose one.")
    notes.append(f"GST of {rules.tax_rate * 100:g}% is shown on its own line and is included in each total.")
    notes += [*branding.disclaimers, f"This quote is valid until {_long_date(quote.valid_until)}.", *branding.terms]
    # Keep the small print together: if it will not all fit, it starts the next page.
    needed = sum(len(pdf.multi_cell(width, 4.4, pdf_safe(line), align="L", dry_run=True, output="LINES"))
                 for line in notes) * 4.4
    if pdf.get_y() + needed > pdf.page_break_trigger:
        pdf.add_page()
    for line in notes:
        pdf.multi_cell(width, 4.4, pdf_safe(line), align="L", new_x="LMARGIN", new_y="NEXT")

    return bytes(pdf.output())


def to_rows(quote: Quote) -> list[dict]:
    """Flat rows for the CSV export (customer-safe columns only)."""
    sinks = "; ".join(f"{s.label} x{s.quantity}" for s in quote.sinks) or "None"
    return [{
        "Quote": quote.number,
        "Customer": quote.customer_name,
        "Option": i,
        "Material": o.name,
        "Thickness / finish": o.spec,
        "Location": o.location,
        "Sq Ft": quote.sqft,
        "Slabs used": o.slabs_used,
        "Serials": "; ".join(o.serials),
        "Installed price (before GST and sinks)": round(o.price.slab_subtotal, 2),
        "Sinks": sinks,
        "Subtotal": round(o.price.subtotal, 2),
        "GST": round(o.price.tax, 2),
        "Total (incl. GST)": round(o.price.total, 2),
    } for i, o in enumerate(quote.options, 1)]
