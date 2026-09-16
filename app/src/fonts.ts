import { readFont } from "./api";

const faces = new Map<string, FontFace>();
const aliases = new Map<string, Promise<string>>();
let counter = 0;

export async function loadFace(path: string): Promise<string> {
  const previous = faces.get(path);
  if (previous) document.fonts.delete(previous);
  const alias = `hb-${++counter}`;
  const face = new FontFace(alias, await readFont(path));
  await face.load();
  document.fonts.add(face);
  faces.set(path, face);
  aliases.set(path, Promise.resolve(alias));
  return alias;
}

export function faceAlias(path: string): Promise<string> {
  let pending = aliases.get(path);
  if (!pending) {
    pending = loadFace(path);
    aliases.set(path, pending);
  }
  return pending;
}
