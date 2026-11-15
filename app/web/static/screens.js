// ---- Teams screen -------------------------------------------------------------------------
// Edits are a draft until Save. Everything from the server is inserted with textContent.
const TM = {loaded: false, revision: 0, saved: [], draft: [], bulbs: [], leagues: [], info: {},
            errors: {}, banner: null, saving: false, seq: 0, league: "nfl", results: [],
            resultsNote: ""};
const keyOf = (t) => `${t.league}:${t.id}`;
const clone = (x) => JSON.parse(JSON.stringify(x));
const dirty = () => JSON.stringify(TM.draft) !== JSON.stringify(TM.saved);
const leagueLabel = (k) => (TM.leagues.find((l) => l.key === k) || {label: k.toUpperCase()}).label;
function luminance(hex) {
  const c = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255)
    .map((v) => (v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4));
  return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2];
}
async function getJson(url) {
  const r = await fetch(url, {cache: "no-store"});
  const body = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(body.detail || `HTTP ${r.status}`);
  return body;
}
function dot(color) { const d = el("span", undefined, "swatch"); if (color) d.style.background = color; return d; }

async function loadTeams() {
  try {
    const [s, leagues] = await Promise.all([getJson("api/settings"), getJson("api/leagues")]);
    TM.revision = s.sections.teams.revision;
    TM.saved = s.sections.teams.value; TM.draft = clone(TM.saved);
    TM.bulbs = s.sections.bulbs.value.map((b) => b.name);
    TM.leagues = leagues;
    if (!leagues.some((l) => l.key === TM.league) && leagues.length) TM.league = leagues[0].key;
    TM.loaded = true; TM.errors = {}; TM.banner = null;
    renderLeagueSelect();
    await loadInfo();
  } catch (e) {
    TM.banner = {cls: "bad", text: "Couldn't load your teams: " + e.message};
  }
  renderTeams(); runSearch();
}
async function loadInfo() {  // names and ESPN colors for the followed teams
  TM.resultsNote = "";
  await Promise.all([...new Set(TM.draft.map((t) => t.league))].map(async (lg) => {
    try { (await getJson(`api/teams/search?league=${encodeURIComponent(lg)}`)).forEach((t) => { TM.info[keyOf(t)] = t; }); }
    catch (e) { TM.resultsNote = "ESPN isn't answering, so team names and colors are unavailable for now."; }
  }));
}
function renderLeagueSelect() {
  const sel = $("team-league");
  sel.replaceChildren(...TM.leagues.map((l) => { const o = el("option", l.label); o.value = l.key; o.selected = l.key === TM.league; return o; }));
}

// Touching a team clears its error messages (and the "fix these" banner once none are left).
function clearErrors(i) {
  delete TM.errors[i];
  if (TM.banner && TM.banner.fix && !Object.keys(TM.errors).length) TM.banner = null;
  renderBanner();
}
function colorField(t, key, label, espn, i) {
  const wrap = el("span", undefined, "colorfield");
  const input = document.createElement("input");
  input.type = "color"; input.value = t[key] || espn || "#ffffff";
  input.setAttribute("aria-label", `${t.abbr} ${label.toLowerCase()} color`);
  input.addEventListener("input", () => { t[key] = input.value; renderSaveBar(); });
  input.addEventListener("change", () => { clearErrors(i); renderFollowed(); });  // picker closed
  wrap.append(el("span", label), input);
  const same = t[key] && espn && t[key].toLowerCase() === espn.toLowerCase();  // pre-filled, unchanged
  wrap.append(el("span", t[key] && !same ? "custom" : (espn ? "ESPN's" : "default"), "muted"));
  if (t[key] && !same) {
    const reset = el("button", "Use ESPN's"); reset.type = "button";
    reset.addEventListener("click", () => { t[key] = null; clearErrors(i); renderFollowed(); renderSaveBar(); });
    wrap.append(reset);
  }
  const shown = t[key] || espn;
  if (shown && luminance(shown) < 0.03) wrap.append(el("span", "very dark: will look dim or off on a bulb", "muted"));
  return wrap;
}
// Test: plays the team's score effect with the colors as they are in the draft, so you can try
// a color before saving. Teams with no color of their own use ESPN's, as in a real game.
const TT = {busy: {}, note: {}};
function teamTestText(body) {
  const good = body.bulbs.filter((b) => b.ok).map((b) => b.name), bad = body.bulbs.filter((b) => !b.ok);
  return `Played on ${good.join(", ")} (${body.duration_s}s).` + bad.map((b) => ` ${b.name} failed: ${b.error}`).join("");
}
async function testTeam(t) {
  const k = keyOf(t), info = TM.info[k] || {};
  TT.busy[k] = true; delete TT.note[k]; renderFollowed();
  let note;
  try {
    const r = await fetch("api/teams/test", {method: "POST", headers: {"X-Gameday": "1", "Content-Type": "application/json"},
      body: JSON.stringify({league: t.league, id: t.id, bulbs: t.bulbs, color: t.color, alt_color: t.alt_color, espn_color: info.color || null, espn_alt_color: info.alt_color || null})});
    const body = await r.json().catch(() => ({}));
    note = r.ok ? {text: body.dry_run ? "Dry-run: nothing was sent to the bulbs." : teamTestText(body), cls: body.ok ? "ok" : "bad"}
               : {text: body.detail || `HTTP ${r.status}`, cls: "bad"};
  } catch (e) { note = {text: "Request failed: " + e.message, cls: "bad"}; }
  TT.busy[k] = false; TT.note[k] = note; renderFollowed();
  setTimeout(() => { if (TT.note[k] === note) { delete TT.note[k]; renderFollowed(); } }, 8000);
}
function followedRow(t, i) {
  const info = TM.info[keyOf(t)] || {}, row = el("div", undefined, "teamrow");
  const head = el("div", undefined, "teamhead");
  head.append(dot(t.color || info.color), dot(t.alt_color || info.alt_color), el("strong", t.abbr),
              el("span", `${info.name ? info.name + " · " : ""}${leagueLabel(t.league)}`, "muted grow"));
  if (!TM.saved.some((s) => keyOf(s) === keyOf(t))) head.append(el("span", "not saved yet", "pill warn"));
  const rm = el("button", "Remove", "danger"); rm.type = "button";
  rm.setAttribute("aria-label", `Stop following ${t.abbr}`);
  rm.addEventListener("click", () => { TM.draft.splice(i, 1); TM.errors = {}; renderFollowed(); renderSaveBar(); renderResults(); });
  const test = el("button", TT.busy[keyOf(t)] ? "Testing…" : (lastStatus && lastStatus.mode !== "live" ? "Test (dry-run)" : "Test"));
  test.type = "button"; test.disabled = !!TT.busy[keyOf(t)] || !t.bulbs.length;
  test.title = t.bulbs.length ? "Flash this team's colors on its bulbs (as edited, saved or not), then restore them" : "No lights on this team: nothing to test";
  test.setAttribute("aria-label", `Test ${t.abbr} colors`);
  test.addEventListener("click", () => testTeam(t));
  head.append(test, rm);
  row.append(head);
  if (TT.note[keyOf(t)]) row.append(el("div", TT.note[keyOf(t)].text, "help " + TT.note[keyOf(t)].cls));

  const fields = el("div", undefined, "fields"), bulbs = el("span", undefined, "bulbpick");
  bulbs.append(el("span", "Bulbs", "muted"));
  TM.bulbs.forEach((name) => {
    const lab = el("label"), cb = document.createElement("input");
    cb.type = "checkbox"; cb.checked = t.bulbs.includes(name);
    cb.addEventListener("change", () => {
      t.bulbs = TM.bulbs.filter((b) => (b === name ? cb.checked : t.bulbs.includes(b)));
      clearErrors(i); renderFollowed(); renderSaveBar();
    });
    lab.append(cb, document.createTextNode(name)); bulbs.append(lab);
  });
  if (!t.bulbs.length) bulbs.append(el("span", TM.bulbs.length ? "No lights: scores are recorded but nothing flashes" : "No lights: scores are recorded but nothing flashes. Add a bulb on the Bulbs screen.", "warn"));
  fields.append(bulbs, colorField(t, "color", "Color", info.color, i), colorField(t, "alt_color", "Alternate", info.alt_color, i));
  row.append(fields);
  (TM.errors[i] || []).forEach((m) => row.append(el("div", m, "err")));
  return row;
}
function renderFollowed() {
  const box = $("teams-followed");
  if (!TM.loaded) { box.replaceChildren(el("p", "Loading…", "empty")); return; }
  box.replaceChildren(...(TM.draft.length ? TM.draft.map(followedRow)
    : [el("p", "No teams followed. Search below to follow one.", "empty")]));
}
function renderBanner() {
  const box = $("teams-banner");
  if (!TM.banner) { box.replaceChildren(); return; }
  const b = el("div", undefined, "banner " + TM.banner.cls);
  b.setAttribute("role", TM.banner.cls === "bad" ? "alert" : "status");
  b.append(el("span", TM.banner.text));
  if (TM.banner.action) { const a = el("button", TM.banner.action.label); a.type = "button"; a.addEventListener("click", TM.banner.action.fn); b.append(a); }
  box.replaceChildren(b);
}
function renderSaveBar() {
  const bar = $("teams-savebar"), changed = dirty();
  const save = el("button", TM.saving ? "Saving…" : "Save", "primary"); save.type = "button";
  save.disabled = TM.saving || !changed; save.addEventListener("click", saveTeams);
  const discard = el("button", "Discard changes"); discard.type = "button";
  discard.disabled = TM.saving || !changed;
  discard.addEventListener("click", () => { TM.draft = clone(TM.saved); TM.errors = {}; TM.banner = null; renderTeams(); });
  bar.replaceChildren(el("span", changed ? "Unsaved changes" : (TM.loaded ? "All changes saved" : ""), "grow " + (changed ? "warn" : "muted")), discard, save);
}
function renderResults() {
  const box = $("team-results");
  if (TM.resultsNote && !TM.results.length) { box.replaceChildren(el("p", TM.resultsNote, "err")); return; }
  if (!TM.results.length) { box.replaceChildren(el("p", "No teams match.", "empty")); return; }
  box.replaceChildren(...TM.results.map((t) => {
    const row = el("div", undefined, "result"), mine = TM.draft.some((d) => keyOf(d) === keyOf(t));
    const text = el("span", undefined, "grow");
    text.append(el("strong", t.name), el("span", ` ${t.abbr} · ${leagueLabel(t.league)}`, "muted"));
    const btn = el("button", mine ? "Following" : "Follow"); btn.type = "button"; btn.disabled = mine;
    btn.setAttribute("aria-label", `${mine ? "Following" : "Follow"} ${t.name}`);
    btn.addEventListener("click", () => follow(t));
    row.append(dot(t.color), dot(t.alt_color), text, btn);
    return row;
  }));
}
function renderTeams() { renderBanner(); renderFollowed(); renderSaveBar(); renderResults(); }

