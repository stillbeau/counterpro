// Fetch the Moraware inventory views and send them to the CounterPro store.
// No browser-extension APIs in this file, so it can be tested on its own.

export const DEFAULTS = {
  views: [
    "https://floformcountertops.moraware.net/sys/inventory?&view=14938",
    "https://floformcountertops.moraware.net/sys/inventory?&view=0&prod=F1017&sort=a0&cols=SN6,SN1,PN1,PN2,PN3,PN4,SN8,SN3,SN5,SN9,SN7&pageSize=9999&filter=1,&mrv=14938",
  ],
  repo: "stillbeau/counterpro-data",
  token: "",
  path: "moraware_inventory.json",
  branch: "",
  apiUrl: "https://api.github.com",
  time: "08:30",
};

export class SyncError extends Error {}

const SIGNED_OUT = "Moraware asked for a sign-in. Sign in to Moraware in this Chrome profile, then sync again.";
const COST_HEADING = /serialized on hand cost/gi;

// Moraware pages a long list unless asked for everything.
export function withFullPage(url) {
  return /[?&]pagesize=/i.test(url) ? url : url + (url.includes("?") ? "&" : "?") + "pagesize=9999";
}

// The slab table is whichever table carries the inventory headings. It is found
// by its headings rather than by an id, because the page Moraware sends and the
// page the browser ends up showing do not name it the same way.
export function findInventoryTable(html) {
  if (!html) return "";
  const lower = html.toLowerCase();
  let best = "";
  let bestRows = -1;
  for (const m of html.matchAll(COST_HEADING)) {
    const start = lower.lastIndexOf("<table", m.index);
    const end = lower.indexOf("</table>", m.index);
    if (start < 0 || end < 0) continue;
    const table = html.slice(start, end + "</table>".length);
    if (!/product variant/i.test(table)) continue;
    const rows = (table.match(/<tr\b/gi) || []).length;
    if (rows > bestRows) { best = table; bestRows = rows; }
  }
  return best;
}

export function looksLikeInventory(html) {
  return findInventoryTable(html) !== "";
}

