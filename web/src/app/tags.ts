/** TAGS (T20): the ladder as GET /api/tags/ladder answers it, and the rows behind its numbers. */

export type TagNode = {
  key: string; name: string; in_use: boolean; broad: string | null; root: boolean;
  parents: string[]; children: string[]; rung: number | null;
  albums: number; artists: number; under: number; missing: number | null; below: number;
  variants: string[]; niche: boolean; other_heads: string[];
};

export type Family = { tag: string; key: string; albums: number; tagged: number; missing: number | null;
  children: { tag: string; key: string; albums: number }[] };
export type CheckRow = { key: string; tag: string; ladder: Family | null; jimbodj: Family | null; matches: boolean };

export type LadderCheck = {
  rules: { rows: CheckRow[]; matches: boolean; source: string };
  ends: { tags: number; ok: number; failing: string[]; matches: boolean; rule: string };
  stored: null | { rows: CheckRow[]; matches: boolean; fresh: boolean; built_at: number; source: string };
  passed: boolean;
};

export type LadderSummary = { tags: number; roots: number; deepest: number; shared: number; alone: number; junk: number;
  albums: number; artists: number };

export type Ladder = {
  nodes: Record<string, TagNode>; roots: string[]; alone: string[]; summary: LadderSummary;
  rules: Record<string, string>; check: LadderCheck; seconds: number;
};

export type TagSet = 'carries' | 'under' | 'missing';
export const TAG_SETS: TagSet[] = ['carries', 'under', 'missing'];

export type TagAlbum = { album_key: number; title: string | null; artist: string | null; artist_key: number | null;
  year: number | null; tags: string[]; carries: boolean; via: string[] };
export type TagArtist = { artist_key: number; name: string | null; albums: number; tags: string[] };
type Page<T> = { tag: { key: string; name: string; root: boolean }; rule: string; total: number; limit: number;
  offset: number; items: T[] };
export type TagAlbums = Page<TagAlbum> & { set: TagSet };
export type TagArtists = Page<TagArtist>;

export const TAGS_PATH = '/tags';
export const TAGS_ALBUMS = '/tags/albums';
export const TAGS_ARTISTS = '/tags/artists';
export const TAGS_LIST = '/tags/list';
export const LADDER_API = '/api/tags/ladder';

/** The tags behind a summary number. */
export type TagShow = 'tags' | 'roots' | 'deepest' | 'shared' | 'alone';
export const TAG_SHOWS: TagShow[] = ['tags', 'roots', 'deepest', 'shared', 'alone'];

const q = (params: Record<string, string | number | undefined>) =>
  Object.entries(params).filter(([, v]) => v !== undefined && v !== '').map(([k, v]) => `${k}=${encodeURIComponent(String(v))}`).join('&');

export const albumsHref = (tag: string, set: TagSet = 'carries', offset?: number) =>
  `${TAGS_ALBUMS}?${q({ tag, set, offset: offset || undefined })}`;
export const artistsHref = (tag: string, offset?: number) => `${TAGS_ARTISTS}?${q({ tag, offset: offset || undefined })}`;
export const listHref = (show: TagShow) => `${TAGS_LIST}?${q({ show })}`;
export const albumsApi = (tag: string, set: string, offset: number) => `/api/tags/albums?${q({ tag, set, offset: offset || undefined })}`;
export const artistsApi = (tag: string, offset: number) => `/api/tags/artists?${q({ tag, offset: offset || undefined })}`;

export function params(query: string): URLSearchParams {
  return new URLSearchParams(query.replace(/^\?/, ''));
}

/** The nodes behind a summary number, in ladder order (by broad tag, then rung, then name). */
export function shown(l: Ladder, show: TagShow): TagNode[] {
  const all = Object.values(l.nodes);
  const pick = {
    tags: all.filter((n) => n.in_use),
    roots: l.roots.map((k) => l.nodes[k]),
    deepest: all.filter((n) => n.rung === l.summary.deepest && n.rung !== null),
    shared: all.filter((n) => n.parents.length > 1),
    alone: l.alone.map((k) => l.nodes[k]),
  }[show];
  const rootOrder = new Map(l.roots.map((k, i) => [l.nodes[k].broad, i]));
  return [...pick].sort((a, b) => (rootOrder.get(a.broad) ?? 1e9) - (rootOrder.get(b.broad) ?? 1e9)
    || (a.rung ?? 99) - (b.rung ?? 99) || a.name.localeCompare(b.name));
}

// --- T21: tracks tagged one by one -------------------------------------------------------------------------

/** One raw value from a source through the rules: each canonical tag it makes, on its rung (null: not on the ladder). */
export type SourceTag = { raw: string; key: string; name: string; junk: string | null; broad: string | null;
  rung: number | null; on_ladder: boolean; score?: number; discogs?: string; kept?: boolean };
export type TrackSource = 'track' | 'file' | 'album' | 'artist' | 'mb-release' | 'mb-artist' | 'sound';
export const TRACK_SOURCES: TrackSource[] = ['track', 'file', 'album', 'artist', 'mb-release', 'mb-artist', 'sound'];
export type SourceBlock = { tags: SourceTag[]; read?: boolean; error?: string | null; note?: string; found?: boolean; analysed?: boolean };

/** A tag the track carries by jimbo-dj's per-track rule, with the sources that name it. */
export type TrackTag = { key: string; name: string; broad: string | null; rung: number | null; on_ladder: boolean;
  sources: TrackSource[]; album: boolean };
export type TrackCheckOne = { tags: boolean; styles: boolean; jimbodj_tags: string[]; jimbodj_styles: string[] };

export type TagTrackRow = {
  rating_key: number; title: string | null; artist: string | null; album: string | null; album_key: number | null;
  artist_key: number | null; disc: number | null; track_no: number | null; live: boolean;
  tags: TrackTag[]; differs: TrackTag[]; styles: SourceTag[]; check: TrackCheckOne;
};
export type TagTrack = TagTrackRow & { sources: Record<TrackSource, SourceBlock>;
  album_tags: { name: string; status: string }[]; rules: Record<string, string> };

export type FromTracks = { key: string; name: string; rung: number | null; on_ladder: boolean; broad: string | null;
  tracks: number; files: number; speaks: boolean; album: boolean; status: string };
export type TagAlbumPage = {
  album_key: number; title: string | null; artist: string | null; artist_key: number | null; year: number | null;
  tags: { name: string; status: string }[]; tracks: TagTrackRow[]; differ: number; from_tracks: FromTracks[];
  track_share: number; check: { tags: number; styles: number; tracks: number }; rules: Record<string, string>;
};

type Differ = { rating_key: number; title: string | null; artist: string | null; traqfreq: string[]; jimbodj: string[] };
export type TracksCheck = {
  tags: { tracks: number; with_tags: number; ok: number; differ: number; items: Differ[]; unknown: number[]; matches: boolean; source: string };
  styles: { tracks: number; analysed: number; kept: number; ok: number; differ: number; items: Differ[]; matches: boolean; source: string };
  passed: boolean; rule: string;
};

export const TAGS_ALBUM = '/tags/album/';
export const TAGS_TRACK = '/tags/track/';
export const TRACKS_CHECK_API = '/api/tags/tracks/check';
export const tagAlbumHref = (key: number, differs = false) => `${TAGS_ALBUM}${key}${differs ? '?show=differs' : ''}`;
export const tagTrackHref = (key: number) => `${TAGS_TRACK}${key}`;
export const tagAlbumApi = (key: number) => `/api/tags/album/${key}`;
export const tagTrackApi = (key: number) => `/api/tags/track/${key}`;
