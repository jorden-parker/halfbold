let port;
let retryTimer;
let updates = Promise.resolve();

async function applyUpdate(message) {
  await chrome.storage.local.set({ liveStyle: message });
  const tabs = await chrome.tabs.query({});
  await Promise.all(tabs.map(async (tab) => {
    if (!tab.id) return;
    try {
      await chrome.scripting.executeScript({
        target: { tabId: tab.id, allFrames: true },
        files: ["shadow.js"],
      });
      await chrome.tabs.sendMessage(tab.id, { type: "halfbold-style", ...message });
    } catch {
      return;
    }
  }));
}

function connect() {
  if (port) return;
  clearTimeout(retryTimer);
  const connection = chrome.runtime.connectNative("com.jorden.halfbold");
  port = connection;
  connection.onMessage.addListener((message) => {
    if (message.ping) {
      connection.postMessage({ pong: true });
      return;
    }
    if (typeof message.css !== "string" || typeof message.revision !== "string") return;
    updates = updates.catch(() => {}).then(async () => {
      await applyUpdate(message);
      if (port === connection) connection.postMessage({ revision: message.revision });
    });
  });
  connection.onDisconnect.addListener(() => {
    void chrome.runtime.lastError;
    if (port === connection) port = undefined;
    retryTimer = setTimeout(connect, 2000);
  });
}

chrome.runtime.onInstalled.addListener(connect);
chrome.runtime.onStartup.addListener(connect);
chrome.alarms.create("halfbold-connect", { periodInMinutes: 0.5 });
chrome.alarms.onAlarm.addListener(connect);
connect();
