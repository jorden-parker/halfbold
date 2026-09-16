const WATCHED = ["manifest.json", "halfbold.css", "shadow.js", "autoreload.js"];
const ALARM = "halfbold-watch";
const KEY = "fingerprint";

async function fingerprint() {
  const parts = await Promise.all(
    WATCHED.map((file) =>
      fetch(chrome.runtime.getURL(file), { cache: "no-store" }).then((r) =>
        r.text()
      )
    )
  );
  const bytes = new TextEncoder().encode(parts.join(" "));
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return [...new Uint8Array(digest)]
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

async function remember() {
  await chrome.storage.session.set({ [KEY]: await fingerprint() });
  chrome.alarms.create(ALARM, { periodInMinutes: 0.5 });
}

async function reloadIfChanged() {
  const { [KEY]: known } = await chrome.storage.session.get(KEY);
  const current = await fingerprint();
  if (known === undefined) {
    await chrome.storage.session.set({ [KEY]: current });
    return;
  }
  if (current !== known) chrome.runtime.reload();
}

chrome.runtime.onInstalled.addListener(remember);
chrome.runtime.onStartup.addListener(remember);
chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === ALARM) reloadIfChanged();
});
