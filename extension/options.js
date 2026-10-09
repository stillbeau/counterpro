import { DEFAULTS, LOCATIONS, normalizeSettings } from "./sync.js";

const form = document.getElementById("form");
const places = document.getElementById("places");
const saved = document.getElementById("saved");
const field = (id) => document.getElementById(id);

// One block per location: a tick box with the location's name, its address, and
// what the last sync found there.
for (const place of LOCATIONS) {
  const block = document.createElement("fieldset");
  block.className = "place";
  block.innerHTML = `
    <label class="tick" for="on-${place.key}"><input type="checkbox" id="on-${place.key}"> ${place.name}</label>
    <label class="quiet" for="url-${place.key}">Moraware inventory address for ${place.name}</label>
    <input type="url" id="url-${place.key}" spellcheck="false" autocomplete="off"
           placeholder="https://…moraware.net/sys/inventory?…">
    <p class="small" id="last-${place.key}"></p>`;
  places.append(block);
}

function showLast(status) {
  for (const place of LOCATIONS) {
    const line = field(`last-${place.key}`);
    const page = status && status.ok && (status.pages || []).find((p) => p.location === place.name);
    line.className = "small";
    if (!page) { line.textContent = ""; continue; }
    line.textContent = `Last sync: ${page.slabs} slabs from "${page.name}".`;
    if (page.holds && page.holds !== place.name) {
      line.className = "small problem";
      line.textContent += ` Check this address: it returned ${page.holds} stock.`;
    }
  }
}

async function load() {
  const stored = await chrome.storage.local.get(["settings", "status"]);
  const s = normalizeSettings(stored.settings);
  for (const place of s.locations) {
    field(`on-${place.key}`).checked = place.enabled;
    field(`url-${place.key}`).value = place.url;
  }
  field("repo").value = s.repo;
  field("token").value = s.token;
  field("time").value = s.time;
  showLast(stored.status);
}

function say(text, problem = false) {
  saved.textContent = text;
  saved.className = problem ? "problem" : "";
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const locations = LOCATIONS.map((place) => ({
    key: place.key,
    enabled: field(`on-${place.key}`).checked,
    url: field(`url-${place.key}`).value.trim(),
  }));
  const empty = locations.find((l) => l.enabled && !l.url);
  if (empty) {
    const name = LOCATIONS.find((l) => l.key === empty.key).name;
    say(`Not saved. ${name} is ticked but has no address. Paste its address or untick it.`, true);
    field(`url-${empty.key}`).focus();
    return;
  }
  const bad = locations.find((l) => l.url && !/^https?:\/\//i.test(l.url));
  if (bad) {
    const name = LOCATIONS.find((l) => l.key === bad.key).name;
    say(`Not saved. The ${name} address should start with https://`, true);
    field(`url-${bad.key}`).focus();
    return;
  }
  const { settings } = await chrome.storage.local.get("settings");
  const next = {
    ...normalizeSettings(settings),
    locations,
    repo: field("repo").value.trim(),
    token: field("token").value.trim(),
    time: field("time").value || DEFAULTS.time,
  };
  await chrome.storage.local.set({ settings: next });
  const on = locations.filter((l) => l.enabled).length;
  say(`Saved. ${on} of ${locations.length} locations will sync.`);
});

load();
