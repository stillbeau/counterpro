import streamlit as st
import pandas as pd
import re
from datetime import datetime
from fpdf import FPDF

# --- 1. CONFIGURATION ---
st.set_page_config(
    page_title="Dead Stock Sales Tool",
    page_icon="🧱",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Custom CSS - Modern SaaS Dashboard Style
st.markdown("""
<style>
    .stApp { background: #f8fafc; font-family: "Inter", sans-serif; }

    [data-testid="stVerticalBlockBorderWrapper"] > div {
        background-color: white !important;
        border: 1px solid #e2e8f0 !important;
        border-radius: 12px !important;
        padding: 1.5rem !important;
        box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.05) !important;
        margin-bottom: 1rem !important;
    }
    .card-title {
        font-size: 0.85rem;
        font-weight: 700;
        color: #1e293b;
        margin-bottom: 1rem;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        display: block;
    }
    [data-testid="stMetricValue"] {
        color: #1e293b !important;
        font-weight: 700 !important;
        font-size: 1.8rem !important;
    }
    .large-price {
        text-align: center;
        padding: 2rem 1rem;
        background: linear-gradient(135deg, #4f46e5 0%, #7c3aed 100%);
        border-radius: 12px;
        color: white !important;
        margin: 1rem 0;
    }
    .large-price h1 { color: white !important; font-size: 3rem !important; margin: 0 !important; }
    .large-price p  { color: white !important; opacity: 0.9; margin: 0 !important; }
    .low-stock  { background: #fee2e2; border-left: 4px solid #dc2626; padding: 12px; border-radius: 4px; color: #991b1b !important; margin-bottom: 1rem; }
    .good-margin { color: #059669 !important; font-weight: 700; }
    .low-margin  { color: #dc2626 !important; font-weight: 700; }

    /* Limit multiselect tag container height so it doesn't swallow the screen */
    [data-testid="stMultiSelect"] div[data-baseweb="select"] > div:first-child {
        max-height: 150px !important;
        overflow-y: auto !important;
    }
</style>
""", unsafe_allow_html=True)

# --- 2. CONSTANTS ---
INSTALL_COST_PER_SQFT    = 21.0
FABRICATION_COST_PER_SQFT = 16.0
WASTE_FACTOR  = 1.20
TAX_RATE      = 0.05

# Pricing Controls
IB_MATERIAL_MARKUP    = 1.05   # 5 % markup on raw material for IB
IB_MIN_MARGIN         = 0.18   # Ensure IB is at least 18 % margin over raw costs
IB_TO_CUSTOMER_MARKUP = 1.15   # Customer Mat+Fab is 15 % higher than IB

# DATA SOURCES
DATA_SOURCES = [
    "https://docs.google.com/spreadsheets/d/e/2PACX-1vSkoSeMuPGqr5-JEBhHO5l0fFYlkfmbMUW-VU8UZEpR0pd4lSeyK74WHE47m1zYMg/pub?output=csv"
]

# --- 3. SINK DATA  (emojis added for quick visual scanning) ---
SINK_OPTIONS = {
    "✅ In-Stock/No Sink": 0.00,
    # ── Kitchen Sinks – Standard Radius ──────────────────────────────
    "🥣 50/50 Undermount Standard Radius - SKU 83742 (16 ga)": 300.00,
    "🥣 Large Single Bowl Undermount Standard Radius - SKU 83744 (16 ga)": 325.00,
    "🥣 Medium Single Bowl Undermount Standard Radius - SKU 83745 (18 ga)": 230.00,
    "🥣 60/40 Undermount Standard Radius - SKU 83747 (16 ga)": 370.00,
    "🥣 40/60 Undermount Standard Radius - SKU 83995 (16 ga)": 370.00,
    # ── Bar Sinks – Standard Radius ───────────────────────────────────
    "🍸 Large Bar Undermount Standard Radius - SKU 83993 (18 ga)": 250.00,
    "🍸 Small Bar Undermount Standard Radius - SKU 83992 (18 ga)": 180.00,
    # ── Kitchen Sinks – 15° Radius ────────────────────────────────────
    "🥣 50/50 Undermount 15° Radius - SKU 83749 (18 ga)": 440.00,
    "🥣 Large Single Bowl Undermount 15° Radius - SKU 83748 (18 ga)": 450.00,
    "🥣 Medium Single Bowl Undermount 15° Radius - SKU 83750 (18 ga)": 400.00,
    # ── Top-mount ─────────────────────────────────────────────────────
    "🥣 Top-mount Double Bowl Standard Radius - SKU 85446 (18 ga)": 270.00,
    # ── Vanity Sinks (White Porcelain) ────────────────────────────────
    "🛁 Large Rectangular Undermount Vanity - SKU 84020 (Porcelain)": 105.00,
    "🛁 Medium Rectangular Undermount Vanity - SKU 84022 (Porcelain)": 105.00,
    "🛁 Large Oval Undermount Vanity - SKU 84024 (Porcelain)": 89.00,
    "🛁 Medium Oval Undermount Vanity - SKU 84026 (Porcelain)": 89.00,
}


# --- 4. PRICING LOGIC (unchanged) ---
def calculate_cost(unit_cost, project_sqft, sink_price=0.0):
    """
    Revised pricing logic:
    1. Calculate Raw Direct Cost (Material + Fab).
    2. Calculate IB (Material marked up 5 %, enforcing 18 % floor on total).
    3. Calculate Customer Material + Fab (Fixed 15 % higher than IB).
    4. Add Sink Price to Customer Total.
    """
    uc         = float(unit_cost)
    sq_finished = float(project_sqft)
    sq_with_waste = sq_finished * WASTE_FACTOR
    sink_price = float(sink_price)

    # 1. RAW DIRECT COSTS
    raw_material_cost = uc * sq_with_waste
    raw_fab_cost      = FABRICATION_COST_PER_SQFT * sq_finished
    total_direct_cost = raw_material_cost + raw_fab_cost

    # 2. INTERNAL BASE (IB) CALCULATION
    # Candidate A: Material marked up by 5 % + raw fabrication
    ib_candidate_markup = (raw_material_cost * IB_MATERIAL_MARKUP) + raw_fab_cost
    # Candidate B: Enforce the 18 % margin floor on direct costs
    ib_candidate_floor  = total_direct_cost / (1 - IB_MIN_MARGIN)
    ib_cost = max(ib_candidate_markup, ib_candidate_floor)

    # 3. CUSTOMER PRICING
    customer_mat_fab_total = ib_cost * IB_TO_CUSTOMER_MARKUP
    customer_ins_cost      = INSTALL_COST_PER_SQFT * sq_finished

    slab_subtotal = customer_mat_fab_total + customer_ins_cost
    subtotal      = slab_subtotal + sink_price

    # Analytics
    profit     = slab_subtotal - (total_direct_cost + (INSTALL_COST_PER_SQFT * sq_finished))
    margin_pct = (profit / slab_subtotal * 100) if slab_subtotal > 0 else 0

    return {
        "customer_mat_fab": customer_mat_fab_total,
        "customer_ins":     customer_ins_cost,
        "sink_price":       sink_price,
        "slab_subtotal":    slab_subtotal,
        "subtotal":         subtotal,
        "ib_cost":          ib_cost,
        "margin_pct":       margin_pct,
        "total_with_tax":   subtotal * (1 + TAX_RATE),
    }


# --- 5. PARSING HELPER (unchanged) ---
def parse_product_variant(variant_str):
    """Parse Product Variant to extract Brand, Color, and Thickness."""
    try:
        cleaned = re.sub(r'^\d+\s*-\s*', '', str(variant_str))

        brand_match = re.match(r'^([A-Za-z\s&]+)', cleaned)
        brand = brand_match.group(1).strip() if brand_match else "Unknown"

        thickness_match = re.search(r'(\d+\.?\d*cm)', cleaned, re.IGNORECASE)
        thickness = thickness_match.group(1) if thickness_match else ""

        color_str = re.sub(r'\([^)]*\)', '', cleaned)
        color_str = re.sub(r'#\S+', '', color_str)
        color_str = re.sub(r'\d+\.?\d*cm', '', color_str, flags=re.IGNORECASE)
        color_str = re.sub(r'\s+', ' ', color_str).strip()
        if brand in color_str:
            color_str = color_str.replace(brand, '').strip()
        color = color_str if color_str else "Unknown"

        return brand, color, thickness
    except Exception:
        return "Unknown", str(variant_str), ""


# --- 6. DATA FETCHING  (cached for 60 s) ---
@st.cache_data(ttl=60)
def fetch_data():
    """Fetch inventory data from Google Sheets. Cached for 60 seconds."""
    all_dfs = []
    for url in DATA_SOURCES:
        try:
            df = pd.read_csv(url)
            df.columns = df.columns.str.strip()
            if 'Product Variant' in df.columns:
                df['On Hand Qty'] = pd.to_numeric(
                    df['On Hand Qty'].astype(str).str.replace(r'[$,]', '', regex=True),
                    errors='coerce'
                )
                df['Serialized On Hand Cost'] = pd.to_numeric(
                    df['Serialized On Hand Cost'].astype(str).str.replace(r'[$,]', '', regex=True),
                    errors='coerce'
                )
                all_dfs.append(df)
        except Exception as exc:
            st.warning(f"⚠️ Failed to load data source: `{url}`\n\nError: {exc}")

    if not all_dfs:
        return None

    df = pd.concat(all_dfs, ignore_index=True)
    df = df[df['On Hand Qty'] > 0].copy()
    df['Unit_Cost'] = df['Serialized On Hand Cost'] / df['On Hand Qty']

    parsed      = df['Product Variant'].apply(parse_product_variant)
    df['Brand']     = parsed.apply(lambda x: x[0])
    df['Color']     = parsed.apply(lambda x: x[1])
    df['Thickness'] = parsed.apply(lambda x: x[2])

    return df


# --- 7. PDF GENERATION ---
def _pdf_safe(text: str) -> str:
    """
    Strip characters outside latin-1 (e.g. emoji, em-dashes) so fpdf2's
    built-in Helvetica font doesn't raise FPDFUnicodeEncodingException.
    Replace common typographic chars with ASCII equivalents first, then
    silently drop anything that still can't encode.
    """
    replacements = {
        "\u2014": "-",   # em dash  —
        "\u2013": "-",   # en dash  –
        "\u00d7": "x",   # multiplication sign ×  (already latin-1, but keep explicit)
    }
    for orig, repl in replacements.items():
        text = text.replace(orig, repl)
    # Drop everything outside latin-1 (emoji, etc.)
    return text.encode("latin-1", errors="ignore").decode("latin-1")


def generate_quote_pdf(slab_name, sqft, sinks, pricing):
    """Generate a basic quote PDF using fpdf2. Returns bytes."""
    pdf = FPDF()
    pdf.add_page()

    # Header
    pdf.set_font("Helvetica", "B", 20)
    pdf.set_fill_color(79, 70, 229)   # Indigo brand colour
    pdf.set_text_color(255, 255, 255)
    pdf.cell(0, 14, "CounterPro - Customer Quote", new_x="LMARGIN", new_y="NEXT", align="C", fill=True)
    pdf.ln(4)

    # Reset colours for body
    pdf.set_text_color(30, 41, 59)

    # Date
    pdf.set_font("Helvetica", size=9)
    pdf.set_text_color(100, 116, 139)
    pdf.cell(0, 6, f"Generated: {datetime.now().strftime('%B %d, %Y  %H:%M')}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    # Section: Slab
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(30, 41, 59)
    pdf.cell(0, 8, "SLAB DETAILS", new_x="LMARGIN", new_y="NEXT")
    pdf.set_draw_color(226, 232, 240)
    pdf.line(pdf.get_x(), pdf.get_y(), pdf.get_x() + 180, pdf.get_y())
    pdf.ln(2)

    pdf.set_font("Helvetica", size=10)
    pdf.cell(50, 7, "Material:", new_x="RIGHT", new_y="TOP")
    pdf.set_font("Helvetica", "B", 10)
    pdf.multi_cell(0, 7, _pdf_safe(slab_name))
    pdf.set_font("Helvetica", size=10)
    pdf.cell(50, 7, "Square Footage:", new_x="RIGHT", new_y="TOP")
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(0, 7, f"{sqft:.1f} sq ft", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    # Section: Sinks
    if sinks:
        pdf.set_font("Helvetica", "B", 11)
        pdf.set_text_color(30, 41, 59)
        pdf.cell(0, 8, "SINKS", new_x="LMARGIN", new_y="NEXT")
        pdf.line(pdf.get_x(), pdf.get_y(), pdf.get_x() + 180, pdf.get_y())
        pdf.ln(2)
        pdf.set_font("Helvetica", size=10)
        for sink in sinks:
            line_total = sink['price'] * sink['quantity']
            # _pdf_safe strips emoji prefixes and replaces em/en dashes
            sink_label = _pdf_safe(sink['type'])
            pdf.cell(0, 6,
                     f"  {sink_label}  x{sink['quantity']}  -  ${line_total:,.2f}",
                     new_x="LMARGIN", new_y="NEXT")
        pdf.ln(4)

    # Section: Pricing summary
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(30, 41, 59)
    pdf.cell(0, 8, "PRICING SUMMARY", new_x="LMARGIN", new_y="NEXT")
    pdf.line(pdf.get_x(), pdf.get_y(), pdf.get_x() + 180, pdf.get_y())
    pdf.ln(2)

    pdf.set_font("Helvetica", size=10)
    rows = [
        ("Material & Fabrication",  f"${pricing['customer_mat_fab']:,.2f}"),
        ("Installation",             f"${pricing['customer_ins']:,.2f}"),
        ("Sinks",                    f"${pricing['sink_price']:,.2f}"),
        ("Subtotal",                 f"${pricing['subtotal']:,.2f}"),
        ("GST (5%)",                 f"${pricing['subtotal'] * TAX_RATE:,.2f}"),
    ]
    col_w = 90
    for label, value in rows:
        pdf.cell(col_w, 7, label, new_x="RIGHT", new_y="TOP")
        pdf.cell(0, 7, value, new_x="LMARGIN", new_y="NEXT", align="R")

    # Total — highlighted row
    pdf.ln(2)
    pdf.set_fill_color(79, 70, 229)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(col_w, 9, "TOTAL (incl. GST)", fill=True, new_x="RIGHT", new_y="TOP")
    pdf.cell(0,    9, f"${pricing['total_with_tax']:,.2f}", fill=True,
             align="R", new_x="LMARGIN", new_y="NEXT")

    # Footer
    pdf.ln(10)
    pdf.set_text_color(148, 163, 184)
    pdf.set_font("Helvetica", "I", 8)
    pdf.cell(0, 5, "This quote is valid for 30 days. Prices exclude installation site preparation.",
             new_x="LMARGIN", new_y="NEXT", align="C")

    return bytes(pdf.output())


# ═══════════════════════════════════════════════════════════════════════════════
# UI EXECUTION
# ═══════════════════════════════════════════════════════════════════════════════

# ── Sidebar: manual cache refresh ──────────────────────────────────────────────
with st.sidebar:
    st.markdown("### ⚙️ Data Controls")
    if st.button("🔄 Refresh Inventory", use_container_width=True, type="primary"):
        st.cache_data.clear()
        st.rerun()
    st.caption("Inventory data is cached for 60 seconds. Click above to force an immediate refresh.")

# ── Header ─────────────────────────────────────────────────────────────────────
col_logo, col_title = st.columns([1, 4])
with col_logo:
    st.image("https://i.ibb.co/kVXQt6v4/Gemini-Generated-Image-shnzslshnzslshnz.png", width=150)
with col_title:
    st.title("🧱 Dead Stock Sales Tool")

# ── Session State ──────────────────────────────────────────────────────────────
if 'comparison_tray' not in st.session_state:
    st.session_state.comparison_tray = []
if 'selected_sinks' not in st.session_state:
    st.session_state.selected_sinks = []

# ── Fetch Data ─────────────────────────────────────────────────────────────────
df = fetch_data()

if df is not None:
    # Group by Product Variant and calculate totals
    grouped_df = df.groupby('Product Variant').agg({
        'On Hand Qty':              'sum',
        'Serialized On Hand Cost':  'sum',
        'Brand':                    'first',
        'Color':                    'first',
        'Thickness':                'first',
    }).reset_index()
    grouped_df['Unit_Cost'] = grouped_df['Serialized On Hand Cost'] / grouped_df['On Hand Qty']
    grouped_df = grouped_df[grouped_df['Unit_Cost'].notna() & (grouped_df['Unit_Cost'] > 0)].copy()

    # ── Project Settings ───────────────────────────────────────────────────────
    with st.container(border=True):
        st.markdown('<span class="card-title">Project Settings</span>', unsafe_allow_html=True)
        sqft = st.number_input("Finished Sq Ft", 1.0, 500.0, 35.0, step=1.0, key="sqft_input")

    # ── Sink Selection ─────────────────────────────────────────────────────────
    with st.container(border=True):
        st.markdown('<span class="card-title">🚰 Sink Selection</span>', unsafe_allow_html=True)

        col_dropdown, col_add = st.columns([4, 1])
        with col_dropdown:
            sink_to_add = st.selectbox(
                "Select Sink Model",
                options=list(SINK_OPTIONS.keys()),
                help="Choose a sink to add",
                key="sink_selector",
            )
        with col_add:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("➕ Add Sink", use_container_width=True):
                if SINK_OPTIONS[sink_to_add] == 0.0:
                    st.toast("Select a sink model to add. 'No Sink' means no sink is included.")
                else:
                    st.session_state.selected_sinks.append({
                        'type':     sink_to_add,
                        'price':    SINK_OPTIONS[sink_to_add],
                        'quantity': 1,
                    })
                    st.rerun()

        # Display selected sinks with quantity controls
        if st.session_state.selected_sinks:
            st.markdown("**Selected Sinks:**")
            for idx, sink in enumerate(st.session_state.selected_sinks):
                col1, col2, col3, col4 = st.columns([3, 1, 1, 1])
                with col1:
                    st.write(sink['type'])
                with col2:
                    if st.button("➖", key=f"minus_sink_{idx}", use_container_width=True):
                        if sink['quantity'] > 1:
                            st.session_state.selected_sinks[idx]['quantity'] -= 1
                        else:
                            st.session_state.selected_sinks.pop(idx)
                        st.rerun()
                with col3:
                    st.write(f"**{sink['quantity']}**")
                with col4:
                    if st.button("➕", key=f"plus_sink_{idx}", use_container_width=True):
                        st.session_state.selected_sinks[idx]['quantity'] += 1
                        st.rerun()

        total_sink_price = sum(
            s['price'] * s['quantity'] for s in st.session_state.selected_sinks
        )
        if total_sink_price > 0:
            st.markdown(f"**Total Sink Cost: ${total_sink_price:,.2f}**")
        else:
            st.info("No sinks selected")

    # ── Filters ────────────────────────────────────────────────────────────────
    with st.container(border=True):
        st.markdown('<span class="card-title">🔍 Filters</span>', unsafe_allow_html=True)

        # Compute dynamic price range based on slabs that have sufficient stock
        temp_filtered = grouped_df[
            grouped_df['On Hand Qty'] >= (sqft * WASTE_FACTOR)
        ].copy()

        if len(temp_filtered) > 0:
            temp_filtered['_calc_price'] = temp_filtered['Unit_Cost'].apply(
                lambda uc: calculate_cost(uc, sqft, total_sink_price)['total_with_tax']
            )
            min_price = (int(temp_filtered['_calc_price'].min()) // 100) * 100
            max_price = ((int(temp_filtered['_calc_price'].max()) // 100) + 1) * 100
        else:
            min_price, max_price = 500, 10000

        # ── Dual-ended budget range slider ────────────────────────────────────
        budget_range = st.slider(
            "💰 Customer Budget Range",
            min_value=min_price,
            max_value=max_price,
            value=(min_price, max_price),   # dual-ended
            step=100,
            help="Filter slabs by minimum and maximum customer total price (incl. tax)",
        )
        budget_min, budget_max = budget_range

        col1, col2, col3 = st.columns(3)

        with col1:
            all_brands = sorted(grouped_df['Brand'].unique())
            # Default is empty → show all brands
            selected_brands = st.multiselect(
                "Brand",
                options=all_brands,
                default=[],
                help="Leave empty to show all brands, or pick specific ones",
            )

        with col2:
            all_thickness = sorted(grouped_df['Thickness'].unique(), reverse=True)
            selected_thickness = st.multiselect(
                "Thickness",
                options=all_thickness,
                default=all_thickness,
                help="Select one or more thickness options",
            )

        with col3:
            search_term = st.text_input(
                "🔎 Search Colors",
                placeholder="Type to search...",
                help="Search by color name",
            )

    # ── Apply Filters ──────────────────────────────────────────────────────────
    filtered_df = grouped_df.copy()

    # 1. Sufficient stock
    filtered_df = filtered_df[filtered_df['On Hand Qty'] >= sqft * WASTE_FACTOR]

    # 2. Brand — empty selection means "show all"
    if selected_brands:
        filtered_df = filtered_df[filtered_df['Brand'].isin(selected_brands)]

    # 3. Thickness
    if selected_thickness:
        filtered_df = filtered_df[filtered_df['Thickness'].isin(selected_thickness)]

    # 4. Color search
    if search_term:
        filtered_df = filtered_df[
            filtered_df['Color'].str.contains(search_term, case=False, na=False)
            | filtered_df['Brand'].str.contains(search_term, case=False, na=False)
            | filtered_df['Product Variant'].str.contains(search_term, case=False, na=False)
        ]

    # 5. Budget range — calculate price once for all remaining rows
    filtered_df['_temp_price'] = filtered_df['Unit_Cost'].apply(
        lambda uc: calculate_cost(uc, sqft, total_sink_price)['total_with_tax']
    )
    filtered_df = filtered_df[
        (filtered_df['_temp_price'] >= budget_min)
        & (filtered_df['_temp_price'] <= budget_max)
    ]
    filtered_df = filtered_df.drop(columns=['_temp_price'])

    # ── Sort Results ───────────────────────────────────────────────────────────
    sort_by = st.selectbox(
        "Sort By",
        options=[
            "Price (Low to High)",
            "Price (High to Low)",
            "Available Size (Largest First)",
        ],
        help="Order the material list before selecting a slab",
    )

    if sort_by in ("Price (Low to High)", "Price (High to Low)"):
        filtered_df = filtered_df.copy()
        filtered_df['_sort_price'] = filtered_df['Unit_Cost'].apply(
            lambda uc: calculate_cost(uc, sqft, total_sink_price)['total_with_tax']
        )
        ascending = sort_by == "Price (Low to High)"
        filtered_df = filtered_df.sort_values('_sort_price', ascending=ascending)
        filtered_df = filtered_df.drop(columns=['_sort_price'])
    elif sort_by == "Available Size (Largest First)":
        filtered_df = filtered_df.sort_values('On Hand Qty', ascending=False)

    # ── Slab Selection ─────────────────────────────────────────────────────────
    with st.container(border=True):
        st.markdown('<span class="card-title">Select Material</span>', unsafe_allow_html=True)

        filtered_df['display_name'] = filtered_df.apply(
            lambda row: f"{row['Brand']} {row['Color']} {row['Thickness']} ({row['On Hand Qty']:.1f} sf)",
            axis=1,
        )
        display_to_variant = dict(zip(filtered_df['display_name'], filtered_df['Product Variant']))

        if len(filtered_df) > 0:
            # Preserve sort order — don't re-sort the list alphabetically
            ordered_display_names = list(filtered_df['display_name'])
            selected_display = st.selectbox("Select Slab", ordered_display_names)
            selected_variant = display_to_variant[selected_display]
        else:
            st.warning("No materials match your filters. Try adjusting the filters above.")
            selected_variant = None

    # ── Results ────────────────────────────────────────────────────────────────
    if selected_variant:
        slab_data  = grouped_df[grouped_df['Product Variant'] == selected_variant].iloc[0]
        all_slabs  = df[df['Product Variant'] == selected_variant]
        pricing    = calculate_cost(slab_data['Unit_Cost'], sqft, total_sink_price)
        slab_label = f"{slab_data['Brand']} {slab_data['Color']} {slab_data['Thickness']}"

        c1, c2 = st.columns([1, 1])

        with c1:
            with st.container(border=True):
                st.markdown('<span class="card-title">Inventory Context</span>', unsafe_allow_html=True)

                # Display all serial numbers for this variant
                serial_num_cols = [
                    'Serial Number', 'SKU', 'Item Code', 'Product SKU', 'Serialized Inventory'
                ]
                serial_numbers = []
                for col in serial_num_cols:
                    if col in all_slabs.columns:
                        for serial in all_slabs[col]:
                            if pd.notna(serial) and serial not in serial_numbers:
                                serial_numbers.append(str(serial))
                        if serial_numbers:
                            break

                if serial_numbers:
                    st.markdown("**Serial Numbers:**")
                    for serial in serial_numbers:
                        st.write(f"• {serial}")

                st.metric("Available Qty", f"{slab_data['On Hand Qty']:.1f} sf")

                search_query = (
                    f"{slab_data['Brand']} {slab_data['Color']} countertop installed"
                ).replace(" ", "+")
                st.link_button(
                    "🖼️ View Installed Photos",
                    f"https://www.google.com/search?tbm=isch&q={search_query}",
                    use_container_width=True,
                )

        with c2:
            st.markdown(f"""
            <div class="large-price">
                <p>CUSTOMER TOTAL</p>
                <h1>${pricing['total_with_tax']:,.2f}</h1>
                <p>Incl. 5% GST</p>
            </div>
            """, unsafe_allow_html=True)

            with st.expander("💰 Cost Breakdown"):
                margin = pricing['margin_pct']
                margin_class = "good-margin" if margin >= 18 else "low-margin"
                st.markdown(
                    f'Slab Margin: <span class="{margin_class}">{margin:.1f}%</span>',
                    unsafe_allow_html=True,
                )
                st.metric("Slab Cost (Internal IB)", f"${pricing['ib_cost']:,.2f}")
                st.write(f"Customer Mat/Fab: ${pricing['customer_mat_fab']:,.2f}")
                st.write(f"Customer Install: ${pricing['customer_ins']:,.2f}")
                if pricing['sink_price'] > 0:
                    st.write("**Sinks:**")
                    for sink in st.session_state.selected_sinks:
                        st.write(
                            f"  • {sink['type']}: ${sink['price']:,.2f}"
                            f" × {sink['quantity']} = ${sink['price'] * sink['quantity']:,.2f}"
                        )
                    st.write(f"Total Sinks: ${pricing['sink_price']:,.2f}")
                st.write(f"**Subtotal:** ${pricing['subtotal']:,.2f}")
                st.write(f"**Total with Tax:** ${pricing['total_with_tax']:,.2f}")

            # ── Download Quote as PDF ──────────────────────────────────────────
            pdf_bytes = generate_quote_pdf(
                slab_name=slab_label,
                sqft=sqft,
                sinks=st.session_state.selected_sinks,
                pricing=pricing,
            )
            st.download_button(
                label="📄 Download Quote as PDF",
                data=pdf_bytes,
                file_name=f"quote_{slab_label.replace(' ', '_')}.pdf",
                mime="application/pdf",
                use_container_width=True,
            )

        # ── Add to Comparison ──────────────────────────────────────────────────
        st.markdown("---")
        if st.button("➕ Add to Comparison", use_container_width=True, type="primary"):
            already_in_tray = any(
                item['variant'] == selected_variant
                for item in st.session_state.comparison_tray
            )
            if already_in_tray:
                st.warning("This material is already in the comparison tray.")
            else:
                comparison_item = {
                    'variant':   selected_variant,
                    'brand':     slab_data['Brand'],
                    'color':     slab_data['Color'],
                    'thickness': slab_data['Thickness'],
                    'price':     pricing['total_with_tax'],
                    'subtotal':  pricing['subtotal'],
                    'sqft':      sqft,
                    'sinks': [
                        {'type': s['type'], 'quantity': s['quantity'], 'price': s['price']}
                        for s in st.session_state.selected_sinks
                    ],
                }
                st.session_state.comparison_tray.append(comparison_item)
                st.success("Added to comparison tray!")

    # ── Comparison Tray ────────────────────────────────────────────────────────
    if st.session_state.comparison_tray:
        st.markdown("---")
        st.markdown("### 🔍 Comparison Tray")

        col_clear, col_spacer = st.columns([1, 5])
        with col_clear:
            if st.button("🗑️ Clear All", use_container_width=True):
                st.session_state.comparison_tray = []
                st.rerun()

        # Display comparison items in columns (up to 6 per row, wrapping into new rows)
        COLS_PER_ROW = 6
        tray = st.session_state.comparison_tray
        for row_start in range(0, len(tray), COLS_PER_ROW):
            row_items = tray[row_start:row_start + COLS_PER_ROW]
            cols = st.columns(len(row_items))
            for col_idx, item in enumerate(row_items):
                actual_idx = row_start + col_idx
                with cols[col_idx]:
                    with st.container(border=True):
                        st.markdown(f"**{item['brand']} {item['color']}**")
                        st.write(f"{item['thickness']} • {item['sqft']:.0f} sf")

                        if item.get('sinks'):
                            st.write("**Sinks:**")
                            for sink in item['sinks']:
                                st.write(f"• {sink['type'].split('-')[0].strip()}: {sink['quantity']}x")
                        elif item.get('sink'):
                            st.write(f"Sink: {item['sink'].split('-')[0].strip()}")

                        st.markdown(f"### ${item['price']:,.2f}")

                        search_query = (
                            f"{item['brand']} {item['color']} countertop installed"
                        ).replace(" ", "+")
                        st.link_button(
                            "🖼️ View Photos",
                            f"https://www.google.com/search?tbm=isch&q={search_query}",
                            use_container_width=True,
                        )

                        if st.button("Remove", key=f"remove_{actual_idx}", use_container_width=True):
                            st.session_state.comparison_tray.pop(actual_idx)
                            st.rerun()

        # ── Export Comparison Tray as CSV ──────────────────────────────────────
        tray_rows = []
        for item in st.session_state.comparison_tray:
            sink_summary = "; ".join(
                f"{s['type']} ×{s['quantity']}" for s in item.get('sinks', [])
            ) or "None"
            tray_rows.append({
                "Brand":      item['brand'],
                "Color":      item['color'],
                "Thickness":  item['thickness'],
                "Sq Ft":      item['sqft'],
                "Sinks":      sink_summary,
                "Subtotal":   item.get('subtotal', ""),
                "Total (incl. GST)": item['price'],
            })

        tray_csv = pd.DataFrame(tray_rows).to_csv(index=False).encode("utf-8")
        st.download_button(
            label="📥 Export Comparison as CSV",
            data=tray_csv,
            file_name="comparison_tray.csv",
            mime="text/csv",
            use_container_width=True,
        )

else:
    st.error("Unable to load inventory data. Check your network connection or data source URLs.")
