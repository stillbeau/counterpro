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

INK = (28, 37, 38)
MUTED = (94, 107, 108)
RULE = (203, 210, 207)
TAG = (244, 197, 52)


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


def build_pdf(quote: Quote, branding: Branding = BRANDING, rules: PricingRules = RULES) -> bytes:
    """Customer-facing quote. Never includes cost, IB or margin."""
    if not quote.options:
        raise ValueError("a quote needs at least one slab option")

    pdf = FPDF(format="Letter")
    pdf.set_margins(18, 16, 18)
    pdf.set_auto_page_break(True, margin=18)
    pdf.add_page()
    width = pdf.epw
    pdf.set_title(pdf_safe(f"Quote {quote.number}"))
    pdf.set_author(pdf_safe(branding.company))

    # Letterhead
    top = pdf.get_y()
    pdf.set_text_color(*INK)
    pdf.set_font("Helvetica", "B", 17)
    pdf.cell(width * 0.6, 8, pdf_safe(branding.company), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9.5)
    pdf.set_text_color(*MUTED)
    for line in (branding.branch, *branding.contact_lines):
        if line:
            pdf.cell(width * 0.6, 4.6, pdf_safe(line), new_x="LMARGIN", new_y="NEXT")
    left_bottom = pdf.get_y()

    pdf.set_xy(pdf.l_margin + width * 0.6, top)
    pdf.set_text_color(*INK)
    pdf.set_font("Helvetica", "B", 17)
    pdf.cell(width * 0.4, 8, "Quote", align="R", new_x="LEFT", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9.5)
    pdf.set_text_color(*MUTED)
    for line in (f"No. {quote.number}",
                 f"Date: {_long_date(quote.created)}",
                 f"Valid until: {_long_date(quote.valid_until)}"):
        pdf.cell(width * 0.4, 4.6, pdf_safe(line), align="R", new_x="LEFT", new_y="NEXT")

    pdf.set_y(max(left_bottom, pdf.get_y()) + 4)
    pdf.set_draw_color(*INK)
    pdf.set_line_width(0.6)
    pdf.line(pdf.l_margin, pdf.get_y(), pdf.l_margin + width, pdf.get_y())
    pdf.ln(6)

    # Who and what
    def block(x: float, y: float, w: float, heading: str, lines: list[str]) -> float:
        pdf.set_xy(x, y)
        pdf.set_font("Helvetica", "B", 9.5)
        pdf.set_text_color(*MUTED)
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
    job = [f"Finished area: {quote.sqft:,.1f} sq ft"]
    if quote.sinks:
        job += [f"{s.quantity} x {s.label}" + (f", SKU {s.sku}" if s.sku.isdigit() else "")
                for s in quote.sinks]
    else:
        job.append("No sinks included")
    if quote.prepared_by.strip():
        job.append(f"Prepared by: {quote.prepared_by.strip()}")
    y1 = block(pdf.l_margin, y0, half, "Prepared for", who or ["Customer"])
    y2 = block(pdf.l_margin + half + 8, y0, half, "Project", job)
    pdf.set_y(max(y1, y2) + 7)

    # Options
    n = len(quote.options)
    pdf.set_font("Helvetica", "B", 12)
    pdf.set_text_color(*INK)
    heading = "Your countertop" if n == 1 else f"Your {n} countertop options"
    pdf.cell(width, 7, heading, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(1)

    label_w = 46 if n > 1 else 70
    col_w = (width - label_w) / n
    rows = [
        ("Material and fabrication", [money(o.price.material_fab) for o in quote.options]),
        ("Installation", [money(o.price.install) for o in quote.options]),
        ("Sinks", [money(o.price.sinks) for o in quote.options]),
        ("Subtotal", [money(o.price.subtotal) for o in quote.options]),
        (f"GST ({rules.tax_rate * 100:g}%)", [money(o.price.tax) for o in quote.options]),
    ]
    pdf.set_draw_color(*RULE)
    pdf.set_line_width(0.2)
    pdf.set_font("Helvetica", "", 10)
    head_style = FontFace(emphasis="BOLD", color=INK, fill_color=(255, 255, 255))
    total_style = FontFace(emphasis="BOLD", color=INK, fill_color=TAG, size_pt=12)
    with pdf.table(
        col_widths=(label_w, *([col_w] * n)),
        text_align=("LEFT", *(["RIGHT"] * n)),
        borders_layout="HORIZONTAL_LINES",
        cell_fill_mode=TableCellFillMode.NONE,
        headings_style=head_style,
        line_height=6,
        padding=(1.6, 2, 1.6, 2),
        width=width,
        align="LEFT",
    ) as table:
        header = table.row()
        header.cell("")
        for i, o in enumerate(quote.options, 1):
            title = o.name if n == 1 else f"Option {i}\n{o.name}"
            detail = ", ".join(b for b in (o.spec, o.location) if b)
            header.cell(pdf_safe(f"{title}\n{detail}" if detail else title))
        for label, values in rows:
            row = table.row()
            row.cell(label)
            for v in values:
                row.cell(v)
        total = table.row()
        total.cell("Total with GST", style=total_style)
        for o in quote.options:
            total.cell(money(o.price.total), style=total_style)

    # Terms
    pdf.ln(8)
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(*MUTED)
    terms = [f"This quote is valid until {_long_date(quote.valid_until)}.", *branding.terms]
    if n > 1:
        terms.insert(0, "Each option is a complete price for the same project. Choose one.")
    for line in terms:
        pdf.multi_cell(width, 4.8, pdf_safe(line), align="L", new_x="LMARGIN", new_y="NEXT")

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
        "Sinks": sinks,
        "Subtotal": round(o.price.subtotal, 2),
        "GST": round(o.price.tax, 2),
        "Total (incl. GST)": round(o.price.total, 2),
    } for i, o in enumerate(quote.options, 1)]
