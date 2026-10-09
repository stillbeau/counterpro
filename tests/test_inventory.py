import pandas as pd
import pytest

from counterpro.inventory import (clean_slabs, load_slabs, parse_variant,
                                  picks_for_variant, slabs_for_job, summarize)


@pytest.mark.parametrize("raw,brand,color,thickness,finish,location", [
    ("17 - Caesarstone (ABB) Turbine Grey #6313 2cm", "Caesarstone", "Turbine Grey", "2cm", "", "ABB"),
    ("15 - Caesarstone (VER) Himalayan Moon#6611 3cm", "Caesarstone", "Himalayan Moon", "3cm", "", "VER"),
    ("15 - Caesarstone (VER) Calacatta Nuvo #5131 (EX) 2cm", "Caesarstone", "Calacatta Nuvo", "2cm", "", "VER"),
    ("15 - Caesarstone (VER) Airy Concrete #4044 2cm", "Caesarstone", "Airy Concrete", "2cm", "", "VER"),
    ("17 - Cambria (ABB) Berwyn (EX) 2cm Polished", "Cambria", "Berwyn", "2cm", "Polished", "ABB"),
    ("15 - Cambria (VER) Southampton (VER) 3cm Polished", "Cambria", "Southampton", "3cm", "Polished", "VER"),
    ("17 - Cambria (ABB) Weybourne 2cm Matte", "Cambria", "Weybourne", "2cm", "Matte", "ABB"),
    ("17 - Dekton (ABB ) Bromo Matte 2cm", "Dekton", "Bromo", "2cm", "Matte", "ABB"),
    ("17 - Dekton (ABB ) Rem Velvet 1.2cm", "Dekton", "Rem", "1.2cm", "Velvet", "ABB"),
    ("17 - Firstone (ABB) C5127 2cm", "Firstone", "C5127", "2cm", "", "ABB"),
    ("17 - Infinity (ABB) MB11 Nero Marquinia 1.2cm Polished", "Infinity", "MB11 Nero Marquinia", "1.2cm", "Polished", "ABB"),
    ("17 - Natural Stone (ABB) *HD Ashen White 3cm", "Natural Stone", "HD Ashen White", "3cm", "", "ABB"),
    ("17 - Rona Quartz/FF Signature (ABB) UHD-686/8K-66 - Ultra Bianco (R) 3cm",
     "Rona Quartz/FF Signature", "UHD-686/8K-66 - Ultra Bianco", "3cm", "", "ABB"),
    ("15 - Vicostone (VER) Crystal Salt BQ900 3cm", "Vicostone", "Crystal Salt BQ900", "3cm", "", "VER"),
    ("17 - Wilsonart Quartz (ABB) Capogrossi Q4052 3cm", "Wilsonart", "Capogrossi Q4052", "3cm", "", "ABB"),
    ("15 - Granite - Natural Stone (VER) Andino White 3cm Polished", "Natural Stone", "Andino White", "3cm", "Polished", "VER"),
    ("15 - GS Granite Alaska Bianca 3cm Polished", "GS Granite", "Alaska Bianca", "3cm", "Polished", "VER"),
    ("15 - Silestone (VER) Eternal Calacatta Gold (EX) 1.2cm", "Silestone", "Eternal Calacatta Gold", "1.2cm", "", "VER"),
    ("11 - Caesarstone (EDM) Blizzard #2141 1.3cm", "Caesarstone", "Blizzard", "1.3cm", "", "EDM"),
    ("07 - Cimstone (SKTN Fresh Linens 2cm", "Cimstone", "Fresh Linens", "2cm", "", "SKTN"),
    ("07 - Cimstone (SKTN) Fresh Linens 2cm", "Cimstone", "Fresh Linens", "2cm", "", "SKTN"),
    ("11 - GS Granite Alaska Bianca 3cm Polished", "GS Granite", "Alaska Bianca", "3cm", "Polished", "EDM"),
    ("15 - Cambria (VER) Portrush (EX) 2cm Polished", "Cambria", "Portrush", "2cm", "Polished", "VER"),
])
def test_parse_variant(raw, brand, color, thickness, finish, location):
    v = parse_variant(raw)
    assert (v.brand, v.color, v.thickness, v.finish, v.location) == (brand, color, thickness, finish, location)


