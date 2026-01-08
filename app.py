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

# Custom CSS - Modern SaaS Dashboard Style
st.markdown("""
<style>
    /* Main styling - Modern SaaS theme */
    .stApp {
        background: #f8fafc;
        font-family: -apple-system, BlinkMacSystemFont, "Inter", "Segoe UI", Roboto, sans-serif;
    }

    /* Target native Streamlit bordered containers to act as cards */
    [data-testid="stVerticalBlockBorderWrapper"] > div {
        background-color: white !important;
        border: 1px solid #e2e8f0 !important;
        border-radius: 12px !important;
        padding: 1.75rem !important;
        box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.1) !important;
        margin-bottom: 1rem !important;
    }

    .card-title {
        font-size: 0.95rem;
        font-weight: 700;
        color: #1e293b;
        margin-bottom: 1.25rem;
        text-transform: uppercase;
        letter-spacing: 0.075em;
        display: block;
        line-height: 1.5;
    }

    /* Ensure all text is dark and readable */
    .stApp, .stApp p, .stApp span, .stApp label, .stApp div {
        color: #334155 !important;
    }

    /* Headers */
    h1, h2, h3, .stSubheader {
        color: #1e293b !important;
        font-weight: 600 !important;
    }
    
    /* Metric values - Fixed padding and line-height to prevent clipping */
    [data-testid="stMetricValue"] {
        color: #1e293b !important;
        font-weight: 700 !important;
        font-size: 2rem !important;
        line-height: 1.4 !important;
        padding-top: 5px !important;
        padding-bottom: 10px !important;
    }

    [data-testid="stMetricLabel"] {
        color: #64748b !important;
        font-size: 0.75rem !important;
        text-transform: uppercase !important;
        letter-spacing: 0.05em !important;
        font-weight: 600 !important;
        margin-bottom: 0.25rem !important;
    }

    /* Widget Labels (input fields, dropdowns, etc.) */
    [data-testid="stWidgetLabel"] p {
        font-size: 1rem !important;
        font-weight: 600 !important;
        color: #334155 !important;
        line-height: 1.5 !important;
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
        padding: 8px 12px;
        border-radius: 0 6px 6px 0;
        margin: 0.5rem 0 1rem 0;
        color: #dc2626 !important;
        font-size: 0.95rem;
        font-weight: 500;
        line-height: 1.6;
    }

    .low-stock strong {
        color: #dc2626 !important;
    }

    /* Warning style (yellow) */
    .warning-stock {
        background: #fef3c7;
        border-left: 3px solid #d97706;
        padding: 8px 12px;
        border-radius: 0 6px 6px 0;
        margin: 0.5rem 0 1rem 0;
        color: #92400e !important;
        font-size: 0.95rem;
        font-weight: 500;
        line-height: 1.6;
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
        padding: 12px;
        margin: 0.5rem 0;
        border: 1px solid #e2e8f0;
    }

    .comparison-row strong {
        color: #1e293b !important;
        font-size: 0.95rem;
        font-weight: 600;
        line-height: 1.4;
    }

    .comparison-row span {
        color: #64748b !important;
        font-size: 0.85rem;
        line-height: 1.5;
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
    
    /* Sidebar - dark theme */
    [data-testid="stSidebar"] {
        background: #1e293b;
        border-right: 1px solid #334155;
    }

    [data-testid="stSidebar"] label,
    [data-testid="stSidebar"] span,
    [data-testid="stSidebar"] p,
    [data-testid="stSidebar"] h1,
    [data-testid="stSidebar"] h2,
    [data-testid="stSidebar"] h3 {
        color: #f1f5f9 !important;
        font-weight: 500;
    }

    [data-testid="stSidebar"] .stMarkdown {
        color: #f1f5f9 !important;
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
    
    /* Captions - improved size and readability */
    .stCaption, [data-testid="stCaptionContainer"] {
        font-size: 1rem !important;
        color: #475569 !important;
        line-height: 1.6 !important;
        margin-top: 0.5rem !important;
        font-weight: 500;
    }

    /* Larger captions in inventory context */
    [data-testid="stVerticalBlockBorderWrapper"] .stCaption,
    [data-testid="stVerticalBlockBorderWrapper"] [data-testid="stCaptionContainer"] {
        font-size: 1.05rem !important;
        font-weight: 500 !important;
        line-height: 1.7 !important;
    }

    /* Fix selectbox text clipping */
    .stSelectbox div[data-baseweb="select"] > div {
        font-size: 1rem !important;
        line-height: 1.6 !important;
        padding: 4px 0 !important;
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

    /* Large price display */
    .large-price {
        text-align: center;
        padding: 2.5rem 1rem;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        border-radius: 12px;
        color: white !important;
        box-shadow: 0 10px 25px -5px rgba(102, 126, 234, 0.4);
        margin: 1rem 0;
    }

    .large-price h1 {
        color: white !important;
        font-size: 3.5rem !important;
        margin: 0.5rem 0 !important;
        font-weight: 700 !important;
        line-height: 1.2 !important;
        letter-spacing: -0.02em !important;
    }

    .large-price p {
        color: white !important;
        font-size: 1rem !important;
        opacity: 0.9;
        margin: 0.25rem 0 !important;
    }

    .large-price * {
        color: white !important;
    }

    /* Margin progress bar */
    .margin-bar-container {
        width: 100%;
        height: 12px;
        background: #e2e8f0;
        border-radius: 6px;
        overflow: hidden;
        margin: 0.5rem 0;
    }

    .margin-bar-fill {
        height: 100%;
        border-radius: 6px;
        transition: width 0.3s ease;
    }

    .margin-excellent { background: linear-gradient(90deg, #10b981, #059669); }
    .margin-good { background: linear-gradient(90deg, #f59e0b, #d97706); }
    .margin-low { background: linear-gradient(90deg, #ef4444, #dc2626); }

    /* Compact stat */
    .stat-item {
        padding: 0.875rem 0;
        border-bottom: 1px solid #f1f5f9;
    }

    .stat-item:last-child {
        border-bottom: none;
    }

    .stat-label {
        font-size: 0.75rem;
        color: #64748b !important;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        margin-bottom: 0.375rem;
        font-weight: 600;
        line-height: 1.2;
    }

    .stat-value {
        font-size: 1.5rem;
        font-weight: 700;
        color: #1e293b !important;
        line-height: 1.2;
    }

    /* Sidebar Labels */
    [data-testid="stSidebar"] [data-testid="stWidgetLabel"] p {
        color: #f1f5f9 !important;
    }

    /* Prevent horizontal scroll */
    html, body, .stApp {
        max-width: 100%;
        overflow-x: hidden !important;
    }

    /* ============================= */
    /* 📱 MOBILE & TABLET RESPONSIVE */
    /* ============================= */

    /* Tablets & small laptops */
    @media (max-width: 1024px) {
        h1 {
            font-size: 1.75rem !important;
        }

        .large-price h1 {
            font-size: 2.75rem !important;
        }

        .card-title {
            font-size: 0.8rem !important;
        }

        [data-testid="stMetricValue"] {
            font-size: 1.6rem !important;
        }

        .stButton > button {
            font-size: 13px !important;
            padding: 0.5rem 0.75rem !important;
        }
    }

    /* Tablet-optimized two column mode */
    @media (min-width: 769px) and (max-width: 1024px) {
        [data-testid="column"] {
            flex: 1 1 50% !important;
            max-width: 50% !important;
        }

        /* Hero price for tablets */
        .large-price h1 {
            font-size: 2.5rem !important;
        }

        /* Executive dashboard feel */
        .card-title {
            font-size: 0.85rem !important;
        }
    }

    /* Phones */
    @media (max-width: 768px) {
        /* Stack all columns vertically */
        [data-testid="column"] {
            width: 100% !important;
            flex: 1 1 100% !important;
        }

        /* Make filter row stack vertically */
        .stHorizontalBlock {
            flex-direction: column !important;
            gap: 0.75rem !important;
        }

        /* Filter row optimization */
        .filter-row {
            display: flex !important;
            flex-direction: column !important;
            gap: 0.75rem !important;
        }

        /* Reorder sections for mobile - price first! */
        .large-price {
            order: -1 !important;
            margin-bottom: 1rem !important;
            border-radius: 16px !important;
            padding: 1.5rem 1rem !important;
            text-align: center;
        }

        .project-config {
            order: 0 !important;
        }

        .inventory-details {
            order: 1 !important;
        }

        .price-components {
            order: 2 !important;
        }

        .margin-analysis {
            order: 3 !important;
        }

        /* Reduce padding inside cards */
        [data-testid="stVerticalBlockBorderWrapper"] > div {
            padding: 1.25rem !important;
        }

        /* Header */
        h1 {
            font-size: 1.5rem !important;
        }

        /* Hero price - app-like feel */
        .large-price h1 {
            font-size: 2.1rem !important;
        }

        .large-price p {
            font-size: 0.85rem !important;
            opacity: 0.9;
        }

        /* Metrics */
        [data-testid="stMetricValue"] {
            font-size: 1.4rem !important;
        }

        [data-testid="stMetricLabel"] {
            font-size: 0.7rem !important;
        }

        /* Buttons full width */
        .stButton > button,
        .stDownloadButton > button {
            width: 100% !important;
            font-size: 14px !important;
            padding: 0.75rem !important;
        }

        /* Inputs more touch-friendly - prevents iOS zoom */
        input, select, textarea {
            font-size: 16px !important;
        }

        /* Bigger tap targets on mobile */
        .stSelectbox div,
        .stTextInput div,
        .stNumberInput div {
            min-height: 44px !important;
        }

        label {
            margin-bottom: 0.25rem !important;
        }

        /* Expander headers */
        .streamlit-expanderHeader {
            font-size: 0.75rem !important;
            padding: 0.75rem !important;
        }

        /* Captions */
        .stCaption {
            font-size: 0.9rem !important;
        }

        /* Warning boxes */
        .low-stock, .warning-stock {
            font-size: 0.875rem !important;
            padding: 10px 12px !important;
        }

        /* Card title */
        .card-title {
            font-size: 0.85rem !important;
            margin-bottom: 1rem !important;
        }

        /* Inventory details - condensed */
        .inventory-details h4 {
            font-size: 0.9rem !important;
        }

        .inventory-details p {
            font-size: 0.85rem !important;
        }

        /* Margin analysis - compact */
        .margin-analysis {
            font-size: 0.85rem !important;
        }

        /* Price components - better spacing */
        .price-components [data-testid="stMetricValue"] {
            font-size: 1.3rem !important;
        }
    }
</style>
""", unsafe_allow_html=True)

