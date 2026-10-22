import type { ResetResult } from "./api";

const RESTORED_LABELS: Record<string, string> = {
  vscode: "Visual Studio Code font restored.",
};

function deletedLabel(count: number): string {
  return `${count} Half ${count === 1 ? "font" : "fonts"} deleted.`;
}

export function resetSummary(result: ResetResult): string {
  const parts = result.restored.flatMap((section) => RESTORED_LABELS[section] ?? []);
  if (result.chrome_disabled) parts.push("Chrome conversion turned off.");
  if (result.watcher_removed) parts.push("File watcher removed.");
  if (result.deleted.length > 0) parts.push(deletedLabel(result.deleted.length));
  return parts.length > 0 ? parts.join(" ") : "Nothing to undo.";
}