def test_parse_keeps_codes_and_tags():
    v = parse_variant("15 - Caesarstone (VER) Calacatta Nuvo #5131 (EX) 2cm")
    assert v.color_code == "5131" and v.tags == ("EX",)
    assert parse_variant("15 - Cambria (VER) Southampton (VER) 3cm Polished").tags == ()


@pytest.mark.parametrize("raw", ["", None, "???", "Mystery", 42])
def test_parse_never_raises(raw):
    v = parse_variant(raw)
    assert v.brand and v.color


def test_clean_slabs(slabs):
    assert len(slabs) == 15                       # the zero-quantity slab is dropped
    blizzard = slabs[slabs["color"] == "Blizzard"]
    assert list(blizzard["cost"]) == [1120.00, 1222.67]
    assert slabs.loc[slabs["serial"] == "T2002", "available"].item() == 0   # fully allocated
    assert "T6002 (VRN)" in set(slabs["serial"])
    assert "9999-0001-D01" in set(slabs["serial"])


def test_clean_slabs_needs_core_columns():
    with pytest.raises(ValueError, match="Serialized On Hand Cost"):
        clean_slabs(pd.DataFrame({"Product Variant": ["x"], "On Hand Qty": ["1"]}))


def test_load_reports_bad_source_but_keeps_good(tmp_path):
    from tests.conftest import FIXTURE
    result = load_slabs([str(tmp_path / "missing.csv"), str(FIXTURE)])
    assert len(result.errors) == 1 and "missing.csv" in result.errors[0]
    assert result.slabs is not None and len(result.slabs) == 15
    assert load_slabs([str(tmp_path / "missing.csv")]).slabs is None


def test_summarize(slabs):
    s = summarize(slabs).set_index("variant")
    b = s.loc["15 - Caesarstone (VER) Blizzard #2141 2cm"]
    assert b["slab_count"] == 2
    assert b["available"] == pytest.approx(114.2222)
    assert b["unit_cost"] == pytest.approx((1120.00 + 1222.67) / 114.2222)
    assert b["name"] == "Caesarstone Blizzard" and b["spec"] == "2cm"

    berwyn = s.loc["17 - Cambria (ABB) Berwyn (EX) 2cm Polished"]
    assert berwyn["slab_count"] == 2                 # one of three is allocated
    assert berwyn["available"] == pytest.approx(120.0832)
    assert berwyn["unit_cost"] == pytest.approx(30.0, abs=0.01)   # cost basis still uses all three


def test_slabs_for_job_single():
    picks = slabs_for_job([("a", 56), ("b", 58.2)], 42)
    assert [p.serial for p in picks] == ["a"]       # smaller slab that still covers


def test_slabs_for_job_two_slabs():
    picks = slabs_for_job([("a", 56), ("b", 58.2), ("c", 47)], 72)
    assert len(picks) == 2
    assert sum(p.sqft for p in picks) >= 72
    assert [p.serial for p in picks] == ["b", "c"]  # largest, then smallest that finishes the job


def test_slabs_for_job_not_enough():
    assert slabs_for_job([("a", 56)], 72) is None
    assert slabs_for_job([], 10) is None
    assert slabs_for_job([("a", 0), ("b", float("nan"))], 10) is None


def test_slabs_for_job_exact_fit():
    assert [p.serial for p in slabs_for_job([("a", 42.0)], 35 * 1.2)] == ["a"]


def test_allocated_slab_is_not_offered(slabs):
    variant = "17 - Cambria (ABB) Berwyn (EX) 2cm Polished"
    picks = picks_for_variant(slabs, variant, 100)
    assert {p.serial for p in picks} == {"T2001", "T2003"}
    assert picks_for_variant(slabs, variant, 130) is None    # 180 on hand, only 120 free



def test_all_four_locations_have_names():
    from counterpro.inventory import location_name
    assert [location_name(c) for c in ("VER", "ABB", "EDM", "SKTN")] == ["Vernon", "Abbotsford", "Edmonton", "Saskatoon"]
