"""CounterPro: showroom tool for pricing in-stock slabs and building quotes.

Run with:  streamlit run app.py
Rates, sinks and branch details are in counterpro/config.py.
"""
from __future__ import annotations

import hmac
import os
from datetime import datetime, timedelta
from urllib.parse import quote_plus

import pandas as pd
import streamlit as st

from counterpro import config, store, ui
from counterpro.config import BRANDING, RULES, SINKS, SINKS_BY_SKU, PricingRules
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

st.html(ui.CSS)


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


# Streamlit keeps cached objects alive across a deploy, but swaps in fresh copies
# of the code. `CODE_VERSION` changes with every fresh copy, so a store object built by
# the old code is never reused by the new code.
CODE_VERSION = id(store)


@st.cache_resource(show_spinner=False)
def inventory_store(settings: tuple, code: int):
    """Where Moraware inventory is kept: a GitHub repository when the
    [inventory_store] secrets are set, otherwise a folder on this server."""
    return store.from_settings({k: v for k, v in settings if not k.startswith("COUNTERPRO_")})


@st.cache_data(ttl=config.CACHE_SECONDS, show_spinner="Loading slab inventory")
def fetch(sources: tuple[str, ...], settings: tuple, code: int, upload_stamp: float):
    """Inventory for everyone using the app. Inventory from Moraware wins over
    the feed; `upload_stamp` changes when a new one is saved, which refreshes this.

    Everything returned is plain data (a table, text, dates, numbers). Streamlit
    stores this result by copying it, and copying breaks for the app's own
    classes after a deploy, so none of them are returned."""
    kept, errors, snapshot = inventory_store(settings, code), [], None
    if upload_stamp:
        try:
            snapshot = kept.load()
            kept.last_good = snapshot
        except store.StoreError as exc:
            # A brief outage must not empty the list.
            snapshot = kept.last_good
            errors.append(f"Saved inventory: {exc}" + (" Showing the last copy that loaded." if snapshot else ""))
    else:
        kept.last_good = None
    if snapshot is not None:
        try:
            slabs = drop_duplicate_serials(clean_slabs(snapshot.rows))
            about = {"saved_at": snapshot.saved_at, "files": list(snapshot.files), "filters": dict(snapshot.filters)}
            return slabs, errors, config.now(), about, len(snapshot.rows) - len(slabs)
        except Exception as exc:       # damaged inventory must not take the app down
            errors.append(f"Saved inventory could not be read: {exc}")
    result = load_slabs(sources)
    return result.slabs, [*errors, *result.errors], config.now(), None, 0


def staff_code() -> str:
    code = config.staff_code()
    if not code:
        try:
            code = str(st.secrets.get("staff_code", "")).strip()
        except Exception:              # no secrets file
            code = ""
    return code


esc = ui.esc


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
ss.setdefault("replacing", None)      # the material on the quote that is being swapped out


def add_sink():
    sku = ss["sink_pick"]
    ss["sinks"][sku] = ss["sinks"].get(sku, 0) + 1


def set_sink_qty(sku: str):
    qty = int(ss.get(f"sinkqty_{sku}") or 0)
    if qty <= 0:
        ss["sinks"].pop(sku, None)
    else:
        ss["sinks"][sku] = qty


def new_quote():
    ss["quote"] = []
    ss["sinks"] = {}
    ss["quote_number"] = new_quote_number(config.now())
    for key in ("customer_name", "customer_contact", "project"):
        ss[key] = ""


def reset_paging():
    ss["shown"] = config.PAGE_SIZE


# --- Sidebar: staff controls ------------------------------------------------
STAFF_CODE = staff_code()
ss.setdefault("unlocked", False)
ss.setdefault("upload_round", 0)
unlocked = ss["unlocked"] or not STAFF_CODE

with st.sidebar:
    st.subheader("Staff")
    if STAFF_CODE and not ss["unlocked"]:
        with st.form("unlock", border=False):
            attempt = st.text_input("Staff code", type="password")
            if st.form_submit_button("Unlock", width="stretch"):
                if hmac.compare_digest(attempt.strip().encode(), STAFF_CODE.encode()):
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
STORE = inventory_store(SETTINGS, CODE_VERSION)
slabs, load_errors, loaded_at, snapshot, left_out = fetch(config.data_sources(), SETTINGS, CODE_VERSION, STORE.stamp())

if slabs is None or slabs.empty:
    st.title(BRANDING.app_name)
    if load_errors:
        st.error("The slab inventory could not be loaded, so nothing can be priced right now. "
                 "Choose Refresh inventory in the sidebar to try again.")
    else:
        st.error("There is no slab inventory yet. On the computer with the CounterPro Inventory Sync "
                 "extension, sign in to Moraware and press Sync now.")
    for err in load_errors:
        st.caption(err)
    st.stop()

products = summarize(slabs)
slab_lists = {v: list(zip(g["serial"], g["available"])) for v, g in slabs.groupby("variant", sort=False)}
slab_detail = {(r.variant, r.serial): (r.dimensions, r.bin, r.cost, r.received) for r in slabs.itertuples()}
has_dates = bool(slabs["received"].notna().any())
# Size of each product's largest slab, for the list.
_largest = slabs.sort_values("available", ascending=False).drop_duplicates("variant").set_index("variant")
largest_size = {v: (r.dimensions, r.available) for v, r in zip(_largest.index, _largest.itertuples())}


def since(when) -> str:
    return "" if pd.isna(when) else f"{when:%b %Y}"

