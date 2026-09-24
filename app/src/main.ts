import {
  build,
  browserStatus,
  caskFace,
  caskFonts,
  caskInstall,
  casks,
  installed,
  KINDS,
  preview,
  settings as settingsApi,
  webFonts,
  type Candidate,
  type CaskEntry,
  type Kind,
  type Settings,
  type WebFonts,
} from "./api";
import { faceAlias, loadFace } from "./fonts";

const DEFAULT_SAMPLE_TEXT =
  "The quick brown fox jumps over the lazy dog. Reading gets faster when " +
  "the first half of every word is bold, because your eyes only need the " +
  "start of a word to recognise it.";
const SAMPLE_TEXT_KEY = "halfbold.sampleText";
const HALF_SUFFIX = " Half";

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
  settings: Settings | null;
  defaults: Settings | null;
  previewed: { key: string; candidate: Candidate } | null;
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
  settings: null,
  defaults: null,
  previewed: null,
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
const tuningEl = $<HTMLFormElement>("#tuning");
const tuningNoteEl = $<HTMLSpanElement>("#tuning-note");
const resetTuningEl = $<HTMLButtonElement>("#reset-tuning");
const knobs: Record<keyof Omit<Settings, "max_word_length">, { input: HTMLInputElement; out: HTMLOutputElement }> = {
  bold_share: { input: $("#knob-share"), out: $("#out-share") },
  min_word_length: { input: $("#knob-min"), out: $("#out-min") },
  regular_weight: { input: $("#knob-regular"), out: $("#out-regular") },
  bold_weight: { input: $("#knob-bold"), out: $("#out-bold") },
};

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
    listNoteEl.textContent = `${state.caskEntries.length} casks halfbold can convert. Google Fonts casks preview on select; the rest need a download first.`;
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

function knobValue(name: keyof typeof knobs, value: number): string {
  if (name === "bold_share") return `${Math.round(value * 100)}%`;
  if (name === "min_word_length") return `${value}`;
  return `${Math.round(value)}`;
}

function renderTuning() {
  if (!state.settings) return;
  for (const [name, knob] of Object.entries(knobs) as [keyof typeof knobs, (typeof knobs)[keyof typeof knobs]][]) {
    const value = state.settings[name];
    knob.input.value = String(name === "bold_share" ? Math.round(value * 100) : value);
    knob.out.value = knobValue(name, value);
  }
  const candidate = state.selected?.tab === "installed" ? state.selected.candidate : state.previewed?.candidate;
  const variable = candidate ? candidate.bold === null : true;
  for (const name of ["regular_weight", "bold_weight"] as const) {
    knobs[name].input.disabled = !variable;
    knobs[name].input.closest(".knob")?.classList.toggle("disabled", !variable);
  }
  tuningNoteEl.textContent = variable
    ? "Applies to every font you build."
    : "Weights only apply to variable fonts. This family ships fixed Regular and Bold files.";
}

let tuningTimer: ReturnType<typeof setTimeout> | null = null;

function onTuningInput(event: Event) {
  const input = event.target as HTMLInputElement;
  const name = input.name as keyof typeof knobs;
  const raw = Number(input.value);
  const value = name === "bold_share" ? raw / 100 : raw;
  knobs[name].out.value = knobValue(name, value);
  if (tuningTimer) clearTimeout(tuningTimer);
  tuningTimer = setTimeout(() => void saveTuning({ [name]: value }), 250);
}

async function saveTuning(values: Partial<Settings>) {
  const result = await run("Saving settings…", () => settingsApi(values));
  if (!result) return;
  state.settings = result.settings;
  state.defaults = result.defaults;
  renderTuning();
  await refreshPreview();
}

async function refreshPreview() {
  const selection = state.selected;
  if (!selection) return;
  if (selection.tab === "installed") {
    renderInstalledActions(selection.candidate);
    await previewCandidate(selection.candidate, selection);
  } else if (state.previewed?.key === selectionKey(selection)) {
    await previewCandidate(state.previewed.candidate, selection);
  }
}

async function previewCandidate(c: Candidate, selection: Selection) {
  const p = await run(`Previewing ${c.family}…`, () => preview(c));
  if (!p || !stillSelected(selection)) return;
  state.previewed = { key: selectionKey(selection), candidate: c };
  renderTuning();
  await renderSamples(p.regular, p.half, selection);
}

async function renderSamples(regular: string, half: string, selection: Selection) {
  const [halfAlias, plainAlias] = await Promise.all([loadFace(half), faceAlias(regular)]);
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
  actionsEl.append(makeButton("Use in browser", () => onUseAs(c.kind === "mono" ? "mono" : "sans", c), "primary"));
  actionsEl.append(makeButton(c.built ? "Rebuild Half" : "Build Half", () => onBuild(c)));
  const advanced = document.createElement("details");
  const summary = document.createElement("summary");
  summary.textContent = "Choose slot";
  advanced.append(summary);
  for (const kind of KINDS) {
    const active = state.web?.[kind] === `${c.family}${HALF_SUFFIX}`;
    const button = makeButton(`Use as ${kind}`, () => onUseAs(kind, c), active ? "active" : "");
    advanced.append(button);
  }
  actionsEl.append(advanced);
}

