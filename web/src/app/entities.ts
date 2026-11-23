import { tMaybe } from '../copy/t';
import { LIBRARY_ALBUMS, LIBRARY_ARTISTS, LIBRARY_PLAYS } from './route';

/** T11: albums, artists and a track as /api/library/… answers them (jimbo-dj's page code, vendored). */
export type ListKind = 'albums' | 'artists';
export type ListSort = 'plays' | 'added' | 'name' | 'year';
export const LIST_SORTS: ListSort[] = ['plays', 'added', 'name', 'year'];

export type ListItem = {
  key: number; name: string | null; artist: string | null; artist_key: number | null; tracks: number; plays: number;
  added: string | null; year: number | null; rows: string;
};
export type EntityList = {
  kind: ListKind; sort: ListSort; total: number; limit: number; offset: number; items: ListItem[];
  rules: Record<string, string>;
};

/** jimbo-dj's summarise: plays by source and year, first and last, plus the newest 30 listens. */
export type Summary = {
  plays: number; first?: string | null; last?: string | null; timezone?: string;
  sources?: { source: string; name: string; plays: number }[];
  years?: { year: number; plays: number; by_source: Record<string, number> }[];
  songs?: number; top_songs?: { title: string | null; artist: string | null; rating_key: number | null; album_key: number | null; plays: number }[];
  recent?: { at: string | null; source: string; name: string; rating_key: number | null; local: string }[];
};

/** A track as pages._track gives it (and _top_songs, with versions and albums). */
export type PageTrack = {
  rating_key: number; title: string | null; artist: string | null; artist_key: number | null; album: string | null;
  album_key: number | null; year: number | null; duration_ms: number | null; disc: number | null; track_no: number | null;
  view_count: number | null; track_artist: string | null; bpm: number | null; camelot: string | null; key: string | null;
  scale: string | null; moods: string[]; plays: number; versions?: number; albums?: number;
};

export type Album = {
  album: {
    album_key: number; slug: string; title: string | null; artist: string | null; artist_key: number | null; year: number | null;
    released?: string | null; label?: string | null; mbid?: string | null; plex_year?: number | null;
    musicbrainz?: { first_release: string | null; date: string | null; country: string | null; labels: string[]; type: string | null; secondary: string[] };
  };
  tracks: PageTrack[]; plays: number; minutes: number; history: Summary;
  rows: { tracks: string; plays: string }; rules: Record<string, string>;
};

export type ArtistAlbum = {
  album_key: number; title: string | null; artist: string | null; year: number | null; tracks: number; plays: number;
  appears_on: boolean; rows: string;
};
export type Artist = {
  artist: { artist_key: number; name: string | null; slug: string; mbid: string | null };
  tracks: number; albums: ArtistAlbum[]; top_tracks: PageTrack[]; plays: number; history: Summary;
  rows: { tracks: string; plays: string }; rules: Record<string, string>;
};

export type Track = {
  track: Record<string, string | number | null> & {
    rating_key: number; title: string | null; artist: string | null; track_artist: string | null; album: string | null;
    album_key: number | null; artist_key: number | null; removed_at: string | null;
  };
  kind: string | null; live: boolean;
  plays: { plays: number; plex: number; history: number; last_played: string | null };
  analysis: null | { status: string; version: number; error: string | null; analyzed_at: string | null; seconds: number | null; current: boolean };
  features: null | Record<string, number | string | null> & { moods: string[] };
  analyzer_version: number; history: Summary;
  song: {
    title: string; artist: string; copies: number; history: Summary | null;
    versions: { rating_key: number; title: string | null; album: string | null; album_key: number | null; artist: string | null; year: number | null; kind: string | null; plays: number }[];
  };
  rows: { plays: string; song: string | null }; rules: Record<string, string>;
};

export type PlayRow = {
  started_at: string | null; source: string; name: string; artist: string | null; title: string | null; album: string | null;
  rating_key: number | null; album_key: number | null;
};
export type Plays = {
  track?: number; song?: boolean; album?: number; artist?: number; name?: string; source: string | null; sources: string[];
  total: number; limit: number; offset: number; rule: string; timezone: string; rows: PlayRow[];
};

export const albumHref = (key: number) => `/library/album/${key}`;
export const artistHref = (key: number) => `/library/artist/${key}`;
export const trackHref = (key: number) => `/library/track/${key}`;
export const listHref = (kind: ListKind, sort?: ListSort, offset?: number) => {
  const q = new URLSearchParams();
  if (sort && sort !== 'plays') q.set('sort', sort);
  if (offset) q.set('offset', String(offset));
  const s = q.toString();
  return `${kind === 'albums' ? LIBRARY_ALBUMS : LIBRARY_ARTISTS}${s ? `?${s}` : ''}`;
};
/** The listens page for a query from a page's `rows.plays` (track=…, album=…, artist=…), plus source and offset. */
export const playsHref = (query: string, extra?: Record<string, string | number | undefined>) => {
  const q = new URLSearchParams(query);
  for (const [k, v] of Object.entries(extra ?? {})) {
    if (v === undefined || v === '' || (k === 'offset' && v === 0)) q.delete(k); else q.set(k, String(v));
  }
  return `${LIBRARY_PLAYS}?${q.toString()}`;
};

export function parseListQuery(query: string): { sort: ListSort; offset: number } {
  const q = new URLSearchParams(query);
  const s = q.get('sort');
  const o = q.get('offset');
  return { sort: LIST_SORTS.find((x) => x === s) ?? 'plays', offset: o && /^\d+$/.test(o) ? Number(o) : 0 };
}

/** What a copy is (jimbo-dj's songs.version): the original, live, a compilation, a demo… */
export const kindLabel = (k: string | null) => (k ? tMaybe(`entity.kind.${k}`) ?? k : tMaybe('entity.kind.original') ?? '');
