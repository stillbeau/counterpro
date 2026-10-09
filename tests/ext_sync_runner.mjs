// Runs the extension's sync logic outside the browser so pytest can check it.
// Usage: node ext_sync_runner.mjs '<settings json>'
// settings.renderSuffix, when set, stands in for the "open it in a tab" fallback:
// the rendered page is fetched from the same address with that suffix added.
import { runSync } from "../extension/sync.js";

const settings = JSON.parse(process.argv[2]);
const render = settings.renderSuffix
  ? async (url) => {
      const resp = await fetch(url + settings.renderSuffix);
      return { address: url, html: await resp.text() };
    }
  : null;
try {
  const result = await runSync(settings, fetch, new Date(2026, 9, 8, 6, 30, 0), render);
  console.log(JSON.stringify({ ok: true, ...result }));
} catch (err) {
  console.log(JSON.stringify({ ok: false, name: err.constructor.name, message: err.message }));
}
