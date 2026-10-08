import { DEFAULTS } from "./sync.js";

const form = document.getElementById("form");
const field = (id) => document.getElementById(id);

async function load() {
  const { settings } = await chrome.storage.local.get("settings");
  const s = { ...DEFAULTS, ...(settings || {}) };
  field("views").value = s.views.join("\n");
  field("repo").value = s.repo;
  field("token").value = s.token;
  field("time").value = s.time;
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const { settings } = await chrome.storage.local.get("settings");
  await chrome.storage.local.set({
    settings: {
      ...DEFAULTS,
      ...(settings || {}),
      views: field("views").value.split("\n").map((v) => v.trim()).filter(Boolean),
      repo: field("repo").value.trim(),
      token: field("token").value.trim(),
      time: field("time").value || DEFAULTS.time,
    },
  });
  field("saved").textContent = "Saved.";
  setTimeout(() => { field("saved").textContent = ""; }, 2500);
});

load();
