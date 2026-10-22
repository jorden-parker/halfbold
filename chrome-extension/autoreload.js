importScripts("pagefonts-core.js");

const { familyKey, toBase64 } = globalThis.halfboldPageFonts;
const GENERIC_FAMILIES = ["standard", "sansserif", "serif", "fixed"];
const MAX_FONT_BYTES = 16 * 1024 * 1024;
const MAX_CSS_BYTES = 2 * 1024 * 1024;
const CONTENT_SCRIPTS = ["pagefonts-core.js", "pagefonts.js"];
let port;
let retryTimer;
let nextRequestId = 1;
let config = { enabled: false, generation: null };
let appliedGeneration = null;
let updates = Promise.resolve();
const waiting = new Map();
const conversions = new Map();
const frameTotals = new Map();
const restoredConfig = chrome.storage.local.get("config").then((stored) => {
  if (stored.config && !config.generation) config = stored.config;
});

function isWebUrl(value) {
  try {
    const url = new URL(value);
    return url.protocol === "http:" || url.protocol === "https:";
  } catch {
    return false;
  }
}

function askHost(message) {
  if (!port) return Promise.resolve(null);
  const id = nextRequestId++;
  return new Promise((resolve) => {
    waiting.set(id, resolve);
    port.postMessage({ ...message, id });
  });
}

function settleWaiting(message) {
  const resolve = waiting.get(message.id);
  if (!resolve) return;
  waiting.delete(message.id);
  resolve(message);
}

function releaseWaiting() {
  for (const resolve of waiting.values()) resolve(null);
  waiting.clear();
}

async function fetchLimited(url, limit) {
  const response = await fetch(url, { credentials: "omit" });
  if (!response.ok) throw new Error(`${response.status} ${url}`);
  const bytes = new Uint8Array(await response.arrayBuffer());
  if (bytes.length > limit) throw new Error(`too large ${url}`);
  return bytes;
}

async function encodedFaces(faces) {
  let total = 0;
  return Promise.all(
    faces.filter((face) => isWebUrl(face.url)).map(async (face) => {
      const bytes = await fetchLimited(face.url, MAX_FONT_BYTES);
      total += bytes.length;
      if (total > MAX_FONT_BYTES) throw new Error("family too large");
      return {
        weight: face.weight,
        style: face.style,
        unicodeRange: face.unicodeRange,
        data: toBase64(bytes),
      };
    }),
  );
}

async function convertWebfont(faces) {
  try {
    return await askHost({ type: "convert-webfont", faces: await encodedFaces(faces) });
  } catch (error) {
    return { type: "unchanged", reason: String(error) };
  }
}

function remembered(key, convert) {
  const storageKey = `served:${config.generation}:${key}`;
  if (!conversions.has(storageKey)) {
    const conversion = chrome.storage.local.get(storageKey).then(async (stored) => {
      if (stored[storageKey]) return stored[storageKey];
      const reply = await convert();
      if (reply?.type === "converted") await chrome.storage.local.set({ [storageKey]: reply });
      else conversions.delete(storageKey);
      return reply;
    });
    conversions.set(storageKey, conversion);
  }
  return conversions.get(storageKey);
}

function webfontKey(faces) {
  return faces
    .map((face) => [face.url, face.weight.join(" "), face.style, face.unicodeRange].join("|"))
    .sort()
    .join("\n");
}

async function fetchCss(url) {
  if (!isWebUrl(url)) return null;
  try {
    return { css: new TextDecoder().decode(await fetchLimited(url, MAX_CSS_BYTES)) };
  } catch {
    return null;
  }
}

function recordTotals(sender, message) {
  if (!sender.tab?.id) return;
  frameTotals.set(`${sender.tab.id}:${sender.frameId}`, {
    tab: sender.tab.id,
    converted: Number(message.converted) || 0,
    unchanged: Number(message.unchanged) || 0,
  });
}

function summedTotals() {
  let converted = 0;
  let unchanged = 0;
  for (const totals of frameTotals.values()) {
    converted += totals.converted;
    unchanged += totals.unchanged;
  }
  return { converted, unchanged };
}