def upload_panel():
    """Staff replace the inventory with a page saved from Moraware."""
    st.divider()
    st.subheader("Inventory source")
    if snapshot is not None:
        saved_at = snapshot["saved_at"]
        age = config.now() - saved_at
        st.caption(f"Moraware inventory updated {saved_at:%b} {saved_at.day} at "
                   f"{saved_at:%H:%M}" + "".join(f". {k}: {v}" for k, v in snapshot["filters"].items()
                                                          if k in ("Product",) and v) + ".")
        if age > timedelta(days=config.UPLOAD_STALE_DAYS):
            st.warning(f"This inventory is {age.days} days old, so the daily sync has stopped. Slabs may have "
                       "sold since. Open the sync extension on the work computer to see why.")
    else:
        st.caption("No Moraware inventory has been synced yet." if not config.data_sources()
                   else "No Moraware inventory yet; reading the extra feed.")
    if STORE.durable:
        st.caption(f"Inventory is kept {STORE.where}.")
    else:
        st.caption("Uploads are kept on this server only and are lost when it restarts. "
                   "Add an [inventory_store] block to the app's secrets to keep them.")

    if not STAFF_CODE:
        st.caption("Updated by the sync extension. Uploading by hand is off because no staff code is set.")
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
    if snapshot is not None and st.button("Remove this inventory", width="stretch",
                                          help="Clears the stored inventory. The list stays empty until the next sync or upload."):
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
           f", loaded {loaded_at:%H:%M}.")
    )
    for code, count in sorted(report["by_location"].items()):
        st.caption(f"{location_name(code)}: {plural(count, 'slab')}")
    if report["allocated_slabs"]:
        st.caption(f"{plural(report['allocated_slabs'], 'slab')} allocated to other jobs and not offered.")
    if left_out:
        st.caption(f"{plural(left_out, 'Moraware row')} left out: no real size or no cost "
                   "(placeholder serial numbers, or the same slab listed twice).")
    for err in load_errors:
        st.warning(err if err.startswith("Saved inventory") else f"A feed did not load: {err}")
    if report["unparsed"]:
        with st.expander(f"{plural(len(report['unparsed']), 'name')} not fully recognised"):
            for name in report["unparsed"]:
                st.caption(name)
    upload_panel()


# --- Header -----------------------------------------------------------------
flash = ss.pop("flash", None)
if flash:
    st.toast(flash, icon=":material/check_circle:")

logo_url = os.environ.get("COUNTERPRO_LOGO_URL", BRANDING.logo_url)
with st.container(horizontal=True, vertical_alignment="center"):
    if logo_url:
        st.image(logo_url, width=56)
    st.title(BRANDING.app_name, anchor=False)
status = f"{BRANDING.company}, {BRANDING.branch}. In-stock slabs, priced for the project."
if snapshot is not None:
    updated = snapshot["saved_at"]
    status += f" Inventory from Moraware, updated {updated:%b} {updated.day} at {updated:%-I:%M %p}."
st.caption(status)

TABS = ["Slabs and quote", "Compare", "IB calculator"]
tab_slabs, tab_compare, tab_ib = st.tabs(TABS, key="view", on_change="rerun")


# --- Project setup ----------------------------------------------------------
with tab_slabs:
    with st.container(key="panel_project"):
        p_size, p_sinks = st.columns([6, 5], gap="large")
        with p_size:
            st.subheader("Project", anchor=False)
            sqft = st.number_input(
                "Finished countertop area (sq ft)", min_value=1.0, max_value=config.SQFT_MAX,
                value=config.SQFT_DEFAULT, step=1.0, format="%.1f", key="sqft", on_change=reset_paging,
                help="The countertop surface the customer ends up with, in square feet. "
                     "Type a number or use the plus and minus buttons.")
            needed = sqft * RULES.waste_factor
            waste_pct = (RULES.waste_factor - 1) * 100
            st.markdown(ui.stats([
                ("Finished area", f"{sqft:,.1f} sq ft", False),
                ("Cutting allowance", f"{waste_pct:g}%", False),
                ("Slab material required", f"{needed:,.1f} sq ft", True),
            ]), unsafe_allow_html=True)
            st.markdown(
                f'<p class="cp-note">Countertops are cut out of full slabs, so a project needs more slab than its '
                f'finished area. {waste_pct:g}% is added for cut-outs, edges and offcuts. A material is only offered '
                f'when its slabs in stock add up to {needed:,.1f} sq ft, and prices already include the allowance.</p>',
                unsafe_allow_html=True)
        with p_sinks:
            st.subheader("Sinks", anchor=False)
            with st.container(horizontal=True, vertical_alignment="bottom"):
                # The choice is remembered as a SKU (plain text), not as a Sink object.
                st.selectbox("Sink", options=[s.sku for s in SINKS], key="sink_pick",
                             format_func=lambda sku: (f"{SINKS_BY_SKU[sku].category}: {SINKS_BY_SKU[sku].label}, "
                                                      f"{money(SINKS_BY_SKU[sku].price, cents=False)}"),
                             help="Pick a sink, then choose Add sink. Sinks are added to every material on the quote.")
                st.button("Add sink", on_click=add_sink, icon=":material/add:")
            if not ss["sinks"]:
                st.markdown('<p class="cp-note">No sinks added. Prices show countertops only.</p>',
                            unsafe_allow_html=True)
            for sku, qty in list(ss["sinks"].items()):
                sink = SINKS_BY_SKU[sku]
                c_name, c_qty = st.columns([4, 1.3], vertical_alignment="center")
                c_name.markdown(md(f"{sink.label}  \n:gray[{money(sink.price)} each, {money(sink.price * qty)} total]"))
                c_qty.number_input(f"Quantity of {sink.name}", min_value=0, max_value=20, value=qty, step=1,
                                   key=f"sinkqty_{sku}", on_change=set_sink_qty, args=(sku,),
                                   label_visibility="collapsed", help="Set to 0 to remove this sink")