# YOUR LIVE DATA SOURCES
DATA_SOURCES = [
    "https://docs.google.com/spreadsheets/d/e/2PACX-1vRRo4w07u5IzWj3Dtj-Emrl1zS1wcYDQXomPVW55zctjq-oQ1cyeMnUTNvQ1sBa5Kp_hbYzkap3hctV/pub?output=csv",
    "https://docs.google.com/spreadsheets/d/e/2PACX-1vSkoSeMuPGqr5-JEBhHO5l0fFYlkfmbMUW-VU8UZEpR0pd4lSeyK74WHE47m1zYMg/pub?output=csv"
]

# PRICING CONSTANTS
INSTALL_COST_PER_SQFT = 19.0
FABRICATION_COST_PER_SQFT = 16.0
WASTE_FACTOR = 1.20
TAX_RATE = 0.05
IB_MARGIN = 0.15  # 15% margin on material + fabrication for IB transfer cost

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
    mat = uc * sq_with_waste
    fab = FABRICATION_COST_PER_SQFT * sq_finished
    ins = INSTALL_COST_PER_SQFT * sq_finished
    # IB transfer cost: Material + Fab should be 15% greater than IB
    # So: IB × 1.15 = Material + Fab
    # Therefore: IB = (Material + Fab) / 1.15
    ib = ((uc * sq_with_waste) + (FABRICATION_COST_PER_SQFT * sq_finished)) / (1 + IB_MARGIN)
    
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


