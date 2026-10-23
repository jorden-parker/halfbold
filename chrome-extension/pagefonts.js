(() => {
  if (globalThis.halfboldPageFontsRunning) return;
  globalThis.halfboldPageFontsRunning = true;
  const {
    LIMITS,
    allowsPageFetch,
    encodedFace,
    familyKey,
    fontFaceDescriptors,
    isConvertibleFamily,
    localSource,
    normalStyle,
    parseFamilyList,
    pickFontUrl,
    weightRange,
  } = globalThis.halfboldPageFonts;
  const { createByteBudget, fetchLimitedBytes } = globalThis.halfboldLimitedBody;
  const SCAN_DELAY = 500;
  const MAX_TEXT_NODES = 5000;
  const caltSheet = new CSSStyleSheet();
  const roots = new Set();
  const requested = new Set();
  const addedFaces = [];
  const crossOriginSheets = new Map();
  const totals = { converted: 0, unchanged: 0 };
  let config = { enabled: false, generation: null };
  let scanTimer = null;
  let pageBudget = createByteBudget(LIMITS.pageBytes);

  caltSheet.replaceSync(
    '* { text-rendering: optimizeLegibility !important; font-feature-settings: "calt" 1 !important; }',
  );

  function ask(message) {
    return chrome.runtime.sendMessage(message).catch(() => null);
  }

  function adoptCalt(root) {
    if (!root.adoptedStyleSheets.includes(caltSheet)) {
      root.adoptedStyleSheets = [...root.adoptedStyleSheets, caltSheet];
    }
  }

  function dropCalt(root) {
    root.adoptedStyleSheets = root.adoptedStyleSheets.filter((sheet) => sheet !== caltSheet);
  }

  function watchRoot(root) {
    if (roots.has(root)) return;
    roots.add(root);
    observer.observe(root, { childList: true, subtree: true });
    if (config.enabled) adoptCalt(root);
    findShadowRoots(root);
  }

  function findShadowRoots(root) {
    for (const element of root.querySelectorAll("*")) {
      if (element.shadowRoot) watchRoot(element.shadowRoot);
    }
  }

  const observer = new MutationObserver((mutations) => {
    for (const mutation of mutations) {
      for (const node of mutation.addedNodes) {
        if (node.nodeType !== Node.ELEMENT_NODE) continue;
        if (node.shadowRoot) watchRoot(node.shadowRoot);
        findShadowRoots(node);
      }
    }
    scheduleScan();
  });

  function scheduleScan() {
    if (!config.enabled || scanTimer) return;
    scanTimer = setTimeout(() => {
      scanTimer = null;
      void scan();
    }, SCAN_DELAY);
  }

  function textElements() {
    const elements = new Set();
    let budget = MAX_TEXT_NODES;
    for (const root of roots) {
      const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
      while (budget > 0 && walker.nextNode()) {
        budget -= 1;
        const text = walker.currentNode;
        if (text.parentElement && text.data.trim()) elements.add(text.parentElement);
      }
    }
    return elements;
  }

  function usedFamilies() {
    const families = new Map();
    for (const element of textElements()) {
      const stack = parseFamilyList(getComputedStyle(element).fontFamily);
      for (const family of stack.filter(isConvertibleFamily)) {
        families.set(familyKey(family), family);
      }
    }
    return families;
  }

  function addFaceRule(rule, baseUrl, faces) {
    const descriptor = (name) => rule.style.getPropertyValue(name);
    const url = pickFontUrl(descriptor("src"), baseUrl);
    const family = parseFamilyList(descriptor("font-family"))[0];
    if (!url || !family) return;
    const key = familyKey(family);
    if (!faces.has(key)) faces.set(key, []);
    faces.get(key).push({
      url,
      weight: weightRange(descriptor("font-weight")),
      style: normalStyle(descriptor("font-style")),
      unicodeRange: descriptor("unicode-range"),
    });
  }

  async function collectFaceRules(rules, baseUrl, faces) {
    for (const rule of rules) {
      if (rule instanceof CSSFontFaceRule) {
        addFaceRule(rule, baseUrl, faces);
      } else if (rule instanceof CSSImportRule) {
        if (rule.styleSheet) await collectSheet(rule.styleSheet, faces);
      } else if (rule.cssRules) {
        await collectFaceRules(rule.cssRules, baseUrl, faces);
      }
    }
  }

  function allowsFromThisPage(url) {
    return allowsPageFetch([location.href], url);
  }

  async function fetchPageBytes(url, limit) {
    if (!allowsFromThisPage(url)) throw new Error(`blocked ${url}`);
    const budget = pageBudget;
    const reserved = budget.reserve(limit);
    const bytes = await fetchLimitedBytes(url, { limit: reserved, timeoutMs: LIMITS.fetchTimeoutMs });
    budget.settle(reserved, bytes.length);
    return bytes;
  }

  async function fetchStylesheetRules(href) {
    try {
      const bytes = await fetchPageBytes(href, LIMITS.stylesheetBytes);
      const sheet = new CSSStyleSheet();
      sheet.replaceSync(new TextDecoder().decode(bytes));
      return [...sheet.cssRules];
    } catch {
      return [];
    }
  }

  async function crossOriginRules(href) {
    if (!crossOriginSheets.has(href)) {
      crossOriginSheets.set(href, fetchStylesheetRules(href));
    }
    return crossOriginSheets.get(href);
  }

  async function collectSheet(sheet, faces) {
    const baseUrl = sheet.href || document.baseURI;
    let rules;
    try {
      rules = sheet.cssRules;
    } catch {
      rules = sheet.href ? await crossOriginRules(sheet.href) : [];
    }
    await collectFaceRules(rules, baseUrl, faces);
  }

  async function declaredFaces() {
    const faces = new Map();
    const sheets = [...document.styleSheets, ...document.adoptedStyleSheets];
    await Promise.all(sheets.map((sheet) => collectSheet(sheet, faces)));
    return faces;
  }

  async function encodedFaces(faces) {
    const encoded = [];
    let familyLeft = LIMITS.familyBytes;
    for (const face of faces.filter((candidate) => allowsFromThisPage(candidate.url))) {
      const bytes = await fetchPageBytes(face.url, familyLeft);
      familyLeft -= bytes.length;
      encoded.push(encodedFace(face, bytes));
    }
    return encoded;
  }

  async function convertDeclared(faces) {
    const stored = await ask({ type: "halfbold-stored-webfont", faces });
    if (stored?.type === "converted") return stored;
    try {
      return await ask({ type: "halfbold-convert-webfont", faces: await encodedFaces(faces) });
    } catch {
      return { type: "unchanged" };
    }
  }

  async function scan() {
    const generation = config.generation;
    const families = usedFamilies();
    const room = Math.max(LIMITS.familiesPerPage - requested.size, 0);
    const fresh = [...families].filter(([key]) => !requested.has(key)).slice(0, room);
    if (!fresh.length) return;
    const declared = await declaredFaces();
    await Promise.all(
      fresh.map(async ([key, family]) => {
        requested.add(key);
        const reply = declared.has(key)
          ? await convertDeclared(declared.get(key))
          : await ask({ type: "halfbold-convert-installed", family });
        if (generation !== config.generation) return;
        await applyConversion(family, reply);
      }),
    );
    void ask({ type: "halfbold-totals", ...totals });
  }

  async function servedFontFace(family, face) {
    const descriptors = fontFaceDescriptors(face);
    if (face.file) {
      const response = await fetch(chrome.runtime.getURL(`fonts/${face.file}`));
      return new FontFace(family, await response.arrayBuffer(), descriptors);
    }
    return new FontFace(family, localSource(face.local), descriptors);
  }

  function unchangedCount(reply) {
    if (Array.isArray(reply?.unchanged)) return reply.unchanged.length;
    return reply?.faces?.length ? 0 : 1;
  }

  async function addServedFaces(family, served) {
    const faces = await Promise.all(served.map((face) => servedFontFace(family, face)));
    await Promise.all(faces.map((face) => face.load()));
    if (!config.enabled) return;
    for (const face of faces) {
      document.fonts.add(face);
      addedFaces.push(face);
    }
    totals.converted += served.filter((face) => face.file).length;
  }

  async function applyConversion(family, reply) {
    totals.unchanged += unchangedCount(reply);
    if (!reply?.faces?.length) return;
    await addServedFaces(family, reply.faces).catch(() => {
      totals.unchanged += 1;
    });
  }

  function removeConversions() {
    for (const face of addedFaces.splice(0)) document.fonts.delete(face);
    requested.clear();
    crossOriginSheets.clear();
    pageBudget = createByteBudget(LIMITS.pageBytes);
    totals.converted = 0;
    totals.unchanged = 0;
  }

  function applyConfig(next) {
    if (typeof next?.generation !== "string") return;
    if (next.generation === config.generation) return;
    config = { enabled: Boolean(next.enabled), generation: next.generation };
    removeConversions();
    for (const root of roots) {
      if (config.enabled) adoptCalt(root);
      else dropCalt(root);
    }
    void ask({ type: "halfbold-totals", ...totals });
    scheduleScan();
  }

  chrome.runtime.onMessage.addListener((message, sender, respond) => {
    if (sender.id !== chrome.runtime.id || message.type !== "halfbold-config") return;
    applyConfig(message);
    respond({ generation: config.generation });
  });
  document.fonts.addEventListener("loadingdone", scheduleScan);
  watchRoot(document);
  ask({ type: "halfbold-config" }).then(applyConfig);
})();