function follow(t) {
  TM.info[keyOf(t)] = t;
  TM.draft.push({league: t.league, id: t.id, abbr: t.abbr, bulbs: TM.bulbs.slice(0, 1), color: t.color, alt_color: t.alt_color});
  TM.banner = null; TM.errors = {};
  renderTeams();
}
let searchTimer = null;
function runSearch() {
  const seq = ++TM.seq, q = $("team-search").value.trim();
  getJson(`api/teams/search?league=${encodeURIComponent(TM.league)}&q=${encodeURIComponent(q)}`)
    .then((r) => { if (seq === TM.seq) { TM.results = r; TM.resultsNote = ""; renderResults(); } })
    .catch((e) => { if (seq === TM.seq) { TM.results = []; TM.resultsNote = "Couldn't search: " + e.message; renderResults(); } });
}
async function saveTeams() {
  TM.saving = true; TM.banner = null; TM.errors = {}; renderSaveBar();
  try {
    const r = await fetch("api/settings/teams", {method: "PUT", headers: {"X-Gameday": "1", "If-Match": String(TM.revision), "Content-Type": "application/json"}, body: JSON.stringify({value: TM.draft})});
    const body = await r.json().catch(() => ({}));
    if (r.ok) {
      TM.revision = body.revision; TM.saved = body.value; TM.draft = clone(body.value);
      TM.banner = {cls: "ok", text: "Saved. Schedules for new teams are loading now."};
      await loadInfo();
      refresh(); setTimeout(refresh, 4000);
    } else if (r.status === 422) {
      const loose = [];
      (body.errors || []).forEach((e) => {
        const m = /^teams\[(\d+)\]\.?(.*)$/.exec(e.path);
        if (m) (TM.errors[m[1]] = TM.errors[m[1]] || []).push(m[2] ? `${m[2]}: ${e.message}` : e.message);
        else loose.push(e.path ? `${e.path}: ${e.message}` : e.message);
      });
      TM.banner = {cls: "bad", fix: !loose.length, text: loose.length ? loose.join("; ") : "Some teams need fixing before this can be saved."};
    } else if (r.status === 409) {
      TM.banner = {cls: "bad", text: `Teams were changed somewhere else (now revision ${body.current_revision}). Your edits were not saved.`, action: {label: "Load latest", fn: loadTeams}};
    } else {
      TM.banner = {cls: "bad", text: body.detail || `HTTP ${r.status}`};
    }
  } catch (e) {
    TM.banner = {cls: "bad", text: "Request failed: " + e.message};
  }
  TM.saving = false; renderTeams();
}
$("team-league").addEventListener("change", (e) => { TM.league = e.target.value; runSearch(); });
$("team-search").addEventListener("input", () => { clearTimeout(searchTimer); searchTimer = setTimeout(runSearch, 250); });
window.addEventListener("beforeunload", (e) => { if (dirty() || editors.some((x) => x.dirty())) { e.preventDefault(); e.returnValue = ""; } });

// ---- section editors (Settings, Effects, Advanced) ------------------------------------------
// One draft per stored section, saved with PUT /api/settings/{section}. `fields` lists the keys the
// screen shows; a 422 message about any other key goes in the banner. `draw(ed, body)` builds the inputs.
const editors = [];
function sectionEditor(o) {
  const ed = {section: o.section, id: o.id, fields: o.fields, draw: o.draw, revision: 0, saved: null, draft: null,
              machine: null, bulbs: [], errors: {}, banner: null, saving: false, loaded: false};
  ed.dirty = () => ed.loaded && JSON.stringify(ed.draft) !== JSON.stringify(ed.saved);
  editors.push(ed);
  return ed;
}
async function edLoad(ed) {
  try {
    const s = await getJson("api/settings");
    ed.revision = s.sections[ed.section].revision;
    ed.saved = s.sections[ed.section].value; ed.draft = clone(ed.saved);
    ed.machine = s.machine; ed.bulbs = s.sections.bulbs.value.map((b) => b.name); ed.teams = s.sections.teams.value; ed.teamsRevision = s.sections.teams.revision;
    ed.loaded = true; ed.errors = {}; ed.banner = null;
  } catch (e) {
    ed.banner = {cls: "bad", text: "Couldn't load these settings: " + e.message};
  }
  edDraw(ed);
}
function edShow(ed) {  // never throw away unsaved edits by navigating away and back
  if (ed.dirty()) edDraw(ed); else edLoad(ed);
}
function edDraw(ed) {
  const box = $(ed.id + "-banner");
  if (!ed.banner) box.replaceChildren();
  else {
    const b = el("div", undefined, "banner " + ed.banner.cls);
    b.setAttribute("role", ed.banner.cls === "bad" ? "alert" : "status");
    b.append(el("span", ed.banner.text));
    if (ed.banner.action) { const a = el("button", ed.banner.action.label); a.type = "button"; a.addEventListener("click", ed.banner.action.fn); b.append(a); }
    box.replaceChildren(b);
  }
  const body = $(ed.id + "-body");
  if (ed.loaded) ed.draw(ed, body); else body.replaceChildren(el("p", "Loading…", "empty"));
  edSaveBar(ed);
}
function edSaveBar(ed) {
  const changed = ed.dirty(), bar = $(ed.id + "-savebar");
  const save = el("button", ed.saving ? "Saving…" : "Save", "primary"); save.type = "button";
  save.disabled = ed.saving || !changed; save.addEventListener("click", () => edSave(ed));
  const discard = el("button", "Discard changes"); discard.type = "button";
  discard.disabled = ed.saving || !changed;
  discard.addEventListener("click", () => { ed.draft = clone(ed.saved); ed.errors = {}; ed.banner = null; edDraw(ed); });
  bar.classList.toggle("dirty", changed);
  bar.replaceChildren(el("span", changed ? "Unsaved changes" : (ed.loaded ? "All changes saved" : ""), "grow " + (changed ? "warn" : "muted")), discard, save);
  if (ed.after) ed.after(ed);
}
// Save the given editors in order, then run `then` only if every one saved cleanly ("Save & test").
async function saveThen(editors, then) {
  for (const ed of editors) {
    await edSave(ed);
    if (ed.dirty() || (ed.banner && ed.banner.cls === "bad")) return;
  }
  then();
}
async function edSave(ed) {
  ed.saving = true; ed.banner = null; ed.errors = {}; edDraw(ed);
  try {
    const r = await fetch(`api/settings/${ed.section}`, {method: "PUT", headers: {"X-Gameday": "1", "If-Match": String(ed.revision), "Content-Type": "application/json"}, body: JSON.stringify({value: ed.payload ? ed.payload(ed.draft) : ed.draft})});
    const body = await r.json().catch(() => ({}));
    if (r.ok) {
      ed.revision = body.revision; ed.saved = body.value; ed.draft = clone(body.value);
      ed.banner = {cls: "ok", text: "Saved. It applies to the next score; nothing needs a restart."};
      refresh();
    } else if (r.status === 422) {
      const loose = [];
      (body.errors || []).forEach((e) => {
        const m = ed.indexed && new RegExp(`^${ed.section}\\[(\\d+)\\]\\.?(.*)$`).exec(e.path);
        if (m) (ed.errors["#" + m[1]] = ed.errors["#" + m[1]] || []).push(m[2] ? `${m[2]}: ${e.message}` : e.message);
        else if (ed.fields.includes(e.path)) (ed.errors[e.path] = ed.errors[e.path] || []).push(e.message);
        else loose.push(e.path ? `${e.path}: ${e.message}` : e.message);
      });
      ed.banner = {cls: "bad", text: loose.length ? loose.join("; ") : "Fix the marked fields before saving."};
    } else if (r.status === 409) {
      ed.banner = {cls: "bad", text: `These settings were changed somewhere else (now revision ${body.current_revision}). Your edits were not saved.`, action: {label: "Load latest", fn: () => edLoad(ed)}};
    } else {
      ed.banner = {cls: "bad", text: body.detail || `HTTP ${r.status}`};
    }
  } catch (e) {
    ed.banner = {cls: "bad", text: "Request failed: " + e.message};
  }
  ed.saving = false; edDraw(ed);
}
// A number field (optionally with a slider) bound to ed.draft[key]. Editing it clears its own error.
// Options: label, unit, min, max, step, slider, help; `obj` (default the draft) holds the value under
// `key`; `err` is the server's error path for it (default `key`); `view` = {to, from} converts the
// stored number to what is shown (brightness 1..255 shown as a percent).
function numField(ed, key, o) {
  const obj = o.obj || ed.draft, ek = o.err || key, view = o.view || {to: (v) => v, from: (v) => v};
  const wrap = el("div", undefined, "field"), id = `f-${ed.section}-${ek}`;
  const lab = el("label", o.label); lab.htmlFor = id;
  const input = document.createElement("input");
  input.type = "number"; input.id = id; input.step = o.step || 1;
  if (o.min !== undefined) input.min = o.min;
  if (o.max !== undefined && !o.slider) input.max = o.max;
  const shown = obj[key] === null || obj[key] === undefined ? "" : view.to(obj[key]);
  input.value = shown;
  const row = el("div", undefined, "numrow");
  row.append(input, el("span", o.unit || "", "muted"));
  let range = null;
  const changed = (v) => {
    obj[key] = v; delete ed.errors[ek];
    wrap.querySelectorAll(".err").forEach((e) => e.remove());
    if (ed.banner && ed.banner.cls === "bad" && !ed.banner.action && !Object.keys(ed.errors).length) { ed.banner = null; $(ed.id + "-banner").replaceChildren(); }
    edSaveBar(ed);
  };
  input.addEventListener("input", () => {
    changed(input.value === "" ? null : view.from(Number(input.value)));
    if (range && input.value !== "") range.value = input.value;
  });
  if (o.slider) {
    range = document.createElement("input");
    range.type = "range"; range.min = o.min; range.max = o.max; range.step = o.step || 1;
    range.value = shown === "" ? o.min : shown; range.setAttribute("aria-label", o.label);
    range.addEventListener("input", () => { input.value = range.value; changed(view.from(Number(range.value))); });
    row.append(range);
  }
  wrap.append(lab, row);
  if (o.help) wrap.append(el("div", o.help, "muted help"));
  (ed.errors[ek] || []).forEach((m) => wrap.append(el("div", m, "err")));
  return wrap;
}