def group_slabs_by_material(df):
    """Group slabs by Brand + Color + Thickness and aggregate quantities."""
    if df.empty:
        return pd.DataFrame()

    # Ensure numeric type for accurate summing
    df = df.copy()
    df['On Hand Qty'] = pd.to_numeric(df['On Hand Qty'], errors='coerce').fillna(0)

    # Check if we have a Serial Number column, otherwise use Product Variant
    serial_col = None
    if 'Serial Number' in df.columns:
        serial_col = 'Serial Number'
    elif 'Product Variant' in df.columns:
        serial_col = 'Product Variant'

    # Group and aggregate using named aggregation (pandas 0.25+)
    if serial_col:
        df_grouped = df.groupby(['Brand', 'Color', 'Thickness']).agg(
            On_Hand_Qty=('On Hand Qty', 'sum'),
            Unit_Cost_Internal=('Unit_Cost_Internal', 'mean'),
            Slab_Count=(serial_col, 'nunique'),
            Serial_Numbers=(serial_col, lambda x: list(sorted(x.astype(str).unique())))
        ).reset_index()
    else:
        # If no serial column, count rows as slab count
        df_grouped = df.groupby(['Brand', 'Color', 'Thickness']).agg(
            On_Hand_Qty=('On Hand Qty', 'sum'),
            Unit_Cost_Internal=('Unit_Cost_Internal', 'mean'),
            Slab_Count=('Brand', 'count')  # Count rows
        ).reset_index()
        df_grouped['Serial_Numbers'] = [[] for _ in range(len(df_grouped))]

    # Rename back to 'On Hand Qty' (with space)
    df_grouped.rename(columns={'On_Hand_Qty': 'On Hand Qty'}, inplace=True)

    # Create full name
    df_grouped['Full_Name'] = df_grouped['Brand'] + " " + df_grouped['Color'] + " (" + df_grouped['Thickness'] + ")"

    # Create detailed slab list for tracking
    df_grouped['Slab_Details'] = df_grouped.apply(
        lambda row: _get_slab_details(df, row['Brand'], row['Color'], row['Thickness'], serial_col),
        axis=1
    )

    return df_grouped


