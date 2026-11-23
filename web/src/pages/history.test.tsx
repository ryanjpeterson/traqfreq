import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Shell } from '../App';
import { CORE_ONLY } from '../app/api';
import { parseRoute } from '../app/route';
import { count, rowsHref } from '../app/history';
import { parseFilter } from './HistoryRows';

// Invented rows, shaped like the fixture's answers (never real data).
const OVERVIEW = {
  plays: 6, listens: 9, not_plays: { too_short: 1, repeat: 1, duplicate: 1 }, adds_up: true,
  matched: { plays: 5, pct: 83.3 }, songs: { heard: 6, matched: 5 },
  sources: [
    { source: 'lastfm', name: 'Last.fm', listens: 3, play: 3, too_short: 0, repeat: 0, duplicate: 0, duplicate_of: {},
      first: '2026-01-01T05:30:00Z', last: '2026-11-04T19:05:00Z' },
    { source: 'plex', name: 'Plex', listens: 2, play: 1, too_short: 0, repeat: 0, duplicate: 1, duplicate_of: { lastfm: 1 },
      first: '2026-11-01T20:16:00Z', last: '2026-11-01T20:21:00Z' },
  ],
  years: [{ year: 2025, plays: 1, by_source: { lastfm: 1 } }, { year: 2026, plays: 5, by_source: { lastfm: 2, plex: 1 } }],
  top_artists: [{ name: 'Kollektiv Nord', key: 'kollektivnord', plays: 2 }, { name: 'The Paper Lanterns', key: 'paperlanterns', plays: 2 },
    { name: 'Ada Vey', key: 'adavey', plays: 1 }],
  artists_heard: 4, timezone: 'America/Denver', rules: {},
  jimbodj: { plays: 6, built_at: null, source: 'stats.history.overview', matches: true, top_artists_match: true },
  cache: { built_at: 1793847960, seconds: 0.01, hit: true, key: 'v1' },
};

function heatmap(year: number | null) {
  const first = year == null ? '2025-11-17' : `${year}-01-01`;
  const days = year == null ? 371 : 365;
  const start = Date.parse(`${first}T00:00:00Z`);
  const cells = Array.from({ length: days }, (_, i) => {
    const date = new Date(start + i * 86400000).toISOString().slice(0, 10);
    const plays = date === '2026-11-01' ? 2 : ['2025-12-31', '2026-11-02'].includes(date) ? 1 : 0;
    return { date, plays, level: plays === 2 ? 4 : plays };
  });
  return {
    year, first, last: cells[cells.length - 1].date, timezone: 'America/Denver', plays: 4, days, days_played: 3,
    busiest: { date: '2026-11-01', plays: 2 },
    levels: [{ level: 0, min: 0, max: 0 }, { level: 1, min: 1, max: 1 }, { level: 2, min: 2, max: 1 }, { level: 3, min: 2, max: 1 },
      { level: 4, min: 2, max: 2 }],
    cells,
    months: [{ month: '2026-10', plays: 0, days: 31, days_played: 0, busiest: null },
      { month: '2026-11', plays: 3, days: 22, days_played: 2, busiest: { date: '2026-11-01', plays: 2 } }],
    years: [2025, 2026], rules: {},
  };
}

const LISTENS = {
  status: 'duplicate', source: 'plex', year: null, period: null, artist: null, matched: null, timezone: 'America/Denver',
  total: 1, limit: 50, offset: 0, rule: 'listens WHERE counted = 0 AND dup_of IS NOT NULL AND source = ?', params: ['plex'],
  rows: [{ id: 2, source: 'plex', started_at: '2026-11-01T20:16:00Z', ms_played: 312000, artist: 'Kollektiv Nord',
    title: 'Westkreuz', album: 'Ringbahn', dup_of: 'lastfm', rating_key: 101 }],
};

