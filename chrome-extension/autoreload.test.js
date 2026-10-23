import { afterEach, beforeEach, describe, expect, test } from "bun:test";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { compileFunction } from "node:vm";

const EXTENSION_DIR = import.meta.dir;
const HTTPS_PAGE = { id: "halfbold-test", origin: "https://page.example", tab: { id: 1, url: "https://page.example/" }, frameId: 0 };
const OTHER_HTTPS_PAGE = { id: "halfbold-test", origin: "https://other.example", tab: { id: 3, url: "https://other.example/" }, frameId: 0 };
const HTTP_PAGE ={ id: "halfbold-test", origin: "http://page.example", tab: { id: 2, url: "http://page.example/" }, frameId: 0 };
const HTTPS_FONT = "https://cdn.example/bold.woff2";
const HTTP_FONT = "http://cdn.example/regular.woff2";
const REAL_FONT = Buffer.concat([Buffer.from("wOF2"), Buffer.alloc(16)]).toString("base64");
const NOT_A_FONT = Buffer.from("<html>").toString("base64");
const ORIGINAL_GLOBALS = { chrome: globalThis.chrome, fetch: globalThis.fetch, importScripts: globalThis.importScripts };

function loadScript(name) {
  compileFunction(readFileSync(join(EXTENSION_DIR, name), "utf8"), [])();
}

function faceAt(url, data = REAL_FONT, weight = [400, 400]) {
  return { url, weight, style: "normal", unicodeRange: "", data };
}

function createStorage(store) {
  return {
    get: async (keys) => {
      if (keys === null) return { ...store };
      const wanted = Array.isArray(keys) ? keys : [keys];
      return Object.fromEntries(wanted.filter((key) => key in store).map((key) => [key, store[key]]));
    },
    set: async (values) => Object.assign(store, values),
    remove: async (keys) => {
      for (const key of [keys].flat()) delete store[key];
    },
  };
}

function createEnvironment() {
  const env = {
    storage: {},
    hostRequests: [],
    fetchedUrls: [],
    hostListener: null,
    messageListener: null,
  };
  const port = {
    postMessage(message) {
      env.hostRequests.push(message);
      queueMicrotask(() => env.hostListener({ id: message.id, type: "converted", faces: [{ file: "f.ttf" }], unchanged: [] }));
    },
    onMessage: { addListener: (listener) => (env.hostListener = listener) },
    onDisconnect: { addListener() {} },
  };
  globalThis.chrome = {
    runtime: {
      id: "halfbold-test",
      connectNative: () => port,
      getURL: (path) => `chrome-extension://halfbold-test/${path}`,
      onMessage: { addListener: (listener) => (env.messageListener = listener) },
      onInstalled: { addListener() {} },
      onStartup: { addListener() {} },
    },
    storage: { local: createStorage(env.storage) },
    alarms: { create() {}, onAlarm: { addListener() {} } },
    tabs: { onRemoved: { addListener() {} }, query: async () => [] },
    fontSettings: {},
  };
  globalThis.importScripts = () => {};
  globalThis.fetch = async (url) => {
    env.fetchedUrls.push(String(url));
    throw new Error("no network in tests");
  };
  return env;
}

function loadWorker() {
  loadScript("pagefonts-core.js");
  loadScript("autoreload.js");
}

function send(env, message, sender) {
  return new Promise((resolve) => {
    env.messageListener(message, sender, resolve);
  });
}

function convert(env, faces, sender = HTTPS_PAGE) {
  return send(env, { type: "halfbold-convert-webfont", faces }, sender);
}

function hostFaceUrls(env) {
  return env.hostRequests.flatMap((request) => request.faces.map((face) => face.data));
}

