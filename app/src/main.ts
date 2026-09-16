import {
  build,
  caskFace,
  caskFonts,
  caskInstall,
  casks,
  installed,
  KINDS,
  preview,
  webFonts,
  type Candidate,
  type CaskEntry,
  type Kind,
  type WebFonts,
} from "./api";
import { faceAlias, loadFace } from "./fonts";

const DEFAULT_SAMPLE_TEXT =
  "The quick brown fox jumps over the lazy dog. Reading gets faster when " +
  "the first half of every word is bold, because your eyes only need the " +
  "start of a word to recognise it.";
const SAMPLE_TEXT_KEY = "halfbold.sampleText";
const HALF_SUFFIX = " Half";
const ARCHIVE_SETTLE_MS = 600;

type Tab = "installed" | "brew";
type Selection = { tab: "installed"; candidate: Candidate } | { tab: "brew"; token: string } | null;

interface State {
  tab: Tab;
  candidates: Candidate[];
  caskEntries: CaskEntry[] | null;
  caskFaces: Map<string, string | null>;
  caskFacesPending: Set<string>;
  caskPrefetch: Set<string>;
  selected: Selection;
  web: WebFonts | null;
  busy: string | null;
  sampleText: string;
}

const state: State = {
  tab: "installed",
  candidates: [],
  caskEntries: null,
  caskFaces: new Map(),
  caskFacesPending: new Set(),
  caskPrefetch: new Set(),
  selected: null,
  web: null,
  busy: null,
  sampleText: loadSampleText(),
};

const $ = <T extends HTMLElement>(selector: string) => document.querySelector<T>(selector)!;
const tabInstalledEl = $<HTMLButtonElement>("#tab-installed");
const tabBrewEl = $<HTMLButtonElement>("#tab-brew");
const slotsEl = $<HTMLSpanElement>("#slots");
const filterEl = $<HTMLInputElement>("#filter");
const listEl = $<HTMLUListElement>("#list");
const listNoteEl = $<HTMLDivElement>("#list-note");
const emptyEl = $<HTMLDivElement>("#empty");
const panelEl = $<HTMLDivElement>("#panel");
const titleEl = $<HTMLHeadingElement>("#title");
const metaEl = $<HTMLParagraphElement>("#meta");
const actionsEl = $<HTMLDivElement>("#actions");
const statusEl = $<HTMLSpanElement>("#status");
const sampleHalfEl = $<HTMLParagraphElement>("#sample-half");
const samplePlainEl = $<HTMLParagraphElement>("#sample-plain");
const halfNoteEl = $<HTMLSpanElement>("#half-note");
const resetSampleEl = $<HTMLButtonElement>("#reset-sample");

function loadSampleText(): string {
  try {
    return localStorage.getItem(SAMPLE_TEXT_KEY) || DEFAULT_SAMPLE_TEXT;
  } catch {
    return DEFAULT_SAMPLE_TEXT;
  }
}

function saveSampleText(text: string) {
  state.sampleText = text;
  try {
    localStorage.setItem(SAMPLE_TEXT_KEY, text);
  } catch {
    return;
  }
}

function setBusy(label: string | null) {
  state.busy = label;
  statusEl.classList.remove("error");
  statusEl.textContent = label ?? "";
  for (const button of actionsEl.querySelectorAll("button")) {
    button.disabled = label !== null || button.dataset.locked === "true";
  }
}

function showError(message: string) {
  statusEl.classList.add("error");
  statusEl.textContent = message;
}

async function run<T>(label: string, task: () => Promise<T>): Promise<T | null> {
  setBusy(label);
  try {
    const result = await task();
    setBusy(null);
    return result;
  } catch (err) {
    setBusy(null);
    showError(String(err));
    return null;
  }
}

function selectionKey(selection: Selection): string {
  if (!selection) return "";
  return selection.tab === "installed"
    ? `installed:${selection.candidate.regular}`
    : `brew:${selection.token}`;
}

