import { invoke } from "@tauri-apps/api/core";

export type Kind = "sans" | "serif" | "mono";
export const KINDS: Kind[] = ["sans", "serif", "mono"];

export interface Candidate {
  family: string;
  kind: Kind;
  regular: string;
  bold: string | null;
  output: string;
  built: boolean;
  stale: boolean;
}

export interface Preview {
  family: string;
  kind: Kind;
  regular: string;
  bold: string | null;
  half: string;
}

export type WebFonts = Record<Kind, string>;

async function api<T>(...args: string[]): Promise<T> {
  return invoke<T>("api", { args });
}

export function installed() {
  return api<{ fonts_dir: string; candidates: Candidate[] }>("installed");
}

export function build(c: Candidate) {
  const args = ["build", c.regular];
  if (c.bold) args.push(c.bold);
  return api<{ output: string; letters: number }>(...args, "-o", c.output);
}

export function preview(c: Candidate) {
  const args = ["preview", c.regular];
  if (c.bold) args.push(c.bold);
  return api<Preview>(...args);
}

export function casks() {
  return api<{ casks: string[] }>("casks");
}

export function caskFonts(token: string) {
  return api<{ token: string; candidates: Candidate[] }>("cask-fonts", token);
}

export function caskInstall(token: string) {
  return api<{ token: string; candidates: Candidate[] }>("cask-install", token);
}

export function webFonts(kind?: Kind, family?: string) {
  return kind && family ? api<WebFonts>("web", kind, family) : api<WebFonts>("web");
}

export function readFont(path: string) {
  return invoke<ArrayBuffer>("read_font", { path });
}
