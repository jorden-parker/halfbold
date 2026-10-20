import { expect, test } from "bun:test";

import type { ResetResult } from "./api";
import { resetSummary } from "./reset";

const WEB = { sans: "Inter Half", serif: "Source Serif 4 Half", mono: "JetBrainsMono Nerd Font Half" };

function result(overrides: Partial<ResetResult>): ResetResult {
  return { restored: [], deleted: [], watcher_removed: false, web: WEB, ...overrides };
}

test("says when there is nothing to undo", () => {
  expect(resetSummary(result({}))).toBe("Nothing to undo.");
});

test("names each restored place", () => {
  expect(resetSummary(result({ restored: ["vscode", "web"] }))).toBe(
    "Visual Studio Code font restored. Chrome slots restored.",
  );
});

test("counts deleted fonts and points at the extension", () => {
  const summary = resetSummary(result({ deleted: ["Inter Half", "Menlo Half"], watcher_removed: true }));
  expect(summary).toStartWith("File watcher removed. 2 Half fonts deleted;");
  expect(summary).toContain("chrome://extensions");
});

test("uses the singular for one deleted font", () => {
  expect(resetSummary(result({ deleted: ["Inter Half"] }))).toStartWith("1 Half font deleted;");
});