const DELAY_KINDS = [["TD", "Touchdown"], ["PAT", "Extra point"], ["FG", "Field goal"], ["score", "Goal (hockey)"]];
const SETTINGS = sectionEditor({section: "household", id: "settings", fields: ["delay_s", ...DELAY_KINDS.map(([k]) => "delay_by_label." + k)], draw(ed, body) {
  const kinds = el("div", undefined, "field");
  kinds.append(el("label", "A different delay for one kind of score"),
               el("div", "Leave blank to use the delay above. An extra point often shows on TV sooner after ESPN reports it than a touchdown does, so it can need a shorter wait.", "muted help"));
  const row = el("div", undefined, "mx-fields");
  DELAY_KINDS.forEach(([key, label]) => {
    const w = el("div"), input = document.createElement("input"); input.type = "number"; input.min = 0; input.max = 180; input.step = 0.5;
    const have = (ed.draft.delay_by_label || {})[key];
    input.value = have === undefined ? "" : have; input.placeholder = String(ed.draft.delay_s);
    input.setAttribute("aria-label", `Delay for ${label}`);
    input.addEventListener("input", () => {
      if (input.value === "") { if (ed.draft.delay_by_label) delete ed.draft.delay_by_label[key]; }
      else { ed.draft.delay_by_label = ed.draft.delay_by_label || {}; ed.draft.delay_by_label[key] = Number(input.value); }
      if (ed.draft.delay_by_label && !Object.keys(ed.draft.delay_by_label).length) delete ed.draft.delay_by_label;
      delete ed.errors["delay_by_label." + key]; edSaveBar(ed);
    });
    w.append(el("label", label + " (s)"), input);
    (ed.errors["delay_by_label." + key] || []).forEach((m) => w.append(el("div", m, "err")));
    row.append(w);
  });
  kinds.append(row);
  body.replaceChildren(numField(ed, "delay_s", {
    label: "Delay after a score", unit: "seconds", min: 0, max: 180, slider: true,
    help: "How long to wait after ESPN reports a score before the lights fire. Streaming runs behind live TV, so a longer delay keeps the room from spoiling the play. Applies to every game. The Calibrate screen can measure it for you.",
  }), kinds);
}});

// ---- Effects screen -----------------------------------------------------------------------
// The score effect: pulses alternate two colors. Blank colors mean "use each team's colors"
// (colors set on a team in Teams win over the ones here).
const FLASH_CAP = 2;  // color changes per second; the server enforces it, this only warns early
const EFFECT_KEYS = ["effects.score.pulses", "effects.score.duration_s", "effects.score.brightness",
                     "effects.score.color", "effects.score.alt_color", "effects.score"];
function effectColor(ed, s, key, label) {
  const wrap = el("div", undefined, "field"), ek = "effects.score." + key;
  wrap.append(el("label", label));
  const row = el("div", undefined, "numrow"), input = document.createElement("input");
  input.type = "color"; input.value = s[key] || "#ffffff"; input.setAttribute("aria-label", label);
  const note = el("span", s[key] ? "custom" : "team colors", "muted");
  input.addEventListener("input", () => { s[key] = input.value; note.textContent = "custom"; reset.hidden = false; effectPreview(s); edSaveBar(ed); });
  const reset = el("button", "Use team colors"); reset.type = "button"; reset.hidden = !s[key];
  reset.addEventListener("click", () => { s[key] = null; edDraw(ed); });
  row.append(input, note, reset); wrap.append(row);
  (ed.errors[ek] || []).forEach((m) => wrap.append(el("div", m, "err")));
  return wrap;
}
function effectPreview(s) {
  const box = $("effects-preview"); if (!box) return;
  const n = Math.min(Math.max(Number(s.pulses) || 0, 0), 20) * 2, a = s.color || "#8a948e", b = s.alt_color || "#d5dbd7";
  box.replaceChildren(...Array.from({length: n}, (_, i) => { const d = dot(i % 2 ? b : a); d.style.width = d.style.height = "16px"; d.style.opacity = String(Number(s.brightness) / 255 || 1); return d; }));
  const rate = (Number(s.pulses) * 2) / Number(s.duration_s), line = $("effects-rate");
  if (!isFinite(rate)) { line.textContent = ""; return; }
  line.textContent = `${rate.toFixed(1)} color changes per second (limit ${FLASH_CAP})`;
  line.className = "help " + (rate > FLASH_CAP ? "bad" : rate > FLASH_CAP * 0.8 ? "warn" : "muted");
}
function drawEffects(ed, body) {
  const s = ed.draft.score;
  const pct = {to: (v) => Math.round(v / 255 * 100), from: (v) => Math.round(v / 100 * 255)};
  const preview = el("div", undefined, "field");
  const strip = el("div"); strip.id = "effects-preview"; strip.style.display = "flex"; strip.style.flexWrap = "wrap"; strip.style.gap = "4px";
  const rate = el("div"); rate.id = "effects-rate";
  preview.append(el("label", "Preview"), strip, rate);
  const redo = () => effectPreview(s);
  const f = [
    numField(ed, "pulses", {obj: s, err: "effects.score.pulses", label: "Pulses", min: 1, step: 1, help: "Each pulse is two color changes."}),
    numField(ed, "duration_s", {obj: s, err: "effects.score.duration_s", label: "Duration", unit: "seconds", min: 0.1, step: 0.5}),
    numField(ed, "brightness", {obj: s, err: "effects.score.brightness", label: "Brightness", unit: "%", min: 1, max: 100, slider: true, view: pct}),
  ];
  f.forEach((x) => x.addEventListener("input", redo));
  body.replaceChildren(...f, effectColor(ed, s, "color", "Color"), effectColor(ed, s, "alt_color", "Alternate color"), preview);
  (ed.errors["effects.score"] || []).forEach((m) => body.append(el("div", m, "err")));
  redo();
}
// "Bulb defaults": the fixture layer (effects.fixtures.<bulb>), edited as part of the effects section.
const FX_OPEN = {};
function drawFixtureDefaults() {
  const box = $("fixtures-body"), ed = EFFECTS; if (!box) return;
  if (!ed.loaded) { box.replaceChildren(); return; }
  if (!ed.bulbs.length) { box.replaceChildren(el("p", "No bulbs configured yet.", "empty")); return; }
  box.replaceChildren(...ed.bulbs.map((name) => {
    const row = el("div", undefined, "mx-teameffect"), head = el("div", undefined, "mx-actions");
    const layer = () => (ed.draft.fixtures || {})[name] || {};
    const own = () => { ed.draft.fixtures = ed.draft.fixtures || {}; return (ed.draft.fixtures[name] = ed.draft.fixtures[name] || {}); };
    const prune = () => {
      const fx = ed.draft.fixtures;
      if (fx && fx[name] && !Object.keys(fx[name]).length) delete fx[name];
      if (fx && !Object.keys(fx).length) delete ed.draft.fixtures;
    };
    const bi = MATRIX.bulbInfo[name], opened = !!FX_OPEN[name] || hasKeys(layer());
    head.append(el("strong", name), el("span", hasKeys(layer()) ? "customized" : "uses the default effect", "muted"));
    const toggle = el("button", hasKeys(layer()) ? "Clear" : (opened ? "Close" : "Customize")); toggle.type = "button";
    toggle.addEventListener("click", () => { if (hasKeys(layer())) { delete ed.draft.fixtures[name]; prune(); FX_OPEN[name] = false; } else FX_OPEN[name] = !opened; edDraw(ed); });
    head.append(toggle); row.append(head);
    if (opened) row.append(layerFields(ed, {label: `${name} (all teams)`, layer, own, prune, kinds: bi ? bi.kinds : ["pulse"], kind: layer().kind || "pulse", info: null,
                                            redraw: () => edDraw(ed), touched: () => edSaveBar(ed)}));
    return row;
  }));
}
const EFFECTS = sectionEditor({section: "effects", id: "effects", fields: EFFECT_KEYS, draw(ed, body) { drawEffects(ed, body); drawFixtureDefaults(); }});

