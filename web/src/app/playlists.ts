import { t, tf, type StringKey } from '../copy/t';
import { fmt } from './history';

/** T24: PLAYLISTS, the Junction preview (P5): jimbo-dj's saved playlists and their lines, read-only. */
export const PLAYLISTS_PATH = '/library/playlists';
export const PLAYLIST_ROWS_PATH = '/library/playlists/rows';
export const playlistHref = (ref: string | number) => `${PLAYLISTS_PATH}/${encodeURIComponent(String(ref))}`;
export const playlistApi = (ref: string, limit = 50) => `/api/playlists/${encodeURIComponent(ref)}?limit=${limit}`;

/** T25: the Junction, any tree in jimbo-dj's URL form (b=…&n=…&per=…&shuffle=…). */
export const JUNCTION_PATH = '/library/junction';
export const JUNCTION_ROWS_PATH = '/library/junction/rows';
export const COPIES_PATH = '/library/playlists/copies';
const TREE_PARAMS = ['b', 'n', 'per', 'shuffle'];
/** Only the tree's own params, in order (jimbo-dj's URL form), from any query string. */
export function treeQuery(query: string): string {
  const q = new URLSearchParams(query);
  const out = new URLSearchParams();
  for (const [k, v] of q) if (TREE_PARAMS.includes(k)) out.append(k, v);
  return out.toString();
}
export const junctionHref = (tree: string) => `${JUNCTION_PATH}?${treeQuery(tree)}`;
export const junctionApi = (query: string) => `/api/junction?${treeQuery(query)}`;

/** Which number's rows: a line's matches (count), what it got, its pool, what Never in mixes left out, every pick,
 *  every match. */
export type Which = 'count' | 'got' | 'available' | 'banned' | 'picked' | 'total';
/** Where a number's rows live: a saved playlist (its slug) or a tree in the URL form. */
export type Source = { ref: string } | { tree: string };

/** The rows behind a line's or a condition's count (T24), or another number (T25: which). */
export function rowsHref(ref: string, line: string, path = '', which: Which = 'count'): string {
  const q = new URLSearchParams({ ref, line });
  if (path) q.set('path', path);
  if (which !== 'count') q.set('which', which);
  return `${PLAYLIST_ROWS_PATH}?${q.toString()}`;
}
export function sourceRowsHref(src: Source, line: string, which: Which = 'count', path = ''): string {
  if ('ref' in src) return rowsHref(src.ref, line, path, which);
  const q = new URLSearchParams(treeQuery(src.tree));
  if (line) q.set('line', line);
  if (path) q.set('path', path);
  if (which !== 'count') q.set('which', which);
  return `${JUNCTION_ROWS_PATH}?${q.toString()}`;
}
export function rowsApi(query: string): string {
  const q = new URLSearchParams(query);
  const out = new URLSearchParams({ line: q.get('line') ?? '', limit: '200' });
  if (q.get('path')) out.set('path', q.get('path') ?? '');
  if (q.get('which')) out.set('which', q.get('which') ?? '');
  if (!q.has('ref')) return `/api/junction/rows?${treeQuery(query)}&${out.toString()}`;
  return `/api/playlists/${encodeURIComponent(q.get('ref') ?? '')}/rows?${out.toString()}`;
}

/** The stored tracks behind a switch's copies (missing: only those without a copy). */
export function copiesHref(ref: string, server: Server, missing?: boolean): string {
  const q = new URLSearchParams({ ref, server });
  if (missing !== undefined) q.set('missing', String(missing));
  return `${COPIES_PATH}?${q.toString()}`;
}
export function copiesApi(query: string): string {
  const q = new URLSearchParams(query);
  const out = new URLSearchParams({ server: q.get('server') ?? '', limit: '200' });
  if (q.get('missing')) out.set('missing', q.get('missing') ?? '');
  return `/api/playlists/${encodeURIComponent(q.get('ref') ?? '')}/copies?${out.toString()}`;
}

