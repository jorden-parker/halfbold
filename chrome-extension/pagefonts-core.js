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

  globalThis.halfboldPageFonts = {
    familyKey,
    fontFaceDescriptors,
    isConvertibleFamily,
    localSource,
    normalStyle,
    parseFamilyList,
    pickFontUrl,
    toBase64,
    weightRange,
  };
})();
