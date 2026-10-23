(() => {
  const GENERIC_FAMILIES = new Set([
    "serif",
    "sans-serif",
    "monospace",
    "cursive",
    "fantasy",
    "system-ui",
    "ui-serif",
    "ui-sans-serif",
    "ui-monospace",
    "ui-rounded",
    "math",
    "emoji",
    "fangsong",
    "inherit",
    "initial",
    "unset",
    "revert",
    "revert-layer",
  ]);
  const ICON_FAMILY = /icon|symbol|awesome|material|glyph|emoji|dashicons|codicon/i;
  const ACCEPTED_FORMATS = new Set(["woff2", "woff", "truetype", "ttf", "opentype"]);
  const WEIGHT_KEYWORDS = { normal: 400, bold: 700 };
  const QUOTES = new Set(['"', "'"]);
  const PAREN_DEPTH = { "(": 1, ")": -1 };
  const LIMITS = {
    familyBytes: 16 * 1024 * 1024,
    pageBytes: 64 * 1024 * 1024,
    stylesheetBytes: 2 * 1024 * 1024,
    fetchTimeoutMs: 15000,
  };
  const FONT_SIGNATURES = ["wOF2", "wOFF", "\0\x01\0\0", "true", "OTTO"];

  function nextNesting(nesting, char) {
    if (nesting.quote) return { ...nesting, quote: char === nesting.quote ? null : nesting.quote };
    if (QUOTES.has(char)) return { ...nesting, quote: char };
    return { ...nesting, depth: nesting.depth + (PAREN_DEPTH[char] ?? 0) };
  }

  function splitTopLevel(value, separator) {
    const parts = [""];
    let nesting = { quote: null, depth: 0 };
    for (const char of value) {
      const atTopLevel = !nesting.quote && nesting.depth === 0;
      if (atTopLevel && char === separator) parts.push("");
      else parts[parts.length - 1] += char;
      nesting = nextNesting(nesting, char);
    }
    return parts.map((part) => part.trim()).filter(Boolean);
  }

  function unquote(value) {
    const first = value[0];
    if ((first === '"' || first === "'") && value.endsWith(first)) return value.slice(1, -1);
    return value.replace(/\s+/g, " ");
  }

  function parseFamilyList(value) {
    return splitTopLevel(value, ",").map(unquote).filter(Boolean);
  }

  function familyKey(family) {
    return family.toLowerCase();
  }

  function isConvertibleFamily(family) {
    return !GENERIC_FAMILIES.has(familyKey(family)) && !ICON_FAMILY.test(family);
  }

  function sourceEntry(entry) {
    const url = entry.match(/^url\(\s*(['"]?)(.*?)\1\s*\)/);
    if (!url) return null;
    const format = entry.match(/format\(\s*['"]?([\w-]+)['"]?\s*\)/);
    return { url: url[2], format: format ? format[1].toLowerCase() : null };
  }

  function pickFontUrl(src, baseUrl) {
    const entries = splitTopLevel(src, ",").map(sourceEntry).filter(Boolean);
    const usable = entries.find((entry) => !entry.format || ACCEPTED_FORMATS.has(entry.format));
    if (!usable) return null;
    const url = new URL(usable.url, baseUrl);
    return url.protocol === "http:" || url.protocol === "https:" ? url.href : null;
  }

  function weightRange(value) {
    const weights = (value || "normal")
      .trim()
      .split(/\s+/)
      .map((part) => WEIGHT_KEYWORDS[part] ?? Number(part));
    if (weights.some(Number.isNaN)) return [400, 400];
    return [weights[0], weights[weights.length - 1]];
  }

  function normalStyle(value) {
    return /italic|oblique/.test(value || "") ? "italic" : "normal";
  }

  function fontFaceDescriptors(face) {
    const descriptors = { weight: face.weight, style: face.style };
    if (face.unicode_range) descriptors.unicodeRange = face.unicode_range;
    return descriptors;
  }

  function localSource(names) {
    return names.map((name) => `local(${JSON.stringify(name)})`).join(", ");
  }

  function toBase64(bytes) {
    let binary = "";
    for (let start = 0; start < bytes.length; start += 0x8000) {
      binary += String.fromCharCode(...bytes.subarray(start, start + 0x8000));
    }
    return btoa(binary);
  }

  function isWebUrl(value) {
    return protocolOf(value) === "http:" || protocolOf(value) === "https:";
  }

  function protocolOf(value) {
    try {
      return new URL(value).protocol;
    } catch {
      return "";
    }
  }

  function prohibitsMixedContent(pageUrls) {
    return pageUrls.some((url) => protocolOf(url) === "https:");
  }

  function allowsPageFetch(pageUrls, url) {
    if (!isWebUrl(url)) return false;
    return !(protocolOf(url) === "http:" && prohibitsMixedContent(pageUrls));
  }

  function hasFontSignature(bytes) {
    const prefix = String.fromCharCode(...bytes.subarray(0, 4));
    return FONT_SIGNATURES.includes(prefix);
  }

  function fromBase64Limited(text, limit) {
    if (text.length > Math.ceil(limit / 3) * 4) throw new Error("too large base64");
    const bytes = Uint8Array.from(atob(text), (char) => char.charCodeAt(0));
    if (bytes.length > limit) throw new Error("too large data");
    return bytes;
  }

  function encodedFace(face, bytes) {
    return {
      url: face.url,
      weight: face.weight,
      style: face.style,
      unicodeRange: face.unicodeRange,
      data: toBase64(bytes),
    };
  }

  globalThis.halfboldPageFonts = {
    LIMITS,
    allowsPageFetch,
    encodedFace,
    familyKey,
    fontFaceDescriptors,
    fromBase64Limited,
    hasFontSignature,
    isConvertibleFamily,
    isWebUrl,
    localSource,
    normalStyle,
    parseFamilyList,
    pickFontUrl,
    prohibitsMixedContent,
    toBase64,
    weightRange,
  };
})();
