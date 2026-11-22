import strings from './board.strings.json';

export type BoardKey = keyof typeof strings;

/** The kit board's copy (dev only, so its sample words never ship; D1). */
export function b(key: BoardKey): string {
  return strings[key];
}
