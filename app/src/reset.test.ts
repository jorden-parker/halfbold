import { expect, test } from "bun:test";

import type { ResetResult } from "./api";
import { resetSummary } from "./reset";

function result(overrides: Partial<ResetResult>): ResetResult {
  return { restored: [], deleted: [], watcher_removed: false, chrome_disabled: false, ...overrides };
}

test("says when there is nothing to undo", () => {
  expect(resetSummary(result({}))).toBe("Nothing to undo.");
});

test("names each restored place and leaves out sections it no longer knows", () => {
  expect(resetSummary(result({ restored: ["vscode", "web"] }))).toBe("Visual Studio Code font restored.");
});

test("says Chrome conversion is off", () => {
  expect(resetSummary(result({ restored: ["vscode"], chrome_disabled: true }))).toBe(
    "Visual Studio Code font restored. Chrome conversion turned off.",
  );
});

test("counts deleted fonts", () => {
  const summary = resetSummary(result({ deleted: ["Inter Half", "Menlo Half"], watcher_removed: true }));
  expect(summary).toBe("File watcher removed. 2 Half fonts deleted.");
});

test("uses the singular for one deleted font", () => {
  expect(resetSummary(result({ deleted: ["Inter Half"] }))).toBe("1 Half font deleted.");
});