/** T26: rooted to roaming, how far each line could reach if it followed its tag. A preview, not the Junction's. */
export const REACH_ROWS_PATH = '/library/junction/reach';
export type Stop = 'rooted' | 'ladder' | 'movement' | 'roaming';
export type ReachWhich = 'count' | 'added';
export const reachApi = (query: string) => `/api/junction/reach?${treeQuery(query)}`;
/** The rows behind a stop's number; ref (a saved playlist's slug) is only where Back goes. */
export function reachRowsHref(tree: string, line: string, stop: Stop, which: ReachWhich = 'count', ref?: string): string {
  const q = new URLSearchParams(treeQuery(tree));
  if (ref) q.set('ref', ref);
  q.set('line', line);
  q.set('stop', stop);
  if (which !== 'count') q.set('which', which);
  return `${REACH_ROWS_PATH}?${q.toString()}`;
}
export function reachRowsApi(query: string): string {
  const q = new URLSearchParams(query);
  const out = new URLSearchParams({ line: q.get('line') ?? '', stop: q.get('stop') ?? '', which: q.get('which') ?? 'count', limit: '200' });
  return `/api/junction/reach/rows?${treeQuery(query)}&${out.toString()}`;
}
export type ReachTag = {
  key: string; name: string; via: 'tag' | 'ladder' | 'movement' | 'neighbour'; follows: string; in_use: boolean;
  movement?: string; movement_name?: string; of?: string;
};
export type ReachStop = { stop: Stop; count: number; added: number; tags: number; new_tags: ReachTag[] };
export type ReachLine = {
  id: string; label: string | null; words: string;
  follows: { path: string; value: string; key: string; name: string; text: string; movements: { id: string; name: string }[] }[];
  stops: ReachStop[];
};
export type Reach = {
  query: string; name: string; stops: Stop[]; lines: ReachLine[]; following: number; movements: number;
  rules: Record<string, string>;
};
export type ReachRows = {
  line: string; stop: Stop; which: ReachWhich; words: string; count: number; rule: string; rows: TrackRow[];
};

export type Server = 'plex' | 'jellyfin' | 'navidrome';
export type Copies = {
  count: number; of: number; missing: number; reasons: Record<string, number>; snapshot: boolean; rule: string;
  rows: string; missing_rows: string;
};
export type Switch = {
  server: Server; on: boolean; set_by: string | null; rule: string; from?: string;
  pushed_at?: number | null; plex_key?: number | null; error?: string | null; copies?: Copies;
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
export type Line = {
  id: string; label: string | null; share: number; words: string; count: number; match: Group | Condition;
  got?: number; available?: number; banned?: number;
};
/** How a track follows the one before (jimbo-dj's flow.describe): Camelot steps and the tempo gap (a share). */
export type Transition = { key_steps?: number | null; bpm_gap?: number | null };
/** A picked track (T25), in flow order with its key, tempo and transition, and per path of its line whether it
 *  meets that condition or group (T27, B3). */
export type Picked = TrackRow & {
  line: string; line_name: string | null; camelot?: string | null; bpm?: number | null; transition?: Transition;
  met?: Record<string, boolean>;
};
export type Lines = {
  n: number; per_artist: number; shuffle: number; name: string; query: string; lines: Line[]; total: number;
  library: number; rules: Record<string, string>;
  summary?: string; read_only?: string;
  picked?: { count: number; minutes: number; order: 'flow'; seconds: number; tracks: Picked[] };
  bans?: { songs: number; artists: number; styles: number };
};
export type TrackRow = {
  rating_key: number; title: string; artist: string; album: string; year: number | null; duration_ms: number | null; live: boolean;
};
export type PlaylistPage = {
  playlist: PlaylistRow;
  stored: { count: number; live: number; rows: TrackRow[]; limit: number; offset: number; rule: string };
  tree: unknown; lines: Lines | null; lines_error: string | null;
};
export type LineRows = {
  line: string | null; path: string; words?: string; which?: Which; count: number; rule: string;
  rows: (TrackRow & { line?: string | null })[];
};
export type CopyRow = TrackRow & { copy: boolean; reason: string | null };
export type CopyRows = {
  server: Server; missing: boolean | null; count: number; rows: CopyRow[]; rule: string; reasons: Record<string, string>;
};

type Unit = 'playlist' | 'line' | 'track' | 'minute' | 'song' | 'artist' | 'style' | 'tag' | 'step';
export function count(n: number, unit: Unit): string {
  return `${fmt(n)} ${t(`unit.${unit}.${n === 1 ? 'one' : 'other'}` as StringKey)}`;
}
export const serverName = (s: Server) => t(`playlists.server.${s}` as StringKey);
export const kindName = (k: string) => t(`playlists.kind.${k}` as StringKey) ?? k;
export const fieldName = (f: string) => tf('playlists.field', { f });
