import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, within } from '@testing-library/react';
import { Shell } from '../App';
import { CORE_ONLY } from '../app/api';
import { parseRoute } from '../app/route';
import { neighbours, periodFilter, topHref } from '../app/periods';
import { parseFilter } from './HistoryRows';

// Invented answers, shaped like the fixture's (never real data).
const MODULES = { modules: CORE_ONLY.map((m) => ({ ...m, on: m.core || m.id === 'H' })) };
const CACHE = { built_at: 1793847960, seconds: 0.01, hit: true, key: 'v1' };

const DAILY = {
  plays: 6, hours: 0, today: '2027-11-01', timezone: 'America/Denver',
  years: [{ year: 2025, plays: 1, hours: 0, minutes: 5, by_source: { lastfm: 1 } },
    { year: 2026, plays: 5, hours: 0, minutes: 23, by_source: { lastfm: 2, plex: 1, spotify: 1, applemusic: 1 } }],
  on_this_day: [{ year: 2026, plays: 2, top: [
    { artist: 'Kollektiv Nord', title: 'Westkreuz', plays: 1, rating_key: 101, album_key: 201 }] }],
  highlights: {
    streak: { current: 0, best: 4, best_ended: '2026-11-04' }, busiest_day: { date: '2026-11-01', plays: 2 },
    peak_year: { year: 2026, plays: 5, hours: 0 }, first_play: { date: '2025-12-31', artist: 'Kollektiv Nord', title: 'Ostkreuz' },
    artists_heard: 4, days_played_pct: 2, average_day: 1,
  },
  cache: CACHE,
};

const months = (n: number) => Array.from({ length: n }, (_, i) => ({ label: String(i + 1), value: i === 10 ? 5 : 0, part: i + 1 }));
const WRAPPED = {
  year: 2026, month: null, day: null, period: '2026', start: 1767250800, end: 1798786800, timezone: 'America/Denver',
  plays: 5, hours: 0.4, minutes: 23, artists: 4, songs: 5, new_artists: 3, new_artist_names: ['The Paper Lanterns', 'Ada Vey', 'Nobody Known'],
  in_library_pct: 80, sources: [{ source: 'lastfm', name: 'Last.fm', plays: 2 }, { source: 'plex', name: 'Plex', plays: 1 }],
  busiest_day: { date: '2026-11-01', plays: 2 },
  top_artists: [{ name: 'The Paper Lanterns', plays: 2, key: 'paperlanterns' }, { name: 'Ada Vey', plays: 1, key: 'adavey' }],
  top_songs: [{ artist: 'Ada Vey', title: 'Coil', plays: 1, key: 'adavey|coil' }],
  top_albums: [{ artist: 'The Paper Lanterns', album: 'Low Tide Radio', plays: 2, key: 'paperlanterns|lowtideradio' }],
  by_part: months(12),
  hours_of_day: Array.from({ length: 24 }, (_, h) => ({ label: String(h).padStart(2, '0'), value: h === 13 ? 2 : 0 })),
  weekdays: Array.from({ length: 7 }, (_, d) => ({ label: 'x', value: d === 6 ? 2 : 0 })),
  by_date: [], every_play: null,
  not_in_p1: { families: 'styles of the plays\' library tracks (TAGS, P4)' }, cache: CACHE,
};

const TOP = {
  kind: 'albums', period: '30d', sort: 'minutes', source: null, page: 1, per: 48, pages: 1, total: 2, plays: 5,
  start: 1791230400, end: 1793826000, timezone: 'America/Denver', sources: [], not_in_p1: { genres: 'library genre tags (TAGS, P4)' },
  items: [
    { key: 'kollektivnord|ringbahn', name: 'Ringbahn', sub: 'Kollektiv Nord', plays: 2, minutes: 10, rank: 1, in_library: true },
    { key: 'nobody|x', name: 'Ghost Album', sub: 'Nobody Known', plays: 1, minutes: 4, rank: 2, in_library: false },
  ],
  cache: CACHE,
};

const COMPARE = {
  rows: [
    { name: 'history.overview', params: '', built_at: null, version: 2, fresh: true, matches: true, compared: 7, matching: 7,
      fields: [{ field: 'plays', matches: true, jimbodj: 6, traqfreq: 6 }] },
    { name: 'history.wrapped', params: '2026-10', built_at: null, version: 2, fresh: false, matches: false, compared: 1, matching: 0,
      fields: [{ field: 'plays', matches: false, jimbodj: 3, traqfreq: 0 }] },
  ],
  stored: 2, fields: 8, matching_fields: 7, matching: 1, differ: 1, stale: 1, explained: 1, passed: true,
  today: '2026-11-22', timezone: 'America/Denver', not_in_p1: { sound: 'the analysis (LIBRARY, P2)' },
  rules: { fresh: 'the stamp is current', passed: 'every row matches or is stale' }, cache: CACHE,
};

function api(answers: Record<string, unknown>) {
  vi.stubGlobal('fetch', vi.fn(async (url: string) => (url in answers
    ? { ok: true, status: 200, json: async () => answers[url] }
    : { ok: false, status: 503, json: async () => ({}) })));
}
function open(path: string) {
  window.history.replaceState(null, '', path);
  return render(<Shell />);
}

beforeEach(() => { window.scrollTo = vi.fn() as unknown as typeof window.scrollTo; });
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

