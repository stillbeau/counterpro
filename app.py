@st.cache_data
def load_and_clean_data(uploaded_file):
    # 1. Determine File Type & Load
    try:
        # Check file extension
        if uploaded_file.name.lower().endswith('.csv'):
            try:
                df = pd.read_csv(uploaded_file)
            except UnicodeDecodeError:
                # Fallback for older CSV encodings
                uploaded_file.seek(0)
                df = pd.read_csv(uploaded_file, encoding='latin1')
        else:
            # Assume Excel (.xlsx)
            try:
                df = pd.read_excel(uploaded_file)
            except Exception:
                # Fallback if header isn't in row 0
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
            # Clean non-numeric characters
            df[actual_col_name] = pd.to_numeric(
                df[actual_col_name].astype(str).str.replace(r'[$,]', '', regex=True), 
                errors='coerce'
            )
            # Rename to standard name
            df.rename(columns={actual_col_name: col}, inplace=True)

    # 5. Final Filtering & Calc
    if 'On Hand Qty' in df.columns and 'Serialized On Hand Cost' in df.columns:
        df = df[df['On Hand Qty'] > 0] # Remove zero qty
        df['Unit_Cost_Internal'] = df['Serialized On Hand Cost'] / df['On Hand Qty']
        df['Full_Name'] = df['Brand'] + " " + df['Color'] + " (" + df['Thickness'] + ")"
        return df, None
    else:
        return None, "Error: Could not find 'On Hand Qty' or 'Serialized On Hand Cost' columns."