// Test: plays the SAVED effect on one bulb through the same pulse endpoint and state as the Status page.
let testBulb = "";
function renderEffectTest() {
  const box = $("effects-test"), ed = EFFECTS; if (!box) return;
  if (!ed.loaded) { box.replaceChildren(); return; }
  if (!ed.bulbs.length) { box.replaceChildren(el("p", "No bulbs configured.", "empty")); return; }
  if (!ed.bulbs.includes(testBulb)) testBulb = ed.bulbs[0];
  const sel = document.createElement("select"); sel.setAttribute("aria-label", "Bulb to test on");
  sel.replaceChildren(...ed.bulbs.map((n) => { const o = el("option", n); o.value = n; o.selected = n === testBulb; return o; }));
  sel.addEventListener("change", () => { testBulb = sel.value; renderEffectTest(); });
  const dry = lastStatus && lastStatus.mode !== "live", unsaved = ed.dirty(), going = !!busy[testBulb];
  const label = unsaved ? "Save & test" : (dry ? "Test (dry-run)" : "Test");
  const btn = el("button", going ? "Pulsing…" : label, "primary"); btn.type = "button";
  btn.disabled = going || ed.saving;
  btn.addEventListener("click", () => unsaved ? saveThen([ed], () => pulse(testBulb)) : pulse(testBulb));
  const row = el("div", undefined, "numrow"); row.append(sel, btn);
  const parts = [row];
  if (unsaved) parts.push(el("div", "Your unsaved changes will be saved first.", "muted help"));
  if (notes[testBulb]) parts.push(el("div", notes[testBulb].text, "help " + notes[testBulb].cls));
  box.replaceChildren(...parts);
}
EFFECTS.after = () => { renderEffectTest(); if (typeof MATRIX !== "undefined") MATRIX.after(); };

// ---- Effects matrix: what each followed team plays on each bulb --------------------------------
// Edits the team x fixture layer (teams[i].fixture_effects[bulb]) in the `teams` section. The summary
// line comes from GET /api/effects/matrix, which uses the same resolver a real score does.
const FX_KIND_LABEL = {pulse: "Pulse", chase: "Chase"};
const KIND_FIELDS = {
  pulse: [["pulses", "Pulses", 1, 1, ""], ["duration_s", "Duration", 0.1, 0.5, "s"]],
  chase: [["chunk", "Chunk", 1, 1, "segments"], ["speed", "Speed", 0.1, 0.5, "seg/s"], ["duration_s", "Duration", 0.1, 0.5, "s"]],
};
const FROM_LABEL = {"team x fixture": "this cell", "built-in": "built-in"};
const mxFrom = (f) => FROM_LABEL[f] || f;
const MATRIX = sectionEditor({section: "teams", id: "matrix", fields: [], draw: drawMatrix});
MATRIX.indexed = true;
MATRIX.cells = {}; MATRIX.sig = ""; MATRIX.note = {}; MATRIX.open = {}; MATRIX.bulbInfo = {};
const mxKey = (t, bulb) => `${t.league}/${t.id}/${bulb}`;
async function loadMatrix() {
  try { const m = await getJson("api/effects/matrix"); MATRIX.cells = Object.fromEntries(m.cells.map((c) => [mxKey(c, c.bulb), c])); MATRIX.bulbInfo = Object.fromEntries(m.bulbs.map((b) => [b.name, b])); drawFixtureDefaults(); }
  catch (e) { MATRIX.banner = {cls: "bad", text: "Couldn't load the effect summary: " + e.message}; }
  if (MATRIX.loaded) edDraw(MATRIX);
}
MATRIX.after = () => {  // reload the summary whenever the saved settings behind it change
  const sig = JSON.stringify([MATRIX.saved, EFFECTS.saved]);
  if (MATRIX.loaded && sig !== MATRIX.sig) { MATRIX.sig = sig; loadMatrix(); }
};
function mxSummary(info) {
  const box = el("div", undefined, "mx-resolved");
  if (!info) { box.append(el("span", "Saved effect not loaded yet.", "muted")); return box; }
  box.append(el("strong", FX_KIND_LABEL[info.kind] || info.kind), el("span", " " + mxFromTag(info.kind_from), "mx-from"));
  Object.entries(info.params).forEach(([k, p]) => {
    if (k === "brightness") return;
    box.append(el("span", ` · ${k.replace("_s", "")} ${p.value}`), el("span", " " + mxFromTag(p.from), "mx-from"));
  });
  [["color", info.color], ["alt_color", info.alt_color]].forEach(([k, c]) => {
    box.append(document.createTextNode(" · "));
    if (c.value) { box.append(dot(c.value), el("span", mxFromTag(c.from), "mx-from")); }
    else box.append(el("span", k === "color" ? "team color" : "team alt color", "mx-from"));
  });
  return box;
}
const mxFromTag = (f) => `(${mxFrom(f)})`;
// One override layer as fields: effect kind, its parameters and (optionally) colors. Used for a cell
// (team x bulb), a bulb's defaults and a team's effect. `o`: label (for screen readers), layer() the
// current layer or {}, own() creates it, prune() drops it when empty, kinds, kind (the effective kind),
// info (resolved values for placeholders, or null), colors (false hides them), redraw/touched.
function layerFields(ed, o) {
  const layer = o.layer(), fields = el("div", undefined, "mx-fields");
  const ksel = document.createElement("select"); ksel.setAttribute("aria-label", `Effect for ${o.label}`);
  const inherit = el("option", "Same as the level above"); inherit.value = ""; ksel.append(inherit);
  o.kinds.forEach((k) => { const op = el("option", FX_KIND_LABEL[k] || k); op.value = k; ksel.append(op); });
  ksel.value = layer.kind || "";
  ksel.addEventListener("change", () => { if (ksel.value) o.own().kind = ksel.value; else if (o.layer().kind) delete o.layer().kind; o.prune(); o.redraw(); });
  const kw = el("div"); kw.append(el("label", "Effect"), ksel); fields.append(kw);
  (KIND_FIELDS[o.kind] || []).forEach(([key, label, min, step, unit]) => {
    const w = el("div"), input = document.createElement("input"); input.type = "number"; input.min = min; input.step = step;
    input.value = layer[key] === undefined ? "" : layer[key];
    if (o.info && o.info.params[key]) input.placeholder = String(o.info.params[key].value);
    input.setAttribute("aria-label", `${label} for ${o.label}`);
    input.addEventListener("input", () => {
      if (input.value === "") { if (o.layer()[key] !== undefined) delete o.layer()[key]; } else o.own()[key] = Number(input.value);
      o.prune(); o.touched();
    });
    w.append(el("label", unit ? `${label} (${unit})` : label), input); fields.append(w);
  });
  if (o.colors !== false) [["color", "Color"], ["alt_color", "Alt color"]].forEach(([key, label]) => {
    const w = el("div"), input = document.createElement("input"); input.type = "color";
    input.value = layer[key] || (o.info && o.info[key].value) || "#888888";
    input.setAttribute("aria-label", `${label} for ${o.label}`);
    input.addEventListener("input", () => { o.own()[key] = input.value; o.prune(); o.touched(); });
    w.append(el("label", label), input);
    if (layer[key]) {
      const clear = el("button", "Reset"); clear.type = "button";
      clear.addEventListener("click", () => { delete o.layer()[key]; o.prune(); o.redraw(); });
      w.append(clear);
    }
    fields.append(w);
  });
  return fields;
}
const hasKeys = (x) => !!x && Object.keys(x).length > 0;
function mxCell(ed, t, i, bulb) {
  const info = ed.cells[mxKey(t, bulb)], nk = mxKey(t, bulb);
  const layer = () => (t.fixture_effects || {})[bulb] || {};
  const own = () => { t.fixture_effects = t.fixture_effects || {}; return (t.fixture_effects[bulb] = t.fixture_effects[bulb] || {}); };
  const prune = () => {
    const fx = t.fixture_effects;
    if (fx && fx[bulb] && !Object.keys(fx[bulb]).length) delete fx[bulb];
    if (fx && !Object.keys(fx).length) delete t.fixture_effects;
  };
  const cell = el("div", undefined, "mx-cell"), pending = [EFFECTS, ed].filter((x) => x.dirty());
  cell.append(el("h3", bulb + (info && info.segments > 1 ? ` · ${info.segments} segments` : "")), mxSummary(info));
  if (pending.length) cell.querySelector("h3").append(" ", el("span", "Unsaved", "pill warn"));
  const opened = !!ed.open[nk] || hasKeys(layer());
  if (opened) {
    const bi = ed.bulbInfo[bulb], kinds = info ? info.kinds : (bi ? bi.kinds : ["pulse"]);
    cell.append(layerFields(ed, {label: `${t.abbr} on ${bulb}`, layer, own, prune, kinds, kind: layer().kind || (info ? info.kind : "pulse"), info,
                                 redraw: () => edDraw(ed), touched: () => edSaveBar(ed)}));
  }
  const actions = el("div", undefined, "mx-actions");
  const test = el("button", ed.note[nk] && ed.note[nk].busy ? "Playing…" : (pending.length ? "Save & test" : "Test"), "primary"); test.type = "button";
  test.disabled = !!busy[bulb] || !info || ed.saving;
  test.addEventListener("click", () => pending.length ? saveThen(pending, () => testCell(ed, t, bulb)) : testCell(ed, t, bulb));
  actions.append(test);
  const toggle = el("button", hasKeys(layer()) ? "Clear override" : (opened ? "Close" : "Customize")); toggle.type = "button";
  toggle.addEventListener("click", () => {
    if (hasKeys(layer())) { delete t.fixture_effects[bulb]; prune(); ed.open[nk] = false; }
    else ed.open[nk] = !opened;
    edDraw(ed);
  });
  actions.append(toggle);
  cell.append(actions);
  const n = ed.note[nk]; if (n && n.text) cell.append(el("div", n.text, "help " + n.cls));
  return cell;
}
// A team's own effect (the team layer): kind and parameters for every bulb it uses, where the bulbs allow it.
function mxTeamRow(ed, t) {
  const nk = "team:" + t.league + ":" + t.id, box = el("div", undefined, "mx-teameffect");
  const layer = () => t.effect || {};
  const own = () => (t.effect = t.effect || {});
  const prune = () => { if (t.effect && !Object.keys(t.effect).length) delete t.effect; };
  const sets = t.bulbs.map((b) => (ed.bulbInfo[b] ? ed.bulbInfo[b].kinds : ["pulse"]));
  const kinds = sets.length ? sets[0].filter((k) => sets.every((s) => s.includes(k))) : ["pulse"];
  const opened = !!ed.open[nk] || hasKeys(layer());
  const head = el("div", undefined, "mx-actions");
  head.append(el("span", hasKeys(layer()) ? "Team effect: customized" : "Team effect: same as the default", "muted"));
  const toggle = el("button", hasKeys(layer()) ? "Clear" : (opened ? "Close" : "Customize")); toggle.type = "button";
  toggle.addEventListener("click", () => { if (hasKeys(layer())) { delete t.effect; ed.open[nk] = false; } else ed.open[nk] = !opened; edDraw(ed); });
  head.append(toggle); box.append(head);
  if (opened) box.append(layerFields(ed, {label: `${t.abbr} (all its bulbs)`, layer, own, prune, kinds, kind: layer().kind || "pulse", info: null, colors: false,
                                          redraw: () => edDraw(ed), touched: () => edSaveBar(ed)}),
                         el("div", "Colors for this team are set on the Teams screen.", "muted help"));
  return box;
}
async function testCell(ed, t, bulb) {
  const nk = mxKey(t, bulb);
  ed.note[nk] = {busy: true}; busy[bulb] = true; edDraw(ed); renderBulbs();
  let note;
  try {
    const r = await fetch("api/effects/test", {method: "POST", headers: {"X-Gameday": "1", "Content-Type": "application/json"},
      body: JSON.stringify({league: t.league, id: t.id, bulb})});
    const body = await r.json().catch(() => ({}));
    note = r.ok ? {text: body.dry_run ? "Dry-run: nothing was sent to the bulb." : `Played (${body.duration_s}s).`, cls: "ok"}
               : {text: body.detail || `HTTP ${r.status}`, cls: "bad"};
  } catch (e) { note = {text: "Request failed: " + e.message, cls: "bad"}; }
  busy[bulb] = false; ed.note[nk] = note; edDraw(ed); renderBulbs();
  setTimeout(() => { if (ed.note[nk] === note) { delete ed.note[nk]; edDraw(ed); } }, 8000);
}
function drawMatrix(ed, body) {
  if (!ed.draft.length) { body.replaceChildren(el("p", "No teams followed yet. Follow a team on the Teams screen first.", "empty")); return; }
  body.replaceChildren(...ed.draft.map((t, i) => {
    const box = el("div", undefined, "mx-team"), head = el("strong", `${t.abbr} (${t.league.toUpperCase()})`);
    box.append(head);
    (ed.errors["#" + i] || []).forEach((m) => box.append(el("div", m, "err")));
    box.append(mxTeamRow(ed, t));
    const cells = el("div", undefined, "mx-cells");
    t.bulbs.forEach((b) => cells.append(mxCell(ed, t, i, b)));
    box.append(cells);
    return box;
  }));
}