function stillSelected(selection: Selection): boolean {
  return selectionKey(selection) === selectionKey(state.selected);
}

function renderSlots() {
  slotsEl.textContent = "";
  if (!state.web) return;
  for (const kind of KINDS) {
    const span = document.createElement("span");
    const label = document.createElement("b");
    label.textContent = kind;
    span.append(label, ` ${stripHalf(state.web[kind])}`);
    slotsEl.append(span);
  }
}

function stripHalf(family: string): string {
  return family.endsWith(HALF_SUFFIX) ? family.slice(0, -HALF_SUFFIX.length) : family;
}

function filteredCandidates(): Candidate[] {
  const query = filterEl.value.trim().toLowerCase();
  if (!query) return state.candidates;
  return state.candidates.filter((c) => c.family.toLowerCase().includes(query));
}

function filteredCasks(): CaskEntry[] {
  const query = filterEl.value.trim().toLowerCase();
  const entries = state.caskEntries ?? [];
  if (!query) return entries;
  return entries.filter((e) => e.name.toLowerCase().includes(query) || e.token.toLowerCase().includes(query));
}

function select(selection: Selection) {
  if (stillSelected(selection) && selection !== null) return;
  state.selected = selection;
  renderList();
  void renderDetail();
}

function renderList() {
  faceObserver?.disconnect();
  visibleRows.clear();
  listEl.textContent = "";
  listNoteEl.hidden = true;
  if (state.tab === "installed") {
    for (const c of filteredCandidates()) {
      const li = document.createElement("li");
      li.setAttribute("role", "option");
      const nameSpan = document.createElement("span");
      nameSpan.className = "name";
      nameSpan.textContent = c.family;
      const kindSpan = document.createElement("span");
      kindSpan.className = "kind";
      kindSpan.textContent = c.kind;
      const stateSpan = document.createElement("span");
      stateSpan.className = `state ${c.built ? (c.stale ? "stale" : "built") : ""}`;
      stateSpan.textContent = c.built ? (c.stale ? "outdated" : "Half") : "";
      li.append(nameSpan, kindSpan, stateSpan);
      if (state.selected?.tab === "installed" && state.selected.candidate.regular === c.regular) {
        li.classList.add("selected");
      }
      li.addEventListener("click", () => select({ tab: "installed", candidate: c }));
      void faceAlias(c.regular).then((alias) => {
        if (nameSpan.isConnected) nameSpan.style.fontFamily = alias;
      });
      listEl.append(li);
    }
    return;
  }

  const entries = filteredCasks();
  const shown = entries.slice(0, 200);
  for (const entry of shown) {
    const li = document.createElement("li");
    li.setAttribute("role", "option");
    li.dataset.token = entry.token;
    const nameSpan = document.createElement("span");
    nameSpan.className = "name";
    nameSpan.textContent = entry.name;
    const alias = state.caskFaces.get(entry.token);
    if (alias) nameSpan.style.fontFamily = alias;
    const tokenSpan = document.createElement("span");
    tokenSpan.className = "token";
    tokenSpan.textContent = entry.google ? "Google Fonts" : "";
    li.append(nameSpan, tokenSpan);
    if (state.selected?.tab === "brew" && state.selected.token === entry.token) {
      li.classList.add("selected");
    }
    li.addEventListener("click", () => select({ tab: "brew", token: entry.token }));
    if (entry.google) {
      li.addEventListener("mouseenter", () => prefetchCask(entry.token));
    }
    listEl.append(li);
    if (entry.google && !state.caskFaces.has(entry.token)) {
      faceObserver?.observe(li);
    }
  }
  if (entries.length > shown.length) {
    const more = document.createElement("li");
    more.className = "more";
    more.textContent = `${entries.length - shown.length} more match. Narrow the search.`;
    listEl.append(more);
  }
  if (state.caskEntries) {
    listNoteEl.hidden = false;
    listNoteEl.textContent = `${state.caskEntries.length} font casks. Google Fonts casks download on select; the rest fetch the whole cask archive.`;
  }
}

