import {
  build,
  caskFonts,
  caskInstall,
  casks,
  installed,
  preview,
  webFonts,
  type Candidate,
  type Kind,
  type WebFonts,
} from "./api";
import { loadFace } from "./fonts";

const SAMPLE_TEXT =
  "The quick brown fox jumps over the lazy dog. Reading gets faster when " +
  "the first half of every word is bold, because your eyes only need the " +
  "start of a word to recognise it.";

type Tab = "installed" | "brew";
type Selection = { tab: "installed"; candidate: Candidate } | { tab: "brew"; token: string } | null;

interface State {
  tab: Tab;
  candidates: Candidate[];
  caskTokens: string[] | null;
  selected: Selection;
  web: WebFonts | null;
  busy: string | null;
}

const state: State = {
  tab: "installed",
  candidates: [],
  caskTokens: null,
  selected: null,
  web: null,
  busy: null,
};

const tabInstalledEl = document.querySelector<HTMLButtonElement>("#tab-installed")!;
const tabBrewEl = document.querySelector<HTMLButtonElement>("#tab-brew")!;
const slotsEl = document.querySelector<HTMLDivElement>("#slots")!;
const filterEl = document.querySelector<HTMLInputElement>("#filter")!;
const listEl = document.querySelector<HTMLUListElement>("#list")!;
const emptyEl = document.querySelector<HTMLParagraphElement>("#empty")!;
const panelEl = document.querySelector<HTMLDivElement>("#panel")!;
const titleEl = document.querySelector<HTMLHeadingElement>("#title")!;
const metaEl = document.querySelector<HTMLParagraphElement>("#meta")!;
const actionsEl = document.querySelector<HTMLDivElement>("#actions")!;
const statusEl = document.querySelector<HTMLParagraphElement>("#status")!;
const sampleHalfEl = document.querySelector<HTMLParagraphElement>("#sample-half")!;
const samplePlainEl = document.querySelector<HTMLParagraphElement>("#sample-plain")!;
const headingHalfEl = document.querySelector<HTMLHeadingElement>("#heading-half")!;
const headingPlainEl = document.querySelector<HTMLHeadingElement>("#heading-plain")!;

function setBusy(label: string | null) {
  state.busy = label;
  statusEl.textContent = label ?? "";
  for (const button of actionsEl.querySelectorAll("button")) {
    button.disabled = label !== null;
  }
}

