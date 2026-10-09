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
| `counterpro/store.py` | Keeps the Moraware inventory (GitHub repository or local folder). |
| `extension/` | Chrome extension that syncs Moraware inventory to the store each day. |
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

Inventory comes from Moraware. The app reads it from a small store, and there are two ways to fill it.

**Automatic: the sync extension.** `extension/` is a Chrome extension for a computer that is signed in
to Moraware. Once a day (and whenever you press **Sync now**) it opens the Moraware inventory views
with the sign-in already in that browser, keeps only the slab table, and saves it to the store. No
Moraware password is stored anywhere. If Moraware is signed out, or a view comes back empty, nothing
is sent and the previous inventory stays in place.

It first asks Moraware for the page directly. If the slab table is not in what comes back (Moraware
draws it in the browser), the extension opens the view in a background tab for a few seconds, reads
the finished page, and closes the tab. A failed sync says which view failed and what came back.

**By hand: upload a saved page.** In Moraware open the inventory view, save the page (Ctrl+S,
"Webpage, HTML only"), then in the app sidebar unlock with the staff code and drop the file under
**Update from Moraware**. The app shows how many slabs it found and what changes before you confirm.

Either way the view needs the `Product Variant`, `Serialized On Hand Cost` and `Measurement` columns;
`Serial Number` and `Location` are used when present. Columns can be in any order.

To find the oldest stock, add a date column to the Moraware view (any heading with "date" or
"received" in it). The app then shows how long each slab has been in stock and adds an
**Oldest stock first** sort.

### The store

On Streamlit Community Cloud the app's disk is wiped on every restart, so the inventory is kept in a
private GitHub repository instead.

1. Create a **private** repository, for example `counterpro-data`, with a README so it has a first commit.
2. Create a fine-grained personal access token limited to that one repository, with repository
   permission **Contents: Read and write**.
3. In the Streamlit app's settings, under Secrets, add (see `.streamlit/secrets.toml.example`):

   ```toml
   staff_code = "pick-a-code"

   [inventory_store]
   repo = "your-name/counterpro-data"
   token = "github_pat_..."
   ```

4. On the work computer: open `chrome://extensions`, turn on Developer mode, choose **Load unpacked**
   and pick the `extension` folder. Open the extension's options, enter the same repository and token,
   save, then press **Sync now** in its popup.

Without the `[inventory_store]` secrets the app keeps uploads in a `.counterpro/` folder beside it,
which is fine on a machine you run yourself.

### Fallback feed

Until the store has inventory in it, the app reads the published Google Sheet in
`counterpro/config.py` (re-read every 60 seconds). Remove that address once the sync is running to
drop the sheet completely. To point at a different CSV, or a saved Moraware page on disk:

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

The extension tests run its sync code with Node (skipped when Node is not installed).

The pricing tests include a copy of the original formula and check that every price still matches it.
