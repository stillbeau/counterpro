# CounterPro

Showroom tool for pricing in-stock slabs and printing a customer quote.

Enter the finished square footage and any sinks, browse every slab that can cover the job with its
installed price, add up to four to a quote, and download a PDF that shows them side by side.

## Run it

```
pip install -r requirements.txt
streamlit run app.py
```

## Where things are

| File | What it holds |
| --- | --- |
| `counterpro/config.py` | Rates, markups, GST, the sink price list, branch details, the inventory feed URL. **Change prices here.** |
| `counterpro/pricing.py` | The pricing formula. |
| `counterpro/moraware.py` | Reads a saved Moraware inventory page. |
| `counterpro/inventory.py` | Tidies product names, works out which slabs a job uses. |
| `counterpro/store.py` | Keeps the uploaded inventory between visits. |
| `counterpro/quote.py` | The quote PDF and CSV. |
| `app.py` | The screen. |
| `.streamlit/config.toml` | Colours and fonts. |

## How a price is built

1. Raw cost = slab cost per sq ft x (finished sq ft x 1.20 waste) + $16/sq ft fabrication.
2. Internal base (IB) = the larger of (material + 5%, plus fabrication) and (raw cost / 0.82).
   With today's numbers the second is always larger, so IB is raw cost at an 18% margin.
3. Customer material and fabrication = IB x 1.15.
4. Add installation at $21/sq ft, add sinks, add 5% GST.

Slab cost per sq ft is the total cost of a product's slabs divided by their total area.

## Inventory

Inventory comes from Moraware in one of two ways.

**Uploaded Moraware page (preferred).** In Moraware open the inventory view, save the page
(Ctrl+S, "Webpage, HTML only"), then in the app sidebar unlock with the staff code and drop the file
under **Update from Moraware**. The app shows how many slabs it found and what changes before you
confirm. Everyone using the app sees the new inventory straight away. The view needs the
`Product Variant`, `Serialized On Hand Cost` and `Measurement` columns; `Serial Number` and
`Location` are used when present. Columns can be in any order.

The upload is kept in a `.counterpro/` folder beside the app (set `COUNTERPRO_DATA_DIR` to move it).
On a host that wipes its disk on restart, the app falls back to the feed below until the next upload.

**Spreadsheet feed (fallback).** The published Google Sheet in `counterpro/config.py`, re-read every
60 seconds. Used only when there is no uploaded page. To point at a different CSV, or at a saved
Moraware page on disk:

```
COUNTERPRO_DATA_SOURCES=/path/to/inventory.csv streamlit run app.py
COUNTERPRO_DATA_SOURCES="/path/to/Inventory - Moraware Systemize.html" streamlit run app.py
```

## Staff view

Set a staff code with the `COUNTERPRO_STAFF_CODE` environment variable (or `staff_code` in Streamlit
secrets). In the sidebar, staff enter it to unlock:

- **Show cost and margin**: slab cost, IB and margin in the list and in slab details. These never
  appear on the PDF or CSV.
- **Update from Moraware**: replace the inventory.

Without a staff code, cost and margin are open to anyone who opens the sidebar and uploads are off.

## Tests

```
pip install -r requirements-dev.txt
pytest
```

The pricing tests include a copy of the original formula and check that every price still matches it.
