/** T30: GET /api/cutovers — P6's cut-overs, the switch-off check, the run log, the watcher and the Plex settings. */
export const CUTOVERS_API = '/api/cutovers';

export type CutoverState = 'not_copied' | 'owned' | 'rolled_back';
export type Row = Record<string, string | number | null>;
export type SwitchOffTable = {
  table: string; copied: number | null; now: number | null; new: number | null; moved: boolean;
  rule: { where: string; mark: string; since: string | number | null } | null; examples: Row[];
};
export type SwitchOff = {
  checked_at: number; clean: boolean; missed: number; tables: SwitchOffTable[];
  marks: Record<string, { copied: string | number | null; now: string | number | null; moved: boolean }>;
} | { error: string };
export type Cutover = {
  name: string; title: string; tables: string[]; state: CutoverState; copied_at: number | null; note: string | null;
  switch_off: SwitchOff | null;
};
export type Run = {
  id: number; job: string; started_at: number; seconds: number; ok: boolean; counts: Record<string, unknown>;
  note: string; reason: string; undo: string;
};
export type Watcher = { enabled: boolean; interval: number; checked_at: number | null; changed_at: number | null; scanning: boolean; error: string | null };
export type PlexSettings = { url: string | null; token_set: boolean; section: string | null; path_map: string | null; env: string[] };
export type Cutovers = { file: string; cutovers: Cutover[]; runs: Run[]; watcher: Watcher; plex: PlexSettings };

/** Unix seconds → "2026-11-05 02:00 UTC". */
export function unixUtc(at: number | string | null | undefined, utc: string): string {
  const n = Number(at);
  if (at == null || at === '' || !Number.isFinite(n)) return String(at ?? '');
  const iso = new Date(n * 1000).toISOString();
  return `${iso.slice(0, 10)} ${iso.slice(11, 16)} ${utc}`;
}

/** One of jimbo-dj's rows as it is, column by column ("id 10 · source lastfm · …"). */
export const rowText = (r: Row) => Object.entries(r).map(([k, v]) => `${k} ${v ?? '–'}`).join(' · ');
