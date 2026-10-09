"""The small HTML pieces the screen is built from."""
from counterpro import config, ui


def test_no_photo_means_nothing_is_drawn():
    assert ui.media("", "Calacatta Nuvo") == ""
    card = ui.card(photo_url="", brand="Cambria", colour="Brittanicca", tag_items=[], fact_lines=[], staff_line="",
                   price_label="Estimated installed price", price="$1,000", price_note="note")
    assert "cp-media" not in card and "<img" not in card
    assert "cp-media" not in ui.quote_item(photo_url="", number=1, name="Cambria Brittanicca", colour="Brittanicca",
                                           meta="3cm", price="$1,000", sub="installed")
    assert "No photo" not in ui.CSS and "is-empty" not in ui.CSS


def test_real_photo_is_used_and_described():
    tile = ui.media("https://example.com/a.jpg", "Calacatta Nuvo", "sm")
    assert '<img src="https://example.com/a.jpg" alt="Photo of Calacatta Nuvo"' in tile


def test_text_from_the_feed_is_escaped():
    card = ui.card(photo_url='x" onerror="alert(1)', brand="<b>Brand</b>", colour="<script>x</script>",
                   tag_items=[("<i>3cm</i>", "")], fact_lines=[("In stock:", "<u>1</u>")], staff_line="",
                   price_label="Estimated installed price", price="$1,000", price_note="note")
    assert "<script>" not in card and "<b>Brand</b>" not in card and "<i>3cm</i>" not in card
    assert 'onerror="alert' not in card


def test_empty_facts_and_tags_are_left_out():
    assert ui.tags([("3cm", ""), ("", "soft")]).count("cp-tag") == 2      # the wrapper and one tag
    assert ui.facts([("In stock:", "1 slab"), ("In stock since:", "")]).count("<li>") == 1


def test_compare_table_marks_only_the_lowest():
    options = [{"name": "A", "colour": "A", "installed": "$2,000.00"},
               {"name": "B", "colour": "B", "installed": "$1,500.00"}]
    table = ui.compare_table(options, [("installed", "Estimated installed price")], lowest=1)
    assert table.count("cp-lowtag") == 1
    assert '$1,500.00<span class="cp-lowtag">Lowest</span>' in table
    assert '<td>$2,000.00</td>' in table                                   # the other option is left plain
    alone = ui.compare_table(options[:1], [("installed", "Estimated installed price")], lowest=0)
    assert "cp-lowtag" not in alone and "is-low" not in alone


def test_mobile_bar():
    assert ui.mobile_bar(0, "") == ""
    assert "Quote: 1 material, from $1,933" in ui.mobile_bar(1, "$1,933")
    assert "Quote: 3 materials" in ui.mobile_bar(3, "$1,933") and 'href="#quote"' in ui.mobile_bar(3, "$1")


def test_photo_lookup():
    assert config.photo_for("Caesarstone Blizzard", "") == ""             # no photo is the normal case
    assert config.photo_for("Caesarstone Blizzard", "https://example.com/b.jpg") == "https://example.com/b.jpg"
    assert config.photo_for("Caesarstone Blizzard", "not a link") == ""
