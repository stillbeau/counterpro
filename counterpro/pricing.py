"""Job pricing. No Streamlit in here so it can be tested on its own."""
from __future__ import annotations

from dataclasses import dataclass

from .config import RULES, PricingRules


@dataclass(frozen=True)
class Price:
    sqft: float              # finished square feet
    material_sqft: float     # finished sq ft plus waste
    # What the customer sees
    material_fab: float
    install: float
    sinks: float
    subtotal: float          # before tax, sinks included
    tax: float
    total: float
    # Internal
    direct_cost: float       # raw material + raw fabrication
    ib_cost: float
    slab_subtotal: float     # material_fab + install (no sinks)
    profit: float
    margin_pct: float

    @property
    def per_sqft(self) -> float:
        """Installed price per finished sq ft, before tax and sinks."""
        return self.slab_subtotal / self.sqft if self.sqft else 0.0


def price_job(unit_cost: float, sqft: float, sinks_total: float = 0.0,
              rules: PricingRules = RULES) -> Price:
    """Price a job from a slab's cost per sq ft.

    1. Raw direct cost = material (with waste) + fabrication.
    2. IB = the larger of (material marked up + fabrication) and
       (direct cost at the minimum IB margin).
    3. Customer material + fabrication = IB plus the customer markup.
    4. Installation and sinks are added on top, then GST.
    """
    unit_cost = float(unit_cost)
    sqft = float(sqft)
    sinks_total = float(sinks_total)
    material_sqft = sqft * rules.waste_factor

    raw_material = unit_cost * material_sqft
    raw_fab = rules.fabrication_per_sqft * sqft
    direct_cost = raw_material + raw_fab

    ib_from_markup = raw_material * rules.ib_material_markup + raw_fab
    ib_from_floor = direct_cost / (1 - rules.ib_min_margin)
    ib_cost = max(ib_from_markup, ib_from_floor)

    material_fab = ib_cost * rules.ib_to_customer_markup
    install = rules.install_per_sqft * sqft
    slab_subtotal = material_fab + install
    subtotal = slab_subtotal + sinks_total
    tax = subtotal * rules.tax_rate

    # Installation is passed through at cost, so profit comes from material + fab only.
    profit = slab_subtotal - (direct_cost + install)
    margin_pct = profit / slab_subtotal * 100 if slab_subtotal > 0 else 0.0

    return Price(
        sqft=sqft,
        material_sqft=material_sqft,
        material_fab=material_fab,
        install=install,
        sinks=sinks_total,
        subtotal=subtotal,
        tax=tax,
        total=subtotal + tax,
        direct_cost=direct_cost,
        ib_cost=ib_cost,
        slab_subtotal=slab_subtotal,
        profit=profit,
        margin_pct=margin_pct,
    )


def money(value: float, cents: bool = True) -> str:
    return f"${value:,.2f}" if cents else f"${value:,.0f}"
