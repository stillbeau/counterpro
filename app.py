import streamlit as st
import pandas as pd
import re

# --- 1. CONFIGURATION ---
st.set_page_config(page_title="Dead Stock Sales Tool", page_icon="🧱", layout="wide")

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

def calculate_cost(unit_cost_from_csv, project_sqft):
    uc = float(unit_cost_from_csv)
    sq_finished = float(project_sqft)
    
    sq_with_waste = sq_finished * WASTE_FACTOR
    mat = uc * MARKUP_FACTOR * sq_with_waste
    fab = FABRICATION_COST_PER_SQFT * sq_finished
    ins = INSTALL_COST_PER_SQFT * sq_finished
    ib = ((uc * IB_MATERIAL_MARKUP) + FABRICATION_COST_PER_SQFT) * sq_finished
    
    return {
        "material_total": mat,
        "fab_install_total": fab + ins,
        "ib_transfer_cost": ib,
        "customer_total": mat + fab + ins
    }

# --- 2. DATA PROCESSING ---
def parse_product_variant(variant_str):
    if not isinstance(variant_str, str): return pd.Series([None, None, None, None])
    
    # Extract Thickness
    thickness = "Unknown"
    thick_match = re.search(r'(\d+(\.\d+)?cm)', variant_str, re.IGNORECASE)
    if thick_match:
        thickness = thick_match.group(1).lower().replace(" ", "")

    # Extract Location
    location = "Unknown"
    loc_match = re.search(r'\((VER|VAN|VIC|CAL|EDM|SAS|WIN|ABB|KEL)\)', variant_str, re.IGNORECASE)
    if loc_match:
        location = loc_match.group(1).upper()

    # Clean Name
    clean_name = re.sub(r'^15\s-\s', '', variant_str)
    if thick_match: clean_name = clean_name.replace(thick_match.group(1), '')
    if loc_match: clean_name = clean_name.replace(loc_match.group(0), '')
    
    parts = clean_name.strip().split(' ', 1)
    brand = parts[0]
    color = parts[1] if len(parts) > 1 else clean_name.strip()

    return pd.Series([brand, color, thickness, location])

@st.cache_data(ttl=600) # Auto-refresh every 10 mins
def fetch_all_data():
    all_dfs = []
    
    for url in DATA_SOURCES:
        try:
            # Read CSV directly from Google Sheets
            df = pd.read_csv(url)
            
            # Normalize columns
            df.columns = df.columns.str.strip()
            
            # Fuzzy match for 'Product Variant'
            if 'Product Variant' not in df.columns:
                for c in df.columns:
                    if 'Product Variant' in c:
                        df.rename(columns={c: 'Product Variant'}, inplace=True)
                        break
            
            # Only keep if valid
            if 'Product Variant' in df.columns:
                all_dfs.append(df)
                
        except Exception as e:
            st.warning(f"Error loading one of the sheets: {e}")

    if not all_dfs:
        return None, "Could not load data. Please check the Google Sheet links."

    # Combine
    final_df = pd.concat(all_dfs, ignore_index=True)
    
    # Cleaning
    final_df[['Brand', 'Color', 'Thickness', 'Location']] = final_df['Product Variant'].apply(parse_product_variant)
    
    # Clean Numbers
    for col in ['On Hand Qty', 'Serialized On Hand Cost']:
        found = [c for c in final_df.columns if col in c]
        if found:
            c_name = found[0]
            # Remove $ and , and convert to float
            final_df[c_name] = pd.to_numeric(
                final_df[c_name].astype(str).str.replace(r'[$,]', '', regex=True), 
                errors='coerce'
            )
            final_df.rename(columns={c_name: col}, inplace=True)

    # Filter & Calculate Unit Cost
    if 'On Hand Qty' in final_df.columns and 'Serialized On Hand Cost' in final_df.columns:
        final_df = final_df[final_df['On Hand Qty'] > 0]
        final_df['Unit_Cost_Internal'] = final_df['Serialized On Hand Cost'] / final_df['On Hand Qty']
        final_df['Full_Name'] = final_df['Brand'] + " " + final_df['Color'] + " (" + final_df['Thickness'] + ")"
        return final_df, None
    
    return None, "Critical columns missing (On Hand Qty or Cost)."

# --- 3. APP INTERFACE ---
st.title("🧱 Dead Stock Sales Tool")

# Refresh Button
if st.button("🔄 Refresh Data"):
    st.cache_data.clear()

df, error = fetch_all_data()

if error:
    st.error(error)
    st.stop()

# --- FILTERS ---
st.sidebar.header("Filter Inventory")

# Location Filter
locs = ["All"] + sorted(df['Location'].dropna().unique().tolist())
sel_loc = st.sidebar.selectbox("Location", locs)

# Thickness Filter
thicks = ["All"] + sorted(df['Thickness'].dropna().unique().tolist())
sel_thick = st.sidebar.selectbox("Thickness", thicks)

# Text Search
search = st.sidebar.text_input("Search Brand/Color")

# Apply Filters
df_filt = df.copy()
if sel_loc != "All":
    df_filt = df_filt[df_filt['Location'] == sel_loc]
if sel_thick != "All":
    df_filt = df_filt[df_filt['Thickness'] == sel_thick]
if search:
    df_filt = df_filt[df_filt['Full_Name'].str.contains(search, case=False)]

# Show Table
st.markdown(f"**Found {len(df_filt)} slabs**")
st.dataframe(
    df_filt[['Full_Name', 'Location', 'On Hand Qty', 'Unit_Cost_Internal']], 
    use_container_width=True,
    height=300
)

# --- CALCULATOR ---
st.divider()
st.subheader("💰 Quote Calculator")

col1, col2 = st.columns([1, 2])

with col1:
    req_sqft = st.number_input("Project Sq Ft (Finished)", min_value=1.0, value=35.0, step=1.0)
    slab_options = df_filt['Full_Name'].unique()
    sel_slab = st.selectbox("Select Slab to Quote", slab_options)

if sel_slab:
    row = df_filt[df_filt['Full_Name'] == sel_slab].iloc[0]
    
    # Calculate Costs
    costs = calculate_cost(row['Unit_Cost_Internal'], req_sqft)
    
    subtotal = costs['customer_total']
    tax_amt = subtotal * TAX_RATE
    total = subtotal + tax_amt
    
    with col2:
        m1, m2, m3 = st.columns(3)
        m1.metric("Material", f"${costs['material_total']:,.2f}")
        m2.metric("Fab & Install", f"${costs['fab_install_total']:,.2f}")
        m3.metric("Total (Inc Tax)", f"${total:,.2f}")
        
        with st.expander("🔐 Internal Data"):
            st.write(f"**IB Transfer Cost:** ${costs['ib_transfer_cost']:,.2f}")
            st.write(f"**Unit Cost:** ${row['Unit_Cost_Internal']:,.2f}/sf")
            st.caption(f"Available Slab Size: {row['On Hand Qty']} sf")

        email_body = f"""Hi,

I found a clearance option for your project:
Material: {row['Brand']} {row['Color']}
Thickness: {row['Thickness']}
Location: {row['Location']}

Total Installed Price: ${total:,.2f}
(Based on {req_sqft} sq ft finished area)

Let me know if you'd like to secure this piece."""
        
        st.text_area("Email Copy", email_body, height=200)
