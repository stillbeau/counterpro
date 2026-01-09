import math
import streamlit as st
import pandas as pd
import re
import json
from datetime import datetime

# --- 1. CONFIGURATION ---
st.set_page_config(
    page_title="Dead Stock Sales Tool", 
    page_icon="🧱", 
    layout="wide",
    initial_sidebar_state="expanded"
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
    .large-price p { color: white !important; opacity: 0.9; margin: 0 !important; }
    .low-stock { background: #fee2e2; border-left: 4px solid #dc2626; padding: 12px; border-radius: 4px; color: #991b1b !important; margin-bottom: 1rem; }
    .good-margin { color: #059669 !important; font-weight: 700; }
    .low-margin { color: #dc2626 !important; font-weight: 700; }
</style>
""", unsafe_allow_html=True)

# --- CONSTANTS ---
INSTALL_COST_PER_SQFT = 21.0
FABRICATION_COST_PER_SQFT = 16.0
WASTE_FACTOR = 1.20
TAX_RATE = 0.05

# Pricing Controls
IB_MATERIAL_MARKUP = 1.05      # 5% markup on raw material for IB
IB_MIN_MARGIN = 0.18           # Ensure IB is at least 18% margin over raw costs
IB_TO_CUSTOMER_MARKUP = 1.15   # Customer Mat+Fab is 15% higher than IB

# DATA SOURCES
DATA_SOURCES = [
    "https://docs.google.com/spreadsheets/d/e/2PACX-1vSkoSeMuPGqr5-JEBhHO5l0fFYlkfmbMUW-VU8UZEpR0pd4lSeyK74WHE47m1zYMg/pub?output=csv"
]

def calculate_cost(unit_cost, project_sqft):
    """
    Revised pricing logic:
    1. Calculate Raw Direct Cost (Material + Fab).
    2. Calculate IB (Material marked up 5%, enforcing 18% floor on total).
    3. Calculate Customer Material + Fab (Fixed 15% higher than IB).
    """
    uc = float(unit_cost)
    sq_finished = float(project_sqft)
    sq_with_waste = sq_finished * WASTE_FACTOR
    
    # 1. RAW DIRECT COSTS
    raw_material_cost = uc * sq_with_waste
    raw_fab_cost = FABRICATION_COST_PER_SQFT * sq_finished
    total_direct_cost = raw_material_cost + raw_fab_cost
    
    # 2. INTERNAL BASE (IB) CALCULATION
    # Candidate A: Material marked up by 5% + raw fabrication
    ib_candidate_markup = (raw_material_cost * IB_MATERIAL_MARKUP) + raw_fab_cost
    # Candidate B: Enforcing the 18% margin floor on direct costs
    ib_candidate_floor = total_direct_cost / (1 - IB_MIN_MARGIN)
    
    # Final IB is whichever is higher
    ib_cost = max(ib_candidate_markup, ib_candidate_floor)
    
    # 3. CUSTOMER PRICING
    # The requirement: Material and Fabrication needs to be 15% higher than IB
    customer_mat_fab_total = ib_cost * IB_TO_CUSTOMER_MARKUP
    
    # Installation is a separate direct pass-through
    customer_ins_cost = INSTALL_COST_PER_SQFT * sq_finished
    
    subtotal = customer_mat_fab_total + customer_ins_cost
    
    # Analytics
    profit = subtotal - (total_direct_cost + (INSTALL_COST_PER_SQFT * sq_finished)) # True Profit
    margin_pct = (profit / subtotal * 100) if subtotal > 0 else 0
    
    return {
        "customer_mat_fab": customer_mat_fab_total,
        "customer_ins": customer_ins_cost,
        "subtotal": subtotal,
        "ib_cost": ib_cost,
        "margin_pct": margin_pct,
        "total_with_tax": subtotal * (1 + TAX_RATE)
    }

def parse_product_variant(variant_str):
    """Parse Product Variant to extract Brand, Color, and Thickness"""
    try:
        # Remove leading number (e.g., "17 - ")
        cleaned = re.sub(r'^\d+\s*-\s*', '', str(variant_str))

        # Extract brand (before first parenthesis or up to certain keywords)
        brand_match = re.match(r'^([A-Za-z\s&]+)', cleaned)
        brand = brand_match.group(1).strip() if brand_match else "Unknown"

        # Extract thickness (2cm, 3cm, 1.2cm, etc.)
        thickness_match = re.search(r'(\d+\.?\d*cm)', cleaned, re.IGNORECASE)
        thickness = thickness_match.group(1) if thickness_match else ""

        # Remove codes in parentheses and thickness to isolate color
        color_str = re.sub(r'\([^)]*\)', '', cleaned)  # Remove (ABB), (DISCONTINUED), etc.
        color_str = re.sub(r'#\S+', '', color_str)     # Remove #4130, etc.
        color_str = re.sub(r'\d+\.?\d*cm', '', color_str, flags=re.IGNORECASE)  # Remove thickness
        color_str = re.sub(r'\s+', ' ', color_str).strip()  # Clean whitespace

        # Remove brand from color string
        if brand in color_str:
            color_str = color_str.replace(brand, '').strip()

        color = color_str if color_str else "Unknown"

        return brand, color, thickness
    except:
        return "Unknown", str(variant_str), ""

def fetch_data():
    """Fetches fresh inventory data from Google Sheets (no caching - always up-to-date)"""
    all_dfs = []
    for url in DATA_SOURCES:
        try:
            df = pd.read_csv(url)
            df.columns = df.columns.str.strip()
            if 'Product Variant' in df.columns:
                df['On Hand Qty'] = pd.to_numeric(df['On Hand Qty'].astype(str).str.replace(r'[$,]', '', regex=True), errors='coerce')
                df['Serialized On Hand Cost'] = pd.to_numeric(df['Serialized On Hand Cost'].astype(str).str.replace(r'[$,]', '', regex=True), errors='coerce')
                all_dfs.append(df)
        except: continue

    if not all_dfs: return None
    df = pd.concat(all_dfs, ignore_index=True)
    df = df[df['On Hand Qty'] > 0].copy()
    df['Unit_Cost'] = df['Serialized On Hand Cost'] / df['On Hand Qty']

    # Parse product variants to extract structured data
    parsed = df['Product Variant'].apply(parse_product_variant)
    df['Brand'] = parsed.apply(lambda x: x[0])
    df['Color'] = parsed.apply(lambda x: x[1])
    df['Thickness'] = parsed.apply(lambda x: x[2])

    return df

# --- UI EXECUTION ---
st.title("🧱 Dead Stock Sales Tool")

df = fetch_data()
if df is not None:
    # Group by Product Variant and calculate totals
    grouped_df = df.groupby('Product Variant').agg({
        'On Hand Qty': 'sum',
        'Serialized On Hand Cost': 'sum',
        'Brand': 'first',
        'Color': 'first',
        'Thickness': 'first'
    }).reset_index()
    grouped_df['Unit_Cost'] = grouped_df['Serialized On Hand Cost'] / grouped_df['On Hand Qty']

    # SIDEBAR FILTERS
    with st.sidebar:
        st.markdown("### 🔍 Filters")

        # Brand filter
        all_brands = sorted(grouped_df['Brand'].unique())
        selected_brands = st.multiselect(
            "Brand",
            options=all_brands,
            default=all_brands,
            help="Select one or more brands"
        )

        # Thickness filter
        all_thickness = sorted(grouped_df['Thickness'].unique(), reverse=True)
        selected_thickness = st.multiselect(
            "Thickness",
            options=all_thickness,
            default=all_thickness,
            help="Select one or more thickness options"
        )

        # Search box
        search_term = st.text_input(
            "🔎 Search Colors",
            placeholder="Type to search...",
            help="Search by color name"
        )

    # Apply filters
    filtered_df = grouped_df.copy()

    if selected_brands:
        filtered_df = filtered_df[filtered_df['Brand'].isin(selected_brands)]

    if selected_thickness:
        filtered_df = filtered_df[filtered_df['Thickness'].isin(selected_thickness)]

    if search_term:
        filtered_df = filtered_df[
            filtered_df['Color'].str.contains(search_term, case=False, na=False) |
            filtered_df['Brand'].str.contains(search_term, case=False, na=False) |
            filtered_df['Product Variant'].str.contains(search_term, case=False, na=False)
        ]

    # Main Config Card
    with st.container(border=True):
        st.markdown('<span class="card-title">Project Settings</span>', unsafe_allow_html=True)
        col_a, col_b = st.columns(2)
        with col_a:
            sqft = st.number_input("Finished Sq Ft", 1.0, 500.0, 35.0, step=1.0)
        with col_b:
            # Create clean display names using parsed data
            filtered_df['display_name'] = filtered_df.apply(
                lambda row: f"{row['Brand']} {row['Color']} {row['Thickness']} ({row['On Hand Qty']:.1f} sf)", axis=1
            )

            # Create a mapping for reverse lookup
            display_to_variant = dict(zip(filtered_df['display_name'], filtered_df['Product Variant']))

            if len(filtered_df) > 0:
                selected_display = st.selectbox("Select Slab", sorted(filtered_df['display_name'].unique()))
                selected_variant = display_to_variant[selected_display]
            else:
                st.warning("No materials match your filters. Try adjusting the filters above.")
                selected_variant = None

    # Results
    if selected_variant:
        slab_data = grouped_df[grouped_df['Product Variant'] == selected_variant].iloc[0]
        all_slabs = df[df['Product Variant'] == selected_variant]  # Get all individual slabs for this variant
        pricing = calculate_cost(slab_data['Unit_Cost'], sqft)
        
        c1, c2 = st.columns([1, 1])
        
        with c1:
            with st.container(border=True):
                st.markdown('<span class="card-title">Inventory Context</span>', unsafe_allow_html=True)
                if slab_data['On Hand Qty'] < (sqft * WASTE_FACTOR):
                    st.markdown(f'<div class="low-stock">⚠️ Insufficient Stock: Need {sqft * WASTE_FACTOR:.1f}sf, have {slab_data["On Hand Qty"]:.1f}sf</div>', unsafe_allow_html=True)

                # Display all serial numbers for this variant
                serial_num_cols = ['Serial Number', 'SKU', 'Item Code', 'Product SKU', 'Serialized Inventory']
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

        with c2:
            st.markdown(f"""
            <div class="large-price">
                <p>CUSTOMER TOTAL</p>
                <h1>${pricing['total_with_tax']:,.2f}</h1>
                <p>Incl. 5% GST</p>
            </div>
            """, unsafe_allow_html=True)

            with st.expander("💰 Cost Breakdown"):
                st.metric("Slab Cost (Internal IB)", f"${pricing['ib_cost']:,.2f}")
                st.write(f"Customer Mat/Fab: ${pricing['customer_mat_fab']:,.2f}")
                st.write(f"Customer Install: ${pricing['customer_ins']:,.2f}")

else:
    st.error("Unable to load inventory data.")