export function looksLikeSignIn(html) {
  return /type\s*=\s*["']?password/i.test(html || "");
}

export function countSlabs(html) {
  const table = findInventoryTable(html);
  const rows = (table.match(/<tr\b/gi) || []).length;
  const headingRows = (table.match(COST_HEADING) || []).length;
  return Math.max(rows - headingRows, 0);
}

function infoTables(html) {
  return html.match(/<table[^>]*pageInfoCenteredJustifiedTable[\s\S]*?<\/table>/gi) || [];
}

// Keep only what CounterPro reads: the filter description and the slab table,
// with links, styles and scripts removed. Nothing else on the page is sent.
export function trimPage(html) {
  const strip = (part, keepClass) => part
    .replace(/<colgroup[\s\S]*?<\/colgroup>/gi, "")
    .replace(/<script[\s\S]*?<\/script>/gi, "")
    .replace(/<\/?(?:a|span|div|i|b|font|nobr|img|input)\b[^>]*>/gi, "")
    .replace(/<(table|thead|tbody|tr|td|th)\b[^>]*>/gi, (tag, name) =>
      keepClass && name.toLowerCase() === "table" ? '<table class="pageInfoCenteredJustifiedTable">' : `<${name.toLowerCase()}>`)
    .replace(/<\/(table|thead|tbody|tr|td|th)\s*>/gi, (tag, name) => `</${name.toLowerCase()}>`)
    .replace(/[-]/g, "")
    .replace(/\s+/g, " ");
  return "<title>Inventory - Moraware Systemize</title>\n"
    + infoTables(html).map((part) => strip(part, true)).join("\n") + "\n"
    + strip(findInventoryTable(html), false);
}

// "15 - Stone & Quartz (VER)" from the page's own filter description.
export function pageName(html, url) {
  const m = infoTables(html).join(" ").match(/Product:\s*<\/td>\s*<td[^>]*>([^<]+)<\/td>/i);
  return m ? m[1].replace(/&amp;/g, "&").trim() : url;
}

// A short, cost-free description of a page, so a failed sync can say what came back.
export function describePage(html, address) {
  const text = html || "";
  const title = (text.match(/<title[^>]*>([^<]*)<\/title>/i) || [, ""])[1].trim().slice(0, 60);
  const ids = [...text.matchAll(/<table\b[^>]*\bid\s*=\s*["']?([\w-]+)/gi)].map((m) => m[1]).slice(0, 8);
  let path = address || "";
  try { path = new URL(address).pathname; } catch { /* keep as given */ }
  return `page "${title || "untitled"}" at ${path || "unknown address"}, ${Math.round(text.length / 1024)} KB, `
    + `${(text.match(/<table\b/gi) || []).length} tables`
    + (ids.length ? ` (${ids.join(", ")})` : "")
    + `, headings ${/product variant/i.test(text) ? "found" : "missing"}`;
}

// Read the page with the character set Moraware declares, so the "×" in slab
// sizes survives even when the page is not UTF-8.
async function readText(resp) {
  const bytes = await resp.arrayBuffer();
  const declared = (/charset=["']?([\w-]+)/i.exec(resp.headers.get("content-type") || "") || [])[1];
  const decode = (label) => { try { return new TextDecoder(label).decode(bytes); } catch { return null; } };
  let text = (declared && decode(declared)) || decode("utf-8");
  if (!declared) {
    const meta = (/<meta[^>]+charset\s*=\s*["']?([\w-]+)/i.exec(text.slice(0, 4000)) || [])[1];
    if (meta && meta.toLowerCase() !== "utf-8") text = decode(meta) || text;
  }
  return text;
}

async function fetchPage(url, fetchImpl) {
  let resp;
  try {
    resp = await fetchImpl(url, { credentials: "include", cache: "no-store", redirect: "follow" });
  } catch (err) {
    throw new SyncError(`Moraware could not be reached (${err.message}).`);
  }
  if (!resp.ok) throw new SyncError(`Moraware answered ${resp.status} for ${url}.`);
  return { html: await readText(resp), address: resp.url || url };
}

// `render`, when given, opens the address in a real tab and returns the page as
// the browser shows it. It is the fallback for when the page Moraware sends does
// not contain the table yet (it is put together by the page's own script).
export async function fetchView(url, fetchImpl = fetch, render = null) {
  const full = withFullPage(url);
  let page = await fetchPage(full, fetchImpl);
  let how = "direct";
  if (!looksLikeInventory(page.html) && render) {
    const rendered = await render(full);
    if (rendered && rendered.html) { page = { html: rendered.html, address: rendered.address || full }; how = "tab"; }
  }
  if (!looksLikeInventory(page.html)) {
    if (looksLikeSignIn(page.html)) throw new SyncError(SIGNED_OUT);
    throw new SyncError("Moraware returned a page with no inventory table. Got " + describePage(page.html, page.address) + ".");
  }
  const slabs = countSlabs(page.html);
  if (!slabs) throw new SyncError(`A view came back with no slabs, so nothing was sent: ${url}`);
  return { url, name: pageName(page.html, url), slabs, how, html: trimPage(page.html) };
}

export function localIso(d) {
  const p = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
}

export function buildDocument(pages, now = new Date()) {
  return JSON.stringify({
    saved_at: localIso(now),
    source: "extension",
    files: pages.map((p) => p.name),
    pages: pages.map(({ name, url, html }) => ({ name, url, html })),
  });
}

function toBase64(text) {
  const bytes = new TextEncoder().encode(text);
  let binary = "";
  for (let i = 0; i < bytes.length; i += 0x8000) binary += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  return btoa(binary);
}

function explain(status, repo) {
  return {
    401: "GitHub rejected the token; it may have expired.",
    403: "The token is not allowed to write; it needs Contents read and write on the repository.",
    404: `The repository ${repo} was not found, or the token cannot see it.`,
    409: "The file changed at the same moment; sync again.",
  }[status] || `GitHub answered ${status}.`;
}

export async function pushToGitHub(settings, text, slabs, fetchImpl = fetch) {
  const repo = settings.repo.trim().replace(/^\/+|\/+$/g, "");
  const base = `${(settings.apiUrl || DEFAULTS.apiUrl).replace(/\/+$/, "")}/repos/${repo}/contents/${settings.path || DEFAULTS.path}`;
  const headers = {
    Authorization: `Bearer ${settings.token.trim()}`,
    Accept: "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
  };
  const ref = settings.branch ? `?ref=${encodeURIComponent(settings.branch)}` : "";
  let existing;
  try {
    existing = await fetchImpl(base + ref, { headers, cache: "no-store" });
  } catch (err) {
    throw new SyncError(`GitHub could not be reached (${err.message}).`);
  }
  let sha;
  if (existing.status === 200) sha = (await existing.json()).sha;
  else if (existing.status !== 404) throw new SyncError(explain(existing.status, repo));

  const body = { message: `Update slab inventory (${slabs} slabs)`, content: toBase64(text) };
  if (sha) body.sha = sha;
  if (settings.branch) body.branch = settings.branch;
  const put = await fetchImpl(base, { method: "PUT", headers: { ...headers, "Content-Type": "application/json" }, body: JSON.stringify(body) });
  if (put.status !== 200 && put.status !== 201) throw new SyncError(explain(put.status, repo));
}

// All or nothing: if any view fails, the stored inventory is left as it was,
// so one bad page can never wipe a location's slabs from CounterPro.
export async function runSync(settings, fetchImpl = fetch, now = new Date(), render = null) {
  const views = (settings.views || []).map((v) => v.trim()).filter(Boolean);
  if (!views.length) throw new SyncError("No Moraware views are set. Add at least one in the options.");
  if (!settings.repo) throw new SyncError("The GitHub repository is not set. Add it in the options.");
  if (!settings.token) throw new SyncError("The GitHub token is not set. Paste it in the options.");
  const pages = [];
  for (const [i, url] of views.entries()) {
    try {
      pages.push(await fetchView(url, fetchImpl, render));
    } catch (err) {
      throw new SyncError(`View ${i + 1} of ${views.length}: ${err.message}`);
    }
  }
  const slabs = pages.reduce((n, p) => n + p.slabs, 0);
  await pushToGitHub(settings, buildDocument(pages, now), slabs, fetchImpl);
  return { slabs, savedAt: localIso(now), pages: pages.map(({ name, slabs, how }) => ({ name, slabs, how })) };
}
