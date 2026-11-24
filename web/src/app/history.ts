import { t, tf, tMaybe, type StringKey } from '../copy/t';
import { HISTORY_LISTENS } from './route';

/** What a listen is, as jimbo-dj decided it (history.py dedupe). Each listen is exactly one. */
export type ListenStatus = 'play' | 'too_short' | 'repeat' | 'duplicate';
export const NOT_PLAYS: ListenStatus[] = ['too_short', 'repeat', 'duplicate'];

export type SourceRow = {
  source: string; name: string; listens: number; play: number; too_short: number; repeat: number; duplicate: number;
  duplicate_of: Record<string, number>; first: string | null; last: string | null;
};
export type TopArtist = { name: string; key: string; plays: number };
export type Overview = {
  plays: number; listens: number; not_plays: Record<'too_short' | 'repeat' | 'duplicate', number>; adds_up: boolean;
  matched: { plays: number; pct: number }; songs: { heard: number | null; matched: number | null };
  sources: SourceRow[]; years: { year: number; plays: number; by_source: Record<string, number> }[];
  top_artists: TopArtist[]; artists_heard: number; timezone: string; rules: Record<string, string>;
  jimbodj: null | {
    plays: number; built_at: string | null; source: string; matches: boolean;
    matched_pct?: number; matched_pct_matches?: boolean; top_artists_match?: boolean;
  };
  cache?: { built_at: number; seconds: number; hit: boolean; key: string };
};
export type HeatCell = { date: string; plays: number; level: number };
export type Heatmap = {
  year: number | null; first: string | null; last: string | null; timezone: string; plays: number; days: number;
  days_played: number; busiest: { date: string; plays: number } | null;
  levels: { level: number; min: number; max: number }[]; cells: HeatCell[];
  months: { month: string; plays: number; days: number; days_played: number; busiest: { date: string; plays: number } | null }[];
  years: number[]; rules: Record<string, string>;
};
/** The listen a repeat or duplicate is of (T7), or null when none is in its window. */
export type OfListen = { id: number; source: string; started_at: string | null; play: boolean; gap_s: number; window_s: number };
export type ListenRow = {
  id: number; source: string; started_at: string | null; ms_played: number | null; artist: string | null;
  title: string | null; album: string | null; dup_of: string | null; rating_key: number | null;
  of?: OfListen | null;
};
export type GapBucket = { min: number; max: number; listens: number };
export type GapPair = {
  source: string; of: string; kind: 'repeat' | 'duplicate'; listens: number; windows: number[];
  buckets: GapBucket[]; not_found: number; beyond: number;
};
export type Finding = {
  start: number; end: number; first: string; last: string; plays: number; songs: number;
  sources: Record<string, number>; artist: string | null; title: string | null; held?: number; gap_s?: number;
};
export type CheckReport = { findings: number; plays: number; newest: Finding[]; rule: string; in_bursts?: number };
export type Counted = {
  gaps: { pairs: GapPair[]; repeats: number; duplicates: number; not_found: number; rules: Record<string, string> };
  checks: { plays_checked: number; burst: CheckReport; loop: CheckReport; rhythm: CheckReport };
  timezone: string | null;
  cache?: { built_at: number; seconds: number; hit: boolean; key: string };
};
export type Listens = {
  status: ListenStatus; source: string | null; year: number | null; period: string | null; artist: string | null;
  matched: boolean | null; of?: string | null; gap?: string | null; start?: number | null; end?: number | null;
  timezone: string; total: number; limit: number; offset: number; rule: string;
  params: (string | number)[]; rows: ListenRow[];
};

export type RowsFilter = {
  status?: ListenStatus; source?: string; year?: number; period?: string; artist?: string; matched?: boolean;
  offset?: number;
  /** T7: the source a repeat or duplicate is of; its gap ("a-b" seconds or "none"); a span in UTC epoch seconds. */
  of?: string; gap?: string; start?: number; end?: number;
  /** T8: one song (its match_key), one album (Top's key, artist|album normalised), an hour 0-23 or weekday 0-6. */
  song?: string; album?: string; hour?: number; weekday?: number;
  /** The artist's, song's or album's one name (Names), for the rows page heading only; the API filters by its key. */
  name?: string;
};

/** The rows page for a number: /history/listens?status=…&source=… */
export function rowsHref(f: RowsFilter): string {
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries({ status: 'play', ...f })) {
    if (v !== undefined && v !== null && v !== '' && !(k === 'offset' && v === 0)) q.set(k, String(v));
  }
  return `${HISTORY_LISTENS}?${q.toString()}`;
}

export const fmt = (n: number) => n.toLocaleString('en');

type Unit = 'play' | 'listen' | 'day' | 'song' | 'artist' | 'album' | 'finding' | 'field' | 'row' | 'bar' | 'entry' | 'tag' | 'broadTag' | 'ladder' | 'vote';
/** "1 play", "1,234 plays" (W3: numbers carry units). */
export function count(n: number, unit: Unit): string {
  return `${fmt(n)} ${t(`unit.${unit}.${n === 1 ? 'one' : 'other'}` as StringKey)}`;
}

export const sourceName = (s: string) => tMaybe(`source.${s}`) ?? s;

/** 2026-11-01 → "1 Nov 2026"; 2026-11 → "November 2026" (dates are already in the listening time zone). */
export function dayLabel(iso: string): string {
  const [y, m, d] = iso.split('-').map(Number);
  return new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' })
    .format(Date.UTC(y, m - 1, d));
}
export function monthLabel(ym: string, style: 'long' | 'short' = 'long'): string {
  const [y, m] = ym.split('-').map(Number);
  return new Intl.DateTimeFormat('en-GB', style === 'long'
    ? { month: 'long', year: 'numeric', timeZone: 'UTC' } : { month: 'short', timeZone: 'UTC' }).format(Date.UTC(y, m - 1, 1));
}

/** A UTC instant shown in the listening time zone: "2026-11-01 13:15". */
export function localTime(iso: string, timeZone: string): string {
  try {
    const p = Object.fromEntries(new Intl.DateTimeFormat('en-GB', {
      timeZone, year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
    }).formatToParts(new Date(iso)).map((x) => [x.type, x.value]));
    return `${p.year}-${p.month}-${p.day} ${p.hour}:${p.minute}`;
  } catch {
    return iso;
  }
}

/** Seconds as "20 s", "5 min", "1 min 30 s", "1 h" (W3: numbers carry units). */
export function duration(sec: number): string {
  if (sec < 60) return tf('unit.sec', { n: fmt(sec) });
  if (sec >= 3600 && sec % 3600 === 0) return tf('unit.hour', { n: fmt(sec / 3600) });
  const m = Math.floor(sec / 60);
  return sec % 60 ? tf('unit.minSec', { m: fmt(m), s: sec % 60 }) : tf('unit.min', { n: fmt(m) });
}