function prefetchCask(token: string) {
  if (state.caskPrefetch.has(token)) return;
  state.caskPrefetch.add(token);
  void caskFonts(token).catch(() => state.caskPrefetch.delete(token));
}

const MAX_CONCURRENT_FACES = 4;
let facesInFlight = 0;
const visibleRows = new Map<string, HTMLElement>();
let faceObserver: IntersectionObserver | null = null;

function setupFaceLoader() {
  faceObserver = new IntersectionObserver(
    (entries) => {
      for (const entry of entries) {
        const li = entry.target as HTMLElement;
        const token = li.dataset.token;
        if (!token) continue;
        if (entry.isIntersecting) {
          visibleRows.set(token, li);
        } else if (visibleRows.get(token) === li) {
          visibleRows.delete(token);
        }
      }
      pumpFaces();
    },
    { root: listEl, rootMargin: "200px" },
  );
}

function pumpFaces() {
  for (const [token, li] of visibleRows) {
    if (facesInFlight >= MAX_CONCURRENT_FACES) return;
    if (state.caskFaces.has(token) || state.caskFacesPending.has(token)) continue;
    const entry = state.caskEntries?.find((e) => e.token === token);
    if (!entry?.google) {
      visibleRows.delete(token);
      continue;
    }
    state.caskFacesPending.add(token);
    facesInFlight++;
    void loadCaskFace(token).finally(() => {
      state.caskFacesPending.delete(token);
      facesInFlight--;
      visibleRows.delete(token);
      faceObserver?.unobserve(li);
      pumpFaces();
    });
  }
}

function applyCaskFace(token: string, alias: string) {
  state.caskFaces.set(token, alias);
  const nameSpan = listEl.querySelector(`li[data-token="${CSS.escape(token)}"] .name`) as HTMLElement | null;
  if (nameSpan) nameSpan.style.fontFamily = alias;
}

async function loadCaskFace(token: string) {
  try {
    const result = await caskFace(token);
    if (!result.face) {
      state.caskFaces.set(token, null);
      return;
    }
    applyCaskFace(token, await faceAlias(result.face));
  } catch {
    state.caskFaces.set(token, null);
  }
}

function showPending(message: string) {
  for (const el of [sampleHalfEl, samplePlainEl]) {
    el.classList.add("pending");
    el.style.fontFamily = "";
    el.style.fontFeatureSettings = "";
    el.style.fontWeight = "";
    el.textContent = "";
  }
  sampleHalfEl.textContent = message;
  sampleHalfEl.contentEditable = "false";
  halfNoteEl.textContent = "";
}

async function renderSamples(regular: string, half: string, selection: Selection) {
  const [halfAlias, plainAlias] = await Promise.all([loadFace(half), loadFace(regular)]);
  if (!stillSelected(selection)) return;
  sampleHalfEl.classList.remove("pending");
  sampleHalfEl.style.fontFamily = halfAlias;
  sampleHalfEl.style.fontFeatureSettings = '"calt" 1';
  sampleHalfEl.textContent = state.sampleText;
  sampleHalfEl.contentEditable = "plaintext-only";
  halfNoteEl.textContent = "click to edit the text";

  samplePlainEl.classList.remove("pending");
  samplePlainEl.style.fontFamily = plainAlias;
  samplePlainEl.style.fontWeight = "400";
  samplePlainEl.textContent = state.sampleText;
}

function pairDescription(c: Candidate): string {
  return c.bold ? "Regular and Bold pair" : "variable font";
}

function fileNames(c: Candidate): string {
  return [c.regular, c.bold]
    .filter((p): p is string => Boolean(p))
    .map((p) => p.split("/").pop())
    .join(", ");
}

function makeButton(label: string, onClick: () => void, className = ""): HTMLButtonElement {
  const button = document.createElement("button");
  button.textContent = label;
  button.className = className;
  button.addEventListener("click", onClick);
  return button;
}