async function renderInstalledDetail(c: Candidate) {
  const selection: Selection = { tab: "installed", candidate: c };
  titleEl.textContent = c.family;
  void faceAlias(c.regular).then((alias) => {
    if (stillSelected(selection)) titleEl.style.fontFamily = alias;
  });
  metaEl.textContent = `${c.kind}, ${pairDescription(c)}. ${fileNames(c)}`;
  renderInstalledActions(c);
  renderTuning();
  showPending("Preparing preview…");
  await previewCandidate(c, selection);
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
  if (state.busy) return;
  const result = await run(`Applying ${c.family} to browser…`, async () => {
    await build(c);
    const web = await webFonts(kind, c.family);
    const fonts = await installed();
    const connection = await browserStatus();
    return { web, fonts, connection };
  });
  if (!result) return;
  state.web = result.web;
  state.candidates = result.fonts.candidates;
  renderSlots();
  renderList();
  if (state.selected?.tab === "installed") {
    const selectedPath = state.selected.candidate.regular;
    const updated = state.candidates.find((candidate) => candidate.regular === selectedPath);
    if (updated) state.selected = { tab: "installed", candidate: updated };
    if (state.selected?.tab === "installed") renderInstalledActions(state.selected.candidate);
  }
  statusEl.textContent = `${c.family} Half saved for browser ${kind === "mono" ? "code" : "text"}.`;
  showBrowserStatus(result.connection);
  if (!result.connection.configured) await setupChrome();
}

const browserStatusEl = $("#browser-status");
const browserInstructionsEl = $("#browser-instructions");
const setupChromeEl = $<HTMLButtonElement>("#setup-chrome");
let checkingBrowser = false;

function showBrowserStatus(status: Awaited<ReturnType<typeof browserStatus>>) {
  browserStatusEl.textContent = status.synced
    ? "Chrome connected · font settings received"
    : status.connected ? "Chrome connected · applying…"
    : status.configured ? "Chrome disconnected · open Chrome or finish setup"
    : "Chrome setup needed";
  setupChromeEl.textContent = status.connected ? "Chrome setup" : "Set up Chrome";
  if (status.connected) browserInstructionsEl.hidden = true;
}

async function refreshBrowserStatus() {
  if (checkingBrowser) return;
  checkingBrowser = true;
  try {
    showBrowserStatus(await browserStatus());
  } catch {
    browserStatusEl.textContent = "Could not check Chrome connection";
  } finally {
    checkingBrowser = false;
  }
}

async function setupChrome() {
  setupChromeEl.disabled = true;
  try {
    const status = await browserStatus(true);
    showBrowserStatus(status);
    $("#extension-path").textContent = status.extension_dir;
    browserInstructionsEl.hidden = false;
  } catch (error) {
    showError(String(error));
  } finally {
    setupChromeEl.disabled = false;
  }
}
setupChromeEl.addEventListener("click", () => void setupChrome());
void refreshBrowserStatus();
setInterval(() => void refreshBrowserStatus(), 2000);

async function renderBrewDetail(token: string) {
  const selection: Selection = { tab: "brew", token };
  const entry = state.caskEntries?.find((e) => e.token === token);
  titleEl.textContent = entry?.name ?? token;
  titleEl.style.fontFamily = state.caskFaces.get(token) ?? "";
  metaEl.textContent = `Homebrew cask ${token}`;
  actionsEl.textContent = "";
  actionsEl.append(makeButton("Install and build Half", () => onInstallCask(token), "primary"));
  renderTuning();
  if (entry?.google || state.caskPrefetch.has(token)) {
    showPending("Downloading from Google Fonts…");
    await previewCask(token, selection);
    return;
  }
  showPending("This cask ships as an archive, so the preview is a download away.");
  const download = makeButton("Download and preview", () => {
    showPending("Fetching the cask archive. Large casks can take a minute.");
    void previewCask(token, selection);
  });
  actionsEl.prepend(download);
}

async function previewCask(token: string, selection: Selection) {
  const result = await run(`Loading ${token}…`, () => caskFonts(token));
  if (!stillSelected(selection)) return;
  if (!result || result.candidates.length === 0) {
    showPending(result ? "No preview for this cask." : "Cannot convert this cask.");
    return;
  }
  state.caskPrefetch.add(token);
  const first = result.candidates[0];
  metaEl.textContent = `Homebrew cask ${token}. ${result.candidates
    .map((c) => `${c.family} (${c.kind})`)
    .join(", ")}`;
  const alias = await faceAlias(first.regular);
  applyCaskFace(token, alias);
  if (!stillSelected(selection)) return;
  titleEl.style.fontFamily = alias;
  await previewCandidate(first, selection);
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

function setupTuning() {
  for (const knob of Object.values(knobs)) {
    knob.input.addEventListener("input", onTuningInput);
  }
  tuningEl.addEventListener("submit", (event) => event.preventDefault());
  resetTuningEl.addEventListener("click", () => {
    if (state.defaults) void saveTuning(state.defaults);
  });
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
  setupTuning();
  tabInstalledEl.addEventListener("click", () => selectTab("installed"));
  tabBrewEl.addEventListener("click", () => selectTab("brew"));
  filterEl.addEventListener("input", renderList);

  document.addEventListener("keydown", (event) => {
    if (event.target === sampleHalfEl || event.target instanceof HTMLInputElement && event.target.type === "range") return;
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
    } else if (event.key === "Enter" && state.selected?.tab === "installed"
      && !(event.target instanceof HTMLButtonElement)
      && !(event.target instanceof HTMLElement && event.target.closest("details"))) {
      event.preventDefault();
      void onBuild(state.selected.candidate);
    }
  });

  void (async () => {
    const [installedResult, webResult, settingsResult] = await Promise.all([
      run("Loading fonts…", () => installed()),
      run("Loading slots…", () => webFonts()),
      run("Loading settings…", () => settingsApi()),
    ]);
    if (installedResult) state.candidates = installedResult.candidates;
    if (webResult) state.web = webResult;
    if (settingsResult) {
      state.settings = settingsResult.settings;
      state.defaults = settingsResult.defaults;
    }
    renderSlots();
    renderTuning();
    const first = state.candidates[0];
    state.selected = first ? { tab: "installed", candidate: first } : null;
    renderList();
    void renderDetail();
  })();
}

init();
