"""How CounterPro looks: the stylesheet and the small pieces of HTML the screen
is built from. Nothing in here calculates a price; every number arrives ready
to show, so cards, the comparison and the quote can never disagree."""
from __future__ import annotations

import html

# Palette: white surfaces on a soft background, hairline borders, and the dark
# teal as the one action colour. A light teal tint marks "selected" and "lowest".
CSS = """
<style>
  :root {
    --bg:#F3F5F4; --surface:#FFFFFF; --line:#E1E6E3; --line-strong:#CCD4D0;
    --ink:#14201F; --muted:#586664; --teal:#17494D; --teal-hover:#1E5B60;
    --teal-50:#EDF4F3; --teal-100:#D7E7E5; --warn:#7A5200; --warn-bg:#FFF5DC; --danger:#9A2B22;
    --radius:12px; --shadow:0 1px 2px rgba(20,32,31,.06);
    --display:"Barlow Condensed","Barlow",system-ui,sans-serif;
  }
  .block-container { padding-top: 3.6rem; padding-bottom: 5rem; max-width: 1360px; }
  h1, h2, h3 { letter-spacing: 0; }
  h1 { font-size: 2.3rem !important; line-height: 1.05 !important; padding-bottom: 0.1rem !important; }
  h3 { font-size: 1.55rem !important; padding-top: 0 !important; }

  /* Panels: project setup, filters, quote, calculator */
  [class*="st-key-panel_"] {
    background: var(--surface); border: 1px solid var(--line); border-radius: var(--radius);
    box-shadow: var(--shadow); padding: 1.35rem 1.5rem 1.4rem;
  }

  /* Pop-up windows are white, like the panels */
  [data-testid="stDialog"] [role="dialog"] { background: var(--surface); }

  /* Buttons */
  button[kind="primary"], button[data-testid="stBaseButton-primary"] { transition: background-color .15s ease, box-shadow .15s ease; }
  button[data-testid="stBaseButton-primary"]:hover { background: var(--teal-hover); border-color: var(--teal-hover); }
  button[data-testid="stBaseButton-secondary"] { background: var(--surface); border-color: var(--line-strong); transition: border-color .15s ease, background-color .15s ease; }
  button[data-testid="stBaseButton-secondary"]:hover { border-color: var(--teal); color: var(--teal); background: var(--teal-50); }
  button:disabled { opacity: .55; }
  button:focus-visible, a:focus-visible { outline: 2px solid var(--teal); outline-offset: 2px; }

  /* Location / thickness / view choices: a chosen one is filled, not just outlined */
  [data-testid="stPills"] button, [data-testid="stButtonGroup"] button {
    background: var(--surface); border-color: var(--line-strong); transition: background-color .15s ease, color .15s ease, border-color .15s ease;
  }
  [data-testid="stPills"] button:hover, [data-testid="stButtonGroup"] button:hover { border-color: var(--teal); }
  [data-testid="stPills"] button[aria-pressed="true"], [data-testid="stPills"] button[aria-checked="true"],
  [data-testid="stButtonGroup"] button[aria-pressed="true"], [data-testid="stButtonGroup"] button[aria-checked="true"] {
    background: var(--teal) !important; border-color: var(--teal) !important; color: #fff !important;
  }
  [data-testid="stPills"] button[aria-pressed="true"] *, [data-testid="stPills"] button[aria-checked="true"] *,
  [data-testid="stButtonGroup"] button[aria-pressed="true"] *, [data-testid="stButtonGroup"] button[aria-checked="true"] * { color: #fff !important; }

  /* Project setup figures */
  .cp-stats { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; margin: .35rem 0 .2rem; }
  .cp-stat { background: var(--bg); border-radius: 10px; padding: .7rem .9rem; }
  .cp-stat span { display: block; color: var(--muted); font-size: .86rem; line-height: 1.25; }
  .cp-stat b { display: block; font-family: var(--display); font-weight: 600; font-size: 1.7rem; line-height: 1.15;
               color: var(--ink); font-variant-numeric: tabular-nums; }
  .cp-stat.is-key { background: var(--teal-50); }
  p.cp-note { color: var(--muted); font-size: .9rem !important; line-height: 1.45; margin: .55rem 0 0; }

  /* Slab photo, or a placeholder that cannot be mistaken for one */
  .cp-media { border-radius: 9px; overflow: hidden; background: var(--bg); position: relative; }
  .cp-media img { display: block; width: 100%; height: 100%; object-fit: cover; }
  .cp-media.lg { height: 132px; }
  .cp-media.md { height: 84px; width: 112px; }
  .cp-media.sm { height: 44px; width: 44px; flex: 0 0 44px; border-radius: 8px; }
  .cp-media.md { flex: 0 0 112px; }

  /* Slab cards */
  .st-key-grid { display: grid !important; grid-template-columns: repeat(auto-fill, minmax(232px, 1fr)); gap: 16px; align-items: stretch; }
  .st-key-grid > div { height: 100%; min-width: 0; }
  [class*="st-key-card_"], [class*="st-key-cardq_"], [class*="st-key-row_"], [class*="st-key-rowq_"] {
    background: var(--surface); border: 1px solid var(--line); border-radius: var(--radius); box-shadow: var(--shadow);
    transition: border-color .18s ease, box-shadow .18s ease, transform .18s ease;
  }
  [class*="st-key-card_"], [class*="st-key-cardq_"] { padding: .85rem .9rem .95rem; height: 100%; }
  /* Buttons sit at the foot of every card, so a row of cards lines up */
  [class*="st-key-card_"] > div:last-child, [class*="st-key-cardq_"] > div:last-child { margin-top: auto; }
  [class*="st-key-row_"], [class*="st-key-rowq_"] { padding: .7rem .95rem; }
  [class*="st-key-card_"]:hover, [class*="st-key-row_"]:hover { border-color: var(--line-strong); box-shadow: 0 4px 14px rgba(20,32,31,.08); }
  [class*="st-key-cardq_"], [class*="st-key-rowq_"] { border-color: var(--teal); box-shadow: 0 0 0 1px var(--teal) inset; background: #FBFDFD; }

  .cp-brand { color: var(--muted); font-size: .86rem; line-height: 1.2; margin-top: .65rem; }
  .cp-row .cp-brand { margin-top: 0; }
  .cp-brand:first-child { margin-top: 0; }
  .cp-name { font-family: var(--display); font-weight: 600; font-size: 1.42rem; line-height: 1.12; color: var(--ink); margin-top: 1px; }
  .cp-tags { display: flex; flex-wrap: wrap; gap: 5px; margin: .45rem 0 .5rem; }
  .cp-tag { border: 1px solid var(--line-strong); border-radius: 999px; padding: 1px 9px; font-size: .78rem; line-height: 1.5; color: var(--ink); background: var(--surface); white-space: nowrap; }
  .cp-tag.is-on { background: var(--teal); border-color: var(--teal); color: #fff; }
  .cp-tag.is-soft { background: var(--bg); border-color: var(--bg); color: var(--muted); }
  .cp-facts, ul.cp-facts { margin: 0 !important; padding: 0 !important; list-style: none; color: var(--muted); font-size: .88rem; line-height: 1.5; }
  ul.cp-facts li { margin: 0 !important; padding: 0 !important; font-size: .88rem !important; line-height: 1.5; list-style: none; }
  .cp-facts b { color: var(--ink); font-weight: 600; }
  .cp-staff { color: var(--teal); font-size: .82rem; margin-top: .35rem; }
  .cp-price { margin-top: .7rem; padding-top: .65rem; border-top: 1px solid var(--line); }
  .cp-price small { display: block; color: var(--muted); font-size: .8rem; line-height: 1.2; }
  .cp-price b { display: block; font-family: var(--display); font-weight: 700; font-size: 2.05rem; line-height: 1.08;
                color: var(--ink); font-variant-numeric: tabular-nums; }
  .cp-price span { display: block; color: var(--muted); font-size: .82rem; line-height: 1.3; margin-bottom: .55rem; }
  .cp-row { display: flex; gap: 14px; align-items: center; }
  .cp-row .cp-main { flex: 1 1 auto; min-width: 0; }
  .cp-row .cp-tags { margin: .3rem 0 .25rem; }
  .cp-row .cp-price { border: 0; margin: 0; padding: 0; text-align: right; flex: 0 0 auto; }
  .cp-row .cp-price b { font-size: 1.75rem; }
  .cp-row .cp-price span { margin-bottom: 0; max-width: 11rem; margin-left: auto; }

  /* Breakdown tables and totals */
  .cp-lines { width: 100%; border-collapse: collapse; margin: .4rem 0 .8rem; }
  .cp-lines, .cp-lines tr, .cp-lines td { border: 0 !important; background: transparent !important; }
  .cp-lines td { padding: .38rem 0 !important; border-bottom: 1px solid var(--line) !important; }
  .cp-lines td:last-child { text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; padding-left: 12px !important; }
  .cp-lines tr.is-strong td { font-weight: 600; }
  .cp-total { background: var(--teal-50); border: 1px solid var(--teal-100); color: var(--ink); border-radius: 10px;
              padding: .85rem 1.05rem; display: flex; justify-content: space-between; align-items: baseline; gap: 1rem; }
  .cp-total b { font-family: var(--display); font-weight: 700; font-size: 2.2rem; line-height: 1; font-variant-numeric: tabular-nums; }
  .cp-empty { border: 1.5px dashed var(--line-strong); border-radius: 10px; padding: 1.1rem 1.2rem; color: var(--muted); background: var(--surface); }
  .cp-empty b { color: var(--ink); display: block; margin-bottom: 2px; }
  .cp-banner { background: var(--warn-bg); border: 1px solid #F0DCA8; color: var(--warn); border-radius: 10px; padding: .7rem .95rem; }
  .cp-result { font-size: 1.05rem; color: var(--ink); margin: .2rem 0 0; }
  .cp-result b { font-family: var(--display); font-size: 1.5rem; font-weight: 600; }
  p.cp-excluded { color: var(--muted); font-size: .9rem !important; margin: 0; }
  p.cp-result { margin-bottom: 0; }

  /* Active filters */
  .st-key-chips button { border-radius: 999px; padding: 0 .7rem; min-height: 1.9rem; font-size: .84rem; background: var(--teal-50); border-color: var(--teal-100); color: var(--teal); }
  .st-key-chips button:hover { background: var(--teal-100); }

  /* Quote panel */
  .cp-qitem { display: flex; gap: 11px; align-items: flex-start; }
  .cp-qitem .cp-qtext { min-width: 0; flex: 1 1 auto; }
  .cp-qitem .cp-qname { font-weight: 600; line-height: 1.25; color: var(--ink); }
  .cp-qitem .cp-qmeta { color: var(--muted); font-size: .84rem; line-height: 1.35; }
  .cp-qitem .cp-qprice { font-family: var(--display); font-weight: 600; font-size: 1.3rem; line-height: 1.25; font-variant-numeric: tabular-nums; }
  .cp-qitem .cp-qsub { color: var(--muted); font-size: .8rem; line-height: 1.3; }
  .cp-kv { display: flex; justify-content: space-between; gap: 12px; font-size: .92rem; padding: .18rem 0; }
  .cp-kv span:first-child { color: var(--muted); }
  .cp-kv span:last-child { text-align: right; font-variant-numeric: tabular-nums; }

  /* Comparison */
  .cp-compare-wrap { margin-bottom: .9rem; overflow-x: auto; border: 1px solid var(--line); border-radius: var(--radius); background: var(--surface); box-shadow: var(--shadow); }
  table.cp-compare { width: 100%; min-width: 560px; border-collapse: collapse; table-layout: fixed; }
  table.cp-compare, table.cp-compare tr, table.cp-compare td, table.cp-compare th { border: 0 !important; background: transparent; }
  table.cp-compare th, table.cp-compare td { padding: .6rem .9rem !important; text-align: left; vertical-align: top; border-bottom: 1px solid var(--line) !important; font-weight: 400; }
  table.cp-compare tr:last-child td, table.cp-compare tr:last-child th { border-bottom: 0 !important; }
  table.cp-compare th.cp-rowlabel, table.cp-compare td.cp-rowlabel { color: var(--muted); font-size: .88rem; width: 20%; white-space: nowrap; }
  table.cp-compare td.is-low, table.cp-compare th.is-low { background: var(--teal-50) !important; }
  table.cp-compare .cp-name { font-size: 1.25rem; margin-top: .5rem; }
  table.cp-compare tr.is-price td { font-family: var(--display); font-weight: 700; font-size: 1.5rem; font-variant-numeric: tabular-nums; }
  table.cp-compare tr.is-price td.cp-rowlabel { font-family: inherit; font-weight: 400; font-size: .88rem; }
  .cp-lowtag { display: inline-block; background: var(--teal); color: #fff; border-radius: 999px; font-size: .74rem; padding: 0 8px; line-height: 1.6; font-family: "Barlow",sans-serif; font-weight: 600; vertical-align: middle; margin-left: 6px; }

  /* Keep the quote in view while browsing (desktop and tablet) */
  @media (min-width: 641px) {
    [data-testid="stColumn"]:has(.st-key-panel_quote) { position: sticky; top: 4.2rem; align-self: flex-start;
      max-height: calc(100vh - 5rem); overflow-y: auto; overscroll-behavior: contain; scrollbar-width: thin; }
    .cp-mobilebar { display: none !important; }
  }
  /* Phones: a slim bar that jumps to the quote, so it never covers the slabs */
  .cp-mobilebar { position: fixed; left: 0; right: 0; bottom: 0; z-index: 999; background: var(--teal); color: #fff !important;
                  display: flex; justify-content: space-between; align-items: center; gap: 12px; padding: .7rem 1rem;
                  text-decoration: none !important; font-weight: 600; box-shadow: 0 -2px 10px rgba(0,0,0,.15); }
  .cp-mobilebar span:last-child { font-weight: 400; text-decoration: underline; white-space: nowrap; }
  @media (max-width: 640px) {
    .block-container { padding-left: 1rem; padding-right: 1rem; }
    [class*="st-key-panel_"] { padding: 1.05rem 1rem 1.1rem; }
    .cp-stats { grid-template-columns: 1fr 1fr; } .cp-stat.is-key { grid-column: 1 / -1; }
    .cp-row { flex-wrap: wrap; } .cp-row .cp-price { text-align: left; flex-basis: 100%; }
    .st-key-grid { grid-template-columns: 1fr; }
  }
  @media (prefers-reduced-motion: reduce) { * { transition: none !important; } }
</style>
"""


