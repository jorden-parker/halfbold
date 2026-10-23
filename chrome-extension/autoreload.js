importScripts("pagefonts-core.js");

const {
  LIMITS,
  allowsPageFetch,
  familyKey,
  fromBase64Limited,
  hasFontSignature,
  prohibitsMixedContent,
} = globalThis.halfboldPageFonts;
const GENERIC_FAMILIES = ["standard", "sansserif", "serif", "fixed"];
const CONTENT_SCRIPTS = ["pagefonts-core.js", "limited-body.js", "pagefonts.js"];
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

function pageUrlsOf(sender) {
  return [sender.origin, sender.tab?.url];
}

function facesOf(message) {
  return Array.isArray(message.faces) ? message.faces : [];
}

function hasTupleOrigin(sender) {
  return typeof sender.origin === "string" && sender.origin !== "null";
}

function fetchableFaces(faces, sender) {
  if (!hasTupleOrigin(sender)) return [];
  return faces.filter((face) => allowsPageFetch(pageUrlsOf(sender), face.url));
}

function servedKey(key) {
  return `served:${config.generation}:${key}`;
}

function decodedFaces(faces) {
  let total = 0;
  return faces.map((face) => {
    const bytes = fromBase64Limited(face.data, LIMITS.familyBytes - total);
    if (!hasFontSignature(bytes)) throw new Error("not a font");
    total += bytes.length;
    return {
      weight: face.weight,
      style: face.style,
      unicodeRange: face.unicodeRange,
      data: face.data,
    };
  });
}

async function convertWebfont(faces) {
  try {
    if (!faces.length) throw new Error("no usable faces");
    return await askHost({ type: "convert-webfont", faces: decodedFaces(faces) });
  } catch (error) {
    return { type: "unchanged", reason: String(error) };
  }
}

function remembered(key, convert) {
  const storageKey = servedKey(key);
  if (!conversions.has(storageKey)) {
    const conversion = chrome.storage.local.get(storageKey).then(async (stored) => {
      if (stored[storageKey]) return stored[storageKey];
      const reply = await convert();
      if (reply?.type === "converted" && reply.faces?.length) {
        await chrome.storage.local.set({ [storageKey]: reply });
      }
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

function convertPageFaces(message, sender) {
  const faces = fetchableFaces(facesOf(message), sender);
  return remembered(storageKeyFor(faces, sender), () => convertWebfont(faces));
}

function storageKeyFor(faces, sender) {
  const key = `${sender.origin}\n${webfontKey(faces)}`;
  return prohibitsMixedContent(pageUrlsOf(sender)) ? `no-mixed:${key}` : key;
}

async function storedWebfont(message, sender) {
  const storageKey = servedKey(storageKeyFor(fetchableFaces(facesOf(message), sender), sender));
  const stored = await chrome.storage.local.get(storageKey);
  return stored[storageKey] ?? null;
}

function convertInstalled(message) {
  return remembered(`installed:${familyKey(message.family)}`, () =>
    askHost({ type: "convert-installed", family: message.family }),
  );
}

function reportTotals(message, sender) {
  recordTotals(sender, message);
  return Promise.resolve(null);
}

const pageHandlers = new Map([
  ["halfbold-config", () => restoredConfig.then(() => config)],
  ["halfbold-stored-webfont", storedWebfont],
  ["halfbold-convert-webfont", convertPageFaces],
  ["halfbold-convert-installed", convertInstalled],
  ["halfbold-totals", reportTotals],
]);

function handlePageMessage(message, sender) {
  const handler = pageHandlers.get(message.type);
  return handler ? handler(message, sender) : null;
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