// ---- Advanced screen ----------------------------------------------------------------------
// Timings. The 10 s poll floor is enforced by the server too, so it holds even if this page is bypassed.
const ADV_DEFAULTS = {poll_live_s: 15, poll_break_s: 60, schedule_sync_hours: 6, watch_lead_min: 10, pulse_cooldown_s: 10, final_hold_min: 30};
const ADV_FIELDS = [
  ["poll_live_s", {label: "Poll while a game is live", unit: "seconds", min: 10, help: "How often to ask ESPN during play. 10 seconds is the lowest allowed, to be kind to ESPN."}],
  ["poll_break_s", {label: "Poll during breaks", unit: "seconds", min: 10, help: "Halftime, intermissions and the wait before kickoff. Also at least 10 seconds."}],
  ["schedule_sync_hours", {label: "Refresh schedules every", unit: "hours", min: 0.1, step: 0.1, help: "How often to reload each followed team's upcoming games."}],
  ["watch_lead_min", {label: "Start watching before kickoff", unit: "minutes", min: 0, help: "Polling begins this long before a game's start time."}],
  ["pulse_cooldown_s", {label: "Pulse and Test cooldown", unit: "seconds", min: 1, help: "Wait between test pulses on the same bulb."}],
  ["final_hold_min", {label: "Keep a finished game on the Scoreboard", unit: "minutes", min: 0, help: "How long the final score stays up before the next game replaces it."}],
];
function drawAdvanced(ed, body) {
  const reset = el("button", "Reset to defaults"); reset.type = "button";
  reset.addEventListener("click", () => { Object.assign(ed.draft, ADV_DEFAULTS); ed.errors = {}; ed.banner = null; edDraw(ed); });
  const m = ed.machine, note = el("p", undefined, "muted help");
  note.textContent = m ? `Set in config.toml, not here: dispatch_enabled (${m.dispatch_enabled ? "on" : "off"}) and the web address (${m.web.host}:${m.web.port}). Edit the file and restart to change them.` : "";
  body.replaceChildren(...ADV_FIELDS.map(([key, o]) => numField(ed, key, o)), reset, note);
}
const ADVANCED = sectionEditor({section: "advanced", id: "advanced", fields: Object.keys(ADV_DEFAULTS), draw: drawAdvanced});

