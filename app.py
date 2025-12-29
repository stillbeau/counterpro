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

# Custom CSS for better UX - LIGHT THEME for readability
st.markdown("""
<style>
    /* Main styling - Light theme */
    .stApp {
        background: #f8fafc;
    }
    
    /* Ensure all text is dark and readable */
    .stApp, .stApp p, .stApp span, .stApp label, .stApp div {
        color: #1e293b !important;
    }
    
    /* Headers */
    h1, h2, h3, .stSubheader {
        color: #0f172a !important;
        font-weight: 700 !important;
    }
    
    /* Metric values */
    [data-testid="stMetricValue"] {
        color: #0f172a !important;
        font-weight: 600 !important;
    }
    
    [data-testid="stMetricLabel"] {
        color: #475569 !important;
    }
    
    /* Card styling */
    .metric-card {
        background: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 12px;
        padding: 1.5rem;
        margin: 0.5rem 0;
        box-shadow: 0 1px 3px rgba(0,0,0,0.1);
    }
    
    /* Low stock warning */
    .low-stock {
        background: linear-gradient(90deg, #fef2f2, #ffffff);
        border-left: 4px solid #ef4444;
        padding: 0.75rem 1rem;
        border-radius: 0 8px 8px 0;
        margin: 0.5rem 0;
        color: #991b1b !important;
    }
    
    /* Good margin indicator */
    .good-margin {
        color: #16a34a !important;
        font-weight: 600;
    }
    
    .medium-margin {
        color: #d97706 !important;
        font-weight: 600;
    }
    
    .low-margin {
        color: #dc2626 !important;
        font-weight: 600;
    }
    
    /* Comparison table */
    .comparison-row {
        background: #ffffff;
        border-radius: 8px;
        padding: 1rem;
        margin: 0.5rem 0;
        border: 1px solid #e2e8f0;
        box-shadow: 0 1px 2px rgba(0,0,0,0.05);
    }
    
    .comparison-row strong {
        color: #0f172a !important;
    }
    
    .comparison-row span {
        color: #64748b !important;
    }
    
    /* Stock badges */
    .stock-badge {
        display: inline-block;
        padding: 0.25rem 0.75rem;
        border-radius: 999px;
        font-size: 0.75rem;
        font-weight: 600;
    }
    
    .stock-critical {
        background: #fef2f2;
        color: #dc2626 !important;
        border: 1px solid #fecaca;
    }
    
    .stock-low {
        background: #fffbeb;
        color: #d97706 !important;
        border: 1px solid #fde68a;
    }
    
    .stock-good {
        background: #f0fdf4;
        color: #16a34a !important;
        border: 1px solid #bbf7d0;
    }
    
    /* Sidebar */
    [data-testid="stSidebar"] {
        background: #ffffff;
        border-right: 1px solid #e2e8f0;
    }
    
    [data-testid="stSidebar"] label, 
    [data-testid="stSidebar"] span,
    [data-testid="stSidebar"] p {
        color: #334155 !important;
    }
    
    /* Dataframe */
    .stDataFrame {
        border: 1px solid #e2e8f0;
        border-radius: 8px;
    }
    
    /* Buttons */
    .stButton > button {
        background: #3b82f6;
        color: white !important;
        border: none;
        font-weight: 500;
    }
    
    .stButton > button:hover {
        background: #2563eb;
    }
    
    /* Download button */
    .stDownloadButton > button {
        background: #10b981;
        color: white !important;
    }
    
    /* Expander */
    .streamlit-expanderHeader {
        background: #f1f5f9;
        color: #1e293b !important;
        font-weight: 600;
    }
    
    /* Text area */
    .stTextArea textarea {
        background: #ffffff;
        color: #1e293b !important;
        border: 1px solid #cbd5e1;
    }
    
    /* Captions */
    .stCaption, small {
        color: #64748b !important;
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
    """Return CSS class based on margin percentage."""
    if margin_pct >= 35:
        return "good-margin"
    elif margin_pct >= 25:
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
st.title("🧱 Dead Stock Sales Tool")
st.caption("Clearance inventory quoting system with margin visibility")

# Header actions
col_refresh, col_export, col_spacer = st.columns([1, 1, 4])
with col_refresh:
    if st.button("🔄 Refresh Data", use_container_width=True):
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
st.sidebar.header("🔍 Filter Inventory")

# Thickness Filter
thicks = ["All"] + sorted(df['Thickness'].dropna().unique().tolist())
sel_thick = st.sidebar.selectbox("Thickness", thicks)

# Brand Filter
brands = ["All"] + sorted(df['Brand'].dropna().unique().tolist())
sel_brand = st.sidebar.selectbox("Brand", brands)

# Stock Status Filter
stock_filter = st.sidebar.selectbox(
    "Stock Level",
    ["All", "🔴 Critical Only", "🟡 Low Stock", "🟢 Good Stock"]
)

# Text Search
search = st.sidebar.text_input("🔎 Search Brand/Color", placeholder="Type to search...")

# Apply Filters
df_filt = df.copy()
if sel_thick != "All":
    df_filt = df_filt[df_filt['Thickness'] == sel_thick]
if sel_brand != "All":
    df_filt = df_filt[df_filt['Brand'] == sel_brand]
if stock_filter == "🔴 Critical Only":
    df_filt = df_filt[df_filt['Stock_Status'] == 'critical']
elif stock_filter == "🟡 Low Stock":
    df_filt = df_filt[df_filt['Stock_Status'] == 'low']
elif stock_filter == "🟢 Good Stock":
    df_filt = df_filt[df_filt['Stock_Status'] == 'good']
if search:
    df_filt = df_filt[df_filt['Full_Name'].str.contains(search, case=False, na=False)]

# --- INVENTORY TABLE ---
st.markdown("---")
st.subheader("📦 Available Inventory")

# Summary metrics
m1, m2, m3, m4 = st.columns(4)
m1.metric("Total Slabs", len(df_filt))
m2.metric("🔴 Critical", len(df_filt[df_filt['Stock_Status'] == 'critical']))
m3.metric("🟡 Low Stock", len(df_filt[df_filt['Stock_Status'] == 'low']))
m4.metric("Total Sq Ft", f"{df_filt['On Hand Qty'].sum():,.0f}")

# Format dataframe for display
if len(df_filt) > 0:
    display_df = df_filt[['Full_Name', 'On Hand Qty', 'Unit_Cost_Internal', 'Stock_Status']].copy()
    display_df['Stock'] = display_df['Stock_Status'].map({
        'critical': '🔴 Critical',
        'low': '🟡 Low',
        'good': '🟢 Good'
    })
    display_df['Unit Cost'] = display_df['Unit_Cost_Internal'].apply(lambda x: f"${x:,.2f}/sf")
    display_df['Qty (sf)'] = display_df['On Hand Qty'].apply(lambda x: f"{x:,.0f}")
    
    st.dataframe(
        display_df[['Full_Name', 'Qty (sf)', 'Unit Cost', 'Stock']].rename(columns={'Full_Name': 'Material'}),
        use_container_width=True,
        height=300,
        hide_index=True
    )
else:
    st.warning("No slabs match your filters. Try adjusting your search criteria.")
    st.stop()

# --- QUOTE CALCULATOR ---
st.markdown("---")
st.subheader("💰 Quote Calculator")

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
        # Availability Warning
        if sq_with_waste > available_qty:
            st.markdown(f"""
            <div class="low-stock">
                ⚠️ <strong>Insufficient Stock!</strong> Need {sq_with_waste:.0f} sf (with waste), only {available_qty:.0f} sf available.
            </div>
            """, unsafe_allow_html=True)
        elif sq_with_waste > available_qty * 0.8:
            st.markdown(f"""
            <div class="low-stock" style="border-left-color: #fbbf24; background: linear-gradient(90deg, #fbbf2422, transparent);">
                ⚡ <strong>Tight Fit!</strong> Using {sq_with_waste:.0f} sf of {available_qty:.0f} sf available.
            </div>
            """, unsafe_allow_html=True)
        
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
            if costs['margin_pct'] >= 35:
                st.success("✅ Great margin - standard pricing recommended")
            elif costs['margin_pct'] >= 25:
                st.info("📊 Acceptable margin - some negotiation room available")
            else:
                st.warning("⚠️ Low margin - consider limiting discounts")
            
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
    st.markdown("---")
    st.subheader("📊 Slab Comparison")
    
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
            stock_status, stock_label, stock_class = get_stock_status(slab_row['On Hand Qty'])
            
            with comp_cols[idx]:
                st.markdown(f"""
                <div class="comparison-row">
                    <strong>{slab_row['Brand']}</strong><br>
                    <span style="color: #9ca3af; font-size: 0.875rem;">{slab_row['Color']}</span><br>
                    <span class="{stock_class}" style="margin-top: 0.5rem; display: inline-block;">{stock_label}</span>
                </div>
                """, unsafe_allow_html=True)
                
                st.metric("Total Price", f"${slab_total:,.2f}")
                st.markdown(f"<span class='{margin_class}'>Margin: {slab_costs['margin_pct']:.1f}%</span>", unsafe_allow_html=True)
                st.caption(f"Available: {slab_row['On Hand Qty']:.0f} sf")
                
                if st.button("❌ Remove", key=f"remove_{idx}"):
                    st.session_state.comparison_slabs.remove(slab_name)
                    st.rerun()

# --- FOOTER ---
st.markdown("---")
st.caption(f"Last refresh: {datetime.now().strftime('%Y-%m-%d %H:%M')} | Data auto-refreshes every 10 minutes")