describe('HISTORY by period (T8)', () => {
  it('routes the T8 pages', () => {
    for (const sub of ['years', 'wrapped', 'top', 'compare'] as const) {
      expect(parseRoute(`/history/${sub}`)).toEqual({ page: 'module', module: 'H', sub });
    }
  });

  it('Years: plays and hours per year, each opening its rows and its wrapped page; on this day', async () => {
    api({ '/api/modules': MODULES, '/api/history/years': DAILY });
    open('/history/years');
    const list = await screen.findByRole('list', { name: 'Every year' });
    const items = within(list).getAllByRole('listitem');
    expect(items[0].textContent).toContain('2026');
    expect(within(items[0]).getByRole('link', { name: '5 plays, show the rows' }).getAttribute('href'))
      .toBe('/history/listens?status=play&year=2026');
    expect(within(items[0]).getByRole('link', { name: '2026, Wrapped' }).getAttribute('href')).toBe('/history/wrapped?period=2026');
    expect(screen.getByText(/2 years, 6 plays and 0 h in all\. The most: 2026, 5 plays\./)).toBeTruthy();
    const otd = screen.getByRole('list', { name: 'On this day in earlier years' });
    expect(within(otd).getByRole('link', { name: '2 plays, show the rows' }).getAttribute('href'))
      .toBe('/history/listens?status=play&period=2026-11-01');
    expect(screen.getByText('Longest: 4 days, ended 4 Nov 2026')).toBeTruthy();
  });

  it('Wrapped: totals, tops and parts open their rows; drawings are lists with a summary (L6)', async () => {
    api({ '/api/modules': MODULES, '/api/history/wrapped?period=2026': WRAPPED });
    open('/history/wrapped?period=2026');
    expect(await screen.findByRole('heading', { name: 'Wrapped 2026' })).toBeTruthy();
    expect(await screen.findByText('0.4 h')).toBeTruthy();
    const albums = screen.getByRole('list', { name: 'Top albums' });
    expect(within(albums).getByRole('link').getAttribute('href'))
      .toBe('/history/listens?status=play&period=2026&album=paperlanterns%7Clowtideradio&name=Low+Tide+Radio');
    const byMonth = screen.getByRole('list', { name: 'By month' });
    expect(within(byMonth).getByRole('link', { name: 'Nov' }).getAttribute('href')).toBe('/history/wrapped?period=2026-11');
    expect(screen.getAllByText('Busiest: Nov, 5 plays.')).toHaveLength(1);
    const hours = screen.getByRole('list', { name: 'Hour of the day' });
    expect(within(hours).getByRole('link').getAttribute('href')).toBe('/history/listens?status=play&period=2026&hour=13');
    const week = screen.getByRole('list', { name: 'Day of the week' });
    expect(within(week).getByRole('link').getAttribute('href')).toBe('/history/listens?status=play&period=2026&weekday=6');
    expect(screen.getByRole('link', { name: 'Earlier' }).getAttribute('href')).toBe('/history/wrapped?period=2025');
    expect(screen.getByText(/Not here yet: styles/)).toBeTruthy();
  });

  it('Top: choices are links with aria-current; a rolling period opens rows by its span', async () => {
    api({ '/api/modules': MODULES, '/api/history/top?period=30d&kind=albums&sort=minutes&page=1': TOP });
    open('/history/top?period=30d&kind=albums&sort=minutes');
    expect(await screen.findByRole('heading', { name: 'Top albums, Last 30 days' })).toBeTruthy();
    const periods = screen.getByRole('navigation', { name: 'Period' });
    expect(within(periods).getByRole('link', { name: 'Last 30 days' }).getAttribute('aria-current')).toBe('page');
    const list = await screen.findByRole('list', { name: 'albums' });
    expect(within(list).getAllByRole('link')[0].getAttribute('href'))
      .toBe('/history/listens?status=play&start=1791230400&end=1793825999&album=kollektivnord%7Cringbahn&name=Ringbahn');
    expect(screen.getByText('Nobody Known · 4 min · not in the library')).toBeTruthy();
  });

  it('Compare: each stored row, a stale difference explained', async () => {
    api({ '/api/modules': MODULES, '/api/history/compare': COMPARE });
    open('/history/compare');
    expect(await screen.findByText('All match')).toBeTruthy();
    expect(screen.getByText(/2 stored rows, 1 match; 7 of 8 fields match\. 1 differ, 1 of them stored before/)).toBeTruthy();
    expect(screen.getByText('Differs, stale')).toBeTruthy();
    expect(screen.getByText('plays: jimbo-dj 3, traqfreq 0')).toBeTruthy();
  });

  it('SETUP shows the gate only when HISTORY is on', async () => {
    api({ '/api/modules': MODULES, '/api/history/compare': COMPARE });
    open('/setup');
    expect(await screen.findByText('All match')).toBeTruthy();
    cleanup();
    api({ '/api/modules': { modules: CORE_ONLY } });
    open('/setup');
    await screen.findAllByText(/./);
    expect(screen.queryByText('Same as jimbo-dj')).toBeNull();
  });

  it('periods: neighbours, spans and row filters', () => {
    expect(neighbours('2026-01')).toEqual({ prev: '2025-12', next: '2026-02', up: '2026' });
    expect(neighbours('2026-03-01').prev).toBe('2026-02-28');
    expect(periodFilter('2026-11', null, null)).toEqual({ period: '2026-11' });
    expect(periodFilter('all', null, null)).toEqual({});
    expect(topHref({ period: '2025', page: 2 })).toBe('/history/top?period=2025&kind=artists&sort=plays&page=2');
    expect(parseFilter('?song=a%7Cb&name=B&hour=13&weekday=6')).toMatchObject({ song: 'a|b', name: 'B', hour: 13, weekday: 6 });
  });
});
