import { t, tf, type StringKey } from '../copy/t';
import { fmt } from './history';

/** T24: PLAYLISTS, the Junction preview (P5): jimbo-dj's saved playlists and their lines, read-only. */
export const PLAYLISTS_PATH = '/library/playlists';
export const PLAYLIST_ROWS_PATH = '/library/playlists/rows';
export const playlistHref = (ref: string | number) => `${PLAYLISTS_PATH}/${encodeURIComponent(String(ref))}`;
export const playlistApi = (ref: string, limit = 50) => `/api/playlists/${encodeURIComponent(ref)}?limit=${limit}`;

/** The rows behind a line's or a condition's count. */
export function rowsHref(ref: string, line: string, path = ''): string {
  const q = new URLSearchParams({ ref, line });
  if (path) q.set('path', path);
  return `${PLAYLIST_ROWS_PATH}?${q.toString()}`;
}
export function rowsApi(query: string): string {
  const q = new URLSearchParams(query);
  const ref = q.get('ref') ?? '';
  const out = new URLSearchParams({ line: q.get('line') ?? '', limit: '200' });
  if (q.get('path')) out.set('path', q.get('path') ?? '');
  return `/api/playlists/${encodeURIComponent(ref)}/rows?${out.toString()}`;
}

export type Server = 'plex' | 'jellyfin' | 'navidrome';
export type Switch = {
  server: Server; on: boolean; set_by: string | null; rule: string; from?: string;
  pushed_at?: number | null; plex_key?: number | null; error?: string | null;
};
export type PlaylistRow = {
  id: number; slug: string; kind: string; kind_name: string; title: string; name: string; summary: string | null;
  tracks: number; created_at: number; updated_at: number; stale: boolean; stale_in_plex: number | null;
  made_by: string | null; from: string | null; lines: number; switches: Switch[];
};
export type PlaylistList = {
  count: number; with_lines: number; stale: number; on: Record<Server, number>; rules: Record<string, string>;
  kinds: { kind: string; name: string; count: number; rows: PlaylistRow[] }[];
};
export type Condition = { type: 'condition'; f: string; v: string; text: string; count: number; path: string };
export type Group = {
  type: 'group'; words: string; path: string; count: number; all?: Node[]; any?: Node[]; not?: Node[];
};
export type Node = Condition | Group;
export type Line = { id: string; label: string | null; share: number; words: string; count: number; match: Group | Condition };
export type Lines = {
  n: number; per_artist: number; shuffle: number; name: string; query: string; lines: Line[]; total: number;
  library: number; rules: Record<string, string>;
};
export type TrackRow = {
  rating_key: number; title: string; artist: string; album: string; year: number | null; duration_ms: number | null; live: boolean;
};
export type PlaylistPage = {
  playlist: PlaylistRow;
  stored: { count: number; live: number; rows: TrackRow[]; limit: number; offset: number; rule: string };
  tree: unknown; lines: Lines | null; lines_error: string | null;
};
export type LineRows = { line: string; path: string; words: string; count: number; rows: TrackRow[]; rule: string };

type Unit = 'playlist' | 'line' | 'track';
export function count(n: number, unit: Unit): string {
  return `${fmt(n)} ${t(`unit.${unit}.${n === 1 ? 'one' : 'other'}` as StringKey)}`;
}
export const serverName = (s: Server) => t(`playlists.server.${s}` as StringKey);
export const kindName = (k: string) => t(`playlists.kind.${k}` as StringKey) ?? k;
export const fieldName = (f: string) => tf('playlists.field', { f });
