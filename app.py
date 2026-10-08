"""CounterPro: showroom tool for pricing in-stock slabs and building quotes.

Run with:  streamlit run app.py
Rates, sinks and branch details are in counterpro/config.py.
"""
from __future__ import annotations

import hmac
import html
import os
from datetime import datetime, timedelta
from urllib.parse import quote_plus

import pandas as pd
import streamlit as st

from counterpro import config, store
from counterpro.config import BRANDING, RULES, SINKS, SINKS_BY_SKU
from counterpro.inventory import (clean_slabs, drop_duplicate_serials, feed_report,
                                  load_slabs, location_name,
                                  slabs_for_job, summarize, thickness_value)
from counterpro.moraware import NotAnInventoryPage, parse_inventory_html
from counterpro.pricing import money, price_job
from counterpro.quote import (Quote, QuoteOption, SinkLine, build_pdf,
                              new_quote_number, to_rows)

st.set_page_config(
    page_title=BRANDING.app_name,
    page_icon=":material/countertops:",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.html("""
<style>
  :root { --ink:#1C2526; --muted:#5E6B6C; --rule:#CBD2CF; --tag:#F4C534; --slate:#17494D; }
  .block-container { padding-top: 4.5rem; max-width: 1280px; }
  h1, h2, h3 { letter-spacing: 0; }

  /* White panels on the stone background */
  [class*="st-key-panel_"] { background:#fff; border-color:var(--rule); }

  /* One slab = one row. A yellow edge marks slabs already on the quote. */
  [class*="st-key-slab_"], [class*="st-key-slabq_"] {
    background:#fff; border:1px solid var(--rule); border-left:6px solid var(--rule);
    border-radius:3px; padding:0.8rem 1rem;
  }
  [class*="st-key-slabq_"] { border-left-color:var(--tag); }

  .cp-name { font-family:"Barlow Condensed","Barlow",sans-serif; font-weight:600;
             font-size:1.45rem; line-height:1.15; color:var(--ink); }
  .cp-meta { color:var(--muted); font-size:0.95rem; line-height:1.4; margin-top:2px; }
  .cp-staff { color:var(--slate); font-size:0.85rem; margin-top:2px; }
  .cp-price { text-align:right; white-space:nowrap; }
  .cp-price b { font-family:"Barlow Condensed","Barlow",sans-serif; font-weight:700;
                font-size:2.1rem; line-height:1; color:var(--ink);
                font-variant-numeric:tabular-nums; display:block; }
  .cp-price span { color:var(--muted); font-size:0.85rem; white-space:normal; display:block; }

  .cp-total { background:var(--tag); color:var(--ink); border-radius:3px; padding:0.9rem 1.1rem;
              display:flex; justify-content:space-between; align-items:baseline; gap:1rem; }
  .cp-total b { font-family:"Barlow Condensed","Barlow",sans-serif; font-weight:700;
                font-size:2.4rem; line-height:1; font-variant-numeric:tabular-nums; }
  .cp-lines { width:100%; border-collapse:collapse; margin:0.4rem 0 0.8rem; }
  .cp-lines, .cp-lines tr, .cp-lines td { border:0 !important; background:transparent !important; }
  .cp-lines td { padding:0.35rem 0 !important; border-bottom:1px solid var(--rule) !important; }
  .cp-lines td:last-child { text-align:right; font-variant-numeric:tabular-nums; }
  .cp-empty { border:1.5px dashed var(--rule); border-radius:3px; padding:1rem; color:var(--muted); }

  @media (max-width: 640px) {
    .cp-price { text-align:left; }
    .block-container { padding-left:1rem; padding-right:1rem; }
  }
</style>
""")


# --- Data -------------------------------------------------------------------
def store_settings() -> tuple:
    """The [inventory_store] secrets plus the matching environment variables,
    as a tuple so a change in either gives a fresh store."""
    try:
        settings = dict(st.secrets.get("inventory_store", {}))
    except Exception:                  # no secrets file
        settings = {}
    env = {k: os.environ.get(k, "") for k in ("COUNTERPRO_STORE_REPO", "COUNTERPRO_STORE_TOKEN",
                                              "COUNTERPRO_STORE_PATH", "COUNTERPRO_STORE_BRANCH",
                                              "COUNTERPRO_STORE_API", "COUNTERPRO_DATA_DIR")}
    return tuple(sorted({**{k: str(v) for k, v in settings.items()}, **env}.items()))


@st.cache_resource(show_spinner=False)
def inventory_store(settings: tuple):
    """Where Moraware inventory is kept: a GitHub repository when the
    [inventory_store] secrets are set, otherwise a folder on this server."""
    return store.from_settings({k: v for k, v in settings if not k.startswith("COUNTERPRO_")})


@st.cache_data(ttl=config.CACHE_SECONDS, show_spinner="Loading slab inventory")
def fetch(sources: tuple[str, ...], settings: tuple, upload_stamp: float):
    """Inventory for everyone using the app. Inventory from Moraware wins over
    the feed; `upload_stamp` changes when a new one is saved, which refreshes this."""
    kept, errors, snapshot = inventory_store(settings), [], None
    if upload_stamp:
        try:
            snapshot = kept.load()
            kept.last_good = snapshot
        except store.StoreError as exc:
            # A brief outage must not swap the list for the spreadsheet feed.
            snapshot = kept.last_good
            errors.append(f"Saved inventory: {exc}" + (" Showing the last copy that loaded." if snapshot else ""))
    else:
        kept.last_good = None
    if snapshot is not None:
        try:
            slabs = drop_duplicate_serials(clean_slabs(snapshot.rows))
            return slabs, errors, config.now(), snapshot
        except Exception as exc:       # damaged inventory must not take the app down
            errors.append(f"Saved inventory could not be read: {exc}")
    result = load_slabs(sources)
    return result.slabs, [*errors, *result.errors], config.now(), None


def staff_code() -> str:
    code = config.staff_code()
    if not code:
        try:
            code = str(st.secrets.get("staff_code", "")).strip()
        except Exception:              # no secrets file
            code = ""
    return code


def esc(value: object) -> str:
    return html.escape(str(value))


def md(text: str) -> str:
    """Streamlit reads $...$ as maths. Escape dollar signs in markdown text."""
    return text.replace("$", "\\$")


def plural(n: int, word: str) -> str:
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


# --- Session state ----------------------------------------------------------
ss = st.session_state
ss.setdefault("sinks", {})            # sku -> quantity
ss.setdefault("quote", [])            # product variants on the quote, in order
ss.setdefault("quote_number", new_quote_number(config.now()))
ss.setdefault("shown", config.PAGE_SIZE)


def add_sink():
    sku = ss["sink_pick"].sku
    ss["sinks"][sku] = ss["sinks"].get(sku, 0) + 1


def set_sink_qty(sku: str):
    qty = int(ss.get(f"sinkqty_{sku}") or 0)
    if qty <= 0:
        ss["sinks"].pop(sku, None)
    else:
        ss["sinks"][sku] = qty


def toggle_quote(variant: str):
    if variant in ss["quote"]:
        ss["quote"].remove(variant)
    elif len(ss["quote"]) < BRANDING.max_quote_options:
        ss["quote"].append(variant)


def new_quote():
    ss["quote"] = []
    ss["sinks"] = {}
    ss["quote_number"] = new_quote_number(config.now())
    for key in ("customer_name", "customer_contact", "project"):
        ss[key] = ""


def reset_paging():
    ss["shown"] = config.PAGE_SIZE


# --- Sidebar: staff controls ------------------------------------------------
CODE = staff_code()
ss.setdefault("unlocked", False)
ss.setdefault("upload_round", 0)
unlocked = ss["unlocked"] or not CODE

with st.sidebar:
    st.subheader("Staff")
    if CODE and not ss["unlocked"]:
        with st.form("unlock", border=False):
            attempt = st.text_input("Staff code", type="password")
            if st.form_submit_button("Unlock", width="stretch"):
                if hmac.compare_digest(attempt.strip().encode(), CODE.encode()):
                    ss["unlocked"] = True
                    st.rerun()
                st.error("That code is not right.")
    staff = st.toggle("Show cost and margin", key="staff", disabled=not unlocked,
                      help="Adds internal numbers to the slab list and details. "
                           "They never appear on the quote PDF.") and unlocked
    if st.button("Refresh inventory", icon=":material/refresh:", width="stretch"):
        fetch.clear()
        st.rerun()

SETTINGS = store_settings()
STORE = inventory_store(SETTINGS)
slabs, load_errors, loaded_at, snapshot = fetch(config.data_sources(), SETTINGS, STORE.stamp())

if slabs is None or slabs.empty:
    st.title(BRANDING.app_name)
    st.error("The slab inventory could not be loaded, so nothing can be priced right now. "
             "Check the connection, then choose Refresh inventory in the sidebar, "
             "or upload a saved Moraware inventory page there.")
    for err in load_errors:
        st.caption(err)
    st.stop()

products = summarize(slabs)
slab_lists = {v: list(zip(g["serial"], g["available"])) for v, g in slabs.groupby("variant", sort=False)}
slab_detail = {(r.variant, r.serial): (r.dimensions, r.bin) for r in slabs.itertuples()}

def upload_panel():
    """Staff replace the inventory with a page saved from Moraware."""
    st.divider()
    st.subheader("Inventory source")
    if snapshot is not None:
        age = config.now() - snapshot.saved_at
        st.caption(f"Moraware inventory updated {snapshot.saved_at:%b} {snapshot.saved_at.day} at "
                   f"{snapshot.saved_at:%H:%M}" + "".join(f". {k}: {v}" for k, v in snapshot.filters.items()
                                                          if k in ("Product",) and v) + ".")
        if age > timedelta(days=config.UPLOAD_STALE_DAYS):
            st.warning(f"This inventory is {age.days} days old. Slabs may have sold since.")
    else:
        st.caption("Reading the spreadsheet feed.")
    if STORE.durable:
        st.caption(f"Inventory is kept {STORE.where}.")
    else:
        st.caption("Uploads are kept on this server only and are lost when it restarts. "
                   "Add an [inventory_store] block to the app's secrets to keep them.")

    if not CODE:
        st.caption("Uploads are off until a staff code is set (COUNTERPRO_STAFF_CODE).")
        return
    if not ss["unlocked"]:
        st.caption("Unlock with the staff code to upload inventory.")
        return

    files = st.file_uploader(
        "Update from Moraware", type=["html", "htm"], accept_multiple_files=True,
        key=f"upload_{ss['upload_round']}",
        help="In Moraware open the inventory view, save the page (Ctrl+S, 'Webpage, HTML only'), "
             "then drop the file here. Add one file per view if stock is split across views.")
    if files:
        frames, filters, names, problems = [], {}, [], []
        for f in files:
            if f.size > config.UPLOAD_MAX_MB * 1024 * 1024:
                problems.append(f"{f.name} is larger than {config.UPLOAD_MAX_MB} MB.")
                continue
            try:
                rows, info = parse_inventory_html(f.getvalue().decode("utf-8", errors="replace"))
                clean_slabs(rows)                                   # prove it is usable before saving
            except (NotAnInventoryPage, ValueError) as exc:
                problems.append(f"{f.name}: {exc}")
                continue
            frames.append(rows)
            names.append(f.name)
            for k, v in info["filters"].items():
                filters[k] = f"{filters[k]}; {v}" if k in filters and v not in filters[k] else v
            if info["unsized"]:
                problems.append(f"{f.name}: {plural(info['unsized'], 'slab')} with no readable size left out.")
        for problem in problems:
            st.warning(problem)
        if frames:
            raw = pd.concat(frames, ignore_index=True)
            new = drop_duplicate_serials(clean_slabs(raw))
            before, after = set(slabs["serial"]) - {""}, set(new["serial"]) - {""}
            st.markdown(f"**{plural(len(new), 'slab')}, {plural(new['variant'].nunique(), 'product')}** "
                        f"in the upload. {len(after - before)} not in the current list, "
                        f"{len(before - after)} in the current list but not here.")
            gone = slabs[slabs["serial"].isin(before - after)]
            lost_sites = sorted(set(gone["location"]) - set(new["location"]))
            if lost_sites:
                st.warning("The upload has no slabs for " + ", ".join(location_name(c) for c in lost_sites)
                           + ". They will disappear from the list.")
            if st.button("Use this inventory", type="primary", width="stretch"):
                try:
                    STORE.save(raw, names, filters, now=config.now())
                except store.StoreError as exc:
                    st.error(f"Not saved. {exc}")
                else:
                    ss["upload_round"] += 1
                    fetch.clear()
                    st.rerun()
    if snapshot is not None and st.button("Go back to the spreadsheet feed", width="stretch"):
        try:
            STORE.clear()
        except store.StoreError as exc:
            st.error(f"Not removed. {exc}")
        else:
            fetch.clear()
            st.rerun()


with st.sidebar:
    report = feed_report(slabs)
    st.caption(
        f"{report['slabs']} slabs across {report['products']} products"
        + ("." if snapshot is not None else
           f", loaded {loaded_at:%H:%M}. Refreshes every {config.CACHE_SECONDS} seconds.")
    )
    for code, count in sorted(report["by_location"].items()):
        st.caption(f"{location_name(code)}: {plural(count, 'slab')}")
    if report["allocated_slabs"]:
        st.caption(f"{plural(report['allocated_slabs'], 'slab')} allocated to other jobs and not offered.")
    for err in load_errors:
        st.warning(err if err.startswith("Saved inventory") else f"A feed did not load: {err}")
    if report["unparsed"]:
        with st.expander(f"{plural(len(report['unparsed']), 'name')} not fully recognised"):
            for name in report["unparsed"]:
                st.caption(name)
    upload_panel()


# --- Header -----------------------------------------------------------------
logo_url = os.environ.get("COUNTERPRO_LOGO_URL", BRANDING.logo_url)
with st.container(horizontal=True, vertical_alignment="center"):
    if logo_url:
        st.image(logo_url, width=64)
    st.title(f"{BRANDING.app_name} in-stock slabs", anchor=False)
st.caption(f"{BRANDING.company}, {BRANDING.branch}. Enter the project size, pick slabs, and print a quote.")

main, side = st.columns([7, 4], gap="large")

# --- Project ----------------------------------------------------------------
with main:
    with st.container(border=True, key="panel_project"):
        st.subheader("Project", anchor=False)
        c_sqft, c_note = st.columns([1, 2], vertical_alignment="bottom")
        with c_sqft:
            sqft = st.number_input("Finished area (sq ft)", min_value=1.0, max_value=config.SQFT_MAX,
                                   value=config.SQFT_DEFAULT, step=1.0, format="%.1f", key="sqft",
                                   on_change=reset_paging)
        needed = sqft * RULES.waste_factor
        with c_note:
            st.caption(f"Needs {needed:,.1f} sq ft of slab, which includes "
                       f"{(RULES.waste_factor - 1) * 100:.0f}% for cutting waste.")

        with st.container(horizontal=True, vertical_alignment="bottom"):
            st.selectbox("Sinks", options=SINKS, key="sink_pick",
                         format_func=lambda s: f"{s.category}: {s.label}, {money(s.price, cents=False)}")
            st.button("Add sink", on_click=add_sink)

        for sku, qty in list(ss["sinks"].items()):
            sink = SINKS_BY_SKU[sku]
            c_name, c_qty = st.columns([4, 1], vertical_alignment="center")
            c_name.markdown(md(f"{sink.label}  \n:gray[{money(sink.price)} each, {money(sink.price * qty)} total]"))
            c_qty.number_input(f"Quantity of {sink.name}", min_value=0, max_value=20, value=qty, step=1,
                               key=f"sinkqty_{sku}", on_change=set_sink_qty, args=(sku,),
                               label_visibility="collapsed", help="Set to 0 to remove")

sink_lines = [SinkLine(sku, SINKS_BY_SKU[sku].label, SINKS_BY_SKU[sku].price, qty)
              for sku, qty in ss["sinks"].items()]
sinks_total = sum(s.total for s in sink_lines)

# --- Price every product for this project ----------------------------------
picks = {v: slabs_for_job(slab_lists[v], needed) for v in products["variant"]}
prices = {row.variant: price_job(row.unit_cost, sqft, sinks_total) for row in products.itertuples()}
products["fits"] = products["variant"].map(lambda v: picks[v] is not None)
products["total"] = products["variant"].map(lambda v: prices[v].total)
products["slabs_used"] = products["variant"].map(lambda v: len(picks[v]) if picks[v] is not None else 0)
by_variant = products.set_index("variant")
fitting = products[products["fits"]]


def option_for(variant: str) -> QuoteOption:
    row = by_variant.loc[variant]
    used = picks[variant] or []
    return QuoteOption(name=row["name"], spec=row["spec"], location=location_name(row["location"]),
                       price=prices[variant], slabs_used=len(used),
                       serials=tuple(p.serial for p in used if p.serial))


# --- Slab details -----------------------------------------------------------
@st.dialog("Slab details", width="medium")
def show_details(variant: str):
    row, price, used = by_variant.loc[variant], prices[variant], picks[variant] or []
    st.markdown(f'<div class="cp-name">{esc(row["name"])}</div>'
                f'<div class="cp-meta">{esc(", ".join(b for b in (row["spec"], location_name(row["location"])) if b))}'
                f'{(", colour " + esc(row["color_code"])) if row["color_code"] else ""}</div>',
                unsafe_allow_html=True)
    lines = [("Material and fabrication", price.material_fab), ("Installation", price.install)]
    if price.sinks:
        lines.append(("Sinks", price.sinks))
    lines += [("Subtotal", price.subtotal), (f"GST ({RULES.tax_rate * 100:g}%)", price.tax)]
    st.markdown('<table class="cp-lines">' + "".join(
        f"<tr><td>{esc(label)}</td><td>{money(value)}</td></tr>" for label, value in lines)
        + "</table>"
        f'<div class="cp-total"><span>Total with GST for {sqft:,.1f} sq ft</span><b>{money(price.total)}</b></div>',
        unsafe_allow_html=True)

    st.markdown(f"**In stock:** {plural(int(row['slab_count']), 'slab')}, "
                f"{row['available']:,.1f} sq ft. This project uses {plural(len(used), 'slab')}.")
    used_serials = {p.serial for p in used}
    stock = pd.DataFrame([
        {"Serial": serial or "(none)", "Sq ft": round(area, 1),
         "Size": slab_detail.get((variant, serial), ("", ""))[0],
         "Yard location": slab_detail.get((variant, serial), ("", ""))[1],
         "For this project": "Yes" if serial in used_serials else ""}
        for serial, area in slab_lists[variant] if area > 0
    ])
    stock = stock[[c for c in stock.columns if c in ("Serial", "Sq ft", "For this project")
                   or stock[c].astype(bool).any()]]
    st.dataframe(stock, hide_index=True, width="stretch")
    query = quote_plus(f"{row['brand']} {row['color']} countertop installed")
    st.link_button("See installed photos", f"https://www.google.com/search?tbm=isch&q={query}",
                   icon=":material/image_search:")

    if ss.get("staff"):
        st.divider()
        st.markdown("**Staff only**")
        healthy = price.margin_pct >= RULES.healthy_margin_pct
        a, b, c = st.columns(3)
        a.metric("Slab cost per sq ft", money(row["unit_cost"]))
        b.metric("Internal base (IB)", money(price.ib_cost))
        c.metric("Margin", f"{price.margin_pct:.1f}%")
        st.caption(md(
            f"Raw material and fabrication {money(price.direct_cost)}. Profit {money(price.profit)} "
            f"on {money(price.slab_subtotal)} before sinks and GST. "
            + ("" if healthy else f"Below the {RULES.healthy_margin_pct:g}% guide: installation is charged at "
               "cost, so low-cost slabs carry a thinner margin on the whole job.")
        ))
        if row["tags"]:
            st.caption(f"Feed codes: {row['tags']}")


# --- Browse -----------------------------------------------------------------
with main:
    with st.container(border=True, key="panel_filters"):
        st.subheader("Find a slab", anchor=False)
        f1, f2 = st.columns([3, 2])
        search = f1.text_input("Search", placeholder="Colour, brand or code", key="search",
                               on_change=reset_paging)
        sort_by = f2.selectbox("Sort by", ["Price, low to high", "Price, high to low",
                                           "Most in stock", "Name"], key="sort")

        locations = sorted(products["location"].unique(),
                           key=lambda c: (c != config.HOME_LOCATION, c))
        f3, f4 = st.columns(2)
        picked_locations = f3.pills("Location", locations, selection_mode="multi",
                                    format_func=location_name, key="locations",
                                    on_change=reset_paging) if len(locations) > 1 else []
        thicknesses = sorted((t for t in products["thickness"].unique() if t),
                             key=thickness_value, reverse=True)
        picked_thickness = f4.pills("Thickness", thicknesses, selection_mode="multi",
                                    key="thickness", on_change=reset_paging)
        picked_brands = st.multiselect("Brand", sorted(products["brand"].unique()), key="brands",
                                       placeholder="All brands", on_change=reset_paging)

        # Budget range follows the project: bounds move with size and sinks.
        if len(fitting):
            lo = int(fitting["total"].min() // 100) * 100
            hi = int(fitting["total"].max() // 100 + 1) * 100
        else:
            lo, hi = 0, 100
        prev_bounds = ss.get("budget_bounds")
        current = ss.get("budget")
        if current is None or prev_bounds is None or tuple(current) == tuple(prev_bounds):
            ss["budget"] = (lo, hi)                      # untouched slider stays wide open
        else:
            a, b = max(lo, min(current[0], hi)), max(lo, min(current[1], hi))
            ss["budget"] = (a, b) if a < b else (lo, hi)
        ss["budget_bounds"] = (lo, hi)
        budget_lo, budget_hi = st.slider("Budget, total with GST", min_value=lo, max_value=hi,
                                         step=100, format="$%d", key="budget", on_change=reset_paging)

    shown = fitting
    if picked_locations:
        shown = shown[shown["location"].isin(picked_locations)]
    if picked_thickness:
        shown = shown[shown["thickness"].isin(picked_thickness)]
    if picked_brands:
        shown = shown[shown["brand"].isin(picked_brands)]
    if search.strip():
        term = search.strip()
        shown = shown[shown["variant"].str.contains(term, case=False, regex=False, na=False)
                      | shown["name"].str.contains(term, case=False, regex=False, na=False)]
    shown = shown[(shown["total"] >= budget_lo) & (shown["total"] <= budget_hi)]

    if sort_by == "Price, low to high":
        shown = shown.sort_values(["total", "name"])
    elif sort_by == "Price, high to low":
        shown = shown.sort_values(["total", "name"], ascending=[False, True])
    elif sort_by == "Most in stock":
        shown = shown.sort_values(["available", "name"], ascending=[False, True])
    else:
        shown = shown.sort_values(["name", "thickness"])

    too_small = len(products) - len(fitting)
    summary = f"{plural(len(shown), 'slab option')} for {sqft:,.1f} sq ft"
    if too_small:
        summary += f". {too_small} more in stock are too small for this project."
    st.markdown(f"**{summary}**")

    if shown.empty:
        hints = []
        if search.strip():
            hints.append("clear the search")
        if picked_brands or picked_thickness or picked_locations:
            hints.append("remove a filter")
        if (budget_lo, budget_hi) != (lo, hi):
            hints.append("widen the budget")
        if not hints:
            hints.append("reduce the finished area")
        st.markdown(f'<div class="cp-empty">Nothing matches. Try to {" or ".join(hints)}.</div>',
                    unsafe_allow_html=True)

    quote_full = len(ss["quote"]) >= BRANDING.max_quote_options
    for i, row in enumerate(shown.head(ss["shown"]).itertuples()):
        price = prices[row.variant]
        in_quote = row.variant in ss["quote"]
        with st.container(key=f"{'slabq' if in_quote else 'slab'}_{i}"):
            c_info, c_price = st.columns([5, 2], vertical_alignment="center")
            stock = f"{plural(int(row.slab_count), 'slab')} in stock"
            if row.slabs_used > 1:
                stock += f", this project uses {row.slabs_used}"
            meta = ", ".join(b for b in (row.spec, location_name(row.location)) if b)
            if row.discontinued:
                meta += ". Discontinued colour"
            staff_line = (f'<div class="cp-staff">Cost {money(row.unit_cost)}/sq ft, '
                          f'margin {price.margin_pct:.1f}%</div>') if staff else ""
            c_info.markdown(f'<div class="cp-name">{esc(row.name)}</div>'
                            f'<div class="cp-meta">{esc(meta)}. {esc(stock)}.<br>'
                            f'{money(price.per_sqft, cents=False)} per sq ft installed, before GST and sinks.</div>'
                            f'{staff_line}',
                            unsafe_allow_html=True)
            c_price.markdown(f'<div class="cp-price"><b>{money(price.total, cents=False)}</b>'
                             f'<span>with GST</span></div>',
                             unsafe_allow_html=True)
            with st.container(horizontal=True, horizontal_alignment="right"):
                if st.button("Details", key=f"det_{row.variant}"):
                    show_details(row.variant)
                st.button("On quote, remove" if in_quote else "Add to quote",
                          icon=":material/check:" if in_quote else ":material/add:",
                          key=f"add_{row.variant}", on_click=toggle_quote, args=(row.variant,),
                          type="secondary" if in_quote else "primary",
                          disabled=quote_full and not in_quote,
                          help=(f"A quote holds up to {BRANDING.max_quote_options} options"
                                if quote_full and not in_quote else None))

    if len(shown) > ss["shown"]:
        left = len(shown) - ss["shown"]
        if st.button(f"Show {min(left, config.PAGE_SIZE)} more ({left} not shown)", width="stretch"):
            ss["shown"] += config.PAGE_SIZE
            st.rerun()


# --- Quote ------------------------------------------------------------------
with side:
    with st.container(border=True, key="panel_quote"):
        st.subheader("Quote", anchor=False)
        st.caption(f"No. {ss['quote_number']}")

        gone = [v for v in ss["quote"] if v not in by_variant.index]
        if gone:
            ss["quote"] = [v for v in ss["quote"] if v in by_variant.index]
            st.warning(f"{plural(len(gone), 'slab')} on this quote sold or left inventory and was removed.")

        ready, short = [], []
        for variant in ss["quote"]:
            (ready if picks[variant] is not None else short).append(variant)

        if not ss["quote"]:
            st.markdown(f'<div class="cp-empty">Add up to {BRANDING.max_quote_options} slabs from the list '
                        "to compare them side by side on one quote.</div>", unsafe_allow_html=True)
        for n, variant in enumerate(ready, 1):
            opt = option_for(variant)
            c_text, c_x = st.columns([6, 1], vertical_alignment="center")
            c_text.markdown(md(f"**{n}. {opt.name}**  \n:gray[{', '.join(b for b in (opt.spec, opt.location) if b)}]  \n"
                               f"{money(opt.price.total)} with GST"))
            c_x.button("", icon=":material/close:", key=f"rm_{variant}", on_click=toggle_quote,
                       args=(variant,), help=f"Remove {opt.name} from the quote", type="tertiary")
        for variant in short:
            row = by_variant.loc[variant]
            c_text, c_x = st.columns([6, 1], vertical_alignment="center")
            c_text.markdown(f"**{md(row['name'])}**  \n:orange[Only {row['available']:,.1f} sq ft in stock; "
                            f"this project needs {needed:,.1f}. Left off the quote.]")
            c_x.button("", icon=":material/close:", key=f"rm_{variant}", on_click=toggle_quote,
                       args=(variant,), help=f"Remove {row['name']} from the quote", type="tertiary")

        if sink_lines:
            st.caption("Sinks on every option: " + "; ".join(f"{s.quantity} x {s.label}" for s in sink_lines))

        st.divider()
        st.text_input("Customer name", key="customer_name")
        st.text_input("Phone or email", key="customer_contact")
        st.text_input("Project or address", key="project")
        st.text_input("Prepared by", key="prepared_by")

        if ready:
            quote = Quote(
                number=ss["quote_number"], created=config.now(), sqft=sqft,
                options=[option_for(v) for v in ready], sinks=sink_lines,
                customer_name=ss.get("customer_name", "").strip(),
                customer_contact=ss.get("customer_contact", "").strip(),
                project=ss.get("project", "").strip(),
                prepared_by=ss.get("prepared_by", "").strip(),
            )
            st.download_button("Download quote PDF", data=build_pdf(quote),
                               file_name=f"{quote.file_stem}.pdf", mime="application/pdf",
                               type="primary", icon=":material/picture_as_pdf:", width="stretch",
                               on_click="ignore")
            st.download_button("Download as spreadsheet (CSV)",
                               data=pd.DataFrame(to_rows(quote)).to_csv(index=False).encode("utf-8"),
                               file_name=f"{quote.file_stem}.csv", mime="text/csv", width="stretch",
                               on_click="ignore")
        else:
            st.button("Download quote PDF", disabled=True, width="stretch",
                      icon=":material/picture_as_pdf:", help="Add a slab to the quote first")
        st.button("Start a new quote", on_click=new_quote, width="stretch",
                  help="Clears the slabs, sinks and customer details")
