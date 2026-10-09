export interface Sequencer {
  run(task: () => Promise<void>): void;
  readonly busy: boolean;
}

export function createSequencer(): Sequencer {
  let running = false;
  let queued: (() => Promise<void>) | null = null;

  async function drain() {
    running = true;
    try {
      while (queued) {
        const task = queued;
        queued = null;
        await task().catch(() => undefined);
      }
    } finally {
      running = false;
    }
  }

  return {
    run(task) {
      queued = task;
      if (!running) void drain();
    },
    get busy() {
      return running;
    },
  };
}
