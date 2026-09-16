const sheetReady = fetch(chrome.runtime.getURL("halfbold.css"))
  .then((response) => response.text())
  .then((css) => {
    const sheet = new CSSStyleSheet();
    sheet.replaceSync(css);
    return sheet;
  });

const patched = new WeakSet();

async function adopt(root) {
  if (patched.has(root)) return;
  patched.add(root);
  const sheet = await sheetReady;
  root.adoptedStyleSheets = [...root.adoptedStyleSheets, sheet];
  root.querySelectorAll("*").forEach(patchIfShadowHost);
}

function patchIfShadowHost(element) {
  if (element.shadowRoot) adopt(element.shadowRoot);
}

function scan(root) {
  root.querySelectorAll("*").forEach(patchIfShadowHost);
}

new MutationObserver((mutations) => {
  for (const mutation of mutations) {
    for (const node of mutation.addedNodes) {
      if (node.nodeType !== Node.ELEMENT_NODE) continue;
      patchIfShadowHost(node);
      scan(node);
    }
  }
}).observe(document, { childList: true, subtree: true });

scan(document);
setTimeout(() => scan(document), 1000);
setTimeout(() => scan(document), 3000);
