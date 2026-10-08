import { DEFAULTS, runSync } from "./sync.js";

const ALARM = "counterpro-daily";
const CATCH_UP_HOURS = 20;

async function getSettings() {
  const { settings } = await chrome.storage.local.get("settings");
  return { ...DEFAULTS, ...(settings || {}) };
}

// Next time the clock reads the chosen time, then every 24 hours.
async function schedule() {
  const { time } = await getSettings();
  const [h, m] = (time || DEFAULTS.time).split(":").map(Number);
  const when = new Date();
  when.setHours(h || 0, m || 0, 0, 0);
  if (when <= new Date()) when.setDate(when.getDate() + 1);
  await chrome.alarms.create(ALARM, { when: when.getTime(), periodInMinutes: 24 * 60 });
}

let running = null;

function sync(reason) {
  if (!running) running = doSync(reason).finally(() => { running = null; });
  return running;
}

async function doSync(reason) {
  const at = new Date().toISOString();
  let status;
  try {
    const result = await runSync(await getSettings());
    status = { ok: true, at, reason, ...result };
    await chrome.storage.local.set({ lastSuccess: at });
    await chrome.action.setBadgeText({ text: "" });
  } catch (err) {
    status = { ok: false, at, reason, message: err.message || String(err) };
    await chrome.action.setBadgeBackgroundColor({ color: "#B3261E" });
    await chrome.action.setBadgeText({ text: "!" });
  }
  await chrome.storage.local.set({ status });
  return status;
}

async function catchUp() {
  await schedule();
  const { lastSuccess } = await chrome.storage.local.get("lastSuccess");
  const settings = await getSettings();
  const stale = !lastSuccess || Date.now() - new Date(lastSuccess).getTime() > CATCH_UP_HOURS * 3600 * 1000;
  if (stale && settings.repo && settings.token) await sync("catch-up");
}

chrome.runtime.onInstalled.addListener(() => { schedule(); });
chrome.runtime.onStartup.addListener(() => { catchUp(); });
chrome.alarms.onAlarm.addListener((alarm) => { if (alarm.name === ALARM) sync("daily"); });
chrome.storage.onChanged.addListener((changes, area) => { if (area === "local" && changes.settings) schedule(); });
chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message && message.type === "sync-now") {
    sync("manual").then(sendResponse);
    return true;      // answer arrives later
  }
  return false;
});
