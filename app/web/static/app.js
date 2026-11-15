// Everything from the server is inserted with textContent, never as HTML.
const $ = (id) => document.getElementById(id);
const fmt = (iso) => iso ? new Date(iso).toLocaleString([], {month: "short", day: "numeric", hour: "numeric", minute: "2-digit", second: "2-digit"}) : "–";
const ago = (iso, now) => { if (!iso) return "never"; const s = Math.round((new Date(now) - new Date(iso)) / 1000);
  return s < 90 ? s + "s ago" : s < 5400 ? Math.round(s / 60) + " min ago" : Math.round(s / 3600) + " h ago"; };
function el(tag, text, cls) { const e = document.createElement(tag); if (text !== undefined) e.textContent = text; if (cls) e.className = cls; return e; }
function row(left, right, rightCls) { const li = el("li"); li.append(el("span", left), el("span", right, rightCls)); return li; }
function fill(id, items, emptyText) { const u = $(id); u.replaceChildren(...(items.length ? items : [el("li", emptyText, "empty")])); }
const statusCls = { fired: "ok", dry_run: "warn", failed: "bad", skipped_restart: "warn", pending: "warn", no_lights: "warn" };

// Pulse-button state lives outside render() so it survives the 10 s refresh.
let lastStatus = null; const busy = {}; const notes = {}; let bulbsSig = "";
function renderBulbs() {
  const s = lastStatus; if (!s) return;
  const dry = s.mode !== "live";
  // Skip identical re-renders so a refresh never steals focus or hover from the button.
  const sig = JSON.stringify([dry, s.bulbs, busy, Object.fromEntries(Object.entries(notes).map(([k, v]) => [k, v.text]))]);
  if (sig === bulbsSig) return;
  bulbsSig = sig;
  fill("bulbs", s.bulbs.map((b) => {
    const li = el("li", undefined, "bulb");
    const right = el("span", undefined, "bulb-right");
    right.append(el("span", b.ping_ms === null ? "unreachable" : `${b.ping_ms} ms`, b.ping_ms === null ? "bad" : "ok"));
    const btn = el("button", busy[b.name] ? "Pulsing…" : (dry ? "Pulse (dry-run)" : "Pulse"));
    btn.type = "button"; btn.disabled = !!busy[b.name];
    btn.title = dry ? "Dry-run mode: runs the pulse without sending anything to the bulb" : "Flash this bulb with its team pattern, then restore it";
    btn.addEventListener("click", () => pulse(b.name));
    right.append(btn);
    li.append(el("span", `${b.name} (${b.ip})`), right);
    if (notes[b.name]) li.append(el("div", notes[b.name].text, "note " + notes[b.name].cls));
    return li;
  }), "No bulbs configured.");
}
async function pulse(name) {
  busy[name] = true; delete notes[name]; renderBulbs(); renderEffectTest(); bulbsRefresh();
  let note;
  try {
    const r = await fetch(`api/bulbs/${encodeURIComponent(name)}/pulse`, {method: "POST", headers: {"X-Gameday": "1"}});
    const body = await r.json().catch(() => ({}));
    note = r.ok ? {text: body.dry_run ? "Dry-run: nothing was sent to the bulb." : `Pulse done (${body.duration_s}s).`, cls: "ok"}
               : {text: body.detail || `HTTP ${r.status}`, cls: "bad"};
  } catch (e) { note = {text: "Request failed: " + e.message, cls: "bad"}; }
  busy[name] = false; notes[name] = note; renderBulbs(); renderEffectTest(); bulbsRefresh();
  setTimeout(() => { if (notes[name] === note) { delete notes[name]; renderBulbs(); renderEffectTest(); bulbsRefresh(); } }, 8000);
}