sink_lines = [SinkLine(sku, SINKS_BY_SKU[sku].label, SINKS_BY_SKU[sku].price, qty)
              for sku, qty in ss["sinks"].items()]
sinks_total = sum(s.total for s in sink_lines)
if sink_lines:
    with p_sinks:
        st.markdown(ui.key_values([("Sinks total, added to every material", money(sinks_total))]),
                    unsafe_allow_html=True)

# --- Price every product for this project ----------------------------------
# One calculation per product, used by the cards, the comparison, the quote panel
# and the PDF. Nothing below works a price out a second time.
picks = {v: slabs_for_job(slab_lists[v], needed) for v in products["variant"]}
prices = {row.variant: price_job(row.unit_cost, sqft, sinks_total) for row in products.itertuples()}
products["fits"] = products["variant"].map(lambda v: picks[v] is not None)
products["total"] = products["variant"].map(lambda v: prices[v].total)
products["installed"] = products["variant"].map(lambda v: prices[v].slab_subtotal)
products["slabs_used"] = products["variant"].map(lambda v: len(picks[v]) if picks[v] is not None else 0)
by_variant = products.set_index("variant")
fitting = products[products["fits"]]

INSTALLED_LABEL = "Estimated installed price"


def per_sqft_note(price, cents: bool = False) -> str:
    return f"{money(price.per_sqft, cents=cents)} per finished sq ft, before GST and sinks"


def photo_of(row) -> str:
    return config.photo_for(row["name"], row.get("image", ""))


def size_text(variant: str) -> str:
    dims, area = largest_size.get(variant, ("", 0.0))
    return f"{dims} ({area:,.1f} sq ft)" if dims else f"{area:,.1f} sq ft"


def option_for(variant: str) -> QuoteOption:
    row = by_variant.loc[variant]
    used = picks[variant] or []
    return QuoteOption(name=row["name"], spec=row["spec"], location=location_name(row["location"]),
                       price=prices[variant], slabs_used=len(used),
                       serials=tuple(p.serial for p in used if p.serial), image_url=photo_of(row))


# --- Quote actions ----------------------------------------------------------
def add_to_quote(variant: str):
    name = by_variant.loc[variant, "name"] if variant in by_variant.index else "Material"
    replacing = ss.get("replacing")
    if replacing and replacing in ss["quote"]:
        old = by_variant.loc[replacing, "name"] if replacing in by_variant.index else "the old material"
        ss["quote"][ss["quote"].index(replacing)] = variant
        ss["flash"] = f"Replaced {old} with {name}."
    elif variant not in ss["quote"] and len(ss["quote"]) < BRANDING.max_quote_options:
        ss["quote"].append(variant)
        ss["flash"] = f"Added {name} to the quote ({len(ss['quote'])} of {BRANDING.max_quote_options})."
    ss["replacing"] = None


def remove_from_quote(variant: str):
    if variant in ss["quote"]:
        ss["quote"].remove(variant)
        name = by_variant.loc[variant, "name"] if variant in by_variant.index else "Material"
        ss["flash"] = f"Removed {name} from the quote."
    if ss.get("replacing") == variant:
        ss["replacing"] = None


def start_replace(variant: str):
    ss["replacing"] = variant
    ss["view"] = TABS[0]            # back to the slab list to choose the replacement


def cancel_replace():
    ss["replacing"] = None


def go_compare():
    ss["view"] = TABS[1]


def go_browse():
    ss["view"] = TABS[0]


def clear_quote():
    new_quote()
    ss["replacing"] = None
    ss["flash"] = "Started a new quote."


@st.dialog("Start a new quote?")
def confirm_new_quote():
    n = len(ss["quote"])
    parts = ([plural(n, "material")] if n else []) + (["the sinks"] if ss["sinks"] else []) + ["the customer details"]
    st.write(f"This clears {', '.join(parts[:-1]) + ' and ' + parts[-1] if len(parts) > 1 else parts[0]} "
             "and gives the quote a new number. The project size and filters stay as they are.")
    keep, clear = st.columns(2)
    if keep.button("Keep this quote", width="stretch"):
        st.rerun()
    # The clearing is done by the button's own callback, so it happens the moment
    # the button is pressed; the rerun then closes this window.
    if clear.button("Clear and start new", type="primary", width="stretch", on_click=clear_quote):
        st.rerun()