def _get_slab_details(df, brand, color, thickness, serial_col):
    """Helper to get detailed slab information for a material group."""
    mask = (df['Brand'] == brand) & (df['Color'] == color) & (df['Thickness'] == thickness)
    group_df = df[mask]

    details = []
    for _, row in group_df.iterrows():
        variant = str(row.get(serial_col, 'N/A')) if serial_col else 'N/A'
        details.append({
            'qty': float(row['On Hand Qty']),
            'variant': variant
        })

    # Sort by quantity descending (use largest slabs first)
    return sorted(details, key=lambda x: x['qty'], reverse=True)


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
# Header
st.markdown("""
<div style="padding: 1rem 0 0.5rem 0;">
    <h1 style="margin: 0; padding: 0; font-size: 2rem; font-weight: 700; color: #1e293b;">
        🧱 Dead Stock Sales Tool
    </h1>
    <p style="margin: 0.25rem 0 0 0; color: #64748b; font-size: 0.95rem;">
        Clearance inventory quoting system with margin visibility
    </p>
</div>
""", unsafe_allow_html=True)

st.markdown("<div style='margin: 1rem 0;'></div>", unsafe_allow_html=True)

# Load data first
df, error = fetch_all_data()

if error:
    st.error(error)
    st.stop()

# --- FILTER ROW ---
st.markdown('<div class="filter-row">', unsafe_allow_html=True)
filter_col1, filter_col2, filter_col3, filter_col4 = st.columns([1, 1, 1, 0.5])

with filter_col1:
    thicks = ["All"] + sorted(df['Thickness'].dropna().unique().tolist())
    sel_thick = st.selectbox(
        "📏 Thickness",
        thicks,
        help="Filter by slab thickness"
    )

with filter_col2:
    brands = ["All"] + sorted(df['Brand'].dropna().unique().tolist())
    sel_brand = st.selectbox(
        "🏷️ Brand",
        brands,
        help="Filter by material brand"
    )

with filter_col3:
    search = st.text_input(
        "🔎 Search",
        placeholder="Search by brand or color...",
        help="Type to search materials"
    )

with filter_col4:
    st.markdown("<div style='margin-top: 1.85rem;'></div>", unsafe_allow_html=True)
    if st.button("🔄 Refresh", use_container_width=True, type="primary"):
        st.cache_data.clear()
        st.rerun()

st.markdown('</div>', unsafe_allow_html=True)  # Close filter-row
st.markdown("<div style='margin: 1.5rem 0;'></div>", unsafe_allow_html=True)

# Apply Filters
df_filt = df.copy()
if sel_thick != "All":
    df_filt = df_filt[df_filt['Thickness'] == sel_thick]
if sel_brand != "All":
    df_filt = df_filt[df_filt['Brand'] == sel_brand]
if search:
    df_filt = df_filt[df_filt['Full_Name'].str.contains(search, case=False, na=False)]

# Group slabs by material (Brand + Color + Thickness)
df_grouped = group_slabs_by_material(df_filt)

if df_grouped.empty:
    st.warning("⚠️ No materials match your filters. Try adjusting your search criteria.")
    st.stop()