// Schedule: every game for every followed team, one row per team's schedule (a game between two
// followed teams appears on both). Finished = final score and W/L, live = running score,
// upcoming = day and time. Re-rendered only when something changes so the scroll position stays put.
const dayOf = (iso) => new Date(iso).toLocaleDateString([], {weekday: "short", month: "short", day: "numeric"});
const timeOf = (iso) => new Date(iso).toLocaleTimeString([], {hour: "numeric", minute: "2-digit"});
let scheduleSig = "", scheduleFilter = "all", filterLoaded = false, lastSchedule = null, lastTeams = [];
let aimAtNext = true;  // scroll to the next game on first load and when the filter changes, not on data refreshes
function loadFilter() {
  if (filterLoaded) return; filterLoaded = true;
  try { scheduleFilter = localStorage.getItem("gl-sched-filter") || "all"; } catch (e) { /* storage blocked: fine */ }
}
function setFilter(key) {
  scheduleFilter = key;
  try { localStorage.setItem("gl-sched-filter", key); } catch (e) { /* ignore */ }
  scheduleSig = ""; aimAtNext = true;
  renderSchedule(lastSchedule, lastTeams);
}
function renderFilter(teams) {
  const bar = $("sched-filter"), multi = teams.length > 1;
  bar.hidden = !multi; $("sched-table").classList.toggle("single", !multi);
  if (!multi) return;
  const items = [{key: "all", label: "All teams"}, ...teams];
  bar.replaceChildren(...items.map((t) => {
    const b = el("button", t.label); b.type = "button";
    b.setAttribute("aria-pressed", String(scheduleFilter === t.key));
    b.addEventListener("click", () => setFilter(t.key));
    return b;
  }));
}
function renderSchedule(games, teams) {
  lastSchedule = games; lastTeams = teams; loadFilter();
  const multi = teams.length > 1;
  if (!multi || (scheduleFilter !== "all" && !teams.some((t) => t.key === scheduleFilter))) scheduleFilter = "all";
  const sig = JSON.stringify([games, teams.map((t) => t.key), scheduleFilter]);
  $("no-schedule").hidden = games.length > 0;
  if (sig === scheduleSig) return;
  scheduleSig = sig;
  renderFilter(teams);
  const byKey = Object.fromEntries(teams.map((t) => [t.key, t]));
  const shown = games.filter((g) => scheduleFilter === "all" || g.team_key === scheduleFilter);
  const nextSeen = new Set(); let firstNext = null;
  $("schedule").replaceChildren(...shown.map((g) => {
    const tr = el("tr");
    const game = g.us ? `${g.home ? "vs" : "@"} ${g.opp}` : g.name;
    let result, cls = "";
    if (g.status === "post" && g.result) { result = `${g.result} ${g.us_score}–${g.opp_score}`; cls = g.result === "W" ? "ok" : g.result === "L" ? "bad" : ""; }
    else if (g.status === "post") { result = "Final"; }
    else if (g.status === "in") { result = g.us_score === null ? "LIVE" : `LIVE ${g.us_score}–${g.opp_score}`; cls = "warn"; }
    else { result = timeOf(g.start_utc); }
    const t = byKey[g.team_key], teamCell = el("td", undefined, "teamcol");
    if (t) { const dot = el("span", undefined, "swatch"); if (t.color) dot.style.background = t.color; teamCell.append(dot, document.createTextNode(t.label)); }
    else teamCell.textContent = "–";
    tr.append(el("td", dayOf(g.start_utc)), teamCell, el("td", game), el("td", result, "num " + cls));
    // highlight each visible team's next unplayed game
    const k = g.team_key || "";
    if (g.status !== "post" && !nextSeen.has(k)) { nextSeen.add(k); tr.className = "next"; if (!firstNext) firstNext = tr; }
    return tr;
  }));
  if (aimAtNext) {  // the next game, with a couple of rows of context above it
    aimAtNext = false;
    const box = $("schedule-scroll");
    box.scrollTop = firstNext ? Math.max(0, firstNext.offsetTop - box.offsetTop - 2 * firstNext.offsetHeight) : 0;
  }
}

