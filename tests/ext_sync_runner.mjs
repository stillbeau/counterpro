// Runs the extension's sync logic outside the browser so pytest can check it.
// Usage: node ext_sync_runner.mjs '<settings json>'
import { runSync } from "../extension/sync.js";

const settings = JSON.parse(process.argv[2]);
try {
  const result = await runSync(settings, fetch, new Date(2026, 9, 8, 6, 30, 0));
  console.log(JSON.stringify({ ok: true, ...result }));
} catch (err) {
  console.log(JSON.stringify({ ok: false, name: err.constructor.name, message: err.message }));
}
