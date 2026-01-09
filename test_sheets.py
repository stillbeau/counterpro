import pandas as pd

# DATA SOURCES
DATA_SOURCES = [
    "https://docs.google.com/spreadsheets/d/e/2PACX-1vSkoSeMuPGqr5-JEBhHO5l0fFYlkfmbMUW-VU8UZEpR0pd4lSeyK74WHE47m1zYMg/pub?output=csv"
]

all_dfs = []
for idx, url in enumerate(DATA_SOURCES, 1):
    try:
        print(f"\n{'='*60}")
        print(f"SHEET {idx}")
        print(f"{'='*60}")

        df = pd.read_csv(url)
        df.columns = df.columns.str.strip()

        print(f"\nTotal rows: {len(df)}")
        print(f"\nColumn names: {df.columns.tolist()}")

        # Check for location columns
        location_cols = [col for col in df.columns if any(x in col.lower() for x in ['location', 'warehouse', 'store', 'site'])]
        if location_cols:
            print(f"\nLocation column found: '{location_cols[0]}'")
            print("\nLocation breakdown:")
            print(df[location_cols[0]].value_counts())

        # Check stock
        if 'On Hand Qty' in df.columns:
            df['On Hand Qty'] = pd.to_numeric(df['On Hand Qty'].astype(str).str.replace(r'[$,]', '', regex=True), errors='coerce')
            with_stock = df[df['On Hand Qty'] > 0]
            print(f"\nRows with stock (Qty > 0): {len(with_stock)}")

            if location_cols and len(with_stock) > 0:
                print(f"\nStock by location:")
                print(with_stock[location_cols[0]].value_counts())

            if 'Product Variant' in df.columns and len(with_stock) > 0:
                print(f"\nSample products with stock:")
                for product in with_stock['Product Variant'].head(5):
                    print(f"  • {product}")

        all_dfs.append(df)

    except Exception as e:
        print(f"Error loading Sheet {idx}: {e}")

if all_dfs:
    combined = pd.concat(all_dfs, ignore_index=True)
    combined['On Hand Qty'] = pd.to_numeric(combined['On Hand Qty'].astype(str).str.replace(r'[$,]', '', regex=True), errors='coerce')
    combined_stock = combined[combined['On Hand Qty'] > 0]

    print(f"\n{'='*60}")
    print(f"COMBINED DATA")
    print(f"{'='*60}")
    print(f"Total rows with stock: {len(combined_stock)}")

    # Check for location in combined data
    location_cols = [col for col in combined.columns if any(x in col.lower() for x in ['location', 'warehouse', 'store', 'site'])]
    if location_cols:
        print(f"\nCombined stock by location:")
        print(combined_stock[location_cols[0]].value_counts())