# --- PROJECT CONFIGURATION ---
st.markdown('<div class="project-config">', unsafe_allow_html=True)
with st.container(border=True):
    st.markdown('<span class="card-title">⚙️ Project Configuration</span>', unsafe_allow_html=True)

    config_col1, config_col2 = st.columns(2)

    with config_col1:
        req_sqft = st.number_input(
            "Project Square Footage (Finished)",
            min_value=1.0,
            value=35.0,
            step=5.0,
            help="Enter the finished square footage needed"
        )

    with config_col2:
        # Filter materials to only show those with enough combined material (including waste factor)
        sq_with_waste_needed = req_sqft * WASTE_FACTOR
        df_adequate = df_grouped[df_grouped['On Hand Qty'] >= sq_with_waste_needed].copy() if not df_grouped.empty else pd.DataFrame()
        slab_options = df_adequate['Full_Name'].unique().tolist() if not df_adequate.empty else []

        sel_slab = st.selectbox(
            "Select Material",
            slab_options if slab_options else ["No materials available"],
            help="Choose material from available inventory"
        )

    # Show availability info
    if not df_adequate.empty:
        st.caption(f"✓ {len(slab_options)} material(s) available with {sq_with_waste_needed:.0f} sf needed (incl. waste)")
    else:
        st.warning(f"⚠️ No materials have {sq_with_waste_needed:.0f} sf required")

st.markdown('</div>', unsafe_allow_html=True)  # Close project-config
st.markdown("<div style='margin: 1.5rem 0;'></div>", unsafe_allow_html=True)

