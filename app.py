import streamlit as st
import pandas as pd
import re
from datetime import datetime

# --- 1. CONFIGURATION ---
st.set_page_config(
    page_title="Dead Stock Sales Tool", 
    page_icon="🧱", 
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS - Matching Branch Auditor Extension Style
st.markdown("""
<style>
    /* Main styling - Clean light theme matching extension */
    .stApp {
        background: #f8fafc;
    }
    
    /* Ensure all text is dark and readable */
    .stApp, .stApp p, .stApp span, .stApp label, .stApp div {
        color: #334155 !important;
    }
    
    /* Headers - matching extension header style */
    h1, h2, h3, .stSubheader {
        color: #1e293b !important;
        font-weight: 600 !important;
    }
    
    /* Metric values */
    [data-testid="stMetricValue"] {
        color: #1e293b !important;
        font-weight: 700 !important;
    }
    
    [data-testid="stMetricLabel"] {
        color: #64748b !important;
        font-size: 10px !important;
        text-transform: uppercase !important;
    }
    
    /* Card styling - matching extension cards */
    .metric-card {
        background: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 6px;
        padding: 1rem;
        margin: 0.5rem 0;
    }
    
    /* Low stock warning - matching extension alert style */
    .low-stock {
        background: #fee2e2;
        border-left: 3px solid #dc2626;
        padding: 6px 10px;
        border-radius: 0 4px 4px 0;
        margin: 0.5rem 0;
        color: #dc2626 !important;
        font-size: 10px;
        font-weight: 500;
    }
    
    .low-stock strong {
        color: #dc2626 !important;
    }
    
    /* Warning style (yellow) */
    .warning-stock {
        background: #fef3c7;
        border-left: 3px solid #d97706;
        padding: 6px 10px;
        border-radius: 0 4px 4px 0;
        margin: 0.5rem 0;
        color: #92400e !important;
        font-size: 10px;
        font-weight: 500;
    }
    
    /* Margin indicators - matching extension colors */
    .good-margin {
        color: #059669 !important;
        font-weight: 700;
    }
    
    .medium-margin {
        color: #d97706 !important;
        font-weight: 700;
    }
    
    .low-margin {
        color: #dc2626 !important;
        font-weight: 700;
    }
    
    /* Comparison card - matching extension card style */
    .comparison-row {
        background: #ffffff;
        border-radius: 6px;
        padding: 10px;
        margin: 0.5rem 0;
        border: 1px solid #e2e8f0;
    }
    
    .comparison-row strong {
        color: #1e293b !important;
        font-size: 12px;
    }
    
    .comparison-row span {
        color: #64748b !important;
    }
    
    /* Stock badges - matching extension status pills */
    .stock-badge {
        display: inline-block;
        padding: 3px 8px;
        border-radius: 10px;
        font-size: 9px;
        font-weight: 600;
        text-transform: uppercase;
    }
    
    .stock-critical {
        background: #fee2e2;
        color: #dc2626 !important;
    }
    
    .stock-low {
        background: #fef3c7;
        color: #d97706 !important;
    }
    
    .stock-good {
        background: #dcfce7;
        color: #16a34a !important;
    }
    
    /* Sidebar - clean style */
    [data-testid="stSidebar"] {
        background: #ffffff;
        border-right: 1px solid #e2e8f0;
    }

    [data-testid="stSidebar"] label,
    [data-testid="stSidebar"] span,
    [data-testid="stSidebar"] p {
        color: #334155 !important;
        font-weight: 500;
    }

    /* Selectbox styling - light and readable */
    [data-testid="stSidebar"] .stSelectbox > div > div {
        background: #f8fafc !important;
        border: 1px solid #cbd5e1 !important;
        border-radius: 6px !important;
        color: #1e293b !important;
    }

    [data-testid="stSidebar"] .stSelectbox input {
        color: #1e293b !important;
    }

    /* Dropdown menu styling */
    [data-baseweb="popover"] {
        background: #ffffff !important;
        border: 1px solid #cbd5e1 !important;
        border-radius: 6px !important;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1) !important;
    }

    [data-baseweb="popover"] li {
        background: #ffffff !important;
        color: #1e293b !important;
    }

    [data-baseweb="popover"] li:hover {
        background: #f1f5f9 !important;
    }

    /* Text input styling for search */
    [data-testid="stSidebar"] .stTextInput > div > div > input {
        background: #f8fafc !important;
        border: 1px solid #cbd5e1 !important;
        border-radius: 6px !important;
        color: #1e293b !important;
        font-size: 0.9rem !important;
        padding: 0.5rem 0.75rem !important;
    }

    [data-testid="stSidebar"] .stTextInput > div > div > input::placeholder {
        color: #94a3b8 !important;
    }

    [data-testid="stSidebar"] .stTextInput > div > div > input:focus {
        border-color: #4f46e5 !important;
        box-shadow: 0 0 0 1px #4f46e5 !important;
    }

    /* Filter section header */
    [data-testid="stSidebar"] h2 {
        color: #1e293b !important;
        font-weight: 600 !important;
        padding-bottom: 0.5rem !important;
        border-bottom: 2px solid #e2e8f0 !important;
        margin-bottom: 1rem !important;
    }
    
    /* Dataframe - improved table style */
    .stDataFrame {
        border: 1px solid #e2e8f0;
        border-radius: 8px;
        font-size: 13px;
        overflow: hidden;
    }

    /* Table header styling */
    .stDataFrame thead tr th {
        background: #f8fafc !important;
        color: #475569 !important;
        font-weight: 600 !important;
        font-size: 0.8rem !important;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        padding: 0.75rem !important;
        border-bottom: 2px solid #e2e8f0 !important;
    }

    /* Table body styling */
    .stDataFrame tbody tr td {
        padding: 0.75rem !important;
        color: #334155 !important;
        background: #ffffff !important;
        border-bottom: 1px solid #f1f5f9 !important;
    }

    .stDataFrame tbody tr:hover {
        background: #f8fafc !important;
    }

    /* Remove any dark backgrounds from dataframe */
    .stDataFrame, .stDataFrame > div {
        background: #ffffff !important;
    }
    
    /* Primary button - matching extension indigo */
    .stButton > button {
        background: #4f46e5;
        color: white !important;
        border: none;
        font-weight: 600;
        font-size: 11px;
        border-radius: 4px;
    }
    
    .stButton > button:hover {
        background: #4338ca;
    }
    
    /* Download button - green */
    .stDownloadButton > button {
        background: #059669;
        color: white !important;
        font-weight: 600;
        border-radius: 4px;
    }
    
    .stDownloadButton > button:hover {
        background: #047857;
    }
    
    /* Expander - matching extension collapsible style */
    .streamlit-expanderHeader {
        background: #f8fafc;
        color: #1e293b !important;
        font-weight: 600;
        font-size: 10px;
        text-transform: uppercase;
        border: 1px solid #e2e8f0;
        border-radius: 6px;
    }
    
    /* Text area */
    .stTextArea textarea {
        background: #ffffff;
        color: #334155 !important;
        border: 1px solid #e2e8f0;
        border-radius: 6px;
        font-size: 11px;
    }
    
    /* Captions */
    .stCaption, small {
        color: #64748b !important;
        font-size: 10px;
    }
    
    /* KPI style badges */
    .kpi-excellent {
        background: #dcfce7;
        color: #059669 !important;
        padding: 2px 6px;
        border-radius: 8px;
        font-size: 8px;
        font-weight: 600;
    }
    
    .kpi-warning {
        background: #fef3c7;
        color: #d97706 !important;
        padding: 2px 6px;
        border-radius: 8px;
        font-size: 8px;
        font-weight: 600;
    }
    
    .kpi-danger {
        background: #fee2e2;
        color: #dc2626 !important;
        padding: 2px 6px;
        border-radius: 8px;
        font-size: 8px;
        font-weight: 600;
    }
    
    /* Divider */
    hr {
        border-color: #e2e8f0;
    }
</style>
""", unsafe_allow_html=True)

# YOUR LIVE DATA SOURCES
DATA_SOURCES = [
    "https://docs.google.com/spreadsheets/d/e/2PACX-1vRRo4w07u5IzWj3Dtj-Emrl1zS1wcYDQXomPVW55zctjq-oQ1cyeMnUTNvQ1sBa5Kp_hbYzkap3hctV/pub?output=csv",
    "https://docs.google.com/spreadsheets/d/e/2PACX-1vSkoSeMuPGqr5-JEBhHO5l0fFYlkfmbMUW-VU8UZEpR0pd4lSeyK74WHE47m1zYMg/pub?output=csv"
]

# PRICING CONSTANTS
MARKUP_FACTOR = 1.51
INSTALL_COST_PER_SQFT = 21.0
FABRICATION_COST_PER_SQFT = 17.0
IB_MATERIAL_MARKUP = 1.05
WASTE_FACTOR = 1.05
TAX_RATE = 0.05

# STOCK THRESHOLDS
LOW_STOCK_THRESHOLD = 30  # sq ft
CRITICAL_STOCK_THRESHOLD = 15  # sq ft

# DISCOUNT TIERS (for larger projects)
DISCOUNT_TIERS = [
    (100, 0.05),  # 5% off for 100+ sq ft
    (200, 0.08),  # 8% off for 200+ sq ft
    (300, 0.10),  # 10% off for 300+ sq ft
]


def calculate_cost(unit_cost_from_csv, project_sqft, apply_discount=True):
    """Calculate all costs with optional volume discount."""
    uc = float(unit_cost_from_csv)
    sq_finished = float(project_sqft)
    
    # Calculate discount
    discount_pct = 0
    if apply_discount:
        for threshold, pct in sorted(DISCOUNT_TIERS, reverse=True):
            if sq_finished >= threshold:
                discount_pct = pct
                break
    
    sq_with_waste = sq_finished * WASTE_FACTOR
    mat = uc * MARKUP_FACTOR * sq_with_waste
    fab = FABRICATION_COST_PER_SQFT * sq_finished
    ins = INSTALL_COST_PER_SQFT * sq_finished
    ib = ((uc * IB_MATERIAL_MARKUP) + FABRICATION_COST_PER_SQFT) * sq_finished
    
    subtotal = mat + fab + ins
    discount_amt = subtotal * discount_pct
    subtotal_after_discount = subtotal - discount_amt
    
    # Margin calculation
    total_cost = ib  # Internal cost
    gross_profit = subtotal_after_discount - total_cost
    margin_pct = (gross_profit / subtotal_after_discount * 100) if subtotal_after_discount > 0 else 0
    
    return {
        "material_total": mat,
        "fab_total": fab,
        "install_total": ins,
        "fab_install_total": fab + ins,
        "ib_transfer_cost": ib,
        "subtotal": subtotal,
        "discount_pct": discount_pct,
        "discount_amt": discount_amt,
        "subtotal_after_discount": subtotal_after_discount,
        "gross_profit": gross_profit,
        "margin_pct": margin_pct,
        "customer_total": subtotal_after_discount
    }


def get_stock_status(qty):
    """Return stock status and styling."""
    if qty <= CRITICAL_STOCK_THRESHOLD:
        return "critical", "🔴 Critical", "stock-critical"
    elif qty <= LOW_STOCK_THRESHOLD:
        return "low", "🟡 Low", "stock-low"
    else:
        return "good", "🟢 Good", "stock-good"


def get_margin_class(margin_pct):
    """Return CSS class based on margin percentage (aligned with Branch Auditor thresholds)."""
    if margin_pct >= 30:
        return "good-margin"
    elif margin_pct >= 20:
        return "medium-margin"
    else:
        return "low-margin"


# --- 2. DATA PROCESSING ---
def parse_product_variant(variant_str):
    """Parse product variant string to extract brand, color, and thickness."""
    if not isinstance(variant_str, str):
        return pd.Series([None, None, None])
    
    # Extract Thickness
    thickness = "Unknown"
    thick_match = re.search(r'(\d+(\.\d+)?cm)', variant_str, re.IGNORECASE)
    if thick_match:
        thickness = thick_match.group(1).lower().replace(" ", "")

    # Clean Name (remove location codes since we're not using location anymore)
    clean_name = re.sub(r'^15\s-\s', '', variant_str)
    if thick_match:
        clean_name = clean_name.replace(thick_match.group(1), '')
    
    # Remove location codes
    clean_name = re.sub(r'\((VER|VAN|VIC|CAL|EDM|SAS|WIN|ABB|KEL)\)', '', clean_name, flags=re.IGNORECASE)
    
    parts = clean_name.strip().split(' ', 1)
    brand = parts[0].strip()
    color = parts[1].strip() if len(parts) > 1 else clean_name.strip()

    return pd.Series([brand, color, thickness])


@st.cache_data(ttl=600)
def fetch_all_data():
    """Fetch and process data from all sources."""
    all_dfs = []
    
    for url in DATA_SOURCES:
        try:
            df = pd.read_csv(url)
            df.columns = df.columns.str.strip()
            
            # Fuzzy match for 'Product Variant'
            if 'Product Variant' not in df.columns:
                for c in df.columns:
                    if 'Product Variant' in c:
                        df.rename(columns={c: 'Product Variant'}, inplace=True)
                        break
            
            if 'Product Variant' in df.columns:
                all_dfs.append(df)
                
        except Exception as e:
            st.warning(f"⚠️ Error loading sheet: {e}")

    if not all_dfs:
        return None, "Could not load data. Please check the Google Sheet links."

    final_df = pd.concat(all_dfs, ignore_index=True)
    
    # Parse product info (no location now)
    final_df[['Brand', 'Color', 'Thickness']] = final_df['Product Variant'].apply(parse_product_variant)
    
    # Clean numeric columns
    for col in ['On Hand Qty', 'Serialized On Hand Cost']:
        found = [c for c in final_df.columns if col in c]
        if found:
            c_name = found[0]
            final_df[c_name] = pd.to_numeric(
                final_df[c_name].astype(str).str.replace(r'[$,]', '', regex=True), 
                errors='coerce'
            )
            final_df.rename(columns={c_name: col}, inplace=True)

    # Filter & Calculate
    if 'On Hand Qty' in final_df.columns and 'Serialized On Hand Cost' in final_df.columns:
        final_df = final_df[final_df['On Hand Qty'] > 0]
        final_df['Unit_Cost_Internal'] = final_df['Serialized On Hand Cost'] / final_df['On Hand Qty']
        final_df['Full_Name'] = final_df['Brand'] + " " + final_df['Color'] + " (" + final_df['Thickness'] + ")"
        
        # Add stock status
        final_df['Stock_Status'] = final_df['On Hand Qty'].apply(lambda x: get_stock_status(x)[0])
        
        return final_df, None
    
    return None, "Critical columns missing (On Hand Qty or Cost)."


# --- 3. APP INTERFACE ---
# Improved header with better layout
header_col1, header_col2 = st.columns([3, 1])
with header_col1:
    st.markdown("""
    <div style="padding: 1rem 0;">
        <h1 style="margin: 0; padding: 0; font-size: 2rem; font-weight: 700; color: #1e293b;">
            🧱 Dead Stock Sales Tool
        </h1>
        <p style="margin: 0.25rem 0 0 0; color: #64748b; font-size: 0.95rem;">
            Clearance inventory quoting system with margin visibility
        </p>
    </div>
    """, unsafe_allow_html=True)
with header_col2:
    # Moved buttons to header
    pass

# Action buttons in a cleaner layout
st.markdown("<div style='margin: 1.5rem 0;'></div>", unsafe_allow_html=True)
col_refresh, col_export, col_spacer = st.columns([1.2, 1.2, 3.6])

with col_refresh:
    if st.button("🔄 Refresh Data", use_container_width=True, type="primary"):
        st.cache_data.clear()
        st.rerun()

# Load data
df, error = fetch_all_data()

if error:
    st.error(error)
    st.stop()

with col_export:
    csv_data = df[['Full_Name', 'On Hand Qty', 'Unit_Cost_Internal', 'Thickness']].to_csv(index=False)
    st.download_button(
        "📥 Export CSV",
        csv_data,
        file_name=f"dead_stock_{datetime.now().strftime('%Y%m%d')}.csv",
        mime="text/csv",
        use_container_width=True
    )

# --- SIDEBAR FILTERS ---
st.sidebar.markdown("""
<div style="padding: 0.5rem 0 1rem 0;">
    <h2 style="margin: 0; font-size: 1.1rem; font-weight: 600; color: #1e293b;">
        🔍 Filter Inventory
    </h2>
</div>
""", unsafe_allow_html=True)

# Thickness Filter
st.sidebar.markdown("<div style='margin-top: 0.5rem;'></div>", unsafe_allow_html=True)
thicks = ["All"] + sorted(df['Thickness'].dropna().unique().tolist())
sel_thick = st.sidebar.selectbox(
    "📏 Thickness",
    thicks,
    help="Filter by slab thickness"
)

# Brand Filter
st.sidebar.markdown("<div style='margin-top: 1rem;'></div>", unsafe_allow_html=True)
brands = ["All"] + sorted(df['Brand'].dropna().unique().tolist())
sel_brand = st.sidebar.selectbox(
    "🏷️ Brand",
    brands,
    help="Filter by material brand"
)

# Text Search
st.sidebar.markdown("<div style='margin-top: 1.5rem;'></div>", unsafe_allow_html=True)
search = st.sidebar.text_input(
    "🔎 Search",
    placeholder="Search by brand or color...",
    help="Type to search materials"
)

# Apply Filters
df_filt = df.copy()
if sel_thick != "All":
    df_filt = df_filt[df_filt['Thickness'] == sel_thick]
if sel_brand != "All":
    df_filt = df_filt[df_filt['Brand'] == sel_brand]
if search:
    df_filt = df_filt[df_filt['Full_Name'].str.contains(search, case=False, na=False)]

# --- INVENTORY TABLE ---
st.markdown("<div style='margin: 2rem 0 1rem 0;'></div>", unsafe_allow_html=True)
st.markdown("""
<div style="background: white; padding: 1.5rem; border-radius: 8px; border: 1px solid #e2e8f0; margin-bottom: 1.5rem;">
    <h2 style="margin: 0 0 1rem 0; font-size: 1.25rem; font-weight: 600; color: #1e293b;">
        📦 Available Inventory
    </h2>
</div>
""", unsafe_allow_html=True)

# Summary metrics with improved styling
st.markdown("<div style='margin: 1.5rem 0;'></div>", unsafe_allow_html=True)
m1, m2 = st.columns(2)
with m1:
    st.markdown(f"""
    <div style="background: white; padding: 1rem; border-radius: 6px; border: 1px solid #e2e8f0;">
        <div style="color: #64748b; font-size: 0.75rem; text-transform: uppercase; margin-bottom: 0.25rem;">TOTAL SLABS</div>
        <div style="color: #1e293b; font-size: 1.75rem; font-weight: 700;">{len(df_filt)}</div>
    </div>
    """, unsafe_allow_html=True)
with m2:
    total_sqft = df_filt['On Hand Qty'].sum()
    st.markdown(f"""
    <div style="background: white; padding: 1rem; border-radius: 6px; border: 1px solid #e2e8f0;">
        <div style="color: #64748b; font-size: 0.75rem; text-transform: uppercase; margin-bottom: 0.25rem;">TOTAL SQ FT</div>
        <div style="color: #1e293b; font-size: 1.75rem; font-weight: 700;">{total_sqft:,.0f}</div>
    </div>
    """, unsafe_allow_html=True)

# Format dataframe for display with improved styling
st.markdown("<div style='margin: 1.5rem 0;'></div>", unsafe_allow_html=True)

if len(df_filt) > 0:
    display_df = df_filt[['Full_Name', 'On Hand Qty', 'Unit_Cost_Internal']].copy()
    display_df['Unit Cost'] = display_df['Unit_Cost_Internal'].apply(lambda x: f"${x:,.2f}/sf")
    display_df['Qty (sf)'] = display_df['On Hand Qty'].apply(lambda x: f"{x:,.0f}")

    st.dataframe(
        display_df[['Full_Name', 'Qty (sf)', 'Unit Cost']].rename(columns={'Full_Name': 'Material'}),
        use_container_width=True,
        height=400,
        hide_index=True
    )
else:
    st.markdown("""
    <div style="background: #fef3c7; padding: 1rem; border-radius: 6px; border-left: 3px solid #d97706; margin: 1.5rem 0;">
        <span style="color: #92400e;">⚠️ No slabs match your filters. Try adjusting your search criteria.</span>
    </div>
    """, unsafe_allow_html=True)
    st.stop()

# --- QUOTE CALCULATOR ---
st.markdown("<div style='margin: 2.5rem 0 1.5rem 0;'></div>", unsafe_allow_html=True)
st.markdown("""
<div style="background: white; padding: 1.5rem; border-radius: 8px; border: 1px solid #e2e8f0; margin-bottom: 1.5rem;">
    <h2 style="margin: 0; font-size: 1.25rem; font-weight: 600; color: #1e293b;">
        💰 Quote Calculator
    </h2>
</div>
""", unsafe_allow_html=True)

# Initialize comparison list in session state
if 'comparison_slabs' not in st.session_state:
    st.session_state.comparison_slabs = []

col1, col2 = st.columns([1, 2])

with col1:
    req_sqft = st.number_input(
        "Project Sq Ft (Finished)", 
        min_value=1.0, 
        value=35.0, 
        step=5.0,
        help="Enter the finished square footage needed"
    )
    
    slab_options = df_filt['Full_Name'].unique().tolist()
    sel_slab = st.selectbox("Select Slab to Quote", slab_options)
    
    # Add to comparison button
    if st.button("➕ Add to Comparison", use_container_width=True):
        if sel_slab and sel_slab not in st.session_state.comparison_slabs:
            if len(st.session_state.comparison_slabs) < 4:
                st.session_state.comparison_slabs.append(sel_slab)
                st.success(f"Added {sel_slab[:30]}...")
            else:
                st.warning("Max 4 slabs for comparison")

if sel_slab:
    row = df_filt[df_filt['Full_Name'] == sel_slab].iloc[0]
    costs = calculate_cost(row['Unit_Cost_Internal'], req_sqft)

    # Stock availability check
    available_qty = row['On Hand Qty']
    sq_with_waste = req_sqft * WASTE_FACTOR

    with col2:
        # Main pricing metrics
        pm1, pm2, pm3 = st.columns(3)
        pm1.metric("Material", f"${costs['material_total']:,.2f}")
        pm2.metric("Fab & Install", f"${costs['fab_install_total']:,.2f}")
        
        # Show discount if applicable
        if costs['discount_pct'] > 0:
            pm3.metric(
                "Subtotal", 
                f"${costs['subtotal_after_discount']:,.2f}",
                f"-{costs['discount_pct']*100:.0f}% volume discount"
            )
        else:
            pm3.metric("Subtotal", f"${costs['subtotal']:,.2f}")
        
        # Tax and total
        tax_amt = costs['subtotal_after_discount'] * TAX_RATE
        total = costs['subtotal_after_discount'] + tax_amt
        
        st.markdown(f"### 💵 Total (Inc. 5% Tax): **${total:,.2f}**")
        
        # --- MARGIN VISIBILITY (Internal) ---
        with st.expander("🔐 Sales Team: Margin & Cost Analysis", expanded=False):
            margin_class = get_margin_class(costs['margin_pct'])

            # Material Details Section
            st.markdown("**📋 Material Details:**")
            mat_col1, mat_col2, mat_col3 = st.columns(3)
            with mat_col1:
                st.markdown(f"**Brand:** {row['Brand']}")
            with mat_col2:
                st.markdown(f"**Color:** {row['Color']}")
            with mat_col3:
                st.markdown(f"**Thickness:** {row['Thickness']}")

            # Display Product Variant (contains serial/item info)
            if 'Product Variant' in row.index and pd.notna(row['Product Variant']):
                st.caption(f"Product Variant: {row['Product Variant']}")

            # Display any serial number columns if they exist
            serial_cols = [col for col in row.index if 'serial' in col.lower() or 'sku' in col.lower() or 'item' in col.lower()]
            if serial_cols:
                serial_info = " | ".join([f"{col}: {row[col]}" for col in serial_cols if pd.notna(row[col])])
                if serial_info:
                    st.caption(f"🔖 {serial_info}")

            st.markdown("---")

            ic1, ic2, ic3 = st.columns(3)
            ic1.metric("IB Transfer Cost", f"${costs['ib_transfer_cost']:,.2f}")
            ic2.metric("Gross Profit", f"${costs['gross_profit']:,.2f}")

            # Color-coded margin
            ic3.markdown(f"""
            <div style="text-align: center;">
                <span style="font-size: 0.875rem; color: #9ca3af;">Margin</span><br>
                <span class="{margin_class}" style="font-size: 1.5rem;">{costs['margin_pct']:.1f}%</span>
            </div>
            """, unsafe_allow_html=True)

            st.markdown("---")

            # Detailed breakdown
            st.markdown("**Cost Breakdown:**")
            breakdown_cols = st.columns(4)
            breakdown_cols[0].write(f"Unit Cost: ${row['Unit_Cost_Internal']:,.2f}/sf")
            breakdown_cols[1].write(f"Material Markup: {MARKUP_FACTOR}x")
            breakdown_cols[2].write(f"Fab Rate: ${FABRICATION_COST_PER_SQFT}/sf")
            breakdown_cols[3].write(f"Install Rate: ${INSTALL_COST_PER_SQFT}/sf")
            
            # Margin guidance
            st.markdown("---")
            if costs['margin_pct'] >= 30:
                st.success("✅ Great margin - standard pricing recommended")
            elif costs['margin_pct'] >= 20:
                st.info("📊 Acceptable margin - some negotiation room available")
            else:
                st.warning("⚠️ Below target margin (<20%) - limit discounts")
            
            st.caption(f"Available: {available_qty:.0f} sf | Using: {sq_with_waste:.0f} sf (with {(WASTE_FACTOR-1)*100:.0f}% waste)")
        
        # --- EMAIL TEMPLATE ---
        st.markdown("---")
        st.markdown("**📧 Customer Email Template**")
        
        discount_text = ""
        if costs['discount_pct'] > 0:
            discount_text = f"\n🎉 Volume Discount Applied: {costs['discount_pct']*100:.0f}% off!"
        
        email_body = f"""Hi,

I found a clearance option for your project:

Material: {row['Brand']} {row['Color']}
Thickness: {row['Thickness']}
{discount_text}
Total Installed Price: ${total:,.2f}
(Based on {req_sqft:.0f} sq ft finished area)

This is a limited-availability clearance piece. Let me know if you'd like to secure it!

Best regards"""

        st.text_area("Email Copy", email_body, height=200, key="email_copy")
        
        # Copy button with feedback
        if st.button("📋 Copy to Clipboard", use_container_width=True):
            st.code(email_body, language=None)
            st.success("✅ Email copied! Use Ctrl+C to copy from the box above.")

# --- COMPARISON TABLE ---
if st.session_state.comparison_slabs:
    st.markdown("<div style='margin: 2.5rem 0 1.5rem 0;'></div>", unsafe_allow_html=True)
    st.markdown("""
    <div style="background: white; padding: 1.5rem; border-radius: 8px; border: 1px solid #e2e8f0; margin-bottom: 1.5rem;">
        <h2 style="margin: 0; font-size: 1.25rem; font-weight: 600; color: #1e293b;">
            📊 Slab Comparison
        </h2>
    </div>
    """, unsafe_allow_html=True)
    
    # Clear comparison button
    if st.button("🗑️ Clear Comparison"):
        st.session_state.comparison_slabs = []
        st.rerun()
    
    comp_cols = st.columns(len(st.session_state.comparison_slabs))
    
    for idx, slab_name in enumerate(st.session_state.comparison_slabs):
        if slab_name in df_filt['Full_Name'].values:
            slab_row = df_filt[df_filt['Full_Name'] == slab_name].iloc[0]
            slab_costs = calculate_cost(slab_row['Unit_Cost_Internal'], req_sqft)
            slab_total = slab_costs['subtotal_after_discount'] * (1 + TAX_RATE)
            margin_class = get_margin_class(slab_costs['margin_pct'])

            with comp_cols[idx]:
                st.markdown(f"""
                <div class="comparison-row">
                    <strong>{slab_row['Brand']}</strong><br>
                    <span style="color: #9ca3af; font-size: 0.875rem;">{slab_row['Color']}</span>
                </div>
                """, unsafe_allow_html=True)

                st.metric("Total Price", f"${slab_total:,.2f}")
                st.markdown(f"<span class='{margin_class}'>Margin: {slab_costs['margin_pct']:.1f}%</span>", unsafe_allow_html=True)
                st.caption(f"Available: {slab_row['On Hand Qty']:.0f} sf")

                if st.button("❌ Remove", key=f"remove_{idx}"):
                    st.session_state.comparison_slabs.remove(slab_name)
                    st.rerun()

# --- FOOTER ---
st.markdown("<div style='margin: 3rem 0 1rem 0;'></div>", unsafe_allow_html=True)
st.markdown(f"""
<div style="text-align: center; padding: 1.5rem; color: #94a3b8; font-size: 0.875rem; border-top: 1px solid #e2e8f0;">
    Last refresh: {datetime.now().strftime('%Y-%m-%d %H:%M')} | Data auto-refreshes every 10 minutes
</div>
""", unsafe_allow_html=True)
