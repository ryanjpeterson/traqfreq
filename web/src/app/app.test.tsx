import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Shell } from '../App';
import { navModules, phoneModules } from './Nav';
import { parseRoute } from './route';
import { formatUtc } from './time';
import { CORE_ONLY, type ModuleSwitch } from './api';

function switches(...on: string[]): ModuleSwitch[] {
  return CORE_ONLY.map((m) => ({ ...m, on: m.core || on.includes(m.id) }));
}

const stored = (value: number) => ({ value, built_at: '2026-11-05T02:01:00Z', source: 'stats.library.stats' });
const SUMMARY = {
  measures: [
    { id: 'tracks', value: 5, rule: 'SELECT COUNT(*) FROM tracks WHERE removed_at IS NULL', jimbodj: stored(5), matches: true },
    { id: 'albums', value: 3, rule: 'SELECT COUNT(DISTINCT album_key) FROM tracks WHERE removed_at IS NULL', jimbodj: stored(4), matches: false },
    { id: 'plays', value: 1200, rule: 'SELECT COUNT(*) FROM listens WHERE counted = 1', jimbodj: null, matches: null },
  ],
  counts: { tracks: 6, listens: 1234 }, missing_tables: ['features'], times: {},
};
const ACTIVITY = {
  last_scan: { at: '2026-11-05T02:00:00Z', source: 'meta.last_sync' },
  jobs: [
    { id: 3, kind: 'history_import', source: 'spotify', at: '2026-11-05T03:05:00Z', rows: 0, added: 0, note: 'file not found' },
    { id: 1, kind: 'history_import', source: 'lastfm', at: '2026-11-05T01:00:00Z', rows: 120, added: 4, note: null },
  ],
  jobs_source: 'history_imports',
};

/** Stub fetch with fixed answers per URL (invented rows; never real data). */
function api(answers: Record<string, unknown>) {
  vi.stubGlobal('fetch', vi.fn(async (url: string) => {
    if (!(url in answers) || answers[url] === 503) return { ok: false, status: 503, json: async () => ({}) };
    return { ok: true, status: 200, json: async () => answers[url] };
  }));
}

function open(path: string) {
  window.history.replaceState(null, '', path);
  return render(<Shell />);
}

const topNav = () => within(screen.getByRole('banner')).getByRole('navigation');
const bottomNav = () => screen.getAllByRole('navigation').find((n) => n.classList.contains('bottombar'))!;
const names = (nav: HTMLElement) => within(nav).getAllByRole('link').map((a) => a.textContent);

beforeEach(() => { window.scrollTo = vi.fn() as unknown as typeof window.scrollTo; });
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

describe('routes', () => {
  it('parses paths', () => {
    expect(parseRoute('/')).toEqual({ page: 'map' });
    expect(parseRoute('/search')).toEqual({ page: 'search' });
    expect(parseRoute('/history/')).toEqual({ page: 'module', module: 'H' });
    expect(parseRoute('/setup')).toEqual({ page: 'module', module: 'S' });
    expect(parseRoute('/nope')).toEqual({ page: 'notFound' });
  });
  it('formats UTC times', () => {
    expect(formatUtc('2026-11-05T02:00:00Z')).toBe('2026-11-05 02:00 UTC');
    expect(formatUtc('soon')).toBe('soon');
  });
});