def esc(value: object) -> str:
    return html.escape(str(value))


def media(photo_url: str, colour: str, size: str = "lg") -> str:
    """A slab photo when there is a real one, otherwise nothing at all: no
    placeholder, and never a stand-in for what the slab looks like."""
    if not photo_url:
        return ""
    return (f'<div class="cp-media {size}"><img src="{esc(photo_url)}" alt="Photo of {esc(colour)}" '
            f'loading="lazy"></div>')


def tags(items: list[tuple[str, str]]) -> str:
    """items: (text, style) where style is '', 'on' or 'soft'."""
    return '<div class="cp-tags">' + "".join(
        f'<span class="cp-tag{(" is-" + style) if style else ""}">{esc(text)}</span>' for text, style in items if text
    ) + "</div>"


def facts(lines: list[tuple[str, str]]) -> str:
    return '<ul class="cp-facts">' + "".join(
        f"<li>{esc(label)} <b>{esc(value)}</b></li>" for label, value in lines if value) + "</ul>"


def price_block(label: str, amount: str, note: str) -> str:
    return (f'<div class="cp-price"><small>{esc(label)}</small><b>{esc(amount)}</b>'
            f'<span>{esc(note)}</span></div>')


def card(*, photo_url: str, brand: str, colour: str, tag_items: list, fact_lines: list, staff_line: str,
         price_label: str, price: str, price_note: str) -> str:
    """One slab as a product card (grid view)."""
    staff = f'<div class="cp-staff">{esc(staff_line)}</div>' if staff_line else ""
    return (media(photo_url, colour, "lg")
            + f'<div class="cp-brand">{esc(brand)}</div><div class="cp-name">{esc(colour)}</div>'
            + tags(tag_items) + facts(fact_lines) + staff + price_block(price_label, price, price_note))


