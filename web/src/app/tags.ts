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
