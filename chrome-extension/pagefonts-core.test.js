import { describe, expect, test } from "bun:test";
import "./pagefonts-core.js";

const {
  familyKey,
  fontFaceDescriptors,
  isConvertibleFamily,
  localSource,
  normalStyle,
  parseFamilyList,
  pickFontUrl,
  toBase64,
  weightRange,
} = globalThis.halfboldPageFonts;

describe("parseFamilyList", () => {
  test("keeps quoted names with commas and unquotes them", () => {
    expect(parseFamilyList(`"Foo, Bar", 'Baz Qux', Inter Display, sans-serif`)).toEqual([
      "Foo, Bar",
      "Baz Qux",
      "Inter Display",
      "sans-serif",
    ]);
  });

  test("ignores empty entries", () => {
    expect(parseFamilyList(" , Georgia ,")).toEqual(["Georgia"]);
  });
});

describe("isConvertibleFamily", () => {
  test("skips generic families and icon fonts", () => {
    expect(isConvertibleFamily("sans-serif")).toBe(false);
    expect(isConvertibleFamily("System-UI")).toBe(false);
    expect(isConvertibleFamily("Material Symbols Outlined")).toBe(false);
    expect(isConvertibleFamily("FontAwesome")).toBe(false);
    expect(isConvertibleFamily("Inter")).toBe(true);
  });

  test("skips family names too long to be real", () => {
    expect(isConvertibleFamily("x".repeat(201))).toBe(false);
    expect(isConvertibleFamily("x".repeat(200))).toBe(true);
  });

  test("matches families without regard to case", () => {
    expect(familyKey("Source Serif 4")).toBe(familyKey("source serif 4"));
  });
});

describe("pickFontUrl", () => {
  const base = "https://fonts.example/css/family.css";

  test("prefers the first supported format and resolves it against the sheet", () => {
    const src = `local("Inter"), url(../f/inter.eot) format("embedded-opentype"), url("../f/inter.woff2") format("woff2")`;
    expect(pickFontUrl(src, base)).toBe("https://fonts.example/f/inter.woff2");
  });

  test("accepts a source with no format hint", () => {
    expect(pickFontUrl("url(a.ttf)", base)).toBe("https://fonts.example/css/a.ttf");
  });

  test("rejects sources that are not served over http", () => {
    expect(pickFontUrl("url(data:font/woff2;base64,AAAA)", base)).toBeNull();
    expect(pickFontUrl(`local("Inter")`, base)).toBeNull();
  });
});

describe("descriptors", () => {
  test("reads weight keywords and ranges", () => {
    expect(weightRange("normal")).toEqual([400, 400]);
    expect(weightRange("bold")).toEqual([700, 700]);
    expect(weightRange("100 900")).toEqual([100, 900]);
    expect(weightRange("")).toEqual([400, 400]);
  });

  test("folds oblique into italic", () => {
    expect(normalStyle("oblique 10deg")).toBe("italic");
    expect(normalStyle("normal")).toBe("normal");
  });

  test("builds FontFace descriptors and leaves out an empty unicode range", () => {
    expect(fontFaceDescriptors({ weight: "400", style: "normal", unicode_range: "" })).toEqual({
      weight: "400",
      style: "normal",
    });
    expect(
      fontFaceDescriptors({ weight: "400", style: "italic", unicode_range: "U+0000-00FF" }),
    ).toEqual({ weight: "400", style: "italic", unicodeRange: "U+0000-00FF" });
  });

  test("quotes local font names", () => {
    expect(localSource(["Multi Light", "Multi-Light"])).toBe(
      `local("Multi Light"), local("Multi-Light")`,
    );
  });
});

test("toBase64 encodes large byte arrays", () => {
  const bytes = new Uint8Array(100000).map((_, index) => index % 256);
  expect(Buffer.from(toBase64(bytes), "base64").equals(Buffer.from(bytes))).toBe(true);
});

