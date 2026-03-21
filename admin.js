const LEAGUE_JSON_URL = "/data/league.json";

let fixtures = [];
let filteredFixtures = [];
let selectedFixture = null;

const $ = (id) => document.getElementById(id);

const els = {
  filterDate: $("filter-date"),
  filterGroup: $("filter-group"),
  filterSearch: $("filter-search"),
  resultsCount: $("results-count"),
  results: $("results"),
  editorCard: $("editor-card"),
  selectedSummary: $("selected-summary"),

  editStatus: $("edit-status"),
  editVenue: $("edit-venue"),
  editDate: $("edit-date"),
  editTime: $("edit-time"),

  homeTeam: $("home-team"),
  awayTeam: $("away-team"),
  homeGoals: $("home-goals"),
  homePoints: $("home-points"),
  awayGoals: $("away-goals"),
  awayPoints: $("away-points"),

  buildOverride: $("build-override"),
  resetForm: $("reset-form"),
  overrideOutput: $("override-output"),
  copyOverride: $("copy-override"),
  clearOutput: $("clear-output"),
};

init();

async function init() {
  setDefaultDate();
  bindEvents();
  await loadFixtures();
  populateGroupFilter();
  applyFilters();
}

function setDefaultDate() {
  const today = new Date();
  const y = today.getFullYear();
  const m = String(today.getMonth() + 1).padStart(2, "0");
  const d = String(today.getDate()).padStart(2, "0");
  els.filterDate.value = `${y}-${m}-${d}`;
}

function bindEvents() {
  els.filterDate.addEventListener("input", applyFilters);
  els.filterGroup.addEventListener("change", applyFilters);
  els.filterSearch.addEventListener("input", applyFilters);

  els.buildOverride.addEventListener("click", buildOverrideJson);
  els.resetForm.addEventListener("click", resetFormToSelectedFixture);
  els.copyOverride.addEventListener("click", copyOverrideJson);
  els.clearOutput.addEventListener("click", () => {
    els.overrideOutput.value = "";
  });
}

async function loadFixtures() {
  const res = await fetch(LEAGUE_JSON_URL, { cache: "no-store" });
  if (!res.ok) throw new Error(`Failed to load ${LEAGUE_JSON_URL}`);
  const data = await res.json();

  fixtures = Array.isArray(data.fixtures) ? data.fixtures.slice() : [];

  fixtures.sort((a, b) => {
    const da = `${a.date || ""} ${a.time_local || ""}`;
    const db = `${b.date || ""} ${b.time_local || ""}`;
    return da.localeCompare(db);
  });
}

function populateGroupFilter() {
  const groups = [...new Set(fixtures.map(f => f.group).filter(Boolean))].sort(naturalDivisionSort);

  for (const group of groups) {
    const opt = document.createElement("option");
    opt.value = group;
    opt.textContent = group;
    els.filterGroup.appendChild(opt);
  }
}

function naturalDivisionSort(a, b) {
  const an = parseInt(String(a).replace(/\D+/g, ""), 10);
  const bn = parseInt(String(b).replace(/\D+/g, ""), 10);
  if (!Number.isNaN(an) && !Number.isNaN(bn)) return an - bn;
  return String(a).localeCompare(String(b));
}

function applyFilters() {
  const dateVal = (els.filterDate.value || "").trim();
  const groupVal = (els.filterGroup.value || "").trim().toLowerCase();
  const q = (els.filterSearch.value || "").trim().toLowerCase();

  filteredFixtures = fixtures.filter(f => {
    if (dateVal && f.date !== dateVal) return false;
    if (groupVal && String(f.group || "").toLowerCase() !== groupVal) return false;

    if (q) {
      const hay = [
        f.home,
        f.away,
        f.group,
        f.round,
        f.venue,
        f.status,
      ].join(" ").toLowerCase();

      if (!hay.includes(q)) return false;
    }

    return true;
  });

  renderResults();
}