# --- Slab details -----------------------------------------------------------
@st.dialog("Slab details", width="medium")
def show_details(variant: str):
    row, price, used = by_variant.loc[variant], prices[variant], picks[variant] or []
    photo = photo_of(row)
    if photo:
        top = st.columns([1, 2.4], vertical_alignment="center")
        top[0].markdown(ui.media(photo, row["color"], "lg"), unsafe_allow_html=True)
        heading = top[1]
    else:
        heading = st
    heading.markdown(
        f'<div class="cp-brand" style="margin-top:0">{esc(row["brand"])}</div>'
        f'<div class="cp-name">{esc(row["color"])}</div>'
        + ui.tags([(row["thickness"], ""), (row["finish"], ""), (location_name(row["location"]), "soft"),
                   (f'Colour {row["color_code"]}' if row["color_code"] else "", "soft"),
                   ("Discontinued colour" if row["discontinued"] else "", "soft")]),
        unsafe_allow_html=True)

    lines = [("Material and fabrication", money(price.material_fab)), ("Installation", money(price.install)),
             (INSTALLED_LABEL, money(price.slab_subtotal))]
    if price.sinks:
        lines.append(("Sinks", money(price.sinks)))
        lines.append(("Subtotal", money(price.subtotal)))
    lines.append((f"GST ({RULES.tax_rate * 100:g}%)", money(price.tax)))
    st.markdown(ui.lines_table(lines, strong=(INSTALLED_LABEL,))
                + ui.total_block(f"Total with GST for {sqft:,.1f} sq ft", money(price.total)),
                unsafe_allow_html=True)
    st.caption(md(f"{per_sqft_note(price, cents=True)}. Finished area {sqft:,.1f} sq ft; slab material required "
                  f"{needed:,.1f} sq ft."))

    st.markdown(f"**In stock:** {plural(int(row['slab_count']), 'slab')}, "
                f"{row['available']:,.1f} sq ft. This project needs {plural(len(used), 'slab')}.")
    used_serials = {p.serial for p in used}
    blank = ("", "", float("nan"), pd.NaT)
    stock = pd.DataFrame([
        {"Serial": serial or "(none)", "Sq ft": round(area, 1),
         "Size": slab_detail.get((variant, serial), blank)[0],
         "Yard location": slab_detail.get((variant, serial), blank)[1],
         "In stock since": since(slab_detail.get((variant, serial), blank)[3]),
         "Slab cost": money(slab_detail.get((variant, serial), blank)[2]) if ss.get("staff") and unlocked else "",
         "For this project": "Yes" if serial in used_serials else ""}
        for serial, area in slab_lists[variant] if area > 0
    ])
    stock = stock[[c for c in stock.columns if c in ("Serial", "Sq ft", "For this project")
                   or stock[c].astype(bool).any()]]
    st.dataframe(stock, hide_index=True, width="stretch")
    query = quote_plus(f"{row['brand']} {row['color']} countertop installed")
    st.link_button("Search the web for installed photos", f"https://www.google.com/search?tbm=isch&q={query}",
                   icon=":material/image_search:",
                   help="Opens an image search in a new tab. Results are not FloForm's photos of this slab.")

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


# --- Filters ----------------------------------------------------------------
SORTS = ["Price, low to high", "Price, high to low", "Name, A to Z", "Most in stock"]
if has_dates:
    SORTS.insert(0, "Oldest stock first")
DEFAULT_SORT = SORTS[0] if has_dates else "Price, low to high"


def reset_filters():
    ss["search"] = ""
    ss["locations"] = []
    ss["thickness"] = []
    ss["brands"] = []
    ss["sort"] = DEFAULT_SORT
    ss.pop("budget", None)
    ss.pop("budget_bounds", None)
    reset_paging()


def remove_filter(kind: str, value: str = ""):
    if kind == "search":
        ss["search"] = ""
    elif kind == "budget":
        ss.pop("budget", None)
        ss.pop("budget_bounds", None)
    else:
        ss[kind] = [v for v in ss.get(kind, []) if v != value]
    reset_paging()


main, side = tab_slabs.columns([8, 4], gap="large")