# --- MAIN DASHBOARD (Two-Column) ---
if sel_slab and sel_slab != "No materials available" and len(slab_options) > 0:
    row = df_adequate[df_adequate['Full_Name'] == sel_slab].iloc[0]
    costs = calculate_cost(row['Unit_Cost_Internal'], req_sqft)

    # Stock availability check
    available_qty = row['On Hand Qty']
    sq_with_waste = req_sqft * WASTE_FACTOR

    col1, col2 = st.columns(2)

    # LEFT COLUMN - Inventory Details
    with col1:
        st.markdown('<div class="inventory-details">', unsafe_allow_html=True)
        # Availability Warning
        if sq_with_waste > available_qty:
            st.markdown(f"""
<div class="low-stock">
⚠️ <strong>Insufficient Stock!</strong> Need {sq_with_waste:.0f} sf (with waste), only {available_qty:.0f} sf available.
</div>
""", unsafe_allow_html=True)
        elif sq_with_waste > available_qty * 0.8:
            st.markdown(f"""
<div class="warning-stock">
⚡ <strong>Tight Fit!</strong> Using {sq_with_waste:.0f} sf of {available_qty:.0f} sf available ({row['Slab_Count']} slabs).
</div>
""", unsafe_allow_html=True)

        # Live Inventory Context Container
        with st.container(border=True):
            st.markdown('<span class="card-title">📦 Inventory Details</span>', unsafe_allow_html=True)

            # Material details
            inv_col1, inv_col2, inv_col3 = st.columns(3)
            inv_col1.metric("Brand", row['Brand'])
            inv_col2.metric("Color", row['Color'])
            inv_col3.metric("Thickness", row['Thickness'])

            st.divider()

            # Calculate slabs needed
            slab_details = row['Slab_Details']
            slabs_needed = []
            remaining_needed = sq_with_waste

            for detail in slab_details:
                if remaining_needed <= 0:
                    break
                slabs_needed.append(detail)
                remaining_needed -= detail['qty']

            # Inventory stats
            inv_stat_col1, inv_stat_col2 = st.columns(2)
            inv_stat_col1.metric("Total Available", f"{available_qty:.0f} sf")
            inv_stat_col1.caption(f"{row['Slab_Count']} slabs in stock")
            inv_stat_col2.metric("Required (w/ waste)", f"{sq_with_waste:.0f} sf")
            inv_stat_col2.caption(f"{len(slabs_needed)} slab(s) needed")

            st.markdown("<br>", unsafe_allow_html=True)

            # Slab details expander
            with st.expander("📋 View Slab Serial Numbers", expanded=False):
                st.markdown("**Slabs Used for This Job:**")
                for idx, slab in enumerate(slabs_needed, 1):
                    st.caption(f"{idx}. {slab['variant']} - {slab['qty']:.0f} sf")

                if len(slabs_needed) < len(slab_details):
                    st.divider()
                    st.markdown(f"**{len(slab_details) - len(slabs_needed)} Additional Slab(s) Available:**")
                    for idx, slab in enumerate(slab_details[len(slabs_needed):], len(slabs_needed) + 1):
                        st.caption(f"{idx}. {slab['variant']} - {slab['qty']:.0f} sf")

        st.markdown('</div>', unsafe_allow_html=True)  # Close inventory-details

    # RIGHT COLUMN - Pricing & Analytics
    with col2:
        # Large Price Display (Hero)
        tax_amt = costs['subtotal_after_discount'] * TAX_RATE
        total = costs['subtotal_after_discount'] + tax_amt

        discount_text = ""
        if costs['discount_pct'] > 0:
            discount_text = f"<p style='margin: 0.5rem 0; color: white; font-size: 1rem;'>🎉 {costs['discount_pct']*100:.0f}% Volume Discount Applied</p>"

        st.markdown(f"""
<div class="large-price">
<p style='text-transform: uppercase; letter-spacing: 0.1em;'>Total Installed Price</p>
<h1>${total:,.2f}</h1>
{discount_text}
<p>Based on {req_sqft:.0f} sf finished (includes 5% tax)</p>
</div>
""", unsafe_allow_html=True)

        # Price breakdown metrics
        st.markdown('<div class="price-components">', unsafe_allow_html=True)
        with st.container(border=True):
            st.markdown('<span class="card-title">💰 Price Components</span>', unsafe_allow_html=True)

            price_col1, price_col2, price_col3 = st.columns(3)
            price_col1.metric("Material", f"${costs['material_total']:,.2f}")
            price_col2.metric("Fabrication", f"${costs['fab_total']:,.2f}")
            price_col3.metric("Installation", f"${costs['install_total']:,.2f}")
        st.markdown('</div>', unsafe_allow_html=True)  # Close price-components

    st.markdown("<div style='margin: 2rem 0;'></div>", unsafe_allow_html=True)

    # MARGIN ANALYSIS (Internal - At Bottom)
    st.markdown('<div class="margin-analysis">', unsafe_allow_html=True)
    with st.expander("🔐 Margin Analysis (Internal Only)", expanded=False):
        margin_class = get_margin_class(costs['margin_pct'])

        # Key metrics
        mc1, mc2, mc3 = st.columns(3)
        mc1.metric("IB Cost", f"${costs['ib_transfer_cost']:,.2f}")
        mc2.metric("Gross Profit", f"${costs['gross_profit']:,.2f}")

        # Margin with color coding
        mc3.markdown(f"""
<div style="text-align: center;">
<div style="font-size: 0.75rem; color: #64748b; text-transform: uppercase; font-weight: 600; margin-bottom: 0.5rem;">Margin</div>
<div class="{margin_class}" style="font-size: 2rem; font-weight: 700; line-height: 1.2;">{costs['margin_pct']:.1f}%</div>
</div>
""", unsafe_allow_html=True)

        # Margin progress bar
        margin_color_class = "margin-excellent" if costs['margin_pct'] >= 30 else ("margin-good" if costs['margin_pct'] >= 20 else "margin-low")
        st.markdown(f"""
<div class="margin-bar-container">
<div class="margin-bar-fill {margin_color_class}" style="width: {min(costs['margin_pct'], 100)}%;"></div>
</div>
""", unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)

        # Cost breakdown
        st.markdown(f"**Unit Cost:** ${row['Unit_Cost_Internal']:,.2f}/sf | **Fab:** ${FABRICATION_COST_PER_SQFT}/sf | **Install:** ${INSTALL_COST_PER_SQFT}/sf | **IB Margin:** {IB_MARGIN*100:.0f}%")

        st.markdown("<br>", unsafe_allow_html=True)

        # Margin guidance
        if costs['margin_pct'] >= 30:
            st.success("✅ Great margin - standard pricing recommended")
        elif costs['margin_pct'] >= 20:
            st.info("📊 Acceptable margin - some negotiation room available")
        else:
            st.warning("⚠️ Below target margin (<20%) - limit discounts")

    st.markdown('</div>', unsafe_allow_html=True)  # Close margin-analysis

else:
    st.markdown("""
    <div style="background: #fef3c7; padding: 1.5rem; border-radius: 6px; border-left: 3px solid #d97706; margin: 1.5rem 0;">
        <span style="color: #92400e;">⚠️ <strong>No materials available for this project size.</strong><br>
        Try reducing the project square footage or check if you need to order new material.</span>
    </div>
    """, unsafe_allow_html=True)

# --- FOOTER ---
st.markdown("<div style='margin: 3rem 0 1rem 0;'></div>", unsafe_allow_html=True)
st.markdown(f"""
<div style="text-align: center; padding: 1.5rem; color: #94a3b8; font-size: 0.875rem; border-top: 1px solid #e2e8f0;">
    Last refresh: {datetime.now().strftime('%Y-%m-%d %H:%M')} | Data auto-refreshes every 10 minutes
</div>
""", unsafe_allow_html=True)