function renderInstalledActions(c: Candidate) {
  actionsEl.textContent = "";
  if (!(c.built && !c.stale)) {
    actionsEl.append(makeButton(c.built ? "Rebuild Half" : "Build Half", () => onBuild(c), "primary"));
  }
  for (const kind of KINDS) {
    const active = state.web?.[kind] === `${c.family}${HALF_SUFFIX}`;
    const button = makeButton(`Use as ${kind}`, () => onUseAs(kind, c), active ? "active" : "");
    button.disabled = !c.built;
    button.dataset.locked = String(!c.built);
    actionsEl.append(button);
  }
}

async function renderInstalledDetail(c: Candidate) {
  const selection: Selection = { tab: "installed", candidate: c };
  titleEl.textContent = c.family;
  void faceAlias(c.regular).then((alias) => {
    if (stillSelected(selection)) titleEl.style.fontFamily = alias;
  });
  metaEl.textContent = `${c.kind}, ${pairDescription(c)}. ${fileNames(c)}`;
  renderInstalledActions(c);
  showPending("Preparing preview…");

  const p = await run(`Previewing ${c.family}…`, () => preview(c));
  if (!p || !stillSelected(selection)) return;
  await renderSamples(p.regular, p.half, selection);
}

async function onBuild(c: Candidate) {
  const result = await run(`Building ${c.family} Half…`, () => build(c));
  if (!result) return;
  await reloadInstalled();
  const updated = state.candidates.find((x) => x.regular === c.regular);
  if (updated) {
    state.selected = { tab: "installed", candidate: updated };
    renderList();
    renderInstalledActions(updated);
    statusEl.textContent = `Built ${updated.family} Half.`;
  }
}

async function onUseAs(kind: Kind, c: Candidate) {
  const result = await run(`Setting ${kind} to ${c.family}…`, () => webFonts(kind, c.family));
  if (!result) return;
  state.web = result;
  renderSlots();
  renderInstalledActions(c);
  statusEl.textContent = `${c.family} Half is now the ${kind} font.`;
}

async function renderBrewDetail(token: string) {
  const selection: Selection = { tab: "brew", token };
  const entry = state.caskEntries?.find((e) => e.token === token);
  titleEl.textContent = entry?.name ?? token;
  titleEl.style.fontFamily = state.caskFaces.get(token) ?? "";
  metaEl.textContent = `Homebrew cask ${token}`;
  actionsEl.textContent = "";
  actionsEl.append(makeButton("Install and build Half", () => onInstallCask(token), "primary"));
  showPending(
    entry?.google
      ? "Downloading from Google Fonts…"
      : "Fetching the whole cask archive. Large casks can take a minute.",
  );

  if (!entry?.google) {
    await new Promise((resolve) => setTimeout(resolve, ARCHIVE_SETTLE_MS));
    if (!stillSelected(selection)) return;
  }
  const result = await run(`Loading ${token}…`, () => caskFonts(token));
  if (!stillSelected(selection)) return;
  if (!result || result.candidates.length === 0) {
    showPending(result ? "No preview for this cask." : "Cannot convert this cask.");
    return;
  }
  const first = result.candidates[0];
  metaEl.textContent = `Homebrew cask ${token}. ${result.candidates
    .map((c) => `${c.family} (${c.kind})`)
    .join(", ")}`;
  const alias = await faceAlias(first.regular);
  applyCaskFace(token, alias);
  if (!stillSelected(selection)) return;
  titleEl.style.fontFamily = alias;
  const p = await run(`Previewing ${first.family}…`, () => preview(first));
  if (!p || !stillSelected(selection)) return;
  await renderSamples(p.regular, p.half, selection);
}