describe('nav order (L1, L2, L3)', () => {
  it('LIBRARY, switched-on modules in order, SETUP; off modules leave no trace', () => {
    expect(navModules(switches())).toEqual(['L', 'S']);
    expect(navModules(switches('F', 'H', 'M'))).toEqual(['L', 'H', 'M', 'F', 'S']);
  });
  it('phone bar keeps at most two modules (plus LIBRARY, map, SETUP = five)', () => {
    expect(phoneModules(switches('H', 'T', 'D', 'M', 'F'))).toEqual(['L', 'H', 'T', 'S']);
  });
  it('top bar renders LIBRARY, on modules, SETUP and search; nothing for off modules', async () => {
    api({ '/api/modules': { modules: switches('T', 'H') } });
    open('/');
    await within(topNav()).findByRole('link', { name: 'HISTORY' });
    expect(names(topNav())).toEqual(['L1LIBRARY', 'H2HISTORY', 'T3TAGS', 'S0SETUP']);
    const banner = within(screen.getByRole('banner'));
    expect(banner.getByRole('link', { name: 'Search' }).getAttribute('href')).toBe('/search');
    expect(banner.queryByText('MIXES')).toBeNull();
  });
  it('bottom bar holds five at most', async () => {
    api({ '/api/modules': { modules: switches('H', 'T', 'D', 'M', 'F') } });
    open('/');
    await screen.findAllByRole('link', { name: 'FETCH' });
    expect(names(bottomNav())).toEqual(['L1LIBRARY', 'H2HISTORY', 'T3TAGS', 'Map', 'S0SETUP']);
  });
  it('without an answer from /api/modules, only the core modules show', async () => {
    api({});
    open('/');
    await screen.findByText('Map', { selector: 'h1' });
    expect(names(topNav())).toEqual(['L1LIBRARY', 'S0SETUP']);
  });
});

describe('navigation', () => {
  it('nav items route client-side and set aria-current', async () => {
    api({ '/api/modules': { modules: switches('H') }, '/api/legacy/summary': SUMMARY, '/api/legacy/activity': ACTIVITY });
    open('/');
    const user = userEvent.setup();
    await user.click(await within(topNav()).findByRole('link', { name: 'HISTORY' }));
    expect(window.location.pathname).toBe('/history');
    expect(within(topNav()).getByRole('link', { name: 'HISTORY' }).getAttribute('aria-current')).toBe('page');
    expect(screen.getByRole('heading', { level: 2, name: 'HISTORY' })).toBeTruthy();
    expect(document.title).toBe('HISTORY · traqfreq');
    // Empty state points to SETUP (D1).
    await user.click(screen.getByRole('link', { name: 'Open SETUP' }));
    expect(window.location.pathname).toBe('/setup');
    expect(await screen.findByText('Readable')).toBeTruthy();
  });
  it('back goes back', async () => {
    api({ '/api/modules': { modules: switches() } });
    open('/');
    const user = userEvent.setup();
    await user.click(within(screen.getByRole('banner')).getByRole('link', { name: 'Search' }));
    expect(screen.getByRole('heading', { level: 1, name: 'Search' })).toBeTruthy();
    window.history.back();
    await screen.findByRole('heading', { level: 1, name: 'Map' });
  });
  it('an off module has no page (L2)', async () => {
    api({ '/api/modules': { modules: switches() } });
    open('/mixes');
    expect(await screen.findByRole('heading', { name: 'No such page' })).toBeTruthy();
  });
  it('an on module page waits for the switches instead of flashing not-found', async () => {
    api({ '/api/modules': { modules: switches('M') } });
    open('/mixes');
    expect(screen.queryByRole('heading', { name: 'No such page' })).toBeNull();
    expect(await screen.findByRole('heading', { level: 2, name: 'MIXES' })).toBeTruthy();
  });
  it('unknown paths show not-found with a way to the map', async () => {
    api({ '/api/modules': { modules: switches() } });
    open('/somewhere');
    const user = userEvent.setup();
    await user.click(await screen.findByRole('link', { name: 'Go to the map' }));
    expect(window.location.pathname).toBe('/');
  });
});

describe('map home (L6)', () => {
  it('draws every line, has a screen-reader summary and a list view', async () => {
    api({ '/api/modules': { modules: switches('H') } });
    const { container } = open('/');
    await within(topNav()).findByRole('link', { name: 'HISTORY' });
    const drawing = container.querySelector('.map-drawing')!;
    expect(drawing.getAttribute('aria-hidden')).toBe('true');
    expect(drawing.querySelectorAll('.map-line')).toHaveLength(7);
    expect(drawing.querySelectorAll('.map-line.is-off')).toHaveLength(4); // off lines dashed
    expect(screen.getByText('The map shows 7 lines. On: LIBRARY, HISTORY, SETUP. Off: TAGS, DISCOVER, MIXES, FETCH.')).toBeTruthy();
    const list = within(screen.getByRole('region', { name: 'Lines' }));
    expect(list.getAllByRole('listitem')).toHaveLength(7);
    expect(list.getAllByText('On')).toHaveLength(3);
    expect(list.getAllByText('Off')).toHaveLength(4);
    expect(list.getByRole('link', { name: 'Open HISTORY' }).getAttribute('href')).toBe('/history');
    expect(list.queryByRole('link', { name: 'Open TAGS' })).toBeNull();
  });
});

