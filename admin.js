const CHAMPIONSHIP_JSON_URL = "/data/hurling_2026.json";
const STORAGE_KEY = "lgh-championship-2026-pending-v1";

let sourceData = { updated: null, matches: [] };
let fixtures = [];
let filteredFixtures = [];
let selectedKey = null;
let pending = loadPending();
let allDatesVisible = false;

const $ = (id) => document.getElementById(id);

const els = {
  filterDate: $("filter-date"),
  filterCompetition: $("filter-competition"),
  filterSearch: $("filter-search"),
  toggleAllDates: $("toggle-all-dates"),
  resultsCount: $("results-count"),
  results: $("results"),
  pendingTop: $("pending-top"),

  editorCard: $("editor-card"),
  selectedSummary: $("selected-summary"),
  homeTeam: $("home-team"),
  awayTeam: $("away-team"),
  homeGoals: $("home-goals"),
  homePoints: $("home-points"),
  awayGoals: $("away-goals"),
  awayPoints: $("away-points"),
  homeDisplay: $("home-display"),
  awayDisplay: $("away-display"),
  homeTotal: $("home-total"),
  awayTotal: $("away-total"),
  editStatus: $("edit-status"),
  editTime: $("edit-time"),
  saveNext: $("save-next"),
  saveScore: $("save-score"),
  undoMatch: $("undo-match"),
  editorNotice: $("editor-notice"),

  downloadCard: $("download-card"),
  pendingSummary: $("pending-summary"),
  clearEdits: $("clear-edits"),
  downloadJson: $("download-json"),
  copyMatch: $("copy-match"),
  copyFull: $("copy-full"),
  downloadNotice: $("download-notice"),
};

init();

async function init() {
  setDefaultDate();
  bindEvents();

  try {
    await loadFixtures();
    reconcilePending();
    populateCompetitionFilter();
    applyFilters();
    renderPendingState();
  } catch (error) {
    console.error(error);
    els.resultsCount.textContent = "Could not load Championship 2026 data.";
  }
}

function bindEvents() {
  els.filterDate.addEventListener("input", applyFilters);
  els.filterCompetition.addEventListener("change", applyFilters);
  els.filterSearch.addEventListener("input", applyFilters);
  els.toggleAllDates.addEventListener("click", toggleAllDates);

  document.querySelectorAll(".score-input").forEach((input) => {
    input.addEventListener("input", () => {
      sanitiseInput(input);
      markAsResultWhenScoring();
      updateScoreTotals();
      clearNotice(els.editorNotice);
    });
    input.addEventListener("focus", () => input.select());
  });

  document.querySelectorAll(".stepper").forEach((button) => {
    button.addEventListener("click", () => stepScore(button));
  });

  els.saveScore.addEventListener("click", () => saveSelected(false));
  els.saveNext.addEventListener("click", () => saveSelected(true));
  els.undoMatch.addEventListener("click", undoSelectedMatch);
  els.clearEdits.addEventListener("click", clearAllEdits);
  els.downloadJson.addEventListener("click", downloadUpdatedJson);
  els.copyMatch.addEventListener("click", copySelectedMatch);
  els.copyFull.addEventListener("click", copyFullJson);
}

function setDefaultDate() {
  const now = new Date();
  const year = now.getFullYear();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  els.filterDate.value = `${year}-${month}-${day}`;
}

async function loadFixtures() {
  const response = await fetch(CHAMPIONSHIP_JSON_URL, { cache: "no-store" });
  if (!response.ok) throw new Error(`Failed to load ${CHAMPIONSHIP_JSON_URL}`);

  const data = await response.json();
  if (!data || !Array.isArray(data.matches)) {
    throw new Error("Championship data does not contain a matches array");
  }

  sourceData = data;
  fixtures = data.matches.map((match, index) => ({
    index,
    key: matchKey(match),
    base: match,
  }));
}

function populateCompetitionFilter() {
  const competitions = [...new Set(
    fixtures.map((fixture) => fixture.base.competition).filter(Boolean)
  )].sort(competitionSort);

  for (const competition of competitions) {
    const option = document.createElement("option");
    option.value = competition;
    option.textContent = shortCompetitionName(competition);
    els.filterCompetition.appendChild(option);
  }
}