describe("service worker font handling", () => {
  let env;

  beforeEach(() => {
    env = createEnvironment();
    loadWorker();
  });

  afterEach(() => {
    for (const [name, value] of Object.entries(ORIGINAL_GLOBALS)) globalThis[name] = value;
  });

  test("makes no network request of its own for page fonts", async () => {
    await convert(env, [faceAt(HTTPS_FONT)]);

    expect(env.fetchedUrls).toEqual([]);
    expect(env.hostRequests).toHaveLength(1);
  });

  test("no longer answers the old cross-origin stylesheet fetch", () => {
    const responses = [];

    const handled = env.messageListener({ type: "halfbold-fetch-css", url: HTTPS_FONT }, HTTPS_PAGE, (reply) =>
      responses.push(reply),
    );

    expect(handled).toBe(false);
    expect(responses).toEqual([]);
    expect(env.fetchedUrls).toEqual([]);
  });

  test("sends only the faces an https page may use, and drops its http faces", async () => {
    const reply = await convert(env, [faceAt(HTTP_FONT, NOT_A_FONT), faceAt(HTTPS_FONT, REAL_FONT, [700, 700])]);

    expect(reply.type).toBe("converted");
    expect(env.hostRequests.map((request) => request.faces.map((face) => face.weight))).toEqual([[[700, 700]]]);
  });

  test("answers unchanged without asking the host when no face is usable", async () => {
    const reply = await convert(env, [faceAt(HTTP_FONT)]);

    expect(reply.type).toBe("unchanged");
    expect(env.hostRequests).toEqual([]);
  });

  test("keeps https conversions apart from http ones so cleartext is never served", async () => {
    await convert(env, [faceAt(HTTP_FONT)], HTTP_PAGE);
    const served = await send(env, { type: "halfbold-stored-webfont", faces: [faceAt(HTTP_FONT)] }, HTTP_PAGE);
    const sameFacesOnHttps = await send(env, { type: "halfbold-stored-webfont", faces: [faceAt(HTTP_FONT)] }, HTTPS_PAGE);

    expect(served.type).toBe("converted");
    expect(sameFacesOnHttps).toBeNull();
  });

  test("returns a stored conversion to the same page after it is made", async () => {
    const faces = [faceAt(HTTPS_FONT)];
    expect(await send(env, { type: "halfbold-stored-webfont", faces }, HTTPS_PAGE)).toBeNull();

    await convert(env, faces);

    expect((await send(env, { type: "halfbold-stored-webfont", faces }, HTTPS_PAGE)).type).toBe("converted");
  });

  test("rejects bytes that are not a font without contacting the host", async () => {
    const reply = await convert(env, [faceAt(HTTPS_FONT, NOT_A_FONT)]);

    expect(reply.type).toBe("unchanged");
    expect(env.hostRequests).toEqual([]);
  });

  test("rejects base64 longer than one family's limit before decoding it", async () => {
    const oversized = "A".repeat(Math.ceil((16 * 1024 * 1024) / 3) * 4 + 8);

    const reply = await convert(env, [faceAt(HTTPS_FONT, oversized)]);

    expect(reply.type).toBe("unchanged");
    expect(env.hostRequests).toEqual([]);
  });

  test("rejects a family whose decoded total goes over one family's limit", async () => {
    const big = Buffer.concat([Buffer.from("wOF2"), Buffer.alloc(10 * 1024 * 1024)]).toString("base64");

    const reply = await convert(env, [faceAt(HTTPS_FONT, big), faceAt("https://cdn.example/italic.woff2", big)]);

    expect(reply.type).toBe("unchanged");
    expect(env.hostRequests).toEqual([]);
  });

  test("never serves one site's conversion to another site that names the same font", async () => {
    const faces = [faceAt(HTTPS_FONT)];
    await convert(env, faces, OTHER_HTTPS_PAGE);

    expect(await send(env, { type: "halfbold-stored-webfont", faces }, HTTPS_PAGE)).toBeNull();
    await convert(env, faces, HTTPS_PAGE);
    expect(env.hostRequests).toHaveLength(2);
  });

  test("answers unchanged for a frame with an opaque origin", async () => {
    const reply = await convert(env, [faceAt(HTTPS_FONT)], { ...HTTPS_PAGE, origin: "null" });

    expect(reply.type).toBe("unchanged");
    expect(env.hostRequests).toEqual([]);
    expect(await send(env, { type: "halfbold-stored-webfont", faces: [faceAt(HTTPS_FONT)] }, { ...HTTPS_PAGE, origin: "null" })).toBeNull();
  });

  test("answers unchanged for a message that carries no faces array", async () => {
    const reply = await send(env, { type: "halfbold-convert-webfont" }, HTTPS_PAGE);

    expect(reply.type).toBe("unchanged");
    expect(hostFaceUrls(env)).toEqual([]);
  });
});
