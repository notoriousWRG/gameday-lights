// ---- navigation ---------------------------------------------------------------------------
// One entry per screen; a screen's `show` runs whenever it is opened.
const ROUTES = {
  "#/status": {view: "view-status", tab: "tab-status"},
  "#/teams": {view: "view-teams", tab: "tab-teams", show() { if (!(TM.loaded && dirty())) loadTeams(); else renderTeams(); }},
  "#/lights": {view: "view-lights", tab: "tab-lights", show: lightsLoad},
  "#/effects": {view: "view-effects", tab: "tab-effects", show() { edShow(EFFECTS); edShow(MATRIX); MATRIX.sig = ""; }},
  "#/bulbs": {view: "view-bulbs", tab: "tab-bulbs", show: () => edShow(BULBS)},
  "#/calibrate": {view: "view-calibrate", tab: "tab-calibrate", show: calLoad},
  "#/settings": {view: "view-settings", tab: "tab-settings", show: () => edShow(SETTINGS)},
  "#/advanced": {view: "view-advanced", tab: "tab-advanced", show: () => edShow(ADVANCED)},
};
function showView() {
  const route = ROUTES[location.hash] || ROUTES["#/status"];
  Object.values(ROUTES).forEach((r) => {
    $(r.view).hidden = r !== route;
    $(r.tab).setAttribute("aria-current", r === route ? "page" : "false");
  });
  if (route.show) route.show();
}
window.addEventListener("hashchange", showView);

showView(); refresh(); setInterval(refresh, 10000); setInterval(tick, 1000);
