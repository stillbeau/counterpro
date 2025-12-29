import streamlit as st
import pandas as pd
import re

# --- 1. CONFIGURATION & PRICING LOGIC ---
st.set_page_config(page_title="Dead Stock Sales Tool", page_icon="🧱", layout="wide")

MARKUP_FACTOR = 1.51
INSTALL_COST_PER_SQFT = 21.0
FABRICATION_COST_PER_SQFT = 17.0
IB_MATERIAL_MARKUP = 1.05
WASTE_FACTOR = 1.05  # Charge customer for 5% waste on material
TAX_RATE = 0.05      # GST

def calculate_cost(unit_cost_from_csv, project_sqft):
    # Ensure inputs are floats
    uc = float(unit_cost_from_csv)
    sq_finished = float(project_sqft)
    
    # Material is charged on project_sqft * WASTE_FACTOR
    sq_with_waste = sq_finished * WASTE_FACTOR
    
    # Material Sale Price
    mat = uc * MARKUP_FACTOR * sq_with_waste
    
    # Fabrication & Install are charged on FINISHED sqft
    fab = FABRICATION_COST_PER_SQFT * sq_finished
    ins = INSTALL_COST_PER_SQFT * sq_finished
    
    # Internal Branch (IB) Transfer Cost
    ib = ((uc * IB_MATERIAL_MARKUP) + FABRICATION_COST_PER_SQFT) * sq_finished
    
    return {
        "material_total": mat,
        "fabrication_total": fab,
        "install_total": ins,
        "ib_transfer_cost": ib,
        "customer_subtotal": mat + fab + ins
    }

# --- 2. DATA CLEANING FUNCTIONS ---
def parse_product_variant(variant_str):
    """Extracts Brand, Color, Thickness, Location from the messy string."""
    if not isinstance(variant_str, str):
        return pd.Series([None, None, None, None])
    
    # 1. Extract Thickness (e.g., 3cm, 2cm, 1.2cm)
    thickness = "Unknown"
    thick_match = re.search(r'(\d+(\.\d+)?cm)', variant_str, re.IGNORECASE)
    if thick_match:
        thickness = thick_match.group(1).lower().replace(" ", "")

    # 2. Extract Location code inside () e.g., (VER)
    location = "Unknown"
    loc_match = re.search(r'\((VER|VAN|VIC|CAL|EDM|SAS|WIN|ABB|KEL)\)', variant_str, re.IGNORECASE)
    if loc_match:
        location = loc_match.group(1).upper()

    # 3. Clean up Name
    clean_name = re.sub(r'^15\s-\s', '', variant_str)
    if thick_match:
        clean_name = clean_name.replace(thick_match.group(1), '')
    if loc_match:
        clean_name = clean_name.replace(loc_match.group(0), '')
    
    clean_name = clean_name.strip()
    
    # Simple split for Brand/Color
    parts = clean_name.split(' ', 1)
    brand = parts[0]
    color = parts[1] if len(parts) > 1 else clean_name

    return pd.Series([brand, color, thickness, location])

@st.cache_data
def load_and_clean_data(uploaded_file):
    # 1. Determine File Type & Load
    try:
        # Check file extension
        if uploaded_file.name.lower().endswith('.csv'):
            try:
                df = pd.read_csv(uploaded_file)
            except UnicodeDecodeError:
                uploaded_file.seek(0)
                df = pd.read_csv(uploaded_file, encoding='latin1')
        else:
            # Assume Excel (.xlsx)
            try:
                df = pd.read_excel(uploaded_file)
            except Exception:
                df = pd.read_excel(uploaded_file, header=1)
    except Exception as e:
        return None, f"Error loading file: {e}"

    # 2. Normalize Columns
    df.columns = df.columns.str.strip()
    
    # Verify critical columns exist (Fuzzy match)
    if 'Product Variant' not in df.columns:
        for c in df.columns:
            if isinstance(c, str) and 'Product Variant' in c:
                df.rename(columns={c: 'Product Variant'}, inplace=True)
                break
    
    if 'Product Variant' not in df.columns:
        return None, f"Error: Could not find 'Product Variant' column. Found: {list(df.columns)}"

    # 3. Parse Columns
    df[['Brand', 'Color', 'Thickness', 'Location']] = df['Product Variant'].apply(parse_product_variant)
    
    # 4. Clean Numbers (Handle currency symbols if present)
    for col in ['On Hand Qty', 'Serialized On Hand Cost']:
        found_col = [c for c in df.columns if col in c]
        if found_col:
            actual_col_name = found_col[0]
            df[actual_col_name] = pd.to_numeric(
                df[actual_col_name].astype(str).str.replace(r'[$,]', '', regex=True), 
                errors='coerce'
            )
            df.rename(columns={actual_col_name: col}, inplace=True)

    # 5. Final Filtering & Calc
    if 'On Hand Qty' in df.columns and 'Serialized On Hand Cost' in df.columns:
        df = df[df['On Hand Qty'] > 0] # Remove zero qty
        df['Unit_Cost_Internal'] = df['Serialized On Hand Cost'] / df['On Hand Qty']
        df['Full_Name'] = df['Brand'] + " " + df['Color'] + " (" + df['Thickness'] + ")"
        return df, None
    else:
        return None, "Error: Could not find 'On Hand Qty' or 'Serialized On Hand Cost' columns."

