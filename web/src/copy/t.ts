import strings from './strings.json';

export type StringKey = keyof typeof strings;

/** All user-facing copy comes from strings.json (W1). */
export function t(key: StringKey): string {
  return strings[key];
}
