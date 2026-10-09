const state = document.getElementById("state");
const pages = document.getElementById("pages");
const button = document.getElementById("sync");
const next = document.getElementById("next");

function when(iso) {
  return new Date(iso).toLocaleString([], { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
}

function show(status) {
  pages.replaceChildren();
  state.className = "";
  if (!status) {
    state.textContent = "Not synced yet.";
    return;
  }
  if (status.ok) {
    state.textContent = `Sent ${status.slabs} slabs on ${when(status.at)}.`;
    for (const page of status.pages || []) {
      const li = document.createElement("li");
      li.textContent = `${page.location || page.name}: ${page.slabs} slabs`;
      pages.append(li);
    }
  } else {
    state.className = "problem";
    state.textContent = `Not sent on ${when(status.at)}. ${status.message}`;
  }
}

async function load() {
  const { status } = await chrome.storage.local.get("status");
  show(status);
  const alarm = await chrome.alarms.get("counterpro-daily");
  next.textContent = alarm ? `Next automatic sync ${when(new Date(alarm.scheduledTime).toISOString())}.` : "";
}

button.addEventListener("click", async () => {
  button.disabled = true;
  button.textContent = "Syncing…";
  show(await chrome.runtime.sendMessage({ type: "sync-now" }));
  button.disabled = false;
  button.textContent = "Sync now";
});

load();