# --- 3. APP UI ---
st.title("🧱 Dead Stock Sales Tool")
st.markdown("Upload your monthly inventory CSV or Excel file to generate quotes.")

# File Uploader
uploaded_file = st.file_uploader("Upload File", type=['csv', 'xlsx'])

if uploaded_file:
    df, error = load_and_clean_data(uploaded_file)
    
    if error:
        st.error(error)
    else:
        # --- FILTERS ---
        col_f1, col_f2, col_f3 = st.columns(3)
        with col_f1:
            locs = ["All"] + sorted(df['Location'].unique().tolist())
            sel_loc = st.selectbox("Filter Location", locs)
        with col_f2:
            thicks = ["All"] + sorted(df['Thickness'].unique().tolist())
            sel_thick = st.selectbox("Filter Thickness", thicks)
        with col_f3:
            search = st.text_input("Search (Name/Color)")

        # Apply Filters
        df_filt = df.copy()
        if sel_loc != "All":
            df_filt = df_filt[df_filt['Location'] == sel_loc]
        if sel_thick != "All":
            df_filt = df_filt[df_filt['Thickness'] == sel_thick]
        if search:
            df_filt = df_filt[df_filt['Full_Name'].str.contains(search, case=False)]

        st.dataframe(df_filt[['Full_Name', 'Location', 'On Hand Qty', 'Unit_Cost_Internal']], use_container_width=True)

        # --- CALCULATOR ---
        st.divider()
        st.subheader("💰 Quote Calculator")
        
        c1, c2 = st.columns([1, 2])
        
        with c1:
            req_sqft = st.number_input("Project Sq Ft (Finished)", min_value=1.0, value=35.0, step=1.0)
            
            # Slab Selector
            slab_options = df_filt['Full_Name'].unique()
            sel_slab = st.selectbox("Select Slab to Quote", slab_options)
        
        if sel_slab:
            # Get slab data
            row = df_filt[df_filt['Full_Name'] == sel_slab].iloc[0]
            unit_cost = row['Unit_Cost_Internal']
            
            # Calculate
            costs = calculate_cost(unit_cost, req_sqft)
            
            # Tax
            subtotal = costs['customer_subtotal']
            tax = subtotal * TAX_RATE
            total = subtotal + tax
            
            with c2:
                # Metrics
                m1, m2, m3 = st.columns(3)
                m1.metric("Material", f"${costs['material_total']:,.2f}")
                m2.metric("Fab/Install", f"${costs['fabrication_total'] + costs['install_total']:,.2f}")
                m3.metric("Total (Inc Tax)", f"${total:,.2f}")
                
                # Internal Info (Hidden)
                with st.expander("🔐 Internal Data (Do not show customer)"):
                    st.write(f"**IB Transfer Cost:** ${costs['ib_transfer_cost']:,.2f}")
                    st.write(f"**Internal Unit Cost:** ${unit_cost:,.2f}/sf")

                # Copy Paste
                email_body = f"""Hi,

I found a great clearance option for your project:
Material: {row['Brand']} {row['Color']}
Thickness: {row['Thickness']}
Location: {row['Location']}

Total Installed Price: ${total:,.2f}
(Based on {req_sqft} sq ft finished area)

Let me know if you'd like to secure this piece."""
                st.text_area("Email Copy", email_body, height=200)

else:
    st.info("👆 Please upload a CSV or Excel file to begin.")
