import { readFont } from "./api";

const faces = new Map<string, FontFace>();
const aliases = new Map<string, string>();
const pending = new Map<string, Promise<string>>();

function aliasFor(path: string): string {
  let alias = aliases.get(path);
  if (!alias) {
    alias = `hb-${aliases.size + 1}`;
    aliases.set(path, alias);
  }
  return alias;
}

async function install(path: string): Promise<string> {
  const alias = aliasFor(path);
  const face = new FontFace(alias, await readFont(path));
  await face.load();
  const previous = faces.get(path);
  if (previous) document.fonts.delete(previous);
  document.fonts.add(face);
  faces.set(path, face);
  return alias;
}

export function loadFace(path: string): Promise<string> {
  const task = install(path).finally(() => {
    if (pending.get(path) === task) pending.delete(path);
  });
  pending.set(path, task);
  return task;
}

export function faceAlias(path: string): Promise<string> {
  const inFlight = pending.get(path);
  if (inFlight) return inFlight;
  if (faces.has(path)) return Promise.resolve(aliasFor(path));
  return loadFace(path);
}
