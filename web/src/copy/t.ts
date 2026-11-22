import strings from './strings.json';

export type StringKey = keyof typeof strings;

/** All user-facing copy comes from strings.json (W1). */
export function t(key: StringKey): string {
  return strings[key];
}

/** A string with {name} slots filled in. */
export function tf(key: StringKey, vars: Record<string, string | number>): string {
  return t(key).replace(/\{(\w+)\}/g, (m, k: string) => (k in vars ? String(vars[k]) : m));
}

/** Copy for a key built at run time (e.g. `source.${x}`), or undefined when there is none. */
export function tMaybe(key: string): string | undefined {
  return (strings as Record<string, string>)[key];
}
