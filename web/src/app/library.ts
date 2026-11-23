import { t, tf, type StringKey } from '../copy/t';
import { fmt } from './history';
import { LIBRARY_TRACKS } from './route';

/** jimbo-dj's library.stats as GET /api/library/stats answers it (T9): its numbers, plus traqfreq's rules and rows. */
export type LibraryStats = {
  server: Record<string, unknown>; last_sync: number | null;
  tracks: number; albums: number; artists: number; hours: number; size_gb: number;
  codecs: Record<string, number>; containers: Record<string, number>; bitrate_kbps: Record<string, number>;
  play_history: {
    played_tracks: number; played_pct: number; total_plays: number; rated_tracks: number; rated_pct: number;
    top_artists: Record<string, number>;
  };
  sonic_analysis: { tracks: number; pct: number };
  analyzer: { version: number; tracks: number; pct: number; errors: number };
  paths: {
    folders: Record<string, { read_from: string; readable_here: boolean; tracks: number }>; folders_compared: false;
    mapped: number; mapped_pct: number; unmapped_examples: string[]; multi_part_tracks: number; removed_since_first_sync: number;
  };
  top_artist_keys: { artist: string; artist_key: number; plays: number }[];
  rules: Record<string, string>;
  /** The /api/library/tracks query string behind each number; by value for codecs, containers, bitrate, top artists. */
  rows: Record<string, string | Record<string, string>>;
  jimbodj: null | { source: string; built_at: string | null; stamp: string | null; fresh: boolean };
  cache?: { built_at: number; seconds: number; hit: boolean; key: string };
};

export type TrackRow = {
  rating_key: number; title: string | null; artist: string | null; track_artist: string | null; album: string | null;
  album_key: number | null; artist_key: number | null; disc: number | null; track_no: number | null; year: number | null;
  duration_ms: number | null; plex_path: string | null; local_path: string | null; parts: number | null;
  file_size: number | null; container: string | null; codec: string | null; bitrate: number | null;
  view_count: number | null; last_viewed_at: string | null; user_rating: number | null; sonic_version: number | null;
  added_at: string | null; removed_at: string | null; analysis_status: string | null; analysis_version: number | null;
  camelot: string | null; bpm: number | null; plays: number; history_plays: number; last_played: string | null;
};
export type Tracks = {
  filters: Record<string, string | number | boolean | null>; sort: TrackSort; total: number; limit: number; offset: number;
  rule: string; params: (string | number)[]; plays_rule: string; rows: TrackRow[];
};

export type TrackSort = 'artist' | 'plex_plays' | 'added';
export const SORTS: TrackSort[] = ['artist', 'plex_plays', 'added'];
export const ANALYSIS = ['ok', 'error', 'older', 'none'] as const;
export const BUCKETS = ['<192k', '192-255k', '256-319k', '320k', '>320k (lossless)'];

/** The filters /api/library/tracks knows, as the rows page reads them from its address. */
export type TrackFilter = {
  codec?: string; container?: string; bitrate?: string; played?: boolean; rated?: boolean; sonic?: boolean;
  analysis?: (typeof ANALYSIS)[number]; mapped?: boolean; multi_part?: boolean; removed?: boolean;
  artist_key?: number; album_key?: number; sort?: TrackSort; offset?: number;
  /** The artist's name, for the heading only; the API filters by its key. */
  name?: string;
};
const BOOLS = ['played', 'rated', 'sonic', 'mapped', 'multi_part', 'removed'] as const;
const ORDER: (keyof TrackFilter)[] = ['codec', 'container', 'bitrate', ...BOOLS, 'analysis', 'artist_key', 'album_key', 'sort', 'offset', 'name'];

export function parseTrackFilter(query: string): TrackFilter {
  const q = new URLSearchParams(query);
  const num = (k: string) => (q.get(k) && /^\d+$/.test(q.get(k)!) ? Number(q.get(k)) : undefined);
  const bool = (k: string) => (q.get(k) === 'true' ? true : q.get(k) === 'false' ? false : undefined);
  const a = q.get('analysis');
  const s = q.get('sort');
  const b = q.get('bitrate');
  const f: TrackFilter = {
    codec: q.get('codec') ?? undefined,
    container: q.get('container') ?? undefined,
    bitrate: b && BUCKETS.includes(b) ? b : undefined,
    analysis: ANALYSIS.find((x) => x === a),
    artist_key: num('artist_key'),
    album_key: num('album_key'),
    sort: SORTS.find((x) => x === s),
    offset: num('offset'),
    name: (q.get('artist_key') && q.get('name')) || undefined,
  };
  for (const k of BOOLS) f[k] = bool(k);
  if (f.removed === false) f.removed = undefined;  // false is the default: live tracks
  return f;
}

/** The query string for a filter, in a fixed order (offset 0 and the default sort left out). */
export function trackQuery(f: TrackFilter): string {
  const q = new URLSearchParams();
  for (const k of ORDER) {
    const v = f[k];
    if (v === undefined || v === null || v === '' || (k === 'offset' && v === 0) || (k === 'sort' && v === 'artist')) continue;
    q.set(k, String(v));
  }
  return q.toString();
}

/** The rows page for a query from the stats' `rows` map: /library/tracks?… (no query = every live track). */
export function tracksHref(query: string, extra?: Record<string, string>): string {
  const q = new URLSearchParams(query);
  for (const [k, v] of Object.entries(extra ?? {})) q.set(k, v);
  const s = q.toString();
  return s ? `${LIBRARY_TRACKS}?${s}` : LIBRARY_TRACKS;
}

/** 3649.6 → "3,649.6"; numbers stored to 0.1 keep their one decimal. */
export const fmt1 = (n: number) => n.toLocaleString('en', { minimumFractionDigits: 1, maximumFractionDigits: 1 });
export const pct = (n: number) => tf('unit.pct', { n: fmt1(n) });

type Unit = 'track' | 'play' | 'album' | 'artist' | 'folder';
export function count(n: number, unit: Unit): string {
  return `${fmt(n)} ${t(`unit.${unit}.${n === 1 ? 'one' : 'other'}` as StringKey)}`;
}

/** A value as jimbo-dj counts it: '?' is "none given" (COALESCE(col, '?')). */
export const valueLabel = (v: string) => (v === '?' ? t('library.none') : v);
