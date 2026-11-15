// ---- Diagnostics screen: the facts a friend texts to whoever set the app up ----------------------
const DIAG = {data: null, note: null, sig: ""};
async function diagLoad() {
  try { DIAG.data = await getJson("api/diagnostics"); DIAG.note = null; }
  catch (e) { DIAG.note = "Couldn't load: " + e.message; }
  const sig = JSON.stringify([DIAG.data, DIAG.note]);
  if (sig !== DIAG.sig) { DIAG.sig = sig; diagDraw(); }
}
// Plain http on a LAN address has no navigator.clipboard: select the text so it can be copied by hand.
async function diagCopy(text, area) {
  try { await navigator.clipboard.writeText(text); return "Copied. Paste it into a text message."; }
  catch (e) { area.focus(); area.select(); return "Select all and copy (Ctrl+C / Cmd+C)."; }
}
function diagDraw() {
  const d = DIAG.data, body = $("diagnostics-body");
  if (!d) { body.replaceChildren(el("p", DIAG.note || "Loading…", "muted")); return; }
  const w = d.watcher;
  const rows = [
    row("Version", d.version), row("Mode", d.mode + (d.practice ? " (practice on)" : "")),
    row("Computer", `${d.platform}, Python ${d.python}`),
    row("Running for", `${Math.round((d.uptime_s || 0) / 60)} min`),
    row("ESPN, last good answer", w.last_ok_at ? fmt(w.last_ok_at) : "never", w.last_ok_at ? "ok" : "warn"),
    row("ESPN errors", String(w.errors) + (w.last_error ? ` (${w.last_error})` : ""), w.errors ? "warn" : "ok"),
    row("Last score", d.last_event ? `${d.last_event.game} ${d.last_event.label}, ${d.last_event.status}` : "none yet"),
    row("Settings file", d.config_path || "–"), row("Database", d.db_path),
  ];
  d.bulbs.forEach((b) => rows.push(row(`Bulb ${b.name} (${b.kind} ${b.ip})`,
    b.reachable ? `answers, ${b.ping_ms} ms` : "not answering", b.reachable ? "ok" : "bad")));
  if (!d.bulbs.length) rows.push(row("Bulbs", "none added yet", "warn"));
  const area = el("textarea"); area.readOnly = true; area.rows = 8; area.value = d.bundle;
  area.setAttribute("aria-label", "Diagnostics text");
  const note = el("span", "", "muted");
  const btn = el("button", "Copy for text message", "primary"); btn.type = "button";
  btn.addEventListener("click", async () => { note.textContent = await diagCopy(d.bundle, area); });
  const ul = el("ul", undefined, "list"); ul.append(...rows);
  const bar = el("div"); bar.append(btn, " ", note);
  body.replaceChildren(ul, el("h3", "Text to send"), area, bar);
}