// ---- Bulbs screen -------------------------------------------------------------------------
// Rows come from the `bulbs` section (signing keys are never sent to the browser). A new key typed
// here is held in b._key until Save; an untouched key is left out of the PUT so the server keeps it.
const DEFAULT_PORTS = {wiz: 38899, govee: 4003};
const KIND_LABEL = {wiz: "WiZ", govee: "Govee"};
const defaultPort = (kind) => DEFAULT_PORTS[kind || "wiz"];
const ADD = {name: "", ip: "", mac: "", port: "", kind: "wiz"};
const BD = {busy: false, found: null, note: ""};
const BR = {editing: null, error: "", busy: false};  // renaming a saved bulb
function bulbPayload(draft) {
  return draft.map((b) => {
    const out = {name: b.name, ip: b.ip, mac: b.mac ? b.mac : null, kind: b.kind || "wiz", port: b.port === "" || b.port === null ? defaultPort(b.kind) : Number(b.port),
                 segments: (b.kind || "wiz") === "govee" && b.segments !== "" && b.segments != null ? Number(b.segments) : 1};
    if (b._clear) out.signing_key = null; else if (b._key) out.signing_key = b._key;
    return out;
  });
}
const freeBulbName = (ed) => { let n = ed.draft.length + 1; while (ed.draft.some((b) => b.name === "bulb-" + n)) n++; return "bulb-" + n; };
function bulbText(ed, i, obj, key, label, o) {
  const wrap = el("label", undefined, "colorfield"), input = document.createElement("input");
  input.type = (o && o.type) || "text"; input.value = obj[key] === null || obj[key] === undefined ? "" : obj[key];
  if (o && o.size) input.size = o.size;
  if (o && o.auto) input.autocomplete = o.auto;
  input.addEventListener("input", () => { obj[key] = input.value; delete ed.errors["#" + i]; wrap.parentElement && wrap.closest(".teamrow").querySelectorAll(".err").forEach((e) => e.remove()); edSaveBar(ed); });
  wrap.append(el("span", label, "muted"), input);
  return wrap;
}
// Renaming also renames the bulb inside every team that uses it, in one server step.
function renameForm(ed, b) {
  const wrap = el("span", undefined, "colorfield"), input = document.createElement("input");
  input.type = "text"; input.className = "rename-in"; input.value = b.name; input.size = 16;
  input.setAttribute("aria-label", `New name for ${b.name}`);
  const ok = el("button", BR.busy ? "Renaming…" : "Rename", "primary"); ok.type = "button"; ok.disabled = BR.busy;
  const cancel = el("button", "Cancel"); cancel.type = "button"; cancel.disabled = BR.busy;
  const go = () => renameBulb(ed, b.name, input.value);
  ok.addEventListener("click", go);
  input.addEventListener("keydown", (e) => { if (e.key === "Enter") go(); else if (e.key === "Escape") cancel.click(); });
  cancel.addEventListener("click", () => { BR.editing = null; BR.error = ""; edDraw(ed); });
  wrap.append(input, ok, cancel);
  if (BR.error) wrap.append(el("span", BR.error, "err"));
  return wrap;
}
async function renameBulb(ed, from, to) {
  if (!to.trim() || to.trim() === from) { BR.editing = null; BR.error = ""; edDraw(ed); return; }
  BR.busy = true; BR.error = ""; edDraw(ed);
  try {
    const r = await fetch(`api/bulbs/${encodeURIComponent(from)}/rename`, {method: "POST", headers: {"X-Gameday": "1", "Content-Type": "application/json"}, body: JSON.stringify({to, revisions: {bulbs: ed.revision, teams: ed.teamsRevision}})});
    const body = await r.json().catch(() => ({}));
    if (r.ok) {
      BR.editing = null; BR.busy = false;
      await edLoad(ed); ed.banner = {cls: "ok", text: `Renamed to ${to.trim()}. Teams using it were updated too.`}; edDraw(ed);
      refresh(); return;
    }
    BR.error = r.status === 422 ? (body.errors || []).map((e) => e.message).join("; ")
             : r.status === 409 ? "Bulbs or teams changed somewhere else. Cancel and reload." : (body.detail || `HTTP ${r.status}`);
  } catch (e) { BR.error = "Request failed: " + e.message; }
  BR.busy = false; edDraw(ed);
  const i = $("bulbs-body").querySelector(".rename-in"); if (i) i.focus();
}
function bulbRow(ed, b, i) {
  const row = el("div", undefined, "teamrow"), head = el("div", undefined, "teamhead");
  const saved = !b._new, live = lastStatus && lastStatus.bulbs.find((x) => x.name === b.name);
  if (saved && BR.editing === b.name) head.append(renameForm(ed, b));
  else if (saved) {
    head.append(el("strong", b.name));
    const rn = el("button", "Rename", "rename-btn"); rn.type = "button"; rn.disabled = ed.dirty();
    rn.title = ed.dirty() ? "Save or discard your other changes first" : "Give this bulb a different name";
    rn.setAttribute("aria-label", `Rename ${b.name}`);
    rn.addEventListener("click", () => { BR.editing = b.name; BR.error = ""; edDraw(ed); const i = $("bulbs-body").querySelector(".rename-in"); if (i) { i.focus(); i.select(); } });
    head.append(rn);
  } else head.append(bulbText(ed, i, b, "name", "Name", {size: 14}), el("span", "not saved yet", "pill warn"));
  const reach = !saved || !live ? "" : (live.ping_ms === null ? "unreachable" : `${live.ping_ms} ms`);
  head.append(el("span", reach, "grow " + (live && live.ping_ms === null ? "bad" : "ok")));
  const test = el("button", busy[b.name] ? "Pulsing…" : "Ping & test"); test.type = "button";
  test.disabled = !saved || !!busy[b.name]; test.title = saved ? "Flash this bulb with its team pattern, then restore it" : "Save the bulb first";
  test.addEventListener("click", () => pulse(b.name));
  const users = saved ? ed.teams.filter((t) => t.bulbs.includes(b.name)).map((t) => t.abbr) : [];
  const rm = el("button", "Remove", "danger"); rm.type = "button"; rm.disabled = users.length > 0;
  rm.title = users.length ? `Used by ${users.join(", ")}: change those teams first` : "";
  rm.setAttribute("aria-label", `Remove ${b.name}`);
  const useNote = users.length ? el("div", undefined, "help warn") : null;
  if (useNote) {
    useNote.id = `bulb-use-${i}`; rm.setAttribute("aria-describedby", useNote.id);
    const go = document.createElement("a"); go.href = "#/teams"; go.textContent = "Teams";
    useNote.append(`In use by ${users.join(", ")}. Take it off those teams to remove it: `, go);
  }
  rm.addEventListener("click", () => { ed.draft.splice(i, 1); ed.errors = {}; edDraw(ed); });
  if (saved || b.kind) head.insertBefore(el("span", KIND_LABEL[b.kind || "wiz"] || b.kind, "pill"), head.firstChild);
  head.append(test, rm); row.append(head);
  if (useNote) row.append(useNote);
  const fields = el("div", undefined, "fields");
  fields.append(bulbText(ed, i, b, "ip", "IP", {size: 14}), bulbText(ed, i, b, "mac", "MAC (optional)", {size: 14}), bulbText(ed, i, b, "port", "Port", {size: 6}));
  if ((b.kind || "wiz") !== "wiz") {
    fields.append(bulbText(ed, i, b, "segments", "Segments", {size: 4, type: "number"}));
    row.append(fields, el("div", "Segments you can color separately along the strip. Chase needs more than 1; leave 1 for a whole-strip color.", "muted help"));
    (ed.errors["#" + i] || []).forEach((m) => row.append(el("div", m, "err")));
    return row;
  }
  const key = el("span", undefined, "colorfield");
  key.append(el("span", "Signing key", "muted"));
  const kin = document.createElement("input"); kin.type = "password"; kin.autocomplete = "new-password"; kin.size = 14;
  kin.placeholder = b.has_signing_key && !b._clear ? "key set; type to replace" : "none";
  kin.value = b._key || "";
  kin.addEventListener("input", () => { b._key = kin.value; if (kin.value) b._clear = false; edSaveBar(ed); });
  key.append(kin);
  if (b.has_signing_key && !b._clear) {
    const clr = el("button", "Remove key"); clr.type = "button";
    clr.addEventListener("click", () => { b._clear = true; b._key = ""; edDraw(ed); });
    key.append(clr);
  } else if (b._clear) key.append(el("span", "key will be removed on Save", "warn"));
  fields.append(key); row.append(fields);
  (ed.errors["#" + i] || []).forEach((m) => row.append(el("div", m, "err")));
  return row;
}
function addBulb(ed, b) {
  ed.draft.push({name: b.name, ip: b.ip, mac: b.mac || null, kind: b.kind || "wiz", port: b.port === "" ? defaultPort(b.kind) : Number(b.port), segments: b.segments || 1, has_signing_key: false, _new: true});
  ed.errors = {}; ed.banner = null; edDraw(ed);
}
function drawBulbs(ed, body) {
  body.replaceChildren(...(ed.draft.length ? ed.draft.map((b, i) => bulbRow(ed, b, i)) : [el("p", "No bulbs yet. Find or add one below.", "empty")]));
  renderBulbAdd();
}
async function runDiscover() {
  BD.busy = true; BD.note = ""; renderBulbAdd();
  try {
    const r = await fetch("api/bulbs/discover", {method: "POST", headers: {"X-Gameday": "1"}});
    const body = await r.json().catch(() => ({}));
    if (r.ok) { BD.found = body; BD.note = body.length ? "" : "No bulbs answered. Check the bulb is on and on this network, or add it by IP."; }
    else { BD.found = null; BD.note = body.detail || `HTTP ${r.status}`; }
  } catch (e) { BD.found = null; BD.note = "Request failed: " + e.message; }
  BD.busy = false; renderBulbAdd();
}
function renderBulbAdd() {
  const box = $("bulbs-add"), ed = BULBS; if (!ed.loaded) { box.replaceChildren(); return; }
  const find = el("button", BD.busy ? "Searching… (about 5 s)" : "Find bulbs on the network"); find.type = "button"; find.disabled = BD.busy;
  find.addEventListener("click", runDiscover);
  const parts = [find];
  if (BD.note) parts.push(el("div", BD.note, "err"));
  (BD.found || []).forEach((f) => {
    if (f.moved) {  // saved under another address: offer to fix it, not to add it again
      const r = el("div", undefined, "result"), text = el("span", `${f.name} is now at ${f.ip} (was ${f.stored_ip}). A DHCP reservation in your router keeps it from moving again.`, "grow warn");
      const fix = el("button", "Update address", "primary"); fix.type = "button"; fix.disabled = ed.saving;
      fix.addEventListener("click", async () => {
        const b = ed.draft.find((x) => x.name === f.name);
        if (!b) return;
        b.ip = f.ip; f.moved = false; f.stored_ip = f.ip;
        await edSave(ed);
        renderBulbAdd();
      });
      r.append(text, fix); parts.push(r); return;
    }
    const taken = f.known || ed.draft.some((b) => b.ip === f.ip || (b.mac && b.mac === f.mac));
    const r = el("div", undefined, "result"), text = el("span", `${KIND_LABEL[f.kind] || "WiZ"}  ·  ${f.ip}  ·  ${f.mac}${f.name ? "  ·  " + f.name : ""}`, "grow");
    const add = el("button", taken ? "Added" : "Add"); add.type = "button"; add.disabled = taken;
    add.addEventListener("click", () => addBulb(ed, {name: freeBulbName(ed), ip: f.ip, mac: f.mac, kind: f.kind, port: "", segments: f.segments}));
    r.append(text, add); parts.push(r);
  });
  const form = el("div", undefined, "fields"); form.style.marginTop = "14px";
  const inp = (key, label, size) => {
    const w = el("label", undefined, "colorfield"), i = document.createElement("input");
    i.type = "text"; i.size = size; i.value = ADD[key]; i.addEventListener("input", () => { ADD[key] = i.value; });
    w.append(el("span", label, "muted"), i); return w;
  };
  const go = el("button", "Add by IP", "primary"); go.type = "button";
  go.addEventListener("click", async () => {
    const miss = !ADD.name.trim() ? "a name" : !ADD.ip.trim() ? "an IP address" : "";
    if (miss) { BD.note = `Add by IP needs ${miss}.`; renderBulbAdd(); return; }
    let found = {};  // a Govee strip: ask the network which model it is, so its segments are filled in
    if (ADD.kind === "govee") {
      BD.busy = true; BD.note = "Looking up the model…"; renderBulbAdd();
      try {
        const r = await fetch("api/bulbs/discover", {method: "POST", headers: {"X-Gameday": "1"}});
        if (r.ok) found = (await r.json()).find((x) => x.ip === ADD.ip.trim()) || {};
      } catch (e) { /* not found: the bulb is added with 1 segment and the field stays editable */ }
      BD.busy = false;
    }
    addBulb(ed, {name: ADD.name.trim(), ip: ADD.ip.trim(), mac: ADD.mac.trim() || found.mac || "", kind: ADD.kind, port: ADD.port.trim(), segments: found.segments});
    ADD.name = ADD.ip = ADD.mac = ADD.port = ""; BD.note = ""; renderBulbAdd();
  });
  const kw = el("label", undefined, "colorfield"), ks = document.createElement("select");
  Object.entries(KIND_LABEL).forEach(([v, t]) => { const o = document.createElement("option"); o.value = v; o.textContent = t; ks.append(o); });
  ks.value = ADD.kind; ks.addEventListener("change", () => { ADD.kind = ks.value; });
  kw.append(el("span", "Brand", "muted"), ks);
  form.append(kw, inp("name", "Name", 12), inp("ip", "IP", 14), inp("mac", "MAC (optional)", 14), inp("port", "Port", 6), go);
  parts.push(form);
  box.replaceChildren(...parts);
}
const BULBS = sectionEditor({section: "bulbs", id: "bulbs", fields: [], draw: drawBulbs});
BULBS.indexed = true; BULBS.payload = bulbPayload;
BULBS.after = () => document.querySelectorAll(".rename-btn").forEach((b) => { b.disabled = BULBS.dirty(); });
function bulbsRefresh() {  // keep reachability and test results current without stealing focus from a field
  if (location.hash !== "#/bulbs" || !BULBS.loaded || BULBS.saving) return;
  const a = document.activeElement;
  if (a && $("bulbs-body").contains(a) && a.tagName === "INPUT") return;
  if (BR.editing) return;
  drawBulbs(BULBS, $("bulbs-body"));
}