function api(answers: Record<string, unknown>) {
  const f = vi.fn(async (url: string) => {
    if (answers[url] === 404) return { ok: false, status: 404, json: async () => ({}) };
    if (!(url in answers)) return { ok: false, status: 503, json: async () => ({}) };
    return { ok: true, status: 200, json: async () => answers[url] };
  });
  vi.stubGlobal('fetch', f);
  return f;
}

const MODULES = { modules: CORE_ONLY.map((m) => ({ ...m, on: m.core || m.id === 'H' })) };

function open(path: string) {
  window.history.replaceState(null, '', path);
  return render(<Shell />);
}

beforeEach(() => { window.scrollTo = vi.fn() as unknown as typeof window.scrollTo; });
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

describe('HISTORY overview', () => {
  const answers = {
    '/api/modules': MODULES, '/api/history/overview': OVERVIEW,
    '/api/history/heatmap': heatmap(null), '/api/history/heatmap?year=2025': heatmap(2025),
  };

  it('shows the plays headline with its rule and rows (W3)', async () => {
    api(answers);
    open('/history');
    expect(await screen.findByText('6 plays', { selector: '.hist-big' })).toBeTruthy();
    expect(screen.getByText(/counted = 1.*Same as jimbo-dj's stored count\./)).toBeTruthy();
    expect(screen.getByRole('link', { name: 'Show the plays' }).getAttribute('href')).toBe('/history/listens?status=play');
  });

  it('counts every listen once and links each bucket', async () => {
    api(answers);
    open('/history');
    const once = await screen.findByRole('list', { name: 'Every listen, counted once' });
    expect(within(once).getByText('9 listens')).toBeTruthy();
    const hrefs = within(once).getAllByRole('link').map((a) => a.getAttribute('href'));
    expect(hrefs).toEqual(['/history/listens?status=play', '/history/listens?status=too_short',
      '/history/listens?status=repeat', '/history/listens?status=duplicate']);
    expect(screen.getByText(/Adds up/)).toBeTruthy();
    expect(screen.getByText('83.3 % of plays')).toBeTruthy();
    const inLib = screen.getByRole('list', { name: 'In the library' });
    expect(within(inLib).getByRole('link', { name: '1 play, show the rows' }).getAttribute('href')).toContain('matched=false');
  });

  it('draws a year of days with a summary, a legend and a list view (L6)', async () => {
    api(answers);
    open('/history');
    await screen.findByText(/Plays per day, 17 Nov 2025 to 22 Nov 2026: 4 plays on 3 of 371 days\. Busiest day 1 Nov 2026, 2 plays\./);
    const drawing = document.querySelector('.heat')!;
    expect(drawing.closest('[aria-hidden="true"]')).toBeTruthy();
    const cells = drawing.querySelectorAll('.heat-cell');
    expect(cells).toHaveLength(371);
    expect(drawing.querySelectorAll('.heat-cell[data-level="4"]')).toHaveLength(1);
    expect(screen.getByText('No plays')).toBeTruthy();
    expect(screen.getByText('2 plays a day')).toBeTruthy();
    const months = screen.getByRole('list', { name: 'By month' });
    expect(within(months).getByText('November 2026')).toBeTruthy();
    expect(within(months).getByRole('link', { name: '3 plays, show the rows' }).getAttribute('href'))
      .toBe('/history/listens?status=play&period=2026-11');
  });

  it('steps the heatmap to an earlier year and back', async () => {
    api(answers);
    open('/history');
    const user = userEvent.setup();
    await user.click(await screen.findByRole('button', { name: 'Earlier year' }));
    expect(await screen.findByRole('heading', { name: '2025' })).toBeTruthy();
    expect(document.querySelectorAll('.heat .heat-cell')).toHaveLength(365);
    await user.click(screen.getByRole('button', { name: 'Last 53 weeks' }));
    expect(await screen.findByRole('heading', { name: 'Last 53 weeks' })).toBeTruthy();
  });

  it('lists top artists under one name each, with their rows', async () => {
    api(answers);
    open('/history');
    const top = (await screen.findByText('Kollektiv Nord')).closest('ol')!;
    expect(within(top).getAllByRole('listitem').map((li) => li.querySelector('strong')!.textContent))
      .toEqual(['Kollektiv Nord', 'The Paper Lanterns', 'Ada Vey']);
    expect(within(top).getAllByRole('link')[1].getAttribute('href')).toBe('/history/listens?status=play&artist=paperlanterns&name=The+Paper+Lanterns');
    expect(screen.getByText(/4 artists heard\. Same as jimbo-dj's stored top artists\./)).toBeTruthy();
  });

  it('shows sources with duplicates of whom, and years', async () => {
    api(answers);
    open('/history');
    const plex = await screen.findByRole('list', { name: 'Plex' });
    expect(within(plex).getByText('of Last.fm 1')).toBeTruthy();
    expect(within(plex).getAllByRole('link').at(-1)!.getAttribute('href')).toBe('/history/listens?status=duplicate&source=plex');
    const years = screen.getByRole('list', { name: 'Years' });
    expect(within(years).getByRole('link', { name: '5 plays, show the rows' }).getAttribute('href')).toBe('/history/listens?status=play&year=2026');
    expect(screen.getByText('Plays per year in America/Denver, jimbo-dj\'s listening time zone.')).toBeTruthy();
  });

  it('a database without listens gets the empty state (D1)', async () => {
    api({ '/api/modules': MODULES, '/api/history/overview': 404 });
    open('/history');
    expect(await screen.findByRole('link', { name: 'Open SETUP' })).toBeTruthy();
  });

  it('a failed read says so with a shape and a word (C5)', async () => {
    api({ '/api/modules': MODULES });
    open('/history');
    expect(await screen.findByText("Can't read")).toBeTruthy();
  });
});

describe('HISTORY rows', () => {
  it('routes /history/listens to the rows page', () => {
    expect(parseRoute('/history/listens')).toEqual({ page: 'module', module: 'H', sub: 'listens' });
    expect(parseRoute('/history/listens?status=play')).toEqual({ page: 'module', module: 'H', sub: 'listens' });
  });

  it('builds and reads the filters', () => {
    const href = rowsHref({ status: 'repeat', source: 'spotify', year: 2026, matched: false, offset: 0 });
    expect(href).toBe('/history/listens?status=repeat&source=spotify&year=2026&matched=false');
    expect(parseFilter(href.split('?')[1])).toEqual({ status: 'repeat', source: 'spotify', year: 2026, period: undefined,
      artist: undefined, matched: false, offset: undefined, name: undefined });
    expect(parseFilter('status=bogus').status).toBe('play');
    expect(count(1, 'play')).toBe('1 play');
    expect(count(1234, 'listen')).toBe('1,234 listens');
  });

  it('shows the rows with their rule and why each is there', async () => {
    const f = api({ '/api/modules': MODULES, '/api/history/listens?status=duplicate&source=plex': LISTENS });
    open('/history/listens?status=duplicate&source=plex');
    expect(await screen.findByRole('heading', { name: 'Duplicates · Plex' })).toBeTruthy();
    expect(await screen.findByText('1 listen in all, newest first. Showing 1 to 1.')).toBeTruthy();
    expect(screen.getByText(/^Rule: listens WHERE .* \[plex\]$/)).toBeTruthy();
    expect(screen.getByText('Westkreuz')).toBeTruthy();
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: "Why it's here" }));
    expect(screen.getByText('Plex · 2026-11-01 13:16 America/Denver · 5 min 12 s played · library track 101 · duplicate of Last.fm'))
      .toBeTruthy();
    expect(f).toHaveBeenCalledWith('/api/history/listens?status=duplicate&source=plex');
    await user.click(screen.getByRole('link', { name: 'Back to HISTORY' }));
    expect(window.location.pathname).toBe('/history');
  });

  it('pages through the rows', async () => {
    const page = { ...LISTENS, total: 120, rows: Array.from({ length: 50 }, (_, i) => ({ ...LISTENS.rows[0], id: 100 + i })) };
    api({ '/api/modules': MODULES, '/api/history/listens?status=play': { ...page, status: 'play' },
      '/api/history/listens?status=play&offset=50': { ...page, status: 'play', offset: 50 } });
    open('/history/listens?status=play');
    const user = userEvent.setup();
    expect(await screen.findByText('120 listens in all, newest first. Showing 1 to 50.')).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Newer' })).toHaveProperty('disabled', true);
    await user.click(screen.getByRole('link', { name: 'Older' }));
    expect(window.location.search).toBe('?status=play&offset=50');
    expect(await screen.findByText('120 listens in all, newest first. Showing 51 to 100.')).toBeTruthy();
  });

  it('is not there when HISTORY is off (L2)', async () => {
    api({ '/api/modules': { modules: CORE_ONLY } });
    open('/history/listens?status=play');
    expect(await screen.findByRole('heading', { name: 'No such page' })).toBeTruthy();
  });
});

// T7, invented rows shaped like the --checks fixture's answers.
const COUNTED = {
  gaps: {
    repeats: 1, duplicates: 3, not_found: 1, rules: {},
    pairs: [
      { source: 'spotify', of: 'spotify', kind: 'repeat', listens: 1, windows: [30], not_found: 0, beyond: 0,
        buckets: [{ min: 0, max: 10, listens: 0 }, { min: 11, max: 30, listens: 1 }, { min: 31, max: 60, listens: 0 },
          { min: 61, max: 120, listens: 0 }, { min: 121, max: 300, listens: 0 }, { min: 301, max: 900, listens: 0 },
          { min: 901, max: 3600, listens: 0 }] },
      { source: 'plex', of: 'lastfm', kind: 'duplicate', listens: 2, windows: [900], not_found: 1, beyond: 0,
        buckets: [{ min: 0, max: 10, listens: 0 }, { min: 11, max: 30, listens: 0 }, { min: 31, max: 60, listens: 1 },
          { min: 61, max: 120, listens: 0 }, { min: 121, max: 300, listens: 0 }, { min: 301, max: 900, listens: 0 },
          { min: 901, max: 3600, listens: 0 }] },
      { source: 'applemusic', of: 'lastfm', kind: 'duplicate', listens: 1, windows: [300, 3600], not_found: 0, beyond: 0,
        buckets: [{ min: 0, max: 10, listens: 0 }, { min: 11, max: 30, listens: 0 }, { min: 31, max: 60, listens: 0 },
          { min: 61, max: 120, listens: 0 }, { min: 121, max: 300, listens: 0 }, { min: 301, max: 900, listens: 0 },
          { min: 901, max: 3600, listens: 1 }] },
    ],
  },
  checks: {
    plays_checked: 33,
    burst: { findings: 1, plays: 3, in_bursts: 4, rule: '3 or more plays in a row', newest: [
      { start: 1791633600, end: 1791633640, first: '2026-10-10T12:00:00Z', last: '2026-10-10T12:00:40Z', plays: 4, songs: 4,
        sources: { lastfm: 4 }, artist: 'Static Choir', title: 'Signal 1', held: 3 }] },
    loop: { findings: 0, plays: 0, newest: [], rule: 'the same song 10 or more plays in a row' },
    rhythm: { findings: 1, plays: 12, rule: '10 or more plays in a row', newest: [
      { start: 1791774000, end: 1791775985, first: '2026-10-12T03:00:00Z', last: '2026-10-12T03:33:05Z', plays: 12, songs: 4,
        sources: { plex: 12 }, artist: 'Metronome Club', title: 'Tick 1', gap_s: 180 }] },
  },
  timezone: 'America/Denver',
  cache: { built_at: 1793847960, seconds: 0.01, hit: true, key: 'v1' },
};

describe('HISTORY counted once (T7)', () => {
  it('routes /history/counted and links it from the overview', async () => {
    expect(parseRoute('/history/counted')).toEqual({ page: 'module', module: 'H', sub: 'counted' });
    api({ '/api/modules': MODULES, '/api/history/overview': OVERVIEW, '/api/history/heatmap': heatmap(null),
      '/api/history/counted': COUNTED });
    open('/history');
    const user = userEvent.setup();
    await user.click(await screen.findByRole('link', { name: "Why each one isn't a play" }));
    expect(window.location.pathname).toBe('/history/counted');
    expect(await screen.findByText('Repeats: 1 listen. Duplicates: 3 listens. No listen in the window: 1 listen.')).toBeTruthy();
  });

  it('lists each gap bucket with its rows, inside the window only', async () => {
    api({ '/api/modules': MODULES, '/api/history/counted': COUNTED });
    open('/history/counted');
    const plex = await screen.findByRole('list', { name: 'Plex, duplicates of Last.fm' });
    // 15 min window: buckets up to 15 min, then "no listen in the window".
    expect(within(plex).getAllByRole('listitem')).toHaveLength(7);
    expect(within(plex).getByText('Over 30 s, up to 1 min')).toBeTruthy();
    const hrefs = within(plex).getAllByRole('link').map((a) => a.getAttribute('href'));
    expect(hrefs).toEqual(['/history/listens?status=duplicate&source=plex&of=lastfm&gap=31-60',
      '/history/listens?status=duplicate&source=plex&of=lastfm&gap=none']);
    const rep = screen.getByRole('list', { name: 'Spotify, repeats of itself' });
    expect(within(rep).getAllByRole('listitem')).toHaveLength(3);  // up to 10 s, up to 30 s, none
    expect(screen.getByText("1 listen. Window 5 min, or 1 h for Apple Music's daily summary.")).toBeTruthy();
  });

  it('reports the checks without changing a count', async () => {
    api({ '/api/modules': MODULES, '/api/history/counted': COUNTED });
    open('/history/counted');
    expect(await screen.findByText('1 finding, 3 plays held')).toBeTruthy();
    expect(screen.getAllByText('Report only')).toHaveLength(3);
    expect(screen.getByText('None found.')).toBeTruthy();
    const burst = screen.getByRole('list', { name: 'Bursts' });
    expect(within(burst).getByText('2026-10-10 06:00 America/Denver, 4 plays, 4 songs')).toBeTruthy();
    expect(within(burst).getByRole('link').getAttribute('href'))
      .toBe('/history/listens?status=play&start=1791633600&end=1791633640');
    expect(screen.getByText(/every 3 min · Plex 12/)).toBeTruthy();
  });

  it('rows of a gap say which play each duplicates and how far apart', async () => {
    const url = '/api/history/listens?status=duplicate&source=plex&of=lastfm&gap=31-60';
    api({ '/api/modules': MODULES, [url]: { ...LISTENS, of: 'lastfm', gap: '31-60', rows: [{ ...LISTENS.rows[0],
      of: { id: 1, source: 'lastfm', started_at: '2026-11-01T20:15:00Z', play: true, gap_s: 60, window_s: 900 } }] } });
    open('/history/listens?status=duplicate&source=plex&of=lastfm&gap=31-60');
    expect(await screen.findByRole('heading', { name: 'Duplicates · Plex · of Last.fm · 31 s to 1 min apart' })).toBeTruthy();
    const user = userEvent.setup();
    await user.click(await screen.findByRole('button', { name: "Why it's here" }));
    expect(screen.getByText(/duplicates the Last\.fm play at 2026-11-01 13:15 America\/Denver, 1 min apart \(window 15 min\)$/))
      .toBeTruthy();
    expect(parseFilter('?status=repeat&gap=bad&start=1&end=2')).toMatchObject({ status: 'repeat', gap: undefined, start: 1, end: 2 });
  });
});