function competitionSort(a, b) {
  const order = [
    "Senior Hurling Championship",
    "Premier Intermediate Hurling Championship",
    "Intermediate Hurling Championship",
    "Premier Junior A Hurling Championship",
    "Junior A Hurling Championship",
    "Premier Junior B Hurling Championship",
    "Junior B Hurling Championship",
    "Premier Junior C Hurling Championship",
    "Junior C Hurling Championship",
  ];
  const aIndex = order.indexOf(a);
  const bIndex = order.indexOf(b);
  return (aIndex < 0 ? 99 : aIndex) - (bIndex < 0 ? 99 : bIndex) || a.localeCompare(b);
}

function shortCompetitionName(name) {
  return String(name || "").replace(" Hurling Championship", "");
}

function toggleAllDates() {
  allDatesVisible = !allDatesVisible;
  els.filterDate.disabled = allDatesVisible;
  els.toggleAllDates.textContent = allDatesVisible ? "Use selected date" : "Show all dates";
  applyFilters();
}

function applyFilters() {
  const dateValue = els.filterDate.value;
  const competitionValue = els.filterCompetition.value;
  const query = els.filterSearch.value.trim().toLowerCase();

  filteredFixtures = fixtures
    .filter((fixture) => {
      const match = effectiveMatch(fixture);
      if (!allDatesVisible && dateValue && match.date !== dateValue) return false;
      if (competitionValue && match.competition !== competitionValue) return false;

      if (query) {
        const haystack = [
          match.home,
          match.away,
          match.competition,
          match.group,
          match.round,
          match.venue,
        ].join(" ").toLowerCase();
        if (!haystack.includes(query)) return false;
      }

      return true;
    })
    .sort((a, b) => matchSortValue(effectiveMatch(a)).localeCompare(matchSortValue(effectiveMatch(b))));

  renderResults();
}

function matchSortValue(match) {
  return `${match.date || ""} ${match.time || ""} ${match.competition || ""} ${match.home || ""}`;
}

function renderResults() {
  els.results.innerHTML = "";

  if (!filteredFixtures.length) {
    els.resultsCount.textContent = "No matches found.";
    return;
  }

  els.resultsCount.textContent = `${filteredFixtures.length} match${filteredFixtures.length === 1 ? "" : "es"}`;

  for (const fixture of filteredFixtures) {
    const match = effectiveMatch(fixture);
    const item = document.createElement("button");
    item.type = "button";
    item.className = "match";
    item.dataset.matchKey = fixture.key;

    if (selectedKey === fixture.key) item.classList.add("active");
    if (pending[fixture.key]) item.classList.add("edited");

    const score = hasCompleteScore(match)
      ? `${match.home_goals}-${match.home_points}  ·  ${match.away_goals}-${match.away_points}`
      : "";

    item.innerHTML = `
      <div class="match-top">
        <div class="match-title">${escapeHtml(match.home)} v ${escapeHtml(match.away)}</div>
        <span class="pill">${pending[fixture.key] ? "Edited" : escapeHtml(match.status || "Fixture")}</span>
      </div>
      ${score ? `<div class="match-score">${escapeHtml(score)}</div>` : ""}
      <div class="meta">
        ${escapeHtml(formatDate(match.date))}${match.time ? ` · ${escapeHtml(match.time)}` : ""}
        ${match.round ? ` · ${escapeHtml(match.round)}` : ""}<br>
        ${escapeHtml(shortCompetitionName(match.competition))}${match.group ? ` · ${escapeHtml(match.group)}` : ""}
        ${match.venue ? ` · ${escapeHtml(match.venue)}` : ""}
      </div>
    `;

    item.addEventListener("click", () => openEditor(fixture));
    els.results.appendChild(item);
  }
}

function openEditor(fixture, shouldScroll = true) {
  selectedKey = fixture.key;
  const match = effectiveMatch(fixture);

  els.editorCard.classList.remove("hidden");
  els.selectedSummary.innerHTML = `
    <div class="match-top">
      <div>
        <div class="editor-title">${escapeHtml(match.home)} v ${escapeHtml(match.away)}</div>
        <div class="meta">${escapeHtml(shortCompetitionName(match.competition))}${match.group ? ` · ${escapeHtml(match.group)}` : ""}${match.round ? ` · ${escapeHtml(match.round)}` : ""}</div>
      </div>
      <span class="pill">${escapeHtml(formatDate(match.date))}</span>
    </div>
  `;

  els.homeTeam.textContent = match.home || "Home";
  els.awayTeam.textContent = match.away || "Away";
  setInputValue(els.homeGoals, match.home_goals);
  setInputValue(els.homePoints, match.home_points);
  setInputValue(els.awayGoals, match.away_goals);
  setInputValue(els.awayPoints, match.away_points);
  els.editStatus.value = statusOption(match.status);
  els.editTime.value = match.time || "";
  clearNotice(els.editorNotice);
  updateScoreTotals();
  renderResults();
  renderPendingState();

  if (shouldScroll) {
    requestAnimationFrame(() => els.editorCard.scrollIntoView({ behavior: "smooth", block: "start" }));
  }
}

