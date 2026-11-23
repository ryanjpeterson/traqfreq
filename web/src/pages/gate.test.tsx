import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Shell } from '../App';
import { CORE_ONLY } from '../app/api';
import { parseRoute } from '../app/route';
import { parseTrackFilter, trackQuery, tracksHref } from '../app/library';
import { filterTitle } from './LibraryRows';
import ANSWERS from './gate.answers.json';

// T12: the API's answers on the fixture (invented rows), generated from traqfreq itself: the P2 gate passes with
// one explained difference (jimbo-dj's stored charts are stale and count FLAC as 3; traqfreq counts 2).
const A = ANSWERS as Record<string, any>;  // eslint-disable-line @typescript-eslint/no-explicit-any
const GATE = '/api/library/compare';
const MODULES = { modules: CORE_ONLY };

function api(answers: Record<string, unknown>) {
  const f = vi.fn(async (url: string) => {
    if (!(url in answers)) return { ok: false, status: 503, json: async () => ({}) };
    return { ok: true, status: 200, json: async () => answers[url] };
  });
  vi.stubGlobal('fetch', f);
  return f;
}

function open(path: string) {
  window.history.replaceState(null, '', path);
  return render(<Shell />);
}

beforeEach(() => { window.scrollTo = vi.fn() as unknown as typeof window.scrollTo; });
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

describe('routes and filters', () => {
  it('routes the comparison to LIBRARY', () => {
    expect(parseRoute('/library/compare')).toEqual({ page: 'module', module: 'L', sub: 'compare' });
    expect(parseRoute('/library/compare/')).toEqual({ page: 'module', module: 'L', sub: 'compare' });
  });
  it('reads and writes a chart bar filter', () => {
    const f = parseTrackFilter('?facet=decade&value=2020s&offset=50');
    expect(f.facet).toBe('decade');
    expect(f.value).toBe('2020s');
    expect(trackQuery(f)).toBe('facet=decade&value=2020s&offset=50');
    expect(parseTrackFilter('?facet=style&value=Techno').facet).toBeUndefined();  // TAGS: not a LIBRARY filter
    expect(parseTrackFilter('?facet=format').facet).toBeUndefined();  // a facet needs its value
    expect(filterTitle(parseTrackFilter('?facet=format&value=FLAC'))).toBe('Tracks · format FLAC');
    expect(filterTitle(parseTrackFilter('?facet=country&value=United%20Kingdom'))).toBe('Tracks · artist from United Kingdom');
    expect(tracksHref('facet=format&value=FLAC')).toBe('/library/tracks?facet=format&value=FLAC');
  });
});