def row(*, photo_url: str, brand: str, colour: str, tag_items: list, fact_text: str, staff_line: str,
        price_label: str, price: str, price_note: str) -> str:
    """One slab as a compact row (list view)."""
    staff = f'<div class="cp-staff">{esc(staff_line)}</div>' if staff_line else ""
    return ('<div class="cp-row">' + media(photo_url, colour, "md")
            + f'<div class="cp-main"><div class="cp-brand">{esc(brand)}</div><div class="cp-name">{esc(colour)}</div>'
            + tags(tag_items) + f'<div class="cp-facts">{esc(fact_text)}</div>' + staff + "</div>"
            + price_block(price_label, price, price_note) + "</div>")


def stats(items: list[tuple[str, str, bool]]) -> str:
    """Project figures: (label, value, is_key)."""
    return '<div class="cp-stats">' + "".join(
        f'<div class="cp-stat{" is-key" if key else ""}"><span>{esc(label)}</span><b>{esc(value)}</b></div>'
        for label, value, key in items) + "</div>"


def lines_table(lines: list[tuple[str, str]], strong: tuple[str, ...] = ()) -> str:
    return '<table class="cp-lines">' + "".join(
        f'<tr{" class=is-strong" if label in strong else ""}><td>{esc(label)}</td><td>{esc(value)}</td></tr>'
        for label, value in lines) + "</table>"


