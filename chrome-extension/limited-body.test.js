import { afterAll, beforeAll, describe, expect, test } from "bun:test";
import "./limited-body.js";

const { createByteBudget, fetchLimitedBytes, readBodyUpTo } = globalThis.halfboldLimitedBody;
const MEGABYTE = 1024 * 1024;
const PARTS = [new Uint8Array([1, 2, 3]), new Uint8Array([4, 5, 6, 7])];
const JOINED = new Uint8Array([1, 2, 3, 4, 5, 6, 7]);

function streamOf(chunks) {
  return new ReadableStream({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(chunk);
      controller.close();
    },
  });
}

function meteredBody(chunkCount, chunkSize) {
  const meter = { pulls: 0, cancelled: false };
  meter.stream = new ReadableStream({
    pull(controller) {
      if (meter.pulls === chunkCount) {
        controller.close();
        return;
      }
      meter.pulls += 1;
      controller.enqueue(new Uint8Array(chunkSize));
    },
    cancel() {
      meter.cancelled = true;
    },
  });
  return meter;
}

function patternBytes(size) {
  return new Uint8Array(size).map((_, index) => index % 251);
}

describe("readBodyUpTo", () => {
  test("returns a body under the limit intact", async () => {
    expect(await readBodyUpTo(streamOf(PARTS), 10)).toEqual(JOINED);
  });

  test("returns a body exactly at the limit intact", async () => {
    expect(await readBodyUpTo(streamOf(PARTS), 7)).toEqual(JOINED);
  });

  test("returns null for a body one byte over the limit", async () => {
    expect(await readBodyUpTo(streamOf(PARTS), 6)).toBeNull();
  });

  test("cancels an over-limit body instead of reading it to the end", async () => {
    const body = meteredBody(1000, 1024);
    expect(await readBodyUpTo(body.stream, 2500)).toBeNull();
    expect(body.cancelled).toBe(true);
    expect(body.pulls).toBeLessThan(10);
  });

  test("treats a missing body as empty", async () => {
    expect(await readBodyUpTo(null, 10)).toEqual(new Uint8Array(0));
  });
});

describe("fetchLimitedBytes", () => {
  let server;
  const urlFor = (path) => `http://localhost:${server.port}${path}`;
  const options = { limit: MEGABYTE, timeoutMs: 200 };

  const routes = {
    "/declared-big": () =>
      new Response(patternBytes(2 * MEGABYTE), {
        headers: { "content-length": String(2 * MEGABYTE) },
      }),
    "/streamed-big": () => new Response(streamOf([patternBytes(2 * MEGABYTE)])),
    "/slow": () => new Promise((resolve) => setTimeout(() => resolve(new Response("late")), 1000)),
    "/redirect": () => Response.redirect(urlFor("/sized?size=10"), 302),
  };

  beforeAll(() => {
    server = Bun.serve({
      port: 0,
      fetch(request) {
        const url = new URL(request.url);
        if (url.pathname === "/sized") {
          return new Response(patternBytes(Number(url.searchParams.get("size"))));
        }
        const route = routes[url.pathname];
        return route ? route() : new Response("missing", { status: 404 });
      },
    });
  });

  afterAll(() => {
    server.stop(true);
  });

  test("returns the bytes of a response under the limit", async () => {
    expect(await fetchLimitedBytes(urlFor("/sized?size=300"), options)).toEqual(patternBytes(300));
  });

  test("rejects a response whose Content-Length is over the limit", async () => {
    await expect(fetchLimitedBytes(urlFor("/declared-big"), options)).rejects.toThrow("too large");
  });

  test("rejects a streamed response that goes over the limit", async () => {
    await expect(fetchLimitedBytes(urlFor("/streamed-big"), options)).rejects.toThrow("too large");
  });

  test("rejects a response that takes longer than the timeout", async () => {
    await expect(fetchLimitedBytes(urlFor("/slow"), options)).rejects.toThrow();
  });

  test("rejects a redirect instead of following it", async () => {
    await expect(fetchLimitedBytes(urlFor("/redirect"), options)).rejects.toThrow();
  });

  test("rejects an error status", async () => {
    await expect(fetchLimitedBytes(urlFor("/missing"), options)).rejects.toThrow("404");
  });
});

describe("createByteBudget", () => {
  test("reserves no more than what remains", () => {
    const budget = createByteBudget(10);

    expect(budget.reserve(7)).toBe(7);
    expect(budget.reserve(7)).toBe(3);
    expect(budget.reserve(7)).toBe(0);
  });

  test("gives back the part of a reservation that was not used", () => {
    const budget = createByteBudget(10);
    const reserved = budget.reserve(8);

    budget.settle(reserved, 3);

    expect(budget.remaining()).toBe(7);
  });

  test("keeps a whole reservation spent when its fetch failed", () => {
    const budget = createByteBudget(10);
    budget.reserve(8);

    expect(budget.remaining()).toBe(2);
  });
});