// ---- Lights screen: set a bulb's steady state (not an effect) ------------------------------------
// Controls apply when released (not while dragging); the server allows one change per bulb per half second.
const LS = {states: {}, notes: {}, names: [], loaded: false, token: 0, pending: new Set()};
const lightUrl = (n) => `api/bulbs/${encodeURIComponent(n)}/state`;
async function lightsLoad() {
  // Each bulb shows as soon as it answers: one that is off or unplugged must not hold up the rest.
  try {
    const s = await getJson("api/settings");
    LS.names = s.sections.bulbs.value.map((b) => b.name);
    LS.loaded = true;
  } catch (e) { $("lights-banner").replaceChildren(el("div", "Couldn't load the lights: " + e.message, "banner bad")); return; }
  drawLights();
  LS.names.forEach(async (n) => {
    if (LS.pending.has(n)) return;  // its last read has not finished; do not stack another behind it
    LS.pending.add(n);
    try { LS.states[n] = await getJson(lightUrl(n)); } catch (e) { LS.states[n] = {error: e.message}; }
    LS.pending.delete(n);
    if (location.hash === "#/lights") drawLights();
  });
}
async function lightsPut(name, body) {
  delete LS.notes[name];
  try {
    const r = await fetch(lightUrl(name), {method: "PUT", headers: {"X-Gameday": "1", "Content-Type": "application/json"}, body: JSON.stringify(body)});
    const j = await r.json().catch(() => ({}));
    if (r.ok) { if (j.dry_run) LS.notes[name] = {text: "Dry-run: nothing was sent to the bulb.", cls: "muted"}; }
    else LS.notes[name] = {text: j.detail || `HTTP ${r.status}`, cls: "bad"};
  } catch (e) { LS.notes[name] = {text: "Request failed: " + e.message, cls: "bad"}; }
  try { LS.states[name] = await getJson(lightUrl(name)); } catch (e) { /* keep the last known state */ }
  drawLights();
}
function lightCard(name) {
  const st = LS.states[name] || {}, card = el("div", undefined, "light"), head = el("div", undefined, "light-head");
  head.append(el("strong", name), el("span", "", "grow"));
  if (!LS.states[name]) { card.append(head, el("div", "Reading…", "muted help")); return card; }
  if (st.error) { card.append(head, el("div", st.error, "err")); return card; }
  const off = busy[name], put = (b) => lightsPut(name, b);
  const on = document.createElement("input"); on.type = "checkbox"; on.checked = !!st.on; on.disabled = !!off;
  on.setAttribute("aria-label", `${name} on`); on.addEventListener("change", () => put({on: on.checked}));
  const sw = el("label", undefined, "colorfield"); sw.append(on, el("span", st.on ? "On" : "Off"));
  head.append(sw);
  const bri = document.createElement("input"); bri.type = "range"; bri.min = 1; bri.max = 100; bri.disabled = !!off;
  bri.value = st.brightness ? Math.max(1, Math.round(st.brightness * 100 / 255)) : 100; bri.setAttribute("aria-label", `${name} brightness`);
  const briOut = el("span", bri.value + "%", "muted"); bri.addEventListener("input", () => { briOut.textContent = bri.value + "%"; });
  bri.addEventListener("change", () => put({on: true, brightness: Math.max(1, Math.round(Number(bri.value) * 255 / 100))}));
  const col = document.createElement("input"); col.type = "color"; col.value = st.color || "#ffffff"; col.disabled = !!off;
  col.setAttribute("aria-label", `${name} color`); col.addEventListener("change", () => put({on: true, color: col.value}));
  const wht = document.createElement("input"); wht.type = "range"; wht.min = 2000; wht.max = 6500; wht.step = 100; wht.disabled = !!off;
  wht.value = st.color_temp_k || 4000; wht.setAttribute("aria-label", `${name} white temperature`);
  const whtOut = el("span", wht.value + " K", "muted"); wht.addEventListener("input", () => { whtOut.textContent = wht.value + " K"; });
  wht.addEventListener("change", () => put({on: true, color_temp_k: Number(wht.value)}));
  const rows = [["Brightness", [bri, briOut]], ["Color", [col, el("span", st.color ? "showing" : "", "muted")]], ["White", [wht, whtOut, el("span", st.color_temp_k ? "showing" : "", "muted")]]];
  card.append(head, ...rows.map(([label, kids]) => { const r = el("div", undefined, "light-row"); r.append(el("label", label), ...kids); return r; }));
  if (off) card.append(el("div", "An effect is playing; try again in a moment.", "muted help"));
  const n = LS.notes[name]; if (n) card.append(el("div", n.text, "help " + n.cls));
  return card;
}
function drawLights() {
  const body = $("lights-body");
  if (!LS.loaded) return;
  if (!LS.names.length) { body.replaceChildren(el("p", "No bulbs configured. Add one on the Bulbs screen.", "empty")); return; }
  body.replaceChildren(...LS.names.map(lightCard));
}
setInterval(() => {  // keep the shown state current without stealing a control mid-drag
  if (location.hash !== "#/lights") return;
  const a = document.activeElement;
  if (a && $("lights-body").contains(a)) return;
  lightsLoad();
}, 10000);