describe('SETUP, read-only', () => {
  it('shows the legacy summary, last scan, jobs and module switches', async () => {
    api({ '/api/modules': { modules: switches('T') }, '/api/legacy/summary': SUMMARY, '/api/legacy/activity': ACTIVITY });
    open('/setup');
    expect(await screen.findByText('Readable')).toBeTruthy();
    const db = within(screen.getByRole('list', { name: 'Legacy database' }));
    expect(db.getByText('1,234 rows')).toBeTruthy();
    expect(screen.getByText('Tables not found: features')).toBeTruthy();
    const counted = within(screen.getByRole('list', { name: 'Counted the way jimbo-dj counts' }));
    expect(counted.getAllByRole('listitem').map((r) => r.querySelector('strong')?.textContent)).toEqual(['Tracks', 'Albums', 'Plays']);
    expect(counted.getByText('Tracks the last Plex sync still saw (removed_at is empty). Same as jimbo-dj\'s stored count.')).toBeTruthy();
    expect(counted.getByText('Distinct album keys of those tracks. jimbo-dj\'s stored count: 4')).toBeTruthy();
    expect(counted.getByText('1,200')).toBeTruthy();
    expect(counted.getByText(/jimbo-dj has no stored count to compare/)).toBeTruthy();
    expect(screen.getByText('Rows per table')).toBeTruthy();
    expect(await screen.findByText('2026-11-05 02:00 UTC')).toBeTruthy();
    const jobs = within(screen.getByRole('list', { name: 'Jobs' }));
    expect(jobs.getByText('Spotify import')).toBeTruthy();
    expect(jobs.getByText('2026-11-05 01:00 UTC · 120 rows read · 4 added')).toBeTruthy();
    const mods = within(screen.getByRole('list', { name: 'Modules' }));
    const rows = mods.getAllByRole('listitem');
    expect(rows.map((r) => r.textContent)).toEqual(
      ['L1LIBRARYOn', 'H2HISTORYOff', 'T3TAGSOn', 'D4DISCOVEROff', 'M5MIXESOff', 'F6FETCHOff', 'S0SETUPOn'],
    );
    expect(rows[1].querySelector('[data-state="off"]')).toBeTruthy();
    expect(rows[2].querySelector('[data-state="ready"]')).toBeTruthy();
  });
  it('says what to do when jimbo-dj\'s database cannot be read', async () => {
    api({ '/api/modules': { modules: switches() }, '/api/legacy/summary': 503, '/api/legacy/activity': 503 });
    open('/setup');
    expect(await screen.findByText(/Set TRAQFREQ_LEGACY_DB/)).toBeTruthy();
    expect(screen.getAllByText('Can\'t read').length).toBeGreaterThan(0);
  });
  it('an older summary without measures still shows the rows', async () => {
    api({ '/api/modules': { modules: switches() }, '/api/legacy/summary': { counts: { tracks: 6 }, missing_tables: [], times: {} },
      '/api/legacy/activity': ACTIVITY });
    open('/setup');
    expect(await screen.findByText('6 rows')).toBeTruthy();
    expect(screen.queryByRole('list', { name: 'Counted the way jimbo-dj counts' })).toBeNull();
  });
  it('empty activity says so', async () => {
    api({ '/api/modules': { modules: switches() }, '/api/legacy/summary': SUMMARY,
      '/api/legacy/activity': { last_scan: null, jobs: [], jobs_source: null } });
    open('/setup');
    expect(await screen.findByText('No scan recorded in jimbo-dj\'s database.')).toBeTruthy();
    expect(screen.getByText('No jobs recorded in jimbo-dj\'s database.')).toBeTruthy();
  });
});