function handlePageMessage(message, sender) {
  switch (message.type) {
    case "halfbold-config":
      return restoredConfig.then(() => config);
    case "halfbold-fetch-css":
      return fetchCss(message.url);
    case "halfbold-convert-webfont":
      return remembered(webfontKey(message.faces), () => convertWebfont(message.faces));
    case "halfbold-convert-installed":
      return remembered(`installed:${familyKey(message.family)}`, () =>
        askHost({ type: "convert-installed", family: message.family }),
      );
    case "halfbold-totals":
      recordTotals(sender, message);
      return Promise.resolve(null);
    default:
      return null;
  }
}

chrome.runtime.onMessage.addListener((message, sender, respond) => {
  if (sender.id !== chrome.runtime.id) return false;
  const reply = handlePageMessage(message, sender);
  if (!reply) return false;
  reply.then(respond, () => respond(null));
  return true;
});

function clearDefaultFonts() {
  return Promise.all(
    GENERIC_FAMILIES.map((genericFamily) => chrome.fontSettings.clearFont({ genericFamily })),
  );
}

async function chromeDefaultFonts() {
  const families = {};
  for (const genericFamily of GENERIC_FAMILIES) {
    const { fontId } = await chrome.fontSettings.getFont({ genericFamily });
    if (fontId) families[genericFamily] = fontId;
  }
  return families;
}

async function applyDefaultFonts() {
  await clearDefaultFonts();
  if (!config.enabled) return;
  const reply = await askHost({ type: "defaults", families: await chromeDefaultFonts() });
  const halfFamilies = Object.entries(reply?.families ?? {});
  await Promise.all(
    halfFamilies.map(([genericFamily, fontId]) => chrome.fontSettings.setFont({ genericFamily, fontId })),
  );
}

async function pushConfigToTabs() {
  const tabs = await chrome.tabs.query({});
  await Promise.all(
    tabs.map(async (tab) => {
      if (!tab.id) return;
      try {
        await chrome.scripting.executeScript({
          target: { tabId: tab.id, allFrames: true },
          files: CONTENT_SCRIPTS,
        });
        await chrome.tabs.sendMessage(tab.id, { type: "halfbold-config", ...config });
      } catch {
        return;
      }
    }),
  );
}

async function applyConfig(message) {
  if (message.generation === appliedGeneration) return;
  config = { enabled: Boolean(message.enabled), generation: message.generation };
  conversions.clear();
  const stored = await chrome.storage.local.get(null);
  const stale = Object.keys(stored).filter(
    (key) => key.startsWith("served:") && !key.startsWith(`served:${config.generation}:`),
  );
  await chrome.storage.local.remove([...stale, "liveStyle"]);
  await chrome.storage.local.set({ config });
  await pushConfigToTabs();
  await applyDefaultFonts().catch(() => {});
  appliedGeneration = config.generation;
}

function connect() {
  if (port) return;
  clearTimeout(retryTimer);
  const connection = chrome.runtime.connectNative("com.jorden.halfbold");
  port = connection;
  connection.onMessage.addListener((message) => {
    if (message.ping) {
      connection.postMessage({ pong: true, generation: appliedGeneration, ...summedTotals() });
      return;
    }
    if (message.id !== undefined) {
      settleWaiting(message);
      return;
    }
    if (message.type !== "config" || typeof message.generation !== "string") return;
    updates = updates.catch(() => {}).then(() => applyConfig(message));
  });
  connection.onDisconnect.addListener(() => {
    void chrome.runtime.lastError;
    if (port === connection) port = undefined;
    releaseWaiting();
    retryTimer = setTimeout(connect, 2000);
  });
}

chrome.tabs.onRemoved.addListener((tabId) => {
  for (const [key, totals] of frameTotals) {
    if (totals.tab === tabId) frameTotals.delete(key);
  }
});
chrome.runtime.onInstalled.addListener(connect);
chrome.runtime.onStartup.addListener(connect);
chrome.alarms.create("halfbold-connect", { periodInMinutes: 0.5 });
chrome.alarms.onAlarm.addListener(connect);
connect();