async function onInstallCask(token: string) {
  const installResult = await run(`Installing ${token}…`, () => caskInstall(token));
  if (!installResult) return;
  for (const c of installResult.candidates) {
    await run(`Building ${c.family} Half…`, () => build(c));
  }
  const first = installResult.candidates[0];
  if (first) applyCaskFace(token, await faceAlias(first.regular));
  await reloadInstalled();
  state.tab = "installed";
  renderTabs();
  const selected = first ? state.candidates.find((x) => x.regular === first.regular) : undefined;
  state.selected = selected ? { tab: "installed", candidate: selected } : null;
  renderList();
  await renderDetail();
}

async function renderDetail() {
  if (!state.selected) {
    emptyEl.hidden = false;
    panelEl.hidden = true;
    return;
  }
  emptyEl.hidden = true;
  panelEl.hidden = false;
  if (state.selected.tab === "installed") {
    await renderInstalledDetail(state.selected.candidate);
  } else {
    await renderBrewDetail(state.selected.token);
  }
}

async function reloadInstalled() {
  const result = await run("Loading fonts…", () => installed());
  if (result) state.candidates = result.candidates;
  renderList();
}

async function ensureCasks() {
  if (state.caskEntries) return;
  const result = await run("Loading casks…", () => casks());
  if (result) state.caskEntries = result.casks;
  renderList();
}

function renderTabs() {
  for (const [el, tab] of [
    [tabInstalledEl, "installed"],
    [tabBrewEl, "brew"],
  ] as const) {
    const active = state.tab === tab;
    el.classList.toggle("active", active);
    el.setAttribute("aria-selected", String(active));
  }
}

function selectTab(tab: Tab) {
  if (state.tab === tab) return;
  state.tab = tab;
  renderTabs();
  state.selected = null;
  renderList();
  void renderDetail();
  if (tab === "brew") void ensureCasks();
}

function moveSelection(delta: number) {
  const items = Array.from(listEl.querySelectorAll("li:not(.more)"));
  if (items.length === 0) return;
  const currentIndex = items.findIndex((el) => el.classList.contains("selected"));
  const nextIndex = Math.min(Math.max(currentIndex + delta, 0), items.length - 1);
  const next = items[nextIndex] as HTMLElement;
  next.click();
  next.scrollIntoView({ block: "nearest" });
}

function setupSampleEditing() {
  sampleHalfEl.addEventListener("input", () => {
    const text = sampleHalfEl.textContent ?? "";
    saveSampleText(text);
    samplePlainEl.textContent = text;
  });
  resetSampleEl.addEventListener("click", () => {
    saveSampleText(DEFAULT_SAMPLE_TEXT);
    if (!sampleHalfEl.classList.contains("pending")) {
      sampleHalfEl.textContent = DEFAULT_SAMPLE_TEXT;
      samplePlainEl.textContent = DEFAULT_SAMPLE_TEXT;
    }
  });
}

function init() {
  setupFaceLoader();
  setupSampleEditing();
  tabInstalledEl.addEventListener("click", () => selectTab("installed"));
  tabBrewEl.addEventListener("click", () => selectTab("brew"));
  filterEl.addEventListener("input", renderList);

  document.addEventListener("keydown", (event) => {
    if (event.target === sampleHalfEl) return;
    if (event.key === "/" && document.activeElement !== filterEl) {
      event.preventDefault();
      filterEl.focus();
      return;
    }
    if (event.target === filterEl && !["ArrowDown", "ArrowUp"].includes(event.key)) return;
    if (event.key === "ArrowDown") {
      event.preventDefault();
      moveSelection(1);
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      moveSelection(-1);
    } else if (event.key === "Enter" && state.selected?.tab === "installed") {
      event.preventDefault();
      void onBuild(state.selected.candidate);
    }
  });

  void (async () => {
    const [installedResult, webResult] = await Promise.all([
      run("Loading fonts…", () => installed()),
      run("Loading slots…", () => webFonts()),
    ]);
    if (installedResult) state.candidates = installedResult.candidates;
    if (webResult) state.web = webResult;
    renderSlots();
    const first = state.candidates[0];
    state.selected = first ? { tab: "installed", candidate: first } : null;
    renderList();
    void renderDetail();
  })();
}

init();
