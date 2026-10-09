import { expect, test } from "bun:test";

import { createSequencer } from "./sequence";

function deferred() {
  let resolve: () => void = () => undefined;
  const promise = new Promise<void>((done) => {
    resolve = done;
  });
  return { promise, resolve };
}

test("runs a single task", async () => {
  const sequencer = createSequencer();
  const done: string[] = [];
  sequencer.run(async () => {
    done.push("one");
  });
  await Bun.sleep(0);
  expect(done).toEqual(["one"]);
  expect(sequencer.busy).toBe(false);
});

test("drops every task superseded while one is in flight", async () => {
  const sequencer = createSequencer();
  const first = deferred();
  const done: string[] = [];

  sequencer.run(async () => {
    done.push("first");
    await first.promise;
  });
  await Bun.sleep(0);
  sequencer.run(async () => {
    done.push("second");
  });
  sequencer.run(async () => {
    done.push("third");
  });
  sequencer.run(async () => {
    done.push("fourth");
  });
  first.resolve();
  await Bun.sleep(0);

  expect(done).toEqual(["first", "fourth"]);
});

test("never runs two tasks at once", async () => {
  const sequencer = createSequencer();
  let live = 0;
  let peak = 0;
  for (let i = 0; i < 5; i += 1) {
    sequencer.run(async () => {
      live += 1;
      peak = Math.max(peak, live);
      await Bun.sleep(1);
      live -= 1;
    });
  }
  while (sequencer.busy) await Bun.sleep(1);
  expect(peak).toBe(1);
});

test("a rejection does not wedge the queue", async () => {
  const sequencer = createSequencer();
  const done: string[] = [];
  sequencer.run(async () => {
    throw new Error("nope");
  });
  await Bun.sleep(0);
  sequencer.run(async () => {
    done.push("after");
  });
  await Bun.sleep(0);
  expect(done).toEqual(["after"]);
  expect(sequencer.busy).toBe(false);
});