describe('the compare page', () => {
  it('says the gate passed, with the explained difference', async () => {
    api({ '/api/modules': MODULES, [GATE]: A[GATE] });
    open('/library/compare');
    expect(await screen.findByText('All match')).toBeTruthy();
    expect(screen.getByText('2 stored rows, 1 match; 59 of 60 fields match. 1 differ, 1 of them stored before jimbo-dj\'s latest data.')).toBeTruthy();
    expect(screen.getByRole('heading', { name: 'Counts · library.stats' })).toBeTruthy();
    expect(screen.getByRole('heading', { name: 'Charts · library.charts' })).toBeTruthy();
    expect(screen.getByText('Differs, stale')).toBeTruthy();
    expect(screen.getByRole('link', { name: 'Back to LIBRARY' }).getAttribute('href')).toBe('/library');
  });

  it('lists every field, each count opening its rows (W3)', async () => {
    api({ '/api/modules': MODULES, [GATE]: A[GATE] });
    open('/library/compare');
    const counts = await screen.findByRole('list', { name: 'Counts' });
    const items = within(counts).getAllByRole('listitem');
    expect(items).toHaveLength(24);  // 23 compared, folders shown as stored
    const tracks = items.find((li) => within(li).queryByText('tracks'))!;
    expect(within(tracks).getByText('jimbo-dj and traqfreq: 5')).toBeTruthy();
    expect(within(tracks).getByRole('link', { name: 'Show the tracks, tracks' }).getAttribute('href')).toBe('/library/tracks');
    const server = items.find((li) => within(li).queryByText('server'))!;
    expect(within(server).getByText('6 entries, the same in both')).toBeTruthy();
    const sonic = items.find((li) => within(li).queryByText('sonic_analysis.tracks'))!;
    expect(within(sonic).getByRole('link', { name: 'Show the tracks, sonic_analysis.tracks' }).getAttribute('href')).toBe('/library/tracks?sonic=true');
    const folders = items.find((li) => within(li).queryByText('paths.folders'))!;
    expect(within(folders).getByText('Not compared')).toBeTruthy();
  });

  it('shows a chart field\'s bars next to jimbo-dj\'s, each opening its tracks', async () => {
    api({ '/api/modules': MODULES, [GATE]: A[GATE] });
    open('/library/compare');
    const charts = await screen.findByRole('list', { name: 'Charts' });
    const formats = within(charts).getAllByRole('listitem').find((li) => within(li).queryByText('files.formats'))!;
    expect(within(formats).getByText(/^3 bars; first difference: /)).toBeTruthy();
    expect(within(formats).getByText('Differs')).toBeTruthy();
    await userEvent.click(within(formats).getByRole('button', { name: 'Show the bars, files.formats' }));
    const bars = within(formats).getByRole('list', { name: 'Bars of files.formats' });
    const flac = within(bars).getAllByRole('listitem')[0];
    expect(within(flac).getByRole('link', { name: 'FLAC' }).getAttribute('href')).toBe('/library/tracks?facet=format&value=FLAC');
    expect(within(flac).getByText('jimbo-dj 3, traqfreq 2')).toBeTruthy();
    expect(within(flac).getByText('Differs')).toBeTruthy();
    expect(within(bars).getAllByRole('listitem')[1].textContent).toContain('jimbo-dj 2, traqfreq 2');
    await userEvent.click(within(formats).getByRole('button', { name: 'Hide the bars, files.formats' }));
    expect(within(formats).queryByRole('list')).toBeNull();
    const genres = within(charts).getAllByRole('listitem').find((li) => within(li).queryByText('genres'))!;
    expect(within(genres).getByText('Not compared')).toBeTruthy();
  });

  it('gives each chart part its rule and names the time zone', async () => {
    api({ '/api/modules': MODULES, [GATE]: A[GATE] });
    open('/library/compare');
    const rules = await screen.findByRole('list', { name: 'Rules' });
    expect(within(rules).getAllByRole('listitem')).toHaveLength(5);
    expect(screen.getByText('Time charts in America/Denver, the time zone jimbo-dj\'s stored charts name.')).toBeTruthy();
    expect(screen.getByText(/^Not compared in P2: paths.folders/)).toBeTruthy();
  });

  it('says when the gate has not passed', async () => {
    const failing = { ...A[GATE], passed: false, explained: 0 };
    api({ '/api/modules': MODULES, [GATE]: failing });
    open('/library/compare');
    expect(await screen.findByText('Some differ')).toBeTruthy();
  });

  it('says when it cannot compare', async () => {
    api({ '/api/modules': MODULES });
    open('/library/compare');
    expect(await screen.findByText('Can\'t compare with jimbo-dj. Open SETUP to check its database.')).toBeTruthy();
  });
});

describe('the gate card', () => {
  it('is on LIBRARY, opening the comparison', async () => {
    api({ '/api/modules': MODULES, [GATE]: A[GATE], '/api/library/stats': A['/api/library/stats'] });
    open('/library');
    const card = (await screen.findByText('LIBRARY same as jimbo-dj')).closest('.kit-card') as HTMLElement;
    expect(await within(card).findByText('All match')).toBeTruthy();
    expect(within(card).getByRole('link', { name: 'Show every number' }).getAttribute('href')).toBe('/library/compare');
  });

  it('is on SETUP, with HISTORY off too (LIBRARY is always on)', async () => {
    api({ '/api/modules': MODULES, [GATE]: A[GATE] });
    open('/setup');
    const card = (await screen.findByText('LIBRARY same as jimbo-dj')).closest('.kit-card') as HTMLElement;
    expect(await within(card).findByText('All match')).toBeTruthy();
    expect(screen.queryByText('Same as jimbo-dj')).toBeNull();  // HISTORY's gate only when HISTORY is on
  });
});

describe('a chart bar\'s rows', () => {
  it('lists the tracks behind one bar with jimbo-dj\'s rule', async () => {
    const url = '/api/library/tracks?facet=format&value=FLAC';
    api({ '/api/modules': MODULES, [url]: A[url] });
    open('/library/tracks?facet=format&value=FLAC');
    expect(await screen.findByRole('heading', { name: 'Tracks · format FLAC' })).toBeTruthy();
    expect(await screen.findByText(/format is FLAC \(jimbo-dj's chart rule/)).toBeTruthy();
  });
});
