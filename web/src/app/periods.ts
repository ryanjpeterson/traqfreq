import { t, tf, tMaybe, type StringKey } from '../copy/t';
import { HISTORY_TOP, HISTORY_WRAPPED } from './route';
import { dayLabel, monthLabel, type RowsFilter } from './history';

/** T8: Years, Wrapped, On this day, Top and the P1 gate, as /api/history/years … /compare give them. */
export type Cache = { built_at: number; seconds: number; hit: boolean; key: string };
export type YearRow = { year: number; plays: number; hours: number; minutes: number; by_source: Record<string, number> };
export type OnThisDay = {
  year: number; plays: number;
  top: { artist: string | null; title: string | null; plays: number; rating_key: number | null; album_key: number | null }[];
};
export type Daily = {
  plays: number; hours: number; years: YearRow[]; on_this_day: OnThisDay[]; today: string; timezone: string;
  highlights?: {
    streak: { current: number; best: number; best_ended: string | null };
    busiest_day: { date: string; plays: number }; peak_year: { year: number; plays: number; hours: number };
    first_play: { date: string; artist: string | null; title: string | null } | null;
    artists_heard: number; days_played_pct: number; average_day: number;
  };
  cache?: Cache;
};
export type Part = { label: string; value: number; part?: number };
export type Wrapped = {
  year: number; month: number | null; day: number | null; period: string; start: number; end: number; timezone: string;
  plays: number; hours?: number; minutes?: number; artists?: number; songs?: number; new_artists?: number;
  new_artist_names?: string[]; in_library_pct?: number;
  sources?: { source: string; name: string; plays: number }[];
  busiest_day?: { date: string; plays: number };
  top_artists?: { name: string; plays: number; key: string }[];
  top_songs?: { artist: string; title: string; plays: number; key: string }[];
  top_albums?: { artist: string; album: string; plays: number; key: string }[];
  by_part?: Part[]; hours_of_day?: Part[]; weekdays?: Part[];
  by_date?: { date: string; plays: number }[] | null;
  every_play?: { time: string; artist: string; title: string; album: string | null; source: string; minutes: number }[] | null;
  not_in_p1: Record<string, string>;
  cache?: Cache;
};
export type TopKind = 'artists' | 'songs' | 'albums';
export type TopSort = 'plays' | 'minutes';
export type TopItem = { key: string; name: string | null; sub: string | null; plays: number; minutes: number; rank: number; in_library: boolean };
export type TopPage = {
  kind: TopKind; period: string; sort: TopSort; source: string | null; page: number; per: number; pages: number;
  total: number; plays: number; start: number | null; end: number | null; timezone: string;
  sources: { source: string; name: string; plays: number }[]; items: TopItem[]; not_in_p1: Record<string, string>;
  cache?: Cache;
};
export type CompareField = {
  field: string; matches: boolean | null; jimbodj?: unknown; traqfreq?: unknown; size?: number;
  first_diff?: unknown; skipped?: string;
};
export type CompareRow = {
  name: string; params: string; built_at: string | null; version: number; fresh: boolean; matches: boolean;
  fields: CompareField[]; compared: number; matching: number; error?: string;
};
export type Compare = {
  rows: CompareRow[]; stored: number; fields: number; matching_fields: number; matching: number; differ: number;
  stale: number; explained: number; passed: boolean; today: string; timezone: string;
  not_in_p1: Record<string, string>; rules: Record<string, string>; cache?: Cache;
};

export const TOP_KINDS: TopKind[] = ['artists', 'songs', 'albums'];
export const TOP_SORTS: TopSort[] = ['plays', 'minutes'];
export const TOP_PERIODS = ['all', '30d', '12m'] as const;

export const wrappedHref = (period: string) => `${HISTORY_WRAPPED}?period=${period}`;
export function topHref(o: { period?: string; kind?: TopKind; sort?: TopSort; page?: number }): string {
  const q = new URLSearchParams();
  q.set('period', o.period ?? 'all');
  q.set('kind', o.kind ?? 'artists');
  q.set('sort', o.sort ?? 'plays');
  if (o.page && o.page > 1) q.set('page', String(o.page));
  return `${HISTORY_TOP}?${q.toString()}`;
}

/** "2025", "June 2025", "14 Jun 2025"; a Top period also "All time", "Last 30 days", "Last 12 months". */
export function periodName(p: string): string {
  const fixed = tMaybe(`top.period.${p}`);
  if (fixed) return fixed;
  return p.length === 10 ? dayLabel(p) : p.length === 7 ? monthLabel(p) : p;
}

/** The rows filter for a period: YYYY… as `period`; the rolling ones as a span (end inclusive). */
export function periodFilter(period: string, start: number | null, end: number | null): RowsFilter {
  if (/^\d{4}(-\d{2}){0,2}$/.test(period)) return { period };
  if (start != null && end != null) return { start, end: end - 1 };
  return {};
}

/** The period before and after a Wrapped period, and the one that holds it. */
export function neighbours(period: string): { prev: string; next: string; up: string | null } {
  const [y, m, d] = period.split('-').map(Number);
  const iso = (dt: Date) => dt.toISOString().slice(0, 10);
  if (d) {
    const at = Date.UTC(y, m - 1, d);
    return { prev: iso(new Date(at - 86400000)), next: iso(new Date(at + 86400000)), up: period.slice(0, 7) };
  }
  if (m) {
    const pm = m === 1 ? [y - 1, 12] : [y, m - 1];
    const nm = m === 12 ? [y + 1, 1] : [y, m + 1];
    const f = ([a, b]: number[]) => `${a}-${String(b).padStart(2, '0')}`;
    return { prev: f(pm), next: f(nm), up: String(y) };
  }
  return { prev: String(y - 1), next: String(y + 1), up: null };
}

/** The Wrapped period a part of a period opens: a year's month, a month's day (a day's hours open rows). */
export function partPeriod(period: string, part: number): string | null {
  if (period.length === 4) return `${period}-${String(part).padStart(2, '0')}`;
  if (period.length === 7) return `${period}-${String(part).padStart(2, '0')}`;
  return null;
}

/** What a part of a Wrapped period is called: "Jan", "1", "13:00". */
export function partLabel(period: string, p: Part): string {
  if (period.length === 4) return monthLabel(`${period}-${String(p.part).padStart(2, '0')}`, 'short');
  if (period.length === 10) return tf('rows.title.hour', { h: p.label });
  return p.label;
}

export const weekdayName = (i: number) => t(`wrapped.weekday.${i}` as StringKey);
