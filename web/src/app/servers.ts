import { t, tf, tMaybe, type StringKey } from '../copy/t';
import { fmt } from './history';

/** T15: the SERVERS page's API answers (/api/servers, /api/servers/identity, /api/servers/copies, /api/servers/matches). */

export type ServerId = 'plex' | 'jellyfin' | 'navidrome';
export const OTHER_SERVERS: ServerId[] = ['jellyfin', 'navidrome'];
export type PairId = 'jellyfin' | 'navidrome' | 'jellyfin-navidrome';

export type ServerSetting = { env: string; set: boolean; secret: boolean; value: string | null };
export type ServerStatus = {
  server: ServerId; name: string; set_up: boolean; read: boolean; settings: ServerSetting[]; note?: string;
  source?: string; server_name?: string | null; version?: string | null; section?: string | null;
  last_sync?: number | null; tracks?: number | null; url?: string | null; missing?: string[];
};
export type Servers = { servers: ServerStatus[]; read_only: string };

export type Identity = {
  counts: Record<string, number>; issues: Record<string, number>; clean: number;
  roots: { folder: string; tracks: number }[]; root_source: string; root_rule: string;
  rules: Record<string, string>; rows: Record<string, string>;
};

export type Copy = {
  rating_key: number; title: string | null; artist: string | null; track_artist: string | null; album: string | null;
  disc: number | null; track_no: number | null; duration_ms: number | null; plex_path: string | null; parts: number | null;
  file: string | null; song?: string; match_key?: string; issues: string[]; song_copies?: number;
};
export type Copies = { total: number; offset: number; limit: number; sort: string; rule: string; copies: Copy[] };

export type Item = {
  id: string; path: string | null; hidden: boolean; file: string | null; title: string | null; artist: string | null;
  album_artist: string | null; album: string | null; disc: number | null; track: number | null; duration_ms: number | null;
  mb_recording: string | null; mb_release: string | null; size: number | null; play_count: number | null;
};

export type Snapshot =
  | { server: ServerId; snapshot: false; note: string }
  | {
    server: ServerId; snapshot: true; read_at: number; age_s: number; stamp: Record<string, unknown>; folders: string[];
    folder_source: string; folder_rule: string; items: number; hidden_paths: number;
  };

export type Pair = {
  pair: PairId; left: ServerId; right: ServerId; counts: Record<string, number>; tiers: Record<string, number>;
  notes: Record<string, number>; unmatched_left: Record<string, number>; unmatched_items: Record<string, number>;
  rules: Record<string, string>; rows: Record<string, string>;
};

export type MatchRow = {
  pair: PairId; side: 'both' | 'left' | 'right'; tier: string | null; how?: string | null; shared?: boolean;
  multi_part?: boolean; mbid_from?: string | null; via?: number | null; reason: string | null;
  left: (Copy & Partial<Item>) | Item | null; right: Item | null;
};

export type Matches = {
  snapshots: Snapshot[]; pairs: Pair[]; missing: PairId[]; tiers: { tier: string; rule: string }[];
  reasons: Record<string, string>; read_only: string;
  rows?: { total: number; offset: number; limit: number; rule: string; rows: MatchRow[] };
  copy?: { rating_key: number; live: boolean };
};

/** SETUP's SERVERS page and its rows pages. */
export const SERVERS_PATH = '/setup/servers';
export const SERVER_COPIES = '/setup/servers/copies';
export const SERVER_MATCHES = '/setup/servers/matches';

export const serverName = (s: string) => tMaybe(`servers.name.${s}`) ?? s;
export const pairName = (p: PairId) => t(`servers.pair.${p}` as StringKey);
export const tierName = (tier: string) => tMaybe(`servers.tier.${tier}`) ?? tier;
/** A tier inside a sentence: "matched by file". */
export const tierIn = (tier: string) => tMaybe(`servers.tierIn.${tier}`) ?? tier;
export const reasonName = (r: string) => tMaybe(`servers.reason.${r}`) ?? r;

/** "2 min", "5 h", "18 days": how old a snapshot is. */
export function ageLabel(s: number): string {
  if (s < 60) return tf('unit.sec', { n: fmt(Math.max(0, s)) });
  if (s < 3600) return tf('unit.min', { n: fmt(Math.floor(s / 60)) });
  if (s < 86400 * 2) return tf('unit.hour', { n: fmt(Math.floor(s / 3600)) });
  const d = Math.floor(s / 86400);
  return `${fmt(d)} ${t(d === 1 ? 'unit.day.one' : 'unit.day.other')}`;
}

/** The API behind a page: the query as the page holds it. */
export const copiesApi = (q: string) => (q ? `/api/servers/copies?${q}` : '/api/servers/copies');
export const matchesApi = (q: string) => (q ? `/api/servers/matches?${q}` : '/api/servers/matches');

/** A rows page link: the API's own rows query, on its page. */
export const copiesHref = (q: string) => (q ? `${SERVER_COPIES}?${q}` : SERVER_COPIES);
export const matchesHref = (q: string) => `${SERVER_MATCHES}?${q}`;

/** The filters a rows page passes on to the API: only the ones it knows, in a fixed order. */
const COPY_KEYS = ['issue', 'has_file', 'versions', 'song', 'file', 'offset'] as const;
const MATCH_KEYS = ['server', 'tier', 'reason', 'rating_key', 'offset'] as const;
function pick(query: string, keys: readonly string[], extra: Record<string, string | number | undefined> = {}): string {
  const p = new URLSearchParams(query);
  const out = new URLSearchParams();
  for (const k of keys) {
    const v = k in extra ? extra[k] : p.get(k);
    if (v != null && v !== '' && !(k === 'offset' && Number(v) === 0)) out.set(k, String(v));
  }
  return out.toString();
}
export const copyQuery = (query: string, extra?: Record<string, string | number | undefined>) => pick(query, COPY_KEYS, extra);
export const matchQuery = (query: string, extra?: Record<string, string | number | undefined>) => pick(query, MATCH_KEYS, extra);

/** The heading for a copies filter: "Copies · with multi-part". */
export function copiesTitle(query: string): string {
  const p = new URLSearchParams(query);
  const issue = p.get('issue');
  return [
    t('servers.copies.title'),
    issue && tf('servers.copies.issue', { i: tMaybe(`servers.issue.${issue}`) ?? issue }),
    p.get('has_file') === 'true' && t('servers.copies.withFile'),
    p.get('has_file') === 'false' && t('servers.copies.withoutFile'),
    p.get('versions') === 'true' && t('servers.copies.versions'),
  ].filter(Boolean).join(' · ');
}

/** The heading for a matches filter: "Plex ↔ Navidrome · by tags". */
export function matchesTitle(query: string): string {
  const p = new URLSearchParams(query);
  const server = p.get('server') as PairId | null;
  const tier = p.get('tier');
  const reason = p.get('reason');
  return [
    server ? pairName(server) : t('servers.pair.every'),
    tier && tf('servers.rows.byTier', { tier: tierIn(tier) }),
    reason && t('servers.on.notMatched'),
    reason && reasonName(reason),
    p.get('rating_key') && tf('servers.rows.copy', { k: p.get('rating_key')! }),
  ].filter(Boolean).join(' · ');
}