def total_block(label: str, amount: str) -> str:
    return f'<div class="cp-total"><span>{esc(label)}</span><b>{esc(amount)}</b></div>'


def quote_item(*, photo_url: str, number: int, name: str, colour: str, meta: str, price: str, sub: str) -> str:
    return ('<div class="cp-qitem">' + media(photo_url, colour, "sm")
            + f'<div class="cp-qtext"><div class="cp-qname">{number}. {esc(name)}</div>'
            f'<div class="cp-qmeta">{esc(meta)}</div><div class="cp-qprice">{esc(price)}</div>'
            f'<div class="cp-qsub">{esc(sub)}</div></div></div>')


def key_values(pairs: list[tuple[str, str]]) -> str:
    return "".join(f'<div class="cp-kv"><span>{esc(k)}</span><span>{esc(v)}</span></div>' for k, v in pairs)


def compare_table(options: list[dict], rows: list[tuple[str, str]], lowest: int | None,
                  price_key: str = "installed") -> str:
    """Side-by-side table. `options` are dicts of ready-to-show text keyed by the
    row keys in `rows`; `lowest` is the index of the least expensive option."""
    def cls(i: int) -> str:
        return ' class="is-low"' if i == lowest and len(options) > 1 else ""

    head = '<tr><th class="cp-rowlabel"></th>' + "".join(
        f'<th{cls(i)}>{media(o.get("photo_url", ""), o["colour"], "md")}'
        f'<div class="cp-brand">Option {i + 1}</div><div class="cp-name">{esc(o["name"])}</div></th>'
        for i, o in enumerate(options)) + "</tr>"
    body = ""
    for key, label in rows:
        cells = ""
        for i, o in enumerate(options):
            text = esc(o.get(key, ""))
            if key == price_key and i == lowest and len(options) > 1:
                text += '<span class="cp-lowtag">Lowest</span>'
            cells += f"<td{cls(i)}>{text}</td>"
        body += (f'<tr{" class=is-price" if key == price_key else ""}>'
                 f'<td class="cp-rowlabel">{esc(label)}</td>{cells}</tr>')
    return f'<div class="cp-compare-wrap"><table class="cp-compare">{head}{body}</table></div>'


def mobile_bar(count: int, lowest_price: str) -> str:
    if not count:
        return ""
    label = f"Quote: {count} material{'' if count == 1 else 's'}" + (f", from {lowest_price}" if lowest_price else "")
    return f'<a class="cp-mobilebar" href="#quote"><span>{esc(label)}</span><span>Review quote</span></a>'
