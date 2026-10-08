// Fetch the Moraware inventory views and send them to the CounterPro store.
// No browser-extension APIs in this file, so it can be tested on its own.

export const DEFAULTS = {
  views: [
    "https://floformcountertops.moraware.net/sys/inventory?&view=14938",
    "https://floformcountertops.moraware.net/sys/inventory?&view=0&prod=F1017&sort=a0&cols=SN6,SN1,PN1,PN2,PN3,PN4,SN8,SN3,SN5,SN9,SN7&pageSize=9999&filter=1,&mrv=14938",
  ],
  repo: "",
  token: "",
  path: "moraware_inventory.json",
  branch: "",
  apiUrl: "https://api.github.com",
  time: "08:30",
};

export class SyncError extends Error {}

const SIGNED_OUT = "Moraware did not return the inventory page. Sign in to Moraware in this browser, then sync again.";

// Moraware pages a long list unless asked for everything.
export function withFullPage(url) {
  return /[?&]pagesize=/i.test(url) ? url : url + (url.includes("?") ? "&" : "?") + "pagesize=9999";
}

export function looksLikeInventory(html) {
  return html.includes('id="ProductsBody"') && html.includes("Product Variant") && html.includes("Serialized On Hand Cost");
}

function bodyTable(html) {
  const marker = html.indexOf('id="ProductsBody"');
  if (marker < 0) return "";
  const start = html.lastIndexOf("<table", marker);
  const end = html.indexOf("</table>", marker);
  return start < 0 || end < 0 ? "" : html.slice(start, end + "</table>".length);
}

export function countSlabs(html) {
  return (bodyTable(html).match(/<tr[^>]*class="(?:oddRow|evenRow)"/g) || []).length;
}

// Keep only what CounterPro reads: the filter description and the slab table,
// with links, styles and scripts removed. Nothing else on the page is sent.
export function trimPage(html) {
  const info = html.match(/<table[^>]*pageInfoCenteredJustifiedTable[\s\S]*?<\/table>/g) || [];
  const strip = (part, keepClass) => part
    .replace(/<colgroup[\s\S]*?<\/colgroup>/g, "")
    .replace(/<\/?(?:a|span|div|i|b|font)\b[^>]*>/g, "")
    .replace(/<(table|thead|tbody|tr|td|th)\b[^>]*>/g, (tag, name) =>
      keepClass && name === "table" ? '<table class="pageInfoCenteredJustifiedTable">' : `<${name}>`)
    .replace(/[-]/g, "")
    .replace(/\s+/g, " ");
  return "<title>Inventory - Moraware Systemize</title>\n"
    + info.map((part) => strip(part, true)).join("\n") + "\n"
    + strip(bodyTable(html), false);
}

// "15 - Stone & Quartz (VER)" from the page's own filter description.
export function pageName(html, url) {
  const info = (html.match(/<table[^>]*pageInfoCenteredJustifiedTable[\s\S]*?<\/table>/g) || []).join(" ");
  const m = info.match(/Product:\s*<\/td>\s*<td[^>]*>([^<]+)<\/td>/);
  return m ? m[1].replace(/&amp;/g, "&").trim() : url;
}

export async function fetchView(url, fetchImpl = fetch) {
  let resp;
  try {
    resp = await fetchImpl(withFullPage(url), { credentials: "include", cache: "no-store", redirect: "follow" });
  } catch (err) {
    throw new SyncError(`Moraware could not be reached (${err.message}).`);
  }
  if (!resp.ok) throw new SyncError(`Moraware answered ${resp.status} for ${url}.`);
  const html = await resp.text();
  if (!looksLikeInventory(html)) throw new SyncError(SIGNED_OUT);
  const slabs = countSlabs(html);
  if (!slabs) throw new SyncError(`A view came back with no slabs, so nothing was sent: ${url}`);
  return { url, name: pageName(html, url), slabs, html: trimPage(html) };
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
export async function runSync(settings, fetchImpl = fetch, now = new Date()) {
  const views = (settings.views || []).map((v) => v.trim()).filter(Boolean);
  if (!views.length) throw new SyncError("No Moraware views are set. Add at least one in the options.");
  if (!settings.repo || !settings.token) throw new SyncError("The GitHub repository and token are not set. Add them in the options.");
  const pages = [];
  for (const url of views) pages.push(await fetchView(url, fetchImpl));
  const slabs = pages.reduce((n, p) => n + p.slabs, 0);
  await pushToGitHub(settings, buildDocument(pages, now), slabs, fetchImpl);
  return { slabs, savedAt: localIso(now), pages: pages.map(({ name, slabs }) => ({ name, slabs })) };
}
