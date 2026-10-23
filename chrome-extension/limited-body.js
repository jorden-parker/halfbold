(() => {
  const FETCH_OPTIONS = { mode: "cors", credentials: "omit", redirect: "error" };

  function joinChunks(chunks, total) {
    const bytes = new Uint8Array(total);
    let offset = 0;
    for (const chunk of chunks) {
      bytes.set(chunk, offset);
      offset += chunk.byteLength;
    }
    return bytes;
  }

  async function readBodyUpTo(body, limit) {
    if (!body) return new Uint8Array(0);
    const reader = body.getReader();
    const chunks = [];
    let total = 0;
    let next = await reader.read();
    while (!next.done) {
      total += next.value.byteLength;
      if (total > limit) {
        await reader.cancel().catch(() => {});
        return null;
      }
      chunks.push(next.value);
      next = await reader.read();
    }
    return joinChunks(chunks, total);
  }

  function declaredLengthExceeds(response, limit) {
    const declared = response.headers.get("content-length");
    return declared !== null && Number(declared) > limit;
  }

  async function bodyOrThrow(response, url, limit) {
    if (declaredLengthExceeds(response, limit)) throw new Error(`too large ${url}`);
    const bytes = await readBodyUpTo(response.body, limit);
    if (bytes === null) throw new Error(`too large ${url}`);
    return bytes;
  }

  async function fetchLimitedBytes(url, { limit, timeoutMs }) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    try {
      const response = await fetch(url, { ...FETCH_OPTIONS, signal: controller.signal });
      if (!response.ok) throw new Error(`${response.status} ${url}`);
      return await bodyOrThrow(response, url, limit);
    } finally {
      clearTimeout(timer);
    }
  }

  function createByteBudget(total) {
    let remaining = total;
    return {
      reserve(limit) {
        const amount = Math.min(limit, remaining);
        remaining -= amount;
        return amount;
      },
      settle(reserved, used) {
        remaining += reserved - used;
      },
      remaining: () => remaining,
    };
  }

  globalThis.halfboldLimitedBody = {
    createByteBudget,
    fetchLimitedBytes,
    readBodyUpTo,
  };
})();
