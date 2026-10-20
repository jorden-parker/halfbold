import type { ResetResult } from "./api";

const RESTORED_LABELS: Record<string, string> = {
  vscode: "Visual Studio Code font restored.",
  web: "Chrome slots restored.",
};

function deletedLabel(count: number): string {
  return `${count} Half ${count === 1 ? "font" : "fonts"} deleted; remove the halfbold extension in chrome://extensions to give pages their own fonts back.`;
}

export function resetSummary(result: ResetResult): string {
  const parts = result.restored.map((section) => RESTORED_LABELS[section] ?? `${section} restored.`);
  if (result.watcher_removed) parts.push("File watcher removed.");
  if (result.deleted.length > 0) parts.push(deletedLabel(result.deleted.length));
  return parts.length > 0 ? parts.join(" ") : "Nothing to undo.";
}
