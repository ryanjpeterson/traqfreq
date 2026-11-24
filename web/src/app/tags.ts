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

export type TagSet = 'carries' | 'under' | 'missing' | 'sound';
export const TAG_SETS: TagSet[] = ['carries', 'under', 'missing', 'sound'];

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

// --- T22: the proposals inbox (shown, never applied) and gate check 3 --------------------------------------

export type IssueKind = 'junk' | 'split' | 'spelling' | 'case' | 'broad' | 'niche' | 'untagged';
export type Fix = { op: 'add' | 'remove' | 'rename'; kind: IssueKind; tag: string | null; to: string[]; albums: number;
  id: string; label: string };
export type Suggestion = { tag: string; albums: number; key: string; in_use: boolean };
export type LadderProposal = { key: string; tag: string; rung: number | null; albums: number; because: string[] };
export type RuleQuestion = { key: string; tag: string; broad: string; family: string; match: string; last: string;
  albums: number; artists: number };

type ListPart<T> = { items: number; ok: number; differ: number; matches: boolean; stored: boolean;
  differing?: { at: number; traqfreq: T | null; jimbodj: T | null; matches: boolean }[] };
type TagNumbers = { key: string; name: string; albums: number; artists: number; tracks: number; musicbrainz: number;
  sound: number; issues: unknown[] };
export type AuditCheck = {
  rule: string; source: string; stored: true | null; passed: boolean; fresh?: boolean; built_at?: number; matches?: boolean;
  tags?: { tags: number; ok: number; differ: number; matches: boolean; stored: boolean; fields: string[];
    differing: { key: string; name: string; traqfreq: TagNumbers | null; jimbodj: TagNumbers | null }[] };
  issues?: { rows: { kind: IssueKind; label: string; traqfreq: number; jimbodj: number | null; matches: boolean }[];
    ok: number; kinds: number; matches: boolean; stored: boolean };
  fixes?: ListPart<Omit<Fix, 'id' | 'label'>>;
  suggestions?: ListPart<Omit<Suggestion, never>>;
};

export type Inbox = {
  summary: { albums: number; proposed: number; issues: number; clean: number; with_recs: number; fixable: number;
    ladder: number; rules: number };
  kinds: { kind: IssueKind; label: string; albums: number; fixable: boolean }[];
  fixable: { kind: IssueKind; label: string; albums: number }[];
  default: IssueKind[];
  fixes: Fix[]; suggestions: Suggestion[]; ladder: LadderProposal[]; rules: RuleQuestion[];
  check: AuditCheck;
  fix_in_plex: { where: string; path: string; port: number; until: string };
  rule: Record<string, string>;
};

export type Change = { kind: IssueKind; op: 'add' | 'remove' | 'rename'; tag: string; to?: string[]; because?: string[] };
export type Rec = { tag: string; key: string; sources: Record<string, number>; score: number; release_votes: number; artist_votes: number };
export type ProposalAlbum = {
  album_key: number; title: string | null; artist: string | null; artist_key: number | null; year: number | null;
  before: string[]; after: string[]; changes: Change[]; issues: (Change & { rule?: string })[]; recs: Rec[];
  proposed: string[]; score: number; ladder: { key: string; tag: string; because: string[]; rung: number | null }[];
};
export type ProposalGroup = 'all' | 'kind' | 'fix' | 'suggest' | 'ladder' | 'rule';
export const PROPOSAL_GROUPS: ProposalGroup[] = ['all', 'kind', 'fix', 'suggest', 'ladder', 'rule'];
export type ProposalAlbums = {
  group: ProposalGroup; value: string | null; label?: string; tag?: string;
  fix?: Omit<Fix, 'id' | 'albums'>; question?: RuleQuestion;
  kinds: IssueKind[]; rule: string; total: number; limit: number; offset: number; items: ProposalAlbum[];
};

export const TAGS_PROPOSALS = '/tags/proposals';
export const TAGS_PROPOSAL_ALBUMS = '/tags/proposals/albums';
export const PROPOSALS_API = '/api/tags/proposals';
export const proposalsHref = (group: ProposalGroup = 'all', value?: string, offset?: number) =>
  `${TAGS_PROPOSAL_ALBUMS}?${q({ group, value, offset: offset || undefined })}`;
export const proposalsApi = (group: string, value: string | undefined, offset: number) =>
  `/api/tags/proposals/albums?${q({ group, value, offset: offset || undefined })}`;

/** Where jimbo-dj's Fix in Plex is: the same host as this page, jimbo-dj's port. */
export function fixInPlexHref(f: Inbox['fix_in_plex'], loc: { protocol: string; hostname: string } = window.location): string {
  return `${loc.protocol}//${loc.hostname}:${f.port}${f.path}`;
}

// --- T23: a page per tag, the genre map, movements and the P4 gate ------------------------------------------

