"""Everything a non-programmer might need to change lives in this file:
pricing rates, the sink price list, branch details and the inventory feed.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

# Hosted servers run on UTC. Quote dates and upload times use the branch's clock.
TIMEZONE = "America/Vancouver"


def now() -> datetime:
    """Current local time at the branch (no timezone attached)."""
    return datetime.now(ZoneInfo(TIMEZONE)).replace(tzinfo=None)


# --- Pricing rules ----------------------------------------------------------
@dataclass(frozen=True)
class PricingRules:
    install_per_sqft: float = 21.0       # charged to the customer per finished sq ft
    fabrication_per_sqft: float = 16.0   # raw fabrication cost per finished sq ft
    waste_factor: float = 1.20           # material needed = finished sq ft x this
    tax_rate: float = 0.05               # GST

    ib_material_markup: float = 1.05     # 5% markup on raw material for IB
    ib_min_margin: float = 0.18          # IB must be at least 18% margin over raw cost
    ib_to_customer_markup: float = 1.15  # customer material + fab is 15% above IB

    healthy_margin_pct: float = 18.0     # staff view flags a quote below this


RULES = PricingRules()


# --- Sinks ------------------------------------------------------------------
@dataclass(frozen=True)
class Sink:
    sku: str
    name: str
    category: str   # Kitchen, Bar, Vanity, Other
    detail: str     # gauge or material
    price: float

    @property
    def label(self) -> str:
        bits = [self.name]
        if self.detail:
            bits.append(f"({self.detail})")
        return " ".join(bits)


SINKS: tuple[Sink, ...] = (
    Sink("NONE", "In-stock / no sink", "Other", "", 0.00),
    # Kitchen, standard radius
    Sink("83742", "50/50 Undermount, Standard Radius", "Kitchen", "16 ga", 300.00),
    Sink("83744", "Large Single Bowl Undermount, Standard Radius", "Kitchen", "16 ga", 325.00),
    Sink("83745", "Medium Single Bowl Undermount, Standard Radius", "Kitchen", "18 ga", 230.00),
    Sink("83747", "60/40 Undermount, Standard Radius", "Kitchen", "16 ga", 370.00),
    Sink("83995", "40/60 Undermount, Standard Radius", "Kitchen", "16 ga", 370.00),
    # Kitchen, 15 degree radius
    Sink("83749", "50/50 Undermount, 15° Radius", "Kitchen", "18 ga", 440.00),
    Sink("83748", "Large Single Bowl Undermount, 15° Radius", "Kitchen", "18 ga", 450.00),
    Sink("83750", "Medium Single Bowl Undermount, 15° Radius", "Kitchen", "18 ga", 400.00),
    # Top-mount
    Sink("85446", "Top-mount Double Bowl, Standard Radius", "Kitchen", "18 ga", 270.00),
    # Bar
    Sink("83993", "Large Bar Undermount, Standard Radius", "Bar", "18 ga", 250.00),
    Sink("83992", "Small Bar Undermount, Standard Radius", "Bar", "18 ga", 180.00),
    # Vanity (white porcelain)
    Sink("84020", "Large Rectangular Undermount Vanity", "Vanity", "porcelain", 105.00),
    Sink("84022", "Medium Rectangular Undermount Vanity", "Vanity", "porcelain", 105.00),
    Sink("84024", "Large Oval Undermount Vanity", "Vanity", "porcelain", 89.00),
    Sink("84026", "Medium Oval Undermount Vanity", "Vanity", "porcelain", 89.00),
)
SINKS_BY_SKU = {s.sku: s for s in SINKS}


# --- Inventory ---------------------------------------------------------------
# Inventory comes from Moraware through the store (see counterpro/store.py).
# The Google Sheet the app used to read has been retired. Extra CSV feeds can
# still be listed here, or in COUNTERPRO_DATA_SOURCES; they are only read when
# the store has no inventory in it.
_DEFAULT_SOURCES: tuple[str, ...] = ()


def data_sources() -> tuple[str, ...]:
    """Extra feed URLs or file paths, used only when the store is empty. Set
    COUNTERPRO_DATA_SOURCES (comma separated) to add a CSV or a saved Moraware page."""
    override = os.environ.get("COUNTERPRO_DATA_SOURCES", "").strip()
    if override:
        return tuple(s.strip() for s in override.split(",") if s.strip())
    return _DEFAULT_SOURCES


CACHE_SECONDS = 60

# Moraware keeps some serial numbers as 1" x 1" placeholders with no cost
# (seen on remnant racks). A row smaller than this, or with no cost, cannot be
# priced, so it is left out and counted in the staff sidebar.
MIN_SLAB_SQFT = 1.0

# Staff are warned in the sidebar once the Moraware inventory is older than this
# many days (the sync has stopped: Chrome closed, signed out, or the token expired).
UPLOAD_STALE_DAYS = 3
UPLOAD_MAX_MB = 5


def staff_code() -> str:
    """Code that unlocks cost, margin and inventory uploads. Set the
    COUNTERPRO_STAFF_CODE environment variable (or `staff_code` in Streamlit
    secrets). Without one, uploads are switched off."""
    return os.environ.get("COUNTERPRO_STAFF_CODE", "").strip()

# The feed names each slab like "15 - Caesarstone (VER) Blizzard #2141 2cm".
# The number is the branch, the code in brackets is the location.
BRANCH_LOCATIONS = {"15": "VER", "17": "ABB", "11": "EDM", "07": "SKTN", "7": "SKTN"}
LOCATION_NAMES = {"VER": "Vernon", "ABB": "Abbotsford", "EDM": "Edmonton", "SKTN": "Saskatoon"}   # shown to staff and customers
HOME_LOCATION = "VER"

# Different spellings of the same supplier in the feed.
BRAND_ALIASES = {
    "Wilsonart Quartz": "Wilsonart",
    "Granite - Natural Stone": "Natural Stone",
    "Viatera Quartz": "Viatera",
    "Corian (Zodiaq)": "Corian Quartz",
    "Corian (Zodiaq) Quartz": "Corian Quartz",
}
# Used only when a feed row has no "(VER)"-style location code to split on.
KNOWN_BRANDS = (
    "GS Granite", "Natural Stone", "Caesarstone", "Cambria", "Dekton", "Firstone",
    "Hanstone", "Infinity", "Omnia Quartz", "Silestone", "Vicostone", "Viatera",
    "Wilsonart",
)
FINISHES = ("Polished", "Matte", "Velvet", "Honed", "Leathered", "Suede", "Brushed", "Satin")


# --- Quote and branding -----------------------------------------------------
@dataclass(frozen=True)
class Branding:
    app_name: str = "CounterPro"
    # Small logo beside the page title. Leave empty for none.
    logo_url: str = "https://i.ibb.co/kVXQt6v4/Gemini-Generated-Image-shnzslshnzslshnz.png"
    company: str = "FloForm Countertops"
    branch: str = "Vernon, BC"
    # Extra lines printed under the company name on the quote
    # (address, phone, email). Empty until filled in.
    contact_lines: tuple[str, ...] = ()
    quote_prefix: str = "CP"
    quote_valid_days: int = 30
    max_quote_options: int = 4
    # Extra lines for the small print at the foot of the quote. Site preparation,
    # which used to be the only line here, is now in the "Not included" list.
    terms: tuple[str, ...] = ()
    # Printed on the quote. Edit these to match what FloForm actually includes.
    # Sinks are added to one list or the other by the quote itself, depending on
    # whether the quote has any.
    included: tuple[str, ...] = (
        "Slab material",
        "Fabrication",
        "Installation",
    )
    excluded: tuple[str, ...] = (
        "Installation site preparation",
        "Anything not listed on this quote",
    )
    disclaimers: tuple[str, ...] = (
        "This is an estimate based on the finished area shown. A different measured area changes the price.",
        "Slabs shown are in stock at the time of this quote and can sell before an order is placed.",
    )


BRANDING = Branding()

# Slab photos. Moraware does not hold any, so the app shows none. A photo only
# appears for a colour listed here (or when the inventory feed has an "Image URL" column).
# Key: the name as shown on the card, brand then colour, e.g. "Caesarstone Blizzard".
SLAB_PHOTOS: dict[str, str] = {}


def photo_for(name: str, feed_url: str = "") -> str:
    """Web address of a real photo of this slab colour, or '' when there is none."""
    url = (feed_url or SLAB_PHOTOS.get(name, "") or "").strip()
    return url if url.lower().startswith(("https://", "http://")) else ""


SQFT_DEFAULT = 35.0
SQFT_MAX = 500.0
PAGE_SIZE = 12
