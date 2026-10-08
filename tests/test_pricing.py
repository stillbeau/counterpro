import itertools

import pytest

from counterpro.config import PricingRules
from counterpro.pricing import price_job


def original_calculate_cost(unit_cost, project_sqft, sink_price=0.0):
    """The pricing function from the pre-rework app.py, copied as-is.
    The rework must not move a customer price by a cent."""
    INSTALL, FAB, WASTE, TAX = 21.0, 16.0, 1.20, 0.05
    uc, sq = float(unit_cost), float(project_sqft)
    raw_material = uc * sq * WASTE
    raw_fab = FAB * sq
    direct = raw_material + raw_fab
    ib = max(raw_material * 1.05 + raw_fab, direct / (1 - 0.18))
    mat_fab = ib * 1.15
    ins = INSTALL * sq
    slab_subtotal = mat_fab + ins
    subtotal = slab_subtotal + float(sink_price)
    profit = slab_subtotal - (direct + ins)
    return {
        "customer_mat_fab": mat_fab, "customer_ins": ins, "sink_price": float(sink_price),
        "slab_subtotal": slab_subtotal, "subtotal": subtotal, "ib_cost": ib,
        "margin_pct": profit / slab_subtotal * 100 if slab_subtotal > 0 else 0,
        "total_with_tax": subtotal * (1 + TAX),
    }


@pytest.mark.parametrize("unit_cost,sqft,sinks", list(itertools.product(
    [5.0, 7.08, 14.44, 21.99, 30.37, 52.8, 65.73], [1, 20, 35, 42.5, 60, 120, 500], [0, 230, 815])))
def test_matches_original_prices(unit_cost, sqft, sinks):
    old = original_calculate_cost(unit_cost, sqft, sinks)
    new = price_job(unit_cost, sqft, sinks)
    assert new.material_fab == pytest.approx(old["customer_mat_fab"], abs=1e-9)
    assert new.install == pytest.approx(old["customer_ins"], abs=1e-9)
    assert new.sinks == pytest.approx(old["sink_price"], abs=1e-9)
    assert new.subtotal == pytest.approx(old["subtotal"], abs=1e-9)
    assert new.total == pytest.approx(old["total_with_tax"], abs=1e-9)
    assert new.ib_cost == pytest.approx(old["ib_cost"], abs=1e-9)
    assert new.margin_pct == pytest.approx(old["margin_pct"], abs=1e-9)


def test_worked_example():
    # $20/sf slab, 35 finished sq ft, one $300 sink
    p = price_job(20.0, 35.0, 300.0)
    assert p.material_sqft == pytest.approx(42.0)
    assert p.direct_cost == pytest.approx(20 * 42 + 16 * 35)          # 1400
    assert p.ib_cost == pytest.approx(1400 / 0.82)
    assert p.material_fab == pytest.approx(1400 / 0.82 * 1.15)
    assert p.install == pytest.approx(735.0)
    assert p.tax == pytest.approx(p.subtotal * 0.05)
    assert p.total == pytest.approx(p.subtotal + p.tax)
    assert round(p.total, 2) == 3148.34


def test_margin_floor_always_sets_ib_under_current_rules():
    """With a 5% material markup and an 18% floor, the floor is always the
    larger number, so the markup never decides the price. This test documents
    that; if the rules change so the markup can win, it will fail and should
    be updated on purpose."""
    for unit_cost, sqft in itertools.product([1, 7, 20, 60, 200], [1, 35, 500]):
        p = price_job(unit_cost, sqft)
        assert p.ib_cost == pytest.approx(p.direct_cost / 0.82)


def test_markup_wins_when_floor_is_low():
    rules = PricingRules(ib_min_margin=0.01)
    p = price_job(40.0, 35.0, rules=rules)
    raw_material, raw_fab = 40 * 42, 16 * 35
    assert p.ib_cost == pytest.approx(raw_material * 1.05 + raw_fab)


def test_sinks_do_not_change_margin():
    assert price_job(20, 35, 0).margin_pct == pytest.approx(price_job(20, 35, 900).margin_pct)


def test_zero_sqft_is_safe():
    p = price_job(20, 0)
    assert p.total == 0 and p.margin_pct == 0 and p.per_sqft == 0