function statusOption(status) {
  const available = [...els.editStatus.options].map((option) => option.value);
  return available.includes(status) ? status : "Fixture";
}

function setInputValue(input, value) {
  input.value = isWholeNumber(value) ? String(value) : "";
}

function sanitiseInput(input) {
  if (input.value === "") return;
  const value = Math.max(0, Math.trunc(Number(input.value)) || 0);
  input.value = String(value);
}

function stepScore(button) {
  const input = $(button.dataset.target);
  if (!input) return;

  const current = input.value === "" ? 0 : Number(input.value);
  const delta = Number(button.dataset.delta) || 0;
  input.value = String(Math.max(0, current + delta));
  markAsResultWhenScoring();
  updateScoreTotals();
  clearNotice(els.editorNotice);
}

function markAsResultWhenScoring() {
  const hasAnyValue = scoreInputs().some((input) => input.value !== "");
  if (hasAnyValue && els.editStatus.value === "Fixture") {
    els.editStatus.value = "Result";
  }
}

function updateScoreTotals() {
  updateTeamTotal(els.homeGoals, els.homePoints, els.homeDisplay, els.homeTotal);
  updateTeamTotal(els.awayGoals, els.awayPoints, els.awayDisplay, els.awayTotal);
}

function updateTeamTotal(goalsInput, pointsInput, display, total) {
  const goals = inputNumber(goalsInput);
  const points = inputNumber(pointsInput);
  if (goals === null || points === null) {
    display.textContent = "—";
    total.textContent = "—";
    return;
  }
  display.textContent = `${goals}-${points}`;
  total.textContent = String((goals * 3) + points);
}

function scoreInputs() {
  return [els.homeGoals, els.homePoints, els.awayGoals, els.awayPoints];
}

function inputNumber(input) {
  if (input.value === "") return null;
  const value = Number(input.value);
  return isWholeNumber(value) && value >= 0 ? value : null;
}

function saveSelected(moveToNext) {
  const fixture = fixtureByKey(selectedKey);
  if (!fixture) return;

  const status = els.editStatus.value;
  const score = {
    home_goals: inputNumber(els.homeGoals),
    home_points: inputNumber(els.homePoints),
    away_goals: inputNumber(els.awayGoals),
    away_points: inputNumber(els.awayPoints),
  };

  if (status === "Result" && Object.values(score).some((value) => value === null)) {
    showNotice(els.editorNotice, "Enter all four score values before saving a result.", true);
    return;
  }

  const candidate = {
    status,
    time: els.editTime.value,
    ...score,
  };

  if (status !== "Result") {
    for (const key of Object.keys(score)) {
      candidate[key] = score[key];
    }
  }

  const changes = changedFields(fixture.base, candidate);
  if (Object.keys(changes).length) {
    pending[fixture.key] = changes;
  } else {
    delete pending[fixture.key];
  }

  persistPending();
  applyFilters();
  renderPendingState();
  if (moveToNext) {
    openNextFixture(fixture);
  } else {
    openEditor(fixture, false);
    showNotice(els.editorNotice, "Score saved on this device.");
  }
}

function changedFields(base, candidate) {
  const changes = {};
  for (const [key, value] of Object.entries(candidate)) {
    const baseValue = base[key] ?? null;
    if (value !== baseValue) changes[key] = value;
  }
  return changes;
}

function openNextFixture(currentFixture) {
  const currentIndex = filteredFixtures.findIndex((fixture) => fixture.key === currentFixture.key);
  const nextFixture = filteredFixtures[currentIndex + 1];
  if (nextFixture) {
    openEditor(nextFixture, false);
    showNotice(els.editorNotice, "Saved. Next match ready.");
    els.editorCard.scrollIntoView({ behavior: "smooth", block: "start" });
  } else {
    showNotice(els.editorNotice, "Saved. That was the last match in this list.");
  }
}