function showError(message: string) {
  statusEl.textContent = `Error: ${message}`;
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

function renderSlots() {
  if (!state.web) {
    slotsEl.textContent = "";
    return;
  }
  slotsEl.textContent = `sans: ${state.web.sans} · serif: ${state.web.serif} · mono: ${state.web.mono}`;
}

function filteredCandidates(): Candidate[] {
  const query = filterEl.value.trim().toLowerCase();
  if (!query) return state.candidates;
  return state.candidates.filter((c) => c.family.toLowerCase().includes(query));
}

function filteredTokens(): string[] {
  const query = filterEl.value.trim().toLowerCase();
  const tokens = state.caskTokens ?? [];
  if (!query) return tokens;
  return tokens.filter((t) => t.toLowerCase().includes(query));
}

function renderList() {
  listEl.textContent = "";
  if (state.tab === "installed") {
    for (const c of filteredCandidates()) {
      const li = document.createElement("li");
      const nameSpan = document.createElement("span");
      nameSpan.textContent = c.family;
      const kindSpan = document.createElement("span");
      kindSpan.className = "kind";
      kindSpan.textContent = c.kind;
      const stateSpan = document.createElement("span");
      stateSpan.className = "state";
      stateSpan.textContent = c.built ? (c.stale ? "stale" : "built") : "not built";
      li.append(nameSpan, kindSpan, stateSpan);
      if (state.selected?.tab === "installed" && state.selected.candidate === c) {
        li.classList.add("selected");
      }
      li.addEventListener("click", () => {
        state.selected = { tab: "installed", candidate: c };
        renderList();
        renderDetail();
      });
      listEl.append(li);
    }
    return;
  }

  const tokens = filteredTokens();
  const shown = tokens.slice(0, 200);
  for (const token of shown) {
    const li = document.createElement("li");
    li.textContent = token;
    if (state.selected?.tab === "brew" && state.selected.token === token) {
      li.classList.add("selected");
    }
    li.addEventListener("click", () => {
      state.selected = { tab: "brew", token };
      renderList();
      renderDetail();
    });
    listEl.append(li);
  }
  if (tokens.length > shown.length) {
    const more = document.createElement("li");
    more.className = "more";
    more.textContent = `… and ${tokens.length - shown.length} more`;
    listEl.append(more);
  }
}

function clearSamples() {
  sampleHalfEl.textContent = "";
  sampleHalfEl.style.fontFamily = "";
  sampleHalfEl.style.fontFeatureSettings = "";
  headingHalfEl.hidden = true;

  samplePlainEl.textContent = "";
  samplePlainEl.style.fontFamily = "";
  samplePlainEl.style.fontWeight = "";
  headingPlainEl.hidden = true;
}

async function renderSamples(regular: string, half: string) {
  const halfAlias = await loadFace(half);
  sampleHalfEl.style.fontFamily = halfAlias;
  sampleHalfEl.style.fontFeatureSettings = '"calt" 1';
  sampleHalfEl.textContent = SAMPLE_TEXT;
  headingHalfEl.hidden = false;

  const plainAlias = await loadFace(regular);
  samplePlainEl.style.fontFamily = plainAlias;
  samplePlainEl.style.fontWeight = "400";
  samplePlainEl.textContent = SAMPLE_TEXT;
  headingPlainEl.hidden = false;
}

function pairDescription(c: Candidate): string {
  return c.bold ? "Regular + Bold pair" : "variable font";
}

function fileNames(c: Candidate): string {
  const names = [c.regular, c.bold].filter((p): p is string => Boolean(p)).map((p) => p.split("/").pop());
  return names.join(", ");
}

async function renderInstalledDetail(c: Candidate) {
  clearSamples();
  titleEl.textContent = c.family;
  metaEl.textContent = `${c.kind} · ${pairDescription(c)} · ${fileNames(c)}`;
  actionsEl.textContent = "";

  if (!(c.built && !c.stale)) {
    const buildButton = document.createElement("button");
    buildButton.textContent = c.built && c.stale ? "Rebuild" : "Build Half font";
    buildButton.addEventListener("click", () => onBuild(c));
    actionsEl.append(buildButton);
  }

  for (const kind of ["sans", "serif", "mono"] as Kind[]) {
    const button = document.createElement("button");
    button.textContent = `Use as ${kind}`;
    button.disabled = !c.built;
    button.addEventListener("click", () => onUseAs(kind, c));
    actionsEl.append(button);
  }

  const p = await run(`Previewing ${c.family}…`, () => preview(c));
  if (!p) return;
  await renderSamples(p.regular, p.half);
}

async function onBuild(c: Candidate) {
  const result = await run(`Building ${c.family} Half…`, () => build(c));
  if (!result) return;
  await reloadInstalled();
  const updated = state.candidates.find((x) => x.family === c.family && x.kind === c.kind);
  if (updated) {
    state.selected = { tab: "installed", candidate: updated };
    renderList();
    await renderInstalledDetail(updated);
  }
}

async function onUseAs(kind: Kind, c: Candidate) {
  const result = await run(`Setting ${kind} to ${c.family}…`, () => webFonts(kind, c.family));
  if (!result) return;
  state.web = result;
  renderSlots();
}

async function renderBrewDetail(token: string) {
  clearSamples();
  titleEl.textContent = token;
  metaEl.textContent = "";
  actionsEl.textContent = "";

  const previewButton = document.createElement("button");
  previewButton.textContent = "Preview";
  previewButton.addEventListener("click", () => onPreviewCask(token));
  const installButton = document.createElement("button");
  installButton.textContent = "Install";
  installButton.addEventListener("click", () => onInstallCask(token));
  actionsEl.append(previewButton, installButton);
}

async function onPreviewCask(token: string) {
  const result = await run(`Loading ${token}…`, () => caskFonts(token));
  if (!result || result.candidates.length === 0) return;
  const first = result.candidates[0];
  metaEl.textContent = result.candidates.map((c) => `${c.family} (${c.kind})`).join(" · ");
  const p = await run(`Previewing ${first.family}…`, () => preview(first));
  if (!p) return;
  await renderSamples(p.regular, p.half);
}

async function onInstallCask(token: string) {
  const installResult = await run(`Installing ${token}…`, () => caskInstall(token));
  if (!installResult) return;
  for (const c of installResult.candidates) {
    await run(`Building ${c.family} Half…`, () => build(c));
  }
  await reloadInstalled();
  state.tab = "installed";
  tabInstalledEl.classList.add("active");
  tabBrewEl.classList.remove("active");
  const first = installResult.candidates[0];
  const selected = first
    ? state.candidates.find((x) => x.family === first.family && x.kind === first.kind)
    : undefined;
  state.selected = selected ? { tab: "installed", candidate: selected } : null;
  renderList();
  if (selected) await renderInstalledDetail(selected);
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
  if (state.caskTokens) return;
  const result = await run("Loading casks…", () => casks());
  if (result) state.caskTokens = result.casks;
  renderList();
}

function selectTab(tab: Tab) {
  state.tab = tab;
  tabInstalledEl.classList.toggle("active", tab === "installed");
  tabBrewEl.classList.toggle("active", tab === "brew");
  state.selected = null;
  renderList();
  renderDetail();
  if (tab === "brew") void ensureCasks();
}

function moveSelection(delta: number) {
  const items = Array.from(listEl.querySelectorAll("li:not(.more)"));
  if (items.length === 0) return;
  const currentIndex = items.findIndex((el) => el.classList.contains("selected"));
  const nextIndex = Math.min(Math.max(currentIndex + delta, 0), items.length - 1);
  (items[nextIndex] as HTMLElement).click();
}

function init() {
  tabInstalledEl.addEventListener("click", () => selectTab("installed"));
  tabBrewEl.addEventListener("click", () => selectTab("brew"));
  filterEl.addEventListener("input", renderList);

  document.addEventListener("keydown", (event) => {
    if (event.key === "/" && document.activeElement !== filterEl) {
      event.preventDefault();
      filterEl.focus();
      return;
    }
    if (event.target === filterEl) return;
    if (event.key === "ArrowDown") {
      event.preventDefault();
      moveSelection(1);
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      moveSelection(-1);
    } else if (event.key === "Enter" && state.tab === "installed" && state.selected?.tab === "installed") {
      event.preventDefault();
      onBuild(state.selected.candidate);
    }
  });

  void (async () => {
    const [installedResult, webResult] = await Promise.all([
      run("Loading fonts…", () => installed()),
      run("Loading slots…", () => webFonts()),
    ]);
    if (installedResult) state.candidates = installedResult.candidates;
    if (webResult) state.web = webResult;
    renderList();
    renderSlots();
  })();
}

init();
