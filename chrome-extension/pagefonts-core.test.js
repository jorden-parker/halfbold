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
