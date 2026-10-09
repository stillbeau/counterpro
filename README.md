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
| `counterpro/ui.py` | The look: the stylesheet and the HTML for cards, rows, the comparison table. |
| `app.py` | The screen. |
| `.streamlit/config.toml` | Colours and fonts. |

## The screen

**Slabs and quote** has three parts:

- **Project** at the top: finished area, the cutting allowance, the slab material that needs, and sinks.
- **Find a material** on the left: search, location, thickness, brand, price range and sort. Filters in
  use appear as chips that can be removed one at a time; **Reset filters** clears them all. Below that,
  every material that can cover the project, as cards (**Grid**) or compact rows (**List**).
- **Quote** on the right, which stays in view while the list scrolls: up to four materials, customer
  details and the PDF. On a phone it sits below the list, with a bar at the bottom that jumps to it.

**Compare** puts the materials on the quote side by side, with the difference from the lowest price.

The headline figure everywhere is the **estimated installed price**: material, fabrication and
installation for the finished area, before sinks and GST. The cards, the quote panel, the comparison
and the PDF all read it from the same calculation (`price_job` in `counterpro/pricing.py`); none of
them works a price out for itself.

### Slab photos

Moraware holds no photos, so each card shows a plain lettered tile marked "No photo yet". It is a
placeholder and does not imitate the stone. To show real photos, either

- list them in `SLAB_PHOTOS` in `counterpro/config.py`, keyed by the name on the card
  (`"Caesarstone Blizzard": "https://..."`), or
- add an **Image URL** column to the inventory feed.

A photo then appears on the card, in the quote panel, in the comparison and on the PDF.

### Quote wording

The "Included in the price", "Not included" and estimate notes printed on the PDF are the `included`,
`excluded` and `disclaimers` lists in `Branding` in `counterpro/config.py`. Change them there.

## IB calculator

The **IB calculator** tab works out the internal base for any slab and job size. Pick a slab to use
its Moraware cost, or type in a cost per sq ft. It shows material, fabrication, raw cost, IB (and
which rule set it), and what the customer pays on that IB. The rates can be changed there for a
what-if; that never changes the prices in the slab list.

## How a price is built

1. Raw cost = slab cost per sq ft x (finished sq ft x 1.20 waste) + $16/sq ft fabrication.
2. Internal base (IB) = the larger of (material + 5%, plus fabrication) and (raw cost / 0.82).
   With today's numbers the second is always larger, so IB is raw cost at an 18% margin.
3. Customer material and fabrication = IB x 1.15.
4. Add installation at $21/sq ft. This is the **estimated installed price** shown on the cards.
5. Add sinks, then 5% GST, for the total.

Slab cost per sq ft is the total cost of a product's slabs divided by their total area.

## Inventory

Inventory comes from Moraware. The app reads it from a small store, and there are two ways to fill it.

**Automatic: the sync extension.** `extension/` is a Chrome extension for a computer that is signed in
to Moraware. Its options have one block per location (Vernon, Abbotsford, Edmonton, Saskatoon), each
with a tick box and the address of that location's Moraware inventory view; an unticked location is
left out of CounterPro. Once a day (and whenever you press **Sync now**) it opens the ticked views
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
   [inventory_store]
   repo = "your-name/counterpro-data"
   token = "github_pat_..."
   ```

4. On the work computer: open `chrome://extensions`, turn on Developer mode, choose **Load unpacked**
   and pick the `extension` folder. Open the extension's options, enter the same repository and token,
   save, then press **Sync now** in its popup.

Without the `[inventory_store]` secrets the app keeps uploads in a `.counterpro/` folder beside it,
which is fine on a machine you run yourself.

### Other sources

The Google Sheet the app used to read has been retired; nothing reads it now. If the store is ever
empty, the app says so and asks for a sync. For testing, or to run from a file, point the app at a CSV
or a saved Moraware page. These are read only when the store has no inventory:

```
COUNTERPRO_DATA_SOURCES=/path/to/inventory.csv streamlit run app.py
COUNTERPRO_DATA_SOURCES="/path/to/Inventory - Moraware Systemize.html" streamlit run app.py
```

Rows that Moraware lists as 1" x 1" with no cost are placeholders and are left out; the staff
sidebar says how many.

## Staff code (optional)

With no staff code, anyone with the link can use the whole app, including the **Show cost and
margin** switch in the sidebar, and uploading inventory by hand is off (the sync extension keeps it
current). Cost and margin never appear on the PDF or CSV either way.

To lock cost, margin and uploads behind a code, add `staff_code = "..."` to the app's secrets (or set
the `COUNTERPRO_STAFF_CODE` environment variable). Staff then enter it in the sidebar.

## Tests

```
pip install -r requirements-dev.txt
pytest
```

The extension tests run its sync code with Node (skipped when Node is not installed).

The pricing tests include a copy of the original formula and check that every price still matches it.