function renderResults() {
  els.results.innerHTML = "";

  if (!filteredFixtures.length) {
    els.resultsCount.textContent = "No matches found.";
    return;
  }

  els.resultsCount.textContent = `${filteredFixtures.length} match${filteredFixtures.length === 1 ? "" : "es"} found`;

  for (const fixture of filteredFixtures) {
    const item = document.createElement("button");
    item.type = "button";
    item.className = "match";
    if (selectedFixture && selectedFixture.id === fixture.id) {
      item.classList.add("active");
    }

    item.innerHTML = `
      <div class="match-top">
        <div class="match-title">${escapeHtml(fixture.home)} v ${escapeHtml(fixture.away)}</div>
        <div class="pill">${escapeHtml(fixture.group || "")}</div>
      </div>
      <div class="meta">
      <div class="meta">
        ${escapeHtml(formatDate(fixture.date))}${fixture.time_local ? ` · ${escapeHtml(fixture.time_local)}` : ""}${fixture.round ? ` · ${escapeHtml(fixture.round)}` : ""}
        <br>
        ${escapeHtml(fixture.venue || "Venue TBC")} · ${escapeHtml(fixture.status || "SCHEDULED")}
      </div>
    `;

    item.addEventListener("click", () => {
      selectedFixture = fixture;
      renderResults();
      openEditor(fixture);
    });

    els.results.appendChild(item);
  }
}

function openEditor(fixture) {
  els.editorCard.classList.remove("hidden");

  els.selectedSummary.innerHTML = `
    <div class="match-top">
      <div>
        <div class="match-title">${escapeHtml(fixture.home)} v ${escapeHtml(fixture.away)}</div>
        <div class="meta">${escapeHtml(fixture.group || "")}${fixture.round ? ` · ${escapeHtml(fixture.round)}` : ""}</div>
      </div>
      <div class="pill">${escapeHtml(fixture.id)}</div>
    </div>
  `;

  els.homeTeam.textContent = fixture.home || "Home";
  els.awayTeam.textContent = fixture.away || "Away";

  resetFormToFixture(fixture);
}

function resetFormToFixture(fixture) {
  els.editStatus.value = fixture.status || "SCHEDULED";
  els.editVenue.value = fixture.venue || "";
  els.editDate.value = fixture.date || "";
  els.editTime.value = fixture.time_local || "";

  els.homeGoals.value = fixture.home_goals ?? "";
  els.homePoints.value = fixture.home_points ?? "";
  els.awayGoals.value = fixture.away_goals ?? "";
  els.awayPoints.value = fixture.away_points ?? "";
}

function resetFormToSelectedFixture() {
  if (!selectedFixture) return;
  resetFormToFixture(selectedFixture);
}

function buildOverrideJson() {
  if (!selectedFixture) return;

  const changes = {};

  maybeAssign(changes, "status", els.editStatus.value, selectedFixture.status);
  maybeAssign(changes, "venue", els.editVenue.value.trim(), selectedFixture.venue || "");
  maybeAssign(changes, "date", els.editDate.value, selectedFixture.date || "");
  maybeAssign(changes, "time_local", els.editTime.value, selectedFixture.time_local || "");

  maybeAssignNumber(changes, "home_goals", els.homeGoals.value, selectedFixture.home_goals);
  maybeAssignNumber(changes, "home_points", els.homePoints.value, selectedFixture.home_points);
  maybeAssignNumber(changes, "away_goals", els.awayGoals.value, selectedFixture.away_goals);
  maybeAssignNumber(changes, "away_points", els.awayPoints.value, selectedFixture.away_points);

  const output = {
    updated_at: new Date().toISOString(),
    overrides: {
      [selectedFixture.id]: changes
    }
  };

  els.overrideOutput.value = JSON.stringify(output, null, 2);
}

function maybeAssign(obj, key, value, originalValue) {
  const normalizedValue = value ?? "";
  const normalizedOriginal = originalValue ?? "";
  if (normalizedValue !== normalizedOriginal) {
    obj[key] = normalizedValue;
  }
}

function maybeAssignNumber(obj, key, value, originalValue) {
  if (value === "") {
    if (originalValue !== null && originalValue !== undefined && originalValue !== "") {
      obj[key] = null;
    }
    return;
  }

  const num = Number(value);
  if (Number.isNaN(num)) return;

  if (num !== originalValue) {
    obj[key] = num;
  }
}

async function copyOverrideJson() {
  const text = els.overrideOutput.value.trim();
  if (!text) return;

  await navigator.clipboard.writeText(text);
  els.copyOverride.textContent = "Copied";
  setTimeout(() => {
    els.copyOverride.textContent = "Copy JSON";
  }, 1200);
}

function formatDate(isoDate) {
  if (!isoDate) return "";
  const [y, m, d] = isoDate.split("-");
  return `${d}/${m}/${y}`;
}

function escapeHtml(str) {
  return String(str ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}
