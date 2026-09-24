(() => {
  if (globalThis.halfboldLiveStyle) return;
  globalThis.halfboldLiveStyle = true;
  const sheet = new CSSStyleSheet();
  const patched = new WeakSet();
  let currentRevision;
  let receivedLiveStyle = false;

  function apply(message) {
    if (typeof message?.css !== "string") return;
    if (message.revision && currentRevision === message.revision) return;
    sheet.replaceSync(message.css);
    currentRevision = message.revision;
  }

  function patchIfShadowHost(element) {
    if (element.shadowRoot) adopt(element.shadowRoot);
  }

  function scan(root) {
    root.querySelectorAll("*").forEach(patchIfShadowHost);
  }

  const observer = new MutationObserver((mutations) => {
    for (const mutation of mutations) {
      for (const node of mutation.addedNodes) {
        if (node.nodeType !== Node.ELEMENT_NODE) continue;
        patchIfShadowHost(node);
        scan(node);
      }
    }
  });

  function adopt(root) {
    if (patched.has(root)) return;
    patched.add(root);
    root.adoptedStyleSheets = [...root.adoptedStyleSheets, sheet];
    observer.observe(root, { childList: true, subtree: true });
    scan(root);
  }

  chrome.runtime.onMessage.addListener((message, sender, respond) => {
    if (sender.id !== chrome.runtime.id || message.type !== "halfbold-style") return;
    receivedLiveStyle = true;
    apply(message);
    respond({ revision: currentRevision });
  });
  chrome.storage.onChanged.addListener((changes, area) => {
    if (area !== "local" || !changes.liveStyle?.newValue) return;
    receivedLiveStyle = true;
    apply(changes.liveStyle.newValue);
  });
  chrome.storage.local.get("liveStyle").then(async ({ liveStyle }) => {
    if (receivedLiveStyle) return;
    if (liveStyle) {
      apply(liveStyle);
    } else {
      const css = await fetch(chrome.runtime.getURL("halfbold.css")).then((r) => r.text());
      if (!receivedLiveStyle) apply({ css });
    }
  });
  adopt(document);
  setTimeout(() => scan(document), 1000);
  setTimeout(() => scan(document), 3000);
})();