export type TagBrief = { key: string; name: string; albums: number; under: number; rung: number | null; children: number;
  parents: number };
export type Spelling = { raw: string; albums: number; artists: number; tracks: number; same: boolean; split: boolean;
  rules: { id: string; label: string }[] };
export type MovementTag = { key: string; name: string; in_use: boolean; broad: string | null; rung: number | null;
  albums: number; artists: number };
export type Movement = { id: string; name: string; about: string; tags: MovementTag[]; broads: string[]; in_use: number };
export type SoundProfile = Record<string, number>;
export type TagPageData = {
  key: string; name: string; in_use: boolean;
  junk: { id: string; label: string; why: string | null } | null;
  broad: string | null; root: boolean; rung: number | null;
  broad_rule: null | { how: 'override' | 'family'; pattern?: string; family?: string; match: string | null; broad: string };
  ladders: { key: string; name: string; rung: number | null }[][];
  parents: TagBrief[]; children: TagBrief[]; below: number; other_heads: string[];
  spellings: Spelling[]; issues: { kind: string; op: string }[];
  numbers: { albums: number; under: number; missing: number | null; artists: number; tracks: number;
    plays: number | null; sound: number; musicbrainz: number };
  history: boolean; profile: SoundProfile | null; movements: Movement[]; rules: Record<string, string>;
};
export type TagTrackItem = { rating_key: number; title: string | null; artist: string | null; album: string | null;
  album_key: number | null; disc: number | null; track_no: number | null; plays: number };
export type TagTracksPage = { tag: { key: string; name: string; root: boolean }; sort: 'plays' | 'album'; rule: string;
  plays_rule: string; total: number; plays: number; limit: number; offset: number; items: TagTrackItem[] };

export type Station = { key: string; name: string; albums: number; under: number; rung: number | null; in_use: boolean;
  also: string[]; movements: string[]; stations: Station[] };
export type MapLine = { key: string; name: string; albums: number; under: number; missing: number | null; in_use: boolean;
  tags: number; stops: number; stations: Station[]; movements: string[] };
export type GenreMapData = {
  lines: MapLine[]; alone: { key: string; name: string; albums: number; under: number; movements: string[] }[];
  movements: Movement[];
  summary: { lines: number; tags: number; alone: number; shared: number; deepest: number; movements: number };
  rules: Record<string, string>;
};

type GateIds<T> = { differing: T[] };
export type GateLadder = { check: 'ladder'; passed: boolean; rule: string; page: string;
  rules: { broad: number; ok: number; matches: boolean } & GateIds<string>;
  ends: { tags: number; ok: number; matches: boolean; failing: string[] };
  stored: null | ({ broad: number; ok: number; matches: boolean; fresh: boolean; built_at: number | null } & GateIds<string>) };
export type GateTracks = { check: 'tracks'; passed: boolean; rule: string; page: string;
  tags: { tracks: number; ok: number; differ: number; with_tags: number; matches: boolean } & GateIds<number>;
  styles: { tracks: number; ok: number; differ: number; analysed: number; kept: number; matches: boolean } & GateIds<number> };
type Part = { items: number; ok: number; matches: boolean };
export type GateAudit = { check: 'audit'; passed: boolean; rule: string; page: string; stored: boolean; fresh: boolean | null;
  built_at?: number;
  tags?: { tags: number; ok: number; differ: number; matches: boolean; only_here: number; only_stored: number;
    differing: { key: string; name: string; fields: Record<string, [unknown, unknown]> }[] };
  issues?: { kinds: number; ok: number; matches: boolean }; fixes?: Part; suggestions?: Part };
export type TagsGate = { gate: 'P4'; checks: [GateLadder, GateTracks, GateAudit]; passed: boolean;
  rules: Record<string, string>; read_only: string };

export const TAGS_TAG = '/tags/tag/';
export const TAGS_MAP = '/tags/map';
export const TAGS_TRACKS = '/tags/tracks';
export const MAP_API = '/api/tags/map';
export const TAGS_GATE_API = '/api/tags/compare';
export const tagHref = (key: string) => `${TAGS_TAG}${encodeURIComponent(key)}`;
export const tagApi = (key: string) => `/api/tags/tag/${encodeURIComponent(key)}`;
export const tagTracksHref = (tag: string, sort: 'plays' | 'album' = 'plays', offset?: number) =>
  `${TAGS_TRACKS}?${q({ tag, sort: sort === 'plays' ? undefined : sort, offset: offset || undefined })}`;
export const tagTracksApi = (tag: string, sort: string, offset: number) =>
  `/api/tags/tracks?${q({ tag, sort, offset: offset || undefined })}`;

/** Every station on a line, depth first (a shared tag once per branch). */
export function stationsOf(st: Station[]): Station[] {
  return st.flatMap((s) => [s, ...stationsOf(s.stations)]);
}