const {
  allowsPageFetch,
  fromBase64Limited,
  hasFontSignature,
  prohibitsMixedContent,
  isWebUrl,
  LIMITS,
} = globalThis.halfboldPageFonts;

describe("isWebUrl", () => {
  test("accepts only http and https", () => {
    expect(isWebUrl("https://a.example/x.woff2")).toBe(true);
    expect(isWebUrl("http://a.example/x.woff2")).toBe(true);
    expect(isWebUrl("file:///etc/passwd")).toBe(false);
    expect(isWebUrl("data:font/woff2;base64,AA==")).toBe(false);
    expect(isWebUrl("not a url")).toBe(false);
    expect(isWebUrl(undefined)).toBe(false);
  });
});

describe("mixed content policy", () => {
  test("an https page prohibits mixed content and an http page does not", () => {
    expect(prohibitsMixedContent(["https://a.example/"])).toBe(true);
    expect(prohibitsMixedContent(["http://a.example/"])).toBe(false);
  });

  test("any https address among the page's urls prohibits mixed content", () => {
    expect(prohibitsMixedContent(["http://a.example/", "https://top.example/"])).toBe(true);
    expect(prohibitsMixedContent([undefined, "about:blank"])).toBe(false);
  });

  test("an https page never allows an http font or stylesheet", () => {
    expect(allowsPageFetch(["https://a.example/"], "http://cdn.example/a.woff2")).toBe(false);
    expect(allowsPageFetch(["https://a.example/"], "https://cdn.example/a.woff2")).toBe(true);
  });

  test("an http page allows http and https fonts but not other schemes", () => {
    expect(allowsPageFetch(["http://a.example/"], "http://cdn.example/a.woff2")).toBe(true);
    expect(allowsPageFetch(["http://a.example/"], "https://cdn.example/a.woff2")).toBe(true);
    expect(allowsPageFetch(["http://a.example/"], "ftp://cdn.example/a.woff2")).toBe(false);
  });
});

describe("hasFontSignature", () => {
  const bytesOf = (text) => new TextEncoder().encode(text);

  test("accepts the signatures of woff2, woff, truetype, opentype and collections", () => {
    expect(hasFontSignature(bytesOf("wOF2 rest"))).toBe(true);
    expect(hasFontSignature(bytesOf("wOFF rest"))).toBe(true);
    expect(hasFontSignature(new Uint8Array([0, 1, 0, 0, 9]))).toBe(true);
    expect(hasFontSignature(bytesOf("true rest"))).toBe(true);
    expect(hasFontSignature(bytesOf("OTTO rest"))).toBe(true);
  });

  test("rejects html, empty and very short data", () => {
    expect(hasFontSignature(bytesOf("<html>"))).toBe(false);
    expect(hasFontSignature(new Uint8Array(0))).toBe(false);
    expect(hasFontSignature(bytesOf("wOF"))).toBe(false);
  });
});

describe("fromBase64Limited", () => {
  test("decodes base64 that fits the limit", () => {
    expect(fromBase64Limited(toBase64(new Uint8Array([9, 8, 7])), 3)).toEqual(
      new Uint8Array([9, 8, 7]),
    );
  });

  test("rejects decoded data over the limit", () => {
    expect(() => fromBase64Limited(toBase64(new Uint8Array(4)), 3)).toThrow("too large");
  });

  test("rejects text too long to fit the limit before decoding it", () => {
    expect(() => fromBase64Limited("A".repeat(100), 3)).toThrow("too large");
  });
});

describe("LIMITS", () => {
  test("bounds each family, each page and each stylesheet", () => {
    expect(LIMITS.familyBytes).toBe(16 * 1024 * 1024);
    expect(LIMITS.pageBytes).toBe(64 * 1024 * 1024);
    expect(LIMITS.stylesheetBytes).toBe(2 * 1024 * 1024);
    expect(LIMITS.fetchTimeoutMs).toBeGreaterThan(0);
  });
});