// ---- Calibrate screen: say when a score showed on your TV, then use the measured delay ------------
const CAL = {data: null, practice: null, sig: "", note: null, busy: false};
const calFmt = (v) => (v === null || v === undefined ? "–" : `${Number(v).toFixed(1)} s`);
async function calLoad() {
  try {
    [CAL.data, CAL.practice] = await Promise.all([getJson("api/calibration"), getJson("api/practice")]);
    if (CAL.note && CAL.note.load) CAL.note = null;  // a failed load clears itself once a load works
  } catch (e) { CAL.note = {cls: "bad", text: "Couldn't load: " + e.message, load: true}; }
  const sig = JSON.stringify([CAL.data, CAL.practice, CAL.note]);
  if (sig !== CAL.sig) { CAL.sig = sig; calDraw(); }
}
async function calMark(key, undo) {
  CAL.note = null;
  try {
    const r = await fetch(`api/events/${encodeURIComponent(key)}/seen`, {method: undo ? "DELETE" : "POST", headers: {"X-Gameday": "1"}});
    if (!r.ok) { const b = await r.json().catch(() => ({})); CAL.note = {cls: "bad", text: b.detail || `HTTP ${r.status}`}; }
  } catch (e) { CAL.note = {cls: "bad", text: "Request failed: " + e.message}; }
  await calLoad();
}
async function calPractice(active) {
  CAL.busy = true; CAL.note = null; calDraw();
  try {
    const r = await fetch("api/practice", {method: "PUT", headers: {"X-Gameday": "1", "Content-Type": "application/json"}, body: JSON.stringify({active})});
    const b = await r.json().catch(() => ({}));
    if (!r.ok) CAL.note = {cls: "bad", text: b.detail || `HTTP ${r.status}`};
  } catch (e) { CAL.note = {cls: "bad", text: "Request failed: " + e.message}; }
  CAL.busy = false; await calLoad(); CAL.sig = ""; calDraw();
}
// The plays' suggestion is only a starting point: it sets the general delay, never a kind's own delay.
async function calUsePlays(seconds) {
  CAL.busy = true; CAL.note = null; calDraw();
  try {
    const s = await getJson("api/settings");
    const value = {...s.sections.household.value, delay_s: seconds};
    const r = await fetch("api/settings/household", {method: "PUT", headers: {"X-Gameday": "1", "If-Match": String(s.sections.household.revision), "Content-Type": "application/json"}, body: JSON.stringify({value})});
    const b = await r.json().catch(() => ({}));
    CAL.note = r.ok ? {cls: "ok", text: `Starting delay set to ${seconds} s. Mark the first real score too: it fine-tunes this, and touchdowns and extra points can differ by a few seconds.`}
                    : {cls: "bad", text: b.detail || (b.errors || []).map((e) => e.message).join("; ") || `HTTP ${r.status}`};
  } catch (e) { CAL.note = {cls: "bad", text: "Request failed: " + e.message}; }
  CAL.busy = false; await calLoad(); CAL.sig = ""; calDraw();
}
function calDrawPractice(d, pr) {
  const box = $("calibrate-practice"), parts = [];
  const head = el("div", undefined, "mx-actions");
  const on = pr && pr.active;
  const sw = el("button", on ? "Practice mode: on. Turn off" : "Start practice mode", on ? "" : "primary"); sw.type = "button";
  sw.disabled = CAL.busy || !pr || (!on && !pr.available);
  sw.addEventListener("click", () => calPractice(!on));
  head.append(sw);
  if (on) head.append(el("span", `on until ${new Date(pr.until).toLocaleTimeString([], {hour: "numeric", minute: "2-digit"})}`, "ok"));
  else if (pr && !pr.available) head.append(el("span", "Starts working when a followed game is about to begin or is live.", "muted"));
  parts.push(head);
  parts.push(el("div", "Lists each play as it is detected. Press the button when you see the same play on TV. Lights do not flash for plays. Plays get you close; touchdowns and extra points can differ by a few seconds, so mark the first real score too.", "muted help"));
  const ps = d.play_summary;
  if (ps && ps.n) {
    const row = el("div", undefined, "mx-actions");
    if (ps.n < 3) row.append(el("span", `${ps.n} play${ps.n === 1 ? "" : "s"} marked: mark a few more plays.`));
    else {
      row.append(el("span", `Plays: ${ps.n} readings · median ${calFmt(ps.median_s)} · from ${calFmt(ps.min_s)} to ${calFmt(ps.max_s)}`));
      const over = ps.suggested_delay_s > 180, same = Number(d.delay_s) === ps.suggested_delay_s;
      const use = el("button", same ? "Already matches" : `Use ${ps.suggested_delay_s} s as starting delay`, "primary"); use.type = "button";
      use.disabled = CAL.busy || same || over; use.addEventListener("click", () => calUsePlays(ps.suggested_delay_s));
      row.append(use);
      if (over) row.append(el("span", "Over the 180 s limit: probably a late press. Undo it below.", "warn"));
    }
    parts.push(row);
  }
  if (on || d.plays.length) {
    const ul = el("ul");
    ul.append(...(d.plays.length ? d.plays.map((p) => {
      const li = el("li"), left = el("span", `${fmt(p.detected_at)} · ${p.text || "Play"}${p.period ? ` · Q${p.period}${p.clock ? " " + p.clock : ""}` : ""}`);
      const right = el("span", undefined, "bulb-right");
      if (p.seen_at) {
        right.append(el("span", `lag ${calFmt(p.lag_s)}`, "ok"));
        const undo = el("button", "Undo"); undo.type = "button"; undo.addEventListener("click", () => calMark(p.key, true)); right.append(undo);
      } else {
        const seen = el("button", "I see it on TV", "primary"); seen.type = "button"; seen.addEventListener("click", () => calMark(p.key, false)); right.append(seen);
      }
      li.append(left, right); return li;
    }) : [el("li", "Waiting for the next play… (a play drops off after a few minutes, or once you mark a later one)", "empty")]));
    parts.push(ul);
  }
  box.replaceChildren(...parts);
}
const CAL_NAMES = {TD: "Touchdown", PAT: "Extra point", FG: "Field goal", "TD+PAT": "Touchdown + extra point",
                   "TD+2pt": "Touchdown + 2-point", "safety/2pt": "Safety or 2-point", score: "Goal"};
const calName = (label) => CAL_NAMES[label] || label;
// Apply suggested delays. The kind with the most readings sets the default delay (everything without its own
// setting follows it); every other kind gets its own. changes: [{label, seconds, main}]
async function calUse(changes) {
  CAL.busy = true; CAL.note = null; calDraw();
  try {
    const s = await getJson("api/settings");
    const value = {...s.sections.household.value}, by = {...(value.delay_by_label || {})};
    changes.forEach((c) => { if (c.main) { value.delay_s = c.seconds; delete by[c.label]; } else by[c.label] = c.seconds; });
    if (Object.keys(by).length) value.delay_by_label = by; else delete value.delay_by_label;
    const r = await fetch("api/settings/household", {method: "PUT", headers: {"X-Gameday": "1", "If-Match": String(s.sections.household.revision), "Content-Type": "application/json"}, body: JSON.stringify({value})});
    const b = await r.json().catch(() => ({}));
    CAL.note = r.ok ? {cls: "ok", text: "Delays saved: " + changes.map((c) => `${calName(c.label)} ${c.seconds} s`).join(", ") + ". They apply to the next score."}
                    : {cls: "bad", text: b.detail || (b.errors || []).map((e) => e.message).join("; ") || `HTTP ${r.status}`};
  } catch (e) { CAL.note = {cls: "bad", text: "Request failed: " + e.message}; }
  CAL.busy = false; await calLoad(); CAL.sig = ""; calDraw();
}
function calDraw() {
  const d = CAL.data, sum = $("calibrate-summary"), list = $("calibrate-list"), banner = $("calibrate-banner");
  banner.replaceChildren(...(CAL.note ? [el("div", CAL.note.text, "banner " + CAL.note.cls)] : []));
  if (!d) { sum.replaceChildren(el("p", "Loading…", "empty")); return; }
  calDrawPractice(d, CAL.practice);
  const parts = [el("div", `Delay now: ${d.delay_s} seconds`, "next-count")];
  if (d.n) {
    const main = d.by_label[0].label;  // the kind with the most readings sets the default delay
    const table = document.createElement("table"), head = document.createElement("tr");
    ["Score", "Readings", "Median", "Range", "Delay now", ""].forEach((t) => head.append(el("th", t)));
    table.append(head);
    d.by_label.forEach((g) => {
      const same = Number(g.delay_s) === g.suggested_delay_s, over = g.suggested_delay_s > 180;  // the Settings slider stops at 180 s
      const tr = document.createElement("tr"), act = el("td");
      const use = el("button", same ? "Matches" : `Use ${g.suggested_delay_s} s`, same ? "" : "primary"); use.type = "button";
      use.disabled = CAL.busy || same || over; use.addEventListener("click", () => calUse([{label: g.label, seconds: g.suggested_delay_s, main: g.label === main}]));
      act.append(use);
      if (over) act.append(el("span", " over 180 s: probably a late press, undo it below", "warn"));
      tr.append(el("td", calName(g.label)), el("td", String(g.n), "num"), el("td", calFmt(g.median_s), "num"),
                el("td", `${Number(g.min_s).toFixed(1)}–${calFmt(g.max_s)}`, "num"),
                el("td", `${g.delay_s} s${g.has_own_delay ? "" : " (default)"}`, "num"), act);
      table.append(tr);
    });
    const wrap = el("div", undefined, "scroll"); wrap.append(table); parts.push(wrap);
    const todo = d.by_label.filter((g) => Number(g.delay_s) !== g.suggested_delay_s && g.suggested_delay_s <= 180);
    if (d.by_label.length > 1 && todo.length > 1) {
      const all = el("button", "Use all of these", "primary"); all.type = "button"; all.disabled = CAL.busy;
      all.addEventListener("click", () => calUse(todo.map((g) => ({label: g.label, seconds: g.suggested_delay_s, main: g.label === main}))));
      parts.push(all);
    }
    parts.push(el("div", `${d.n < 3 ? "A few more readings makes it steadier. " : ""}Suggestions come from the slower end of the readings, so a flash is never early. Each kind of score gets its own delay because a touchdown and an extra point can lag differently.`, "muted help"));
  } else parts.push(el("div", "No readings yet. When the next score appears below, press its button the moment you see it on your TV.", "muted help"));
  sum.replaceChildren(...parts);
  list.replaceChildren(...(d.events.length ? d.events.map((e) => {
    const li = el("li"), left = el("span", `${fmt(e.detected_at)} · ${e.team} ${e.label} · ${e.game}`);
    const right = el("span", undefined, "bulb-right");
    if (e.seen_at) {
      right.append(el("span", `lag ${calFmt(e.lag_s)}`, "ok"));
      const undo = el("button", "Undo"); undo.type = "button"; undo.addEventListener("click", () => calMark(e.key, true)); right.append(undo);
    } else {
      const seen = el("button", "I see it on TV", "primary"); seen.type = "button"; seen.addEventListener("click", () => calMark(e.key, false)); right.append(seen);
    }
    li.append(left, right); return li;
  }) : [el("li", "No scores to mark. They appear here as the app detects them during a game, and drop off after a few minutes or once you mark a later one. Their readings still count.", "empty")]));
}
setInterval(() => { if (location.hash === "#/calibrate") calLoad(); }, 3000);