with main:
    with st.container(key="panel_filters"):
        head = st.container(horizontal=True, vertical_alignment="center", horizontal_alignment="distribute")
        head.subheader("Find a material", anchor=False)

        f1, f2 = st.columns([3, 2])
        search = f1.text_input("Search", placeholder="Colour, manufacturer or product code", key="search",
                               on_change=reset_paging,
                               help="Matches any part of the colour, manufacturer or code. Press Enter to search.")
        sort_by = f2.selectbox("Sort by", SORTS, key="sort")
        fit_by_location = fitting.groupby("location").size().to_dict()
        locations = sorted(products["location"].unique(), key=lambda c: (c != config.HOME_LOCATION, c))
        # Each set of choices gets the full width, so a long row wraps instead of
        # running into its neighbour.
        picked_locations = st.pills(
            "Inventory location", locations, selection_mode="multi", key="locations", on_change=reset_paging,
            format_func=lambda c: f"{location_name(c)} ({fit_by_location.get(c, 0)})",
            help="Choose one or more. With none chosen, every location is shown. "
                 "The number is how many materials there can cover this project.") if len(locations) > 1 else []
        thicknesses = sorted((t for t in products["thickness"].unique() if t), key=thickness_value, reverse=True)
        picked_thickness = st.pills("Thickness", thicknesses, selection_mode="multi", key="thickness",
                                    on_change=reset_paging,
                                    help="Slab thickness in centimetres. 3cm is about 1 1/4 in, 2cm about 3/4 in.")
        more = st.expander("Brand and price range")
        picked_brands = more.multiselect("Brand", sorted(products["brand"].unique()), key="brands",
                                         placeholder="All brands", on_change=reset_paging)

        # Price range follows the project: its ends move with the project size.
        if len(fitting):
            lo = int(fitting["installed"].min() // 100) * 100
            hi = int(fitting["installed"].max() // 100 + 1) * 100
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
        budget_lo, budget_hi = more.slider("Installed price range (before GST and sinks)", min_value=lo,
                                           max_value=hi, step=100, format="$%d", key="budget",
                                           on_change=reset_paging)
        budget_active = (budget_lo, budget_hi) != (lo, hi)

        active = ([("search", "", f'Search: "{search.strip()}"')] if search.strip() else []) \
            + [("locations", c, location_name(c)) for c in picked_locations] \
            + [("thickness", t, t) for t in picked_thickness] \
            + [("brands", b, b) for b in picked_brands] \
            + ([("budget", "", f"{money(budget_lo, cents=False)} to {money(budget_hi, cents=False)}")]
               if budget_active else [])
        head.button("Reset filters", on_click=reset_filters, icon=":material/restart_alt:", type="tertiary",
                    disabled=not active and sort_by == DEFAULT_SORT,
                    help="Clears the search and every filter, and puts the sort order back.")
        if active:
            with st.container(horizontal=True, key="chips"):
                for n, (kind, value, label) in enumerate(active):
                    st.button(label, key=f"chip_{kind}_{n}", icon=":material/close:", icon_position="right",
                              on_click=remove_filter, args=(kind, value), help=f"Remove this filter: {label}")

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
    shown = shown[(shown["installed"] >= budget_lo) & (shown["installed"] <= budget_hi)]

    if sort_by == "Oldest stock first":
        shown = shown.sort_values(["received", "name"], na_position="last")
    elif sort_by == "Price, low to high":
        shown = shown.sort_values(["installed", "name"])
    elif sort_by == "Price, high to low":
        shown = shown.sort_values(["installed", "name"], ascending=[False, True])
    elif sort_by == "Most in stock":
        shown = shown.sort_values(["available", "name"], ascending=[False, True])
    else:
        shown = shown.sort_values(["name", "thickness"])

    # --- Results ------------------------------------------------------------
    replacing = ss.get("replacing") if ss.get("replacing") in ss["quote"] else None
    if replacing:
        with st.container(horizontal=True, vertical_alignment="center", key="replace_banner"):
            st.markdown(f'<div class="cp-banner">Choose a replacement for '
                        f'<b>{esc(by_variant.loc[replacing, "name"])}</b>, then select Replace with this.</div>',
                        unsafe_allow_html=True)
            st.button("Keep it instead", on_click=cancel_replace)

    too_small = products[~products["fits"]]
    bar = st.container(horizontal=True, vertical_alignment="bottom", horizontal_alignment="distribute")
    bar.markdown(f'<p class="cp-result"><b>{len(shown)}</b> of {len(fitting)} materials match, '
                 f'for {sqft:,.1f} sq ft finished</p>', unsafe_allow_html=True)
    view_mode = bar.segmented_control("View", ["Grid", "List"], key="view_mode", default="Grid",
                                      label_visibility="collapsed") or "Grid"
    if len(too_small):
        note = st.container(horizontal=True, vertical_alignment="center")
        note.markdown(f'<p class="cp-excluded">{plural(len(too_small), "more material")} in stock '
                      f'{"is" if len(too_small) == 1 else "are"} left out: not enough slab to cover '
                      f'{needed:,.1f} sq ft.</p>', unsafe_allow_html=True)
        with note.popover("Which ones?", type="tertiary"):
            st.caption(f"These have less than {needed:,.1f} sq ft of slab in stock. "
                       "They come back if the project gets smaller.")
            st.dataframe(pd.DataFrame({
                "Material": too_small["name"], "Thickness": too_small["spec"],
                "Location": too_small["location"].map(location_name),
                "Slab in stock (sq ft)": too_small["available"].round(1),
            }).sort_values("Slab in stock (sq ft)", ascending=False), hide_index=True, width="stretch")

    if shown.empty:
        if fitting.empty:
            tip = (f"<b>No material in stock can cover {needed:,.1f} sq ft of slab.</b>"
                   "Reduce the finished area, or quote this project from ordered material.")
        else:
            tips = (["check the spelling or search for fewer letters"] if search.strip() else []) \
                + (["remove a filter above"] if picked_brands or picked_thickness or picked_locations else []) \
                + (["widen the price range"] if budget_active else [])
            tip = ("<b>No materials match these filters.</b>"
                   + (f"Try to {', or '.join(tips)}. " if tips else "") + "Reset filters shows everything again.")
        st.markdown(f'<div class="cp-empty">{tip}</div>', unsafe_allow_html=True)

    quote_full = len(ss["quote"]) >= BRANDING.max_quote_options

    def slab_actions(variant: str, in_quote: bool, stretch: bool):
        width = "stretch" if stretch else "content"
        if st.button("View details", key=f"det_{variant}", width=width):
            show_details(variant)
        if replacing:
            st.button("In quote" if in_quote else "Replace with this",
                      icon=":material/check:" if in_quote else ":material/swap_horiz:",
                      key=f"add_{variant}", on_click=add_to_quote, args=(variant,), width=width,
                      type="secondary" if in_quote else "primary", disabled=in_quote,
                      help="Already on the quote" if in_quote else None)
        elif in_quote:
            st.button("In quote", icon=":material/check:", key=f"add_{variant}", on_click=remove_from_quote,
                      args=(variant,), width=width, help="On the quote. Select to remove it.")
        else:
            st.button("Add to quote", icon=":material/add:", key=f"add_{variant}", on_click=add_to_quote,
                      args=(variant,), type="primary", width=width, disabled=quote_full,
                      help=(f"The quote holds {BRANDING.max_quote_options} materials. Remove or replace one first."
                            if quote_full else None))

    def slab_view(row):
        price = prices[row.variant]
        in_quote = row.variant in ss["quote"]
        tag_items = [("In quote", "on")] if in_quote else []
        tag_items += [(row.thickness, ""), (row.finish, ""), (location_name(row.location), "soft"),
                      ("Discontinued colour" if row.discontinued else "", "soft")]
        cost_text = (f"Slab cost {money(row.cost)} ({money(row.unit_cost)}/sq ft)" if row.slab_count == 1
                     else f"Cost {money(row.unit_cost)}/sq ft")
        staff_line = f"{cost_text}, margin {price.margin_pct:.1f}%" if staff else ""
        common = dict(photo_url=config.photo_for(row.name, row.image), brand=row.brand, colour=row.color,
                      tag_items=tag_items, staff_line=staff_line, price_label=INSTALLED_LABEL,
                      price=money(price.slab_subtotal, cents=False), price_note=per_sqft_note(price))
        return price, in_quote, common

    page = shown.head(ss["shown"])
    if view_mode == "Grid":
        with st.container(key="grid"):
            for i, row in enumerate(page.itertuples()):
                price, in_quote, common = slab_view(row)
                with st.container(key=f"{'cardq' if in_quote else 'card'}_{i}"):
                    st.markdown(ui.card(**common, fact_lines=[
                        ("In stock:", plural(int(row.slab_count), "slab")),
                        ("Largest slab:", size_text(row.variant)),
                        ("This project needs:", plural(int(row.slabs_used), "slab")),
                        ("In stock since:", since(row.received)),
                    ]), unsafe_allow_html=True)
                    with st.container(horizontal=True):
                        slab_actions(row.variant, in_quote, stretch=True)
    else:
        for i, row in enumerate(page.itertuples()):
            price, in_quote, common = slab_view(row)
            with st.container(key=f"{'rowq' if in_quote else 'row'}_{i}"):
                fact_text = (f"{plural(int(row.slab_count), 'slab')} in stock, largest {size_text(row.variant)}. "
                             f"This project needs {plural(int(row.slabs_used), 'slab')}."
                             + (f" In stock since {since(row.received)}." if since(row.received) else ""))
                r_info, r_act = st.columns([8, 2.3], vertical_alignment="center")
                r_info.markdown(ui.row(**common, fact_text=fact_text), unsafe_allow_html=True)
                with r_act:
                    slab_actions(row.variant, in_quote, stretch=True)

    if len(shown) > ss["shown"]:
        left = len(shown) - ss["shown"]
        if st.button(f"Show {min(left, config.PAGE_SIZE)} more ({left} not shown yet)", width="stretch"):
            ss["shown"] += config.PAGE_SIZE
            st.rerun()


# --- Quote ------------------------------------------------------------------
gone = [v for v in ss["quote"] if v not in by_variant.index]
if gone:
    ss["quote"] = [v for v in ss["quote"] if v in by_variant.index]
ready = [v for v in ss["quote"] if picks[v] is not None]
short = [v for v in ss["quote"] if picks[v] is None]
options = [option_for(v) for v in ready]
quote = Quote(
    number=ss["quote_number"], created=config.now(), sqft=sqft, options=options, sinks=sink_lines,
    customer_name=ss.get("customer_name", "").strip(), customer_contact=ss.get("customer_contact", "").strip(),
    project=ss.get("project", "").strip(), prepared_by=ss.get("prepared_by", "").strip(),
) if options else None
lowest = min(range(len(options)), key=lambda i: options[i].price.slab_subtotal) if options else None

with side:
    with st.container(key="panel_quote"):
        st.subheader("Quote", anchor="quote")
        st.caption(f"No. {ss['quote_number']}")
        if gone:
            st.warning(f"{plural(len(gone), 'material')} on this quote sold or left inventory and "
                       f"{'was' if len(gone) == 1 else 'were'} removed.")

        st.markdown(ui.key_values([
            ("Finished area", f"{sqft:,.1f} sq ft"),
            ("Slab material required", f"{needed:,.1f} sq ft"),
            ("Sinks", money(sinks_total) if sink_lines else "None"),
        ]), unsafe_allow_html=True)
        if sink_lines:
            st.caption("; ".join(f"{s.quantity} x {s.label}" for s in sink_lines))
        st.divider()

        st.markdown(f"**Materials** :gray[{len(ss['quote'])} of {BRANDING.max_quote_options}]")
        if not ss["quote"]:
            st.markdown(f'<div class="cp-empty"><b>No materials yet</b>Choose Add to quote on up to '
                        f'{BRANDING.max_quote_options} materials to price them side by side.</div>',
                        unsafe_allow_html=True)
        for n, (variant, opt) in enumerate(zip(ready, options), 1):
            row = by_variant.loc[variant]
            c_text, c_act = st.columns([5, 1.25], vertical_alignment="top")
            c_text.markdown(ui.quote_item(
                photo_url=opt.image_url, number=n, name=opt.name, colour=row["color"],
                meta=", ".join(b for b in (opt.spec, opt.location) if b),
                price=money(opt.price.slab_subtotal, cents=False),
                sub=f"installed. {money(opt.price.total)} with {'sinks and ' if sink_lines else ''}GST",
            ), unsafe_allow_html=True)
            with c_act:
                st.button("", icon=":material/swap_horiz:", key=f"swap_{variant}", on_click=start_replace,
                          args=(variant,), help=f"Replace {opt.name} with another material", type="tertiary")
                st.button("", icon=":material/close:", key=f"rm_{variant}", on_click=remove_from_quote,
                          args=(variant,), help=f"Remove {opt.name} from the quote", type="tertiary")
        for variant in short:
            row = by_variant.loc[variant]
            c_text, c_act = st.columns([5, 1.25], vertical_alignment="top")
            c_text.markdown(f"**{md(row['name'])}**  \n:orange[Only {row['available']:,.1f} sq ft in stock; "
                            f"this project needs {needed:,.1f}. Left off the quote.]")
            c_act.button("", icon=":material/close:", key=f"rm_{variant}", on_click=remove_from_quote,
                         args=(variant,), help=f"Remove {row['name']} from the quote", type="tertiary")

        if len(options) >= 2:
            st.button("Compare side by side", icon=":material/compare_arrows:", on_click=go_compare,
                      width="stretch")
        st.divider()

        st.markdown("**Customer**")
        st.text_input("Customer name", key="customer_name", max_chars=80)
        st.text_input("Phone or email", key="customer_contact", max_chars=80)
        st.text_input("Project or address", key="project", max_chars=120)
        st.text_input("Prepared by", key="prepared_by", max_chars=60)

        if quote:
            if not quote.customer_name:
                st.caption('No customer name yet. The PDF will be addressed to "Customer".')
            st.download_button("Download quote PDF", data=build_pdf(quote),
                               file_name=f"{quote.file_stem}.pdf", mime="application/pdf",
                               type="primary", icon=":material/picture_as_pdf:", width="stretch",
                               on_click="ignore")
            st.download_button("Download as spreadsheet (CSV)",
                               data=pd.DataFrame(to_rows(quote)).to_csv(index=False).encode("utf-8"),
                               file_name=f"{quote.file_stem}.csv", mime="text/csv", width="stretch",
                               type="tertiary", on_click="ignore")
        else:
            st.button("Download quote PDF", disabled=True, width="stretch",
                      icon=":material/picture_as_pdf:", help="Add a material to the quote first")
        in_progress = bool(ss["quote"] or ss["sinks"] or any(
            ss.get(k, "").strip() for k in ("customer_name", "customer_contact", "project")))
        if st.button("Start a new quote", width="stretch", icon=":material/note_add:",
                     help="Clears the materials, sinks and customer details. You are asked to confirm first."):
            if in_progress:
                confirm_new_quote()
            else:
                # Nothing to lose: the quote is empty, so it only needs a fresh number.
                ss["quote_number"] = new_quote_number(config.now())
                ss["flash"] = "Started a new quote."
                st.rerun()

# Phones only: a slim bar that jumps to the quote panel.
if options:
    with tab_slabs:
        st.html(ui.mobile_bar(len(options), money(options[lowest].price.slab_subtotal, cents=False)))


# --- Compare ----------------------------------------------------------------
with tab_compare:
    if len(options) < 2:
        st.markdown(f'<div class="cp-empty"><b>Nothing to compare yet</b>Add two to '
                    f'{BRANDING.max_quote_options} materials to the quote and they appear here side by side.</div>',
                    unsafe_allow_html=True)
        st.button("Back to the slabs", on_click=go_browse, icon=":material/arrow_back:")
    else:
        st.caption(f"{len(options)} materials for {sqft:,.1f} sq ft finished ({needed:,.1f} sq ft of slab). "
                   "Prices are the same figures shown on the cards and printed on the quote.")
        base = options[lowest].price.slab_subtotal
        cells = []
        for variant, opt in zip(ready, options):
            row = by_variant.loc[variant]
            diff = opt.price.slab_subtotal - base
            cells.append({
                "name": opt.name, "colour": row["color"], "photo_url": opt.image_url, "brand": row["brand"],
                "thickness": row["spec"], "size": size_text(variant), "location": opt.location,
                "stock": f"{plural(int(row['slab_count']), 'slab')}, {row['available']:,.1f} sq ft",
                "needs": plural(opt.slabs_used, "slab"),
                "installed": money(opt.price.slab_subtotal),
                "per_sqft": f"{money(opt.price.per_sqft)}, before GST and sinks",
                "diff": "Lowest price" if abs(diff) < 0.005 else f"{money(diff)} more",
                "sinks": money(opt.price.sinks) if sink_lines else "None",
                "gst": money(opt.price.tax), "total": money(opt.price.total),
            })
        st.markdown(ui.compare_table(cells, [
            ("brand", "Brand"), ("thickness", "Thickness"), ("size", "Largest slab"),
            ("location", "Inventory location"), ("stock", "In stock"), ("needs", "Slabs required"),
            ("installed", INSTALLED_LABEL), ("per_sqft", "Per finished sq ft"),
            ("diff", "Compared with lowest"), ("sinks", "Sinks"),
            ("gst", f"GST ({RULES.tax_rate * 100:g}%)"), ("total", "Total with GST"),
        ], lowest), unsafe_allow_html=True)
        act = st.columns([20] + [80 / len(options)] * len(options))   # same widths as the table's columns
        for column, variant, opt in zip(act[1:], ready, options):
            with column:
                st.button("Replace", key=f"cmp_swap_{variant}", icon=":material/swap_horiz:",
                          on_click=start_replace, args=(variant,), width="stretch",
                          help=f"Go back to the slabs to choose a replacement for {opt.name}")
                st.button("Remove", key=f"cmp_rm_{variant}", icon=":material/close:", type="tertiary",
                          on_click=remove_from_quote, args=(variant,), width="stretch")
        st.button("Back to the slabs", on_click=go_browse, icon=":material/arrow_back:")
    for variant in short:
        st.caption(f"{by_variant.loc[variant, 'name']} is left out: not enough slab in stock for this project size.")


# --- IB calculator ----------------------------------------------------------
def pct(value: float) -> str:
    return f"{value:g}%"


with tab_ib:
    st.caption("Work out the internal base (IB) for a slab and a job size. Nothing here is saved or "
               "added to a quote.")
    ib_in, ib_out = st.columns([5, 6], gap="large")

    with ib_in:
        with st.container(key="panel_ib_in"):
            st.subheader("Slab and job", anchor=False)
            by_name = products.sort_values(["name", "thickness", "location"])
            labels = {r.variant: (f"{r.name}, {r.spec}, {location_name(r.location)}, "
                                  f"{money(r.unit_cost)}/sq ft") for r in by_name.itertuples()}
            ib_pick = st.selectbox("Slab", [""] + list(labels), key="ib_slab",
                                   format_func=lambda v: labels.get(v, "Type in a cost myself"),
                                   help="Pick a slab to use its Moraware cost, or type in your own cost per sq ft.")
            if ib_pick:
                chosen = by_variant.loc[ib_pick]
                ib_unit_cost = float(chosen["unit_cost"])
                dims, area = largest_size.get(ib_pick, ("", 0.0))
                st.markdown(md(f"**Slab cost {money(ib_unit_cost)} per sq ft**, from Moraware.  \n"
                               f":gray[{plural(int(chosen['slab_count']), 'slab')} in stock"
                               + (f", largest {dims} ({area:,.1f} sq ft)" if dims else "") + "]"))
            else:
                ib_unit_cost = st.number_input("Slab cost per sq ft ($)", min_value=0.0, max_value=500.0,
                                               value=20.0, step=0.5, format="%.2f", key="ib_cost")
            ib_sqft = st.number_input("Finished area (sq ft)", min_value=1.0, max_value=config.SQFT_MAX,
                                      value=config.SQFT_DEFAULT, step=1.0, format="%.1f", key="ib_sqft")

            with st.expander("Rates"):
                st.caption("These start at the app's own rates. Changing them here only affects this calculator.")
                r1, r2 = st.columns(2)
                ib_waste = r1.number_input("Cutting waste (%)", 0.0, 100.0, round((RULES.waste_factor - 1) * 100, 2),
                                           step=1.0, format="%g", key="ib_waste")
                ib_fab = r2.number_input("Fabrication ($ per sq ft)", 0.0, 200.0, RULES.fabrication_per_sqft,
                                         step=0.5, format="%.2f", key="ib_fab")
                ib_markup = r1.number_input("IB markup on material (%)", 0.0, 200.0,
                                            round((RULES.ib_material_markup - 1) * 100, 2),
                                            step=1.0, format="%g", key="ib_markup")
                ib_floor = r2.number_input("IB minimum margin (%)", 0.0, 90.0, round(RULES.ib_min_margin * 100, 2),
                                           step=1.0, format="%g", key="ib_floor")
                ib_cust = r1.number_input("Customer markup over IB (%)", 0.0, 300.0,
                                          round((RULES.ib_to_customer_markup - 1) * 100, 2),
                                          step=1.0, format="%g", key="ib_cust")
                ib_install = r2.number_input("Installation ($ per sq ft)", 0.0, 200.0, RULES.install_per_sqft,
                                             step=0.5, format="%.2f", key="ib_install")

    ib_rules = PricingRules(
        install_per_sqft=ib_install, fabrication_per_sqft=ib_fab, waste_factor=1 + ib_waste / 100,
        tax_rate=RULES.tax_rate, ib_material_markup=1 + ib_markup / 100, ib_min_margin=ib_floor / 100,
        ib_to_customer_markup=1 + ib_cust / 100, healthy_margin_pct=RULES.healthy_margin_pct)
    ib = price_job(ib_unit_cost, ib_sqft, 0.0, rules=ib_rules)

    with ib_out:
        with st.container(key="panel_ib_out"):
            st.subheader("Internal base", anchor=False)
            cost_lines = [
                (f"Material: {ib.material_sqft:,.1f} sq ft at {money(ib_unit_cost)} "
                 f"({ib_sqft:,.1f} sq ft plus {pct(ib_waste)} waste)", ib.raw_material),
                (f"Fabrication: {ib_sqft:,.1f} sq ft at {money(ib_fab)}", ib.raw_fab),
                ("Raw cost", ib.direct_cost),
            ]
            st.markdown(ui.lines_table([(label, money(value)) for label, value in cost_lines], strong=("Raw cost",))
                        + ui.total_block(f"IB for {ib_sqft:,.1f} sq ft", money(ib.ib_cost)),
                        unsafe_allow_html=True)
            if ib.ib_rule == "floor":
                why = (f"Set by the {pct(ib_floor)} minimum margin: raw cost divided by {1 - ib_floor / 100:g}. "
                       f"The {pct(ib_markup)} material markup alone would give {money(ib.ib_from_markup)}.")
            else:
                why = (f"Set by the {pct(ib_markup)} material markup plus fabrication. "
                       f"The {pct(ib_floor)} minimum margin alone would give {money(ib.ib_from_floor)}.")
            st.caption(md(f"{money(ib.ib_per_sqft)} per finished sq ft. {why} "
                          f"IB is {money(ib.ib_cost - ib.direct_cost)} over raw cost ({ib.ib_margin_pct:.1f}% of IB)."))

            st.markdown("**What the customer pays on this IB**")
            over_ib = ib.material_fab - ib.ib_cost
            sell_lines = [
                (f"Material and fabrication (IB plus {pct(ib_cust)})", ib.material_fab),
                (f"Installation: {ib_sqft:,.1f} sq ft at {money(ib_install)}", ib.install),
                ("Subtotal", ib.subtotal),
                (f"GST ({RULES.tax_rate * 100:g}%)", ib.tax),
                ("Total with GST", ib.total),
            ]
            st.markdown(ui.lines_table([(label, money(value)) for label, value in sell_lines],
                                       strong=("Total with GST",)), unsafe_allow_html=True)
            st.caption(md(f"Material and fabrication is {money(over_ib)} over IB. "
                          f"{money(ib.per_sqft)} per sq ft installed, before GST."))