// Scoreboard: live/pre/final games in their window, else the next game with a countdown.
// serverSkew keeps the client-side countdown on the server's clock, not this machine's.
let serverSkew = 0;
const serverNow = () => Date.now() + serverSkew;
const REG_PERIODS = {nfl: 4, nhl: 3};
function periodLabel(league, i) {
  if (league === "nfl") return i < 4 ? `Q${i + 1}` : "OT";
  if (league === "nhl") return i < 3 ? `P${i + 1}` : (i === 3 ? "OT" : "SO");
  return String(i + 1);
}
function chipFor(g) {
  if (g.state === "pre") return ["PRE-GAME", "warn"];
  if (g.state === "post") return ["FINAL", ""];
  if (g.status_name === "STATUS_HALFTIME") return ["HALFTIME", "warn"];
  if (/END_PERIOD|DELAYED|DELAY/.test(g.status_name)) return ["BREAK", "warn"];
  return ["LIVE", "live"];
}
function countdownText(startIso) {
  const s = Math.round((Date.parse(startIso) - serverNow()) / 1000);
  if (s <= 0) return "starting now";
  const d = Math.floor(s / 86400), h = Math.floor(s % 86400 / 3600), m = Math.floor(s % 3600 / 60), sec = s % 60;
  if (d > 0) return `${d}d ${h}h ${m}m`;
  if (h > 0) return `${h}h ${m}m ${sec}s`;
  return `${m}m ${String(sec).padStart(2, "0")}s`;
}
function tick() {  // once a second: countdowns and "last poll N s ago"
  document.querySelectorAll("[data-start]").forEach((e) => { e.textContent = (e.dataset.prefix || "") + countdownText(e.dataset.start); });
  document.querySelectorAll("[data-last]").forEach((e) => {
    const s = Math.max(0, Math.round((serverNow() - Date.parse(e.dataset.last)) / 1000));
    e.textContent = s < 90 ? `${s} s ago` : `${Math.round(s / 60)} min ago`;
  });
}
function scoreRow(g, side, cols, other) {
  const t = g[side], tr = el("tr", undefined, t.us ? "us" : "");
  const name = el("td", undefined, "team");
  if (g.situation && g.situation.possession && g.situation.possession === t.abbr) name.append(el("span", "● ", "poss"));
  name.append(el("span", t.abbr || "–", "abbr"));
  if (t.record) name.append(el("span", " " + t.record, "rec"));
  tr.append(name);
  for (let i = 0; i < cols; i++) { const v = t.linescores[i]; tr.append(el("td", v === undefined || v === null ? "–" : String(v), "ls")); }
  const ahead = t.score !== null && other.score !== null && t.score > other.score;
  tr.append(el("td", t.score === null ? "–" : String(t.score), "total" + (ahead ? " lead" : "")));
  return tr;
}
function gameBlock(g) {
  const box = el("div", undefined, "sb-game"), head = el("div", undefined, "sb-gamehead");
  const [chip, cls] = chipFor(g);
  head.append(el("span", chip, "pill " + cls));
  if (g.state === "in" && g.detail) head.append(el("span", g.detail, "sb-detail"));
  if (g.state === "pre") { const c = el("span", "", "sb-detail"); c.dataset.start = g.start_utc; c.dataset.prefix = "Kickoff in "; head.append(c); }
  const meta = [g.broadcast, g.venue].filter(Boolean).join(" · ");
  if (meta) head.append(el("span", meta, "sb-meta"));
  box.append(head);

  const reg = REG_PERIODS[g.league] || 0;
  const cols = g.state === "pre" ? 0 : Math.max(reg, g.home.linescores.length, g.away.linescores.length);
  const table = el("table", undefined, "sb"), thead = el("thead"), hr = el("tr");
  hr.append(el("th", ""));
  for (let i = 0; i < cols; i++) hr.append(el("th", periodLabel(g.league, i), "ls"));
  hr.append(el("th", ""));
  thead.append(hr);
  const tbody = el("tbody");
  tbody.append(scoreRow(g, "away", cols, g.home), scoreRow(g, "home", cols, g.away));  // ESPN order: visitors on top
  table.append(thead, tbody);
  const wrap = el("div", undefined, "scroll"); wrap.append(table); box.append(wrap);

  if (g.situation && (g.situation.text || g.situation.possession_text)) {
    const sit = el("div", g.situation.text || g.situation.possession_text, "sit");
    if (g.situation.red_zone) sit.append(el("span", "RED ZONE", "rz"));
    box.append(sit);
  }
  return box;
}
const teamByKey = (key) => ((lastStatus && lastStatus.teams) || []).find((t) => t.key === key);
const matchup = (n) => (n.us ? `${n.us} ${n.home ? "vs" : "@"} ${n.opp}` : n.name);
function whenLabel(n) {  // TONIGHT / TOMORROW / THIS WEEK / NEXT GAME, by the viewer's calendar
  const start = new Date(n.start_utc), now = new Date(serverNow());
  const days = Math.round((new Date(start.getFullYear(), start.getMonth(), start.getDate()) - new Date(now.getFullYear(), now.getMonth(), now.getDate())) / 86400000);
  if (days <= 0) return start.getHours() >= 17 ? "TONIGHT" : "TODAY";
  if (days === 1) return "TOMORROW";
  return n.in_week ? "THIS WEEK" : "NEXT GAME";
}
function nextCard(n, showTeam) {
  const card = el("div", undefined, "nextcard"), t = teamByKey(n.team_key);
  if (showTeam && t) { const tag = el("div", undefined, "teamtag"); tag.append(dot(t.color), document.createTextNode(t.label)); card.append(tag); }
  const label = whenLabel(n);
  card.append(el("div", label, "pill next-label " + (label === "NEXT GAME" ? "" : "ok")));
  card.append(el("div", matchup(n), "next-big"));
  card.append(el("div", `${dayOf(n.start_utc)} · ${timeOf(n.start_utc)}`, "next-when"));
  const c = el("div", "", "next-count"); c.dataset.start = n.start_utc; c.dataset.prefix = "in "; card.append(c);
  return card;
}
function nextLines(sb) {  // while a game is on the card: the other teams' next games, compactly
  const multi = ((lastStatus && lastStatus.teams) || []).length > 1;
  return sb.next_games.map((n) => {
    const t = teamByKey(n.team_key), line = el("div", undefined, "sb-foot");
    line.textContent = `Next up${multi && t ? " · " + t.label : ""}: ${matchup(n)} · ${dayOf(n.start_utc)} · ${timeOf(n.start_utc)}`;
    return line;
  });
}
function renderScoreboard(sb) {
  const p = sb.polling, poll = $("sb-poll");
  poll.replaceChildren(el("span", undefined, p.active ? "dot" : "dot off"));
  if (p.active) {
    poll.append(document.createTextNode(`Polling every ${p.interval_s} s · last poll `));
    const ago = el("span"); ago.dataset.last = p.last_poll_at; poll.append(ago);
  } else {
    poll.append(document.createTextNode(`Not polling · starts ${p.lead_min} min before kickoff`));
  }

  const box = $("scoreboard"), parts = [];
  if (sb.games.length) {
    sb.games.forEach((g) => parts.push(gameBlock(g)));
    parts.push(...nextLines(sb));
  } else if (sb.next_games.length) {
    const grid = el("div", undefined, "nextgrid"), multi = ((lastStatus && lastStatus.teams) || []).length > 1;
    sb.next_games.forEach((n) => grid.append(nextCard(n, multi)));
    parts.push(grid);
  } else {
    parts.push(el("div", "No upcoming games.", "empty"));
  }
  box.replaceChildren(...parts);
  tick();
}