function undoSelectedMatch() {
  const fixture = fixtureByKey(selectedKey);
  if (!fixture) return;
  delete pending[fixture.key];
  persistPending();
  applyFilters();
  renderPendingState();
  openEditor(fixture, false);
  showNotice(els.editorNotice, "This match has been reset to the published data.");
}

function clearAllEdits() {
  if (!Object.keys(pending).length) return;
  const confirmed = window.confirm("Clear every score edit saved on this device?");
  if (!confirmed) return;

  pending = {};
  persistPending();
  applyFilters();
  renderPendingState();
  const selected = fixtureByKey(selectedKey);
  if (selected) openEditor(selected, false);
  showNotice(els.downloadNotice, "All pending edits cleared.");
}

function renderPendingState() {
  const count = Object.keys(pending).length;
  els.pendingTop.textContent = `${count} edit${count === 1 ? "" : "s"}`;
  els.pendingTop.classList.toggle("hidden", count === 0);
  els.downloadCard.classList.toggle("hidden", count === 0);
  els.pendingSummary.textContent = `${count} match${count === 1 ? "" : "es"} edited on this device`;
  els.copyMatch.disabled = !selectedKey;
}

function buildUpdatedData() {
  const output = JSON.parse(JSON.stringify(sourceData));
  output.updated = isoTimestamp();
  output.matches = output.matches.map((match) => {
    const changes = pending[matchKey(match)];
    return changes ? { ...match, ...changes } : match;
  });
  return output;
}

function downloadUpdatedJson() {
  const text = JSON.stringify(buildUpdatedData(), null, 2) + "\n";
  const blob = new Blob([text], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = "hurling_2026.json";
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
  showNotice(els.downloadNotice, "Updated hurling_2026.json downloaded. Upload it to the data folder in GitHub.");
}

async function copySelectedMatch() {
  const fixture = fixtureByKey(selectedKey);
  if (!fixture) return;
  const match = effectiveMatch(fixture);
  await copyText(JSON.stringify(match, null, 2), els.downloadNotice, "Selected match JSON copied.");
}

async function copyFullJson() {
  const text = JSON.stringify(buildUpdatedData(), null, 2) + "\n";
  await copyText(text, els.downloadNotice, "Full hurling_2026.json copied.");
}

async function copyText(text, noticeElement, successMessage) {
  try {
    await navigator.clipboard.writeText(text);
    showNotice(noticeElement, successMessage);
  } catch (error) {
    console.error(error);
    showNotice(noticeElement, "Copy failed. Use the download button instead.", true);
  }
}

function effectiveMatch(fixture) {
  return pending[fixture.key]
    ? { ...fixture.base, ...pending[fixture.key] }
    : fixture.base;
}

function fixtureByKey(key) {
  return fixtures.find((fixture) => fixture.key === key) || null;
}

function reconcilePending() {
  const validKeys = new Set(fixtures.map((fixture) => fixture.key));
  let changed = false;

  for (const [key, changes] of Object.entries(pending)) {
    const fixture = fixtureByKey(key);
    if (!validKeys.has(key) || !fixture) {
      delete pending[key];
      changed = true;
      continue;
    }

    const alreadyPublished = Object.entries(changes).every(([field, value]) => {
      return (fixture.base[field] ?? null) === value;
    });
    if (alreadyPublished) {
      delete pending[key];
      changed = true;
    }
  }

  if (changed) persistPending();
}

function matchKey(match) {
  return [
    match.competition,
    match.round,
    match.date,
    match.home,
    match.away,
  ].map((value) => String(value ?? "").trim().toLowerCase()).join("|");
}

function hasCompleteScore(match) {
  return [match.home_goals, match.home_points, match.away_goals, match.away_points]
    .every((value) => isWholeNumber(value) && value >= 0);
}

function isWholeNumber(value) {
  return typeof value === "number" && Number.isInteger(value);
}

function loadPending() {
  try {
    const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) || "{}");
    return saved && typeof saved === "object" && !Array.isArray(saved) ? saved : {};
  } catch {
    return {};
  }
}

function persistPending() {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(pending));
}

function showNotice(element, message, isError = false) {
  element.textContent = message;
  element.classList.toggle("error", isError);
}

function clearNotice(element) {
  showNotice(element, "");
}

function isoTimestamp() {
  return new Date().toISOString().replace(/\.\d{3}Z$/, "Z");
}

function formatDate(isoDate) {
  if (!isoDate) return "";
  const [year, month, day] = isoDate.split("-");
  return `${day}/${month}/${year}`;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}
