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
FABRICATION_COST_PER_SQFT = 15.0
WASTE_FACTOR = 1.05  
TAX_RATE = 0.05

# Pricing Controls
IB_MATERIAL_MARKUP = 1.05      # 5% markup on raw material for IB
IB_MIN_MARGIN = 0.18           # Ensure IB is at least 18% margin over raw costs
IB_TO_CUSTOMER_MARKUP = 1.15   # Customer Mat+Fab is 15% higher than IB

# DATA SOURCES
DATA_SOURCES = [
    "https://docs.google.com/spreadsheets/d/e/2PACX-1vRo4w07u5IzWj3Dtj-Emrl1zS1wcYDQXomPVW55zctjq-oQ1cyeMnUTNvQ1sBa5Kp_hbYzkap3hctV/pub?output=csv",
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

@st.cache_data(ttl=600)
def fetch_data():
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
    return df

# --- UI EXECUTION ---
st.title("🧱 Dead Stock Sales Tool")

df = fetch_data()
if df is not None:
    # Filter Sidebar
    with st.sidebar:
        st.header("Filters")
        search = st.text_input("Search Material", "")
        
    # Main Config Card
    with st.container(border=True):
        st.markdown('<span class="card-title">Project Settings</span>', unsafe_allow_html=True)
        col_a, col_b = st.columns(2)
        with col_a:
            sqft = st.number_input("Finished Sq Ft", 1.0, 500.0, 35.0)
        with col_b:
            if search:
                df = df[df['Product Variant'].str.contains(search, case=False)]
            selected_variant = st.selectbox("Select Slab", df['Product Variant'].unique())

    # Results
    if selected_variant:
        slab_data = df[df['Product Variant'] == selected_variant].iloc[0]
        pricing = calculate_cost(slab_data['Unit_Cost'], sqft)
        
        c1, c2 = st.columns([1, 1])
        
        with c1:
            with st.container(border=True):
                st.markdown('<span class="card-title">Inventory Context</span>', unsafe_allow_html=True)
                if slab_data['On Hand Qty'] < (sqft * WASTE_FACTOR):
                    st.markdown(f'<div class="low-stock">⚠️ Insufficient Stock: Need {sqft * WASTE_FACTOR:.1f}sf, have {slab_data["On Hand Qty"]:.1f}sf</div>', unsafe_allow_html=True)
                
                st.metric("Available Qty", f"{slab_data['On Hand Qty']:.1f} sf")
                st.metric("Slab Cost (Internal IB)", f"${pricing['ib_cost']:,.2f}")

        with c2:
            st.markdown(f"""
            <div class="large-price">
                <p>CUSTOMER TOTAL</p>
                <h1>${pricing['total_with_tax']:,.2f}</h1>
                <p>Incl. 5% GST</p>
            </div>
            """, unsafe_allow_html=True)
            
            with st.expander("🔐 Margin Analysis"):
                m_color = "good-margin" if pricing['margin_pct'] >= 25 else "low-margin"
                st.markdown(f"Gross Margin: <span class='{m_color}'>{pricing['margin_pct']:.1f}%</span>", unsafe_allow_html=True)
                st.write(f"Customer Mat/Fab: ${pricing['customer_mat_fab']:,.2f}")
                st.write(f"Customer Install: ${pricing['customer_ins']:,.2f}")
                st.write(f"Spread Check: Material & Fab is {IB_TO_CUSTOMER_MARKUP:.0%} of IB.")

else:
    st.error("Unable to load inventory data.")