function render(s) {
  const mode = $("mode");
  mode.textContent = s.mode === "live" ? "live" : "dry-run";
  mode.className = "pill " + (s.mode === "live" ? "ok" : "warn");
  $("meta").textContent = `v${s.version} · up ${Math.round((s.uptime_s || 0) / 60)} min · delay ${s.delay_s}s · updated ${fmt(s.now)}`;

  const w = s.watcher, box = $("watcher");
  const lines = [
    ["Watching", w.watching.length ? w.watching.join(", ") : "nothing right now"],
    ["Last poll", w.last_poll_at ? ago(w.last_poll_at, s.now) : "none yet"],
    ["Last good poll", w.last_ok_at ? ago(w.last_ok_at, s.now) : "none yet"],
    ["Schedule sync", w.last_sync_at ? ago(w.last_sync_at, s.now) : "none yet"],
    ["Polls / errors", `${w.polls} / ${w.errors}`],
  ].map(([k, v]) => row(k, v));
  const ul = el("ul"); ul.append(...lines); box.replaceChildren(ul);
  if (w.last_error) box.append(el("div", "Last error: " + w.last_error, "err"));

  lastStatus = s; renderBulbs(); bulbsRefresh();
  renderSchedule(s.schedule, s.teams);
  renderScoreboard(s.scoreboard);

  $("events").replaceChildren(...s.events.map((e) => {
    const tr = el("tr");
    const cells = [fmt(e.detected_at), e.game, e.team, `${e.label}${e.delta ? " (+" + e.delta + ")" : ""}`,
                   e.status === "no_lights" ? "no lights" : e.status, e.fire_delay_s === null ? "–" : Math.round(e.fire_delay_s) + "s"];
    cells.forEach((c, i) => tr.append(el("td", c, i === 4 ? statusCls[e.status] : "")));
    return tr;
  }));
  $("no-events").hidden = s.events.length > 0;
}

async function loadSetup() {
  try {
    const items = (await getJson("api/setup")).items.filter((i) => !i.done);
    $("setup-card").hidden = !items.length;
    $("setup-list").replaceChildren(...items.map((i) => {
      const li = el("li"), left = el("span", i.text);
      if (i.hint) left.append(el("div", i.hint, "muted help"));
      li.append(left);
      if (i.fix) { const a = el("a", "Fix"); a.href = i.fix; li.append(a); }
      return li;
    }));
  } catch (e) { /* the status refresh already says when the server is unreachable */ }
}
async function refresh() {
  loadSetup();
  try {
    const r = await fetch("api/status", {cache: "no-store"});
    if (!r.ok) throw new Error("HTTP " + r.status);
    const body = await r.json();
    serverSkew = Date.parse(body.now) - Date.now();
    render(body);
  } catch (e) {
    $("meta").textContent = "can't reach the server (" + e.message + "); retrying…";
  }
}
