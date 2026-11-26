import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, within } from '@testing-library/react';
import { Shell } from '../App';
import { parseRoute } from '../app/route';
import { copiesApi, copiesHref, junctionApi, rowsApi, rowsHref, sourceRowsHref, treeQuery } from '../app/playlists';
import ANSWERS from './playlists.answers.json';

// T24: traqfreq's own answers on the fixture (scripts/make_fixture.py SAVED, MIXES, CLUSTERS), generated from its API.
// T25: with the invented Jellyfin and Navidrome snapshots loaded (P3's matches), and the Junction's answers.
const A = ANSWERS as Record<string, unknown>;
const TREE = A._tree as string;
/** A line's card (its conditions), not the Junction's lever of the same name. */
const card = (name: string) => screen.getAllByText(name).map((x) => x.closest('.kit-card')).find(Boolean) as HTMLElement;
const mods = (on: string[]) => ({ modules: ['L', 'H', 'T', 'D', 'M', 'F', 'S'].map((id) => ({ id, on: on.includes(id), core: id === 'L' || id === 'S' })) });

function api(answers: Record<string, unknown>) {
  const f = vi.fn(async (url: string, init?: RequestInit) => {
    if (init?.method && init.method !== 'GET') throw new Error(`${init.method} ${url}: PLAYLISTS only reads`);
    if (!(url in answers)) return { ok: false, status: url.startsWith('/api/playlists') ? 404 : 503, json: async () => ({}) };
    return { ok: true, status: 200, json: async () => answers[url] };
  });
  vi.stubGlobal('fetch', f);
  return f;
}

function open(path: string, answers: Record<string, unknown> = A) {
  const f = api({ '/api/modules': mods(['L', 'S']), ...answers });
  window.history.replaceState(null, '', path);
  render(<Shell />);
  return f;
}

beforeEach(() => { window.scrollTo = vi.fn() as unknown as typeof window.scrollTo; });
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

describe('T24 routes', () => {
  it('parses the list, a playlist by its slug and the rows behind a count', () => {
    expect(parseRoute('/library/playlists')).toEqual({ page: 'module', module: 'L', sub: 'playlists' });
    expect(parseRoute('/library/playlists/night-lines')).toEqual({ page: 'module', module: 'L', sub: 'playlist', ref: 'night-lines' });
    expect(parseRoute('/library/playlists/rows')).toEqual({ page: 'module', module: 'L', sub: 'playlistRows' });
    expect(parseRoute('/library/playlists/%E0%A4%A')).toEqual({ page: 'notFound' });
    expect(rowsHref('night-lines', 'b', 'all.0')).toBe('/library/playlists/rows?ref=night-lines&line=b&path=all.0');
    expect(rowsApi('?ref=night-lines&line=b&path=all.0')).toBe('/api/playlists/night-lines/rows?line=b&limit=200&path=all.0');
  });
});

describe('the saved playlists', () => {
  it('lists every kind with each playlist\'s three switches, read-only', async () => {
    const f = open('/library/playlists');
    const head = within(await screen.findByRole('list', { name: 'Saved playlists' }));
    expect(head.getByText('10 playlists')).toBeTruthy();
    expect(head.getByText('4 playlists')).toBeTruthy();
    const link = screen.getByRole('link', { name: 'Night lines' });
    expect(link.getAttribute('href')).toBe('/library/playlists/night-lines');
    const row = within(link.closest('li') as HTMLElement);
    expect(row.getByText('Plex: On')).toBeTruthy();
    expect(row.getByText('Jellyfin: Off, set from P6')).toBeTruthy();
    expect(row.getByText('Navidrome: Off, set from P6')).toBeTruthy();
    const more = within(screen.getByRole('link', { name: 'More like Westkreuz' }).closest('li') as HTMLElement);
    expect(more.getByText('Plex: On, last push failed')).toBeTruthy();
    expect(screen.getByText(/Stale: no longer made/)).toBeTruthy();
    expect(f.mock.calls.every(([, init]) => !init?.method || init.method === 'GET')).toBe(true);
  });

  it('shows an empty state when jimbo-dj has no saved playlists table', async () => {
    open('/library/playlists', {});
    expect(await screen.findByText("jimbo-dj's database has no saved playlists yet.")).toBeTruthy();
  });
});

describe('a playlist\'s lines', () => {
  it('shows each line with its AND, OR and NOT conditions, every count opening its rows', async () => {
    open('/library/playlists/night-lines');
    expect(await screen.findByRole('heading', { level: 1, name: 'Night lines' })).toBeTruthy();
    expect(screen.getByText(/3 lines meeting in one playlist of 20 tracks\. Between them they match 4 tracks of the library's 5 tracks\./)).toBeTruthy();
    const a = within(card('Line a · Ringbahn, not sad'));
    expect(a.getByRole('link', { name: '1 track, 2010s · not sad' }).getAttribute('href')).toBe('/library/playlists/rows?ref=night-lines&line=a');
    expect(a.getByText('NOT')).toBeTruthy();
    expect(a.getByRole('link', { name: '1 track, sad' }).getAttribute('href')).toBe('/library/playlists/rows?ref=night-lines&line=a&path=not.0');
    const b = within(card('Line b'));
    expect(b.getAllByText('OR')).toHaveLength(2);
    // The line is one OR group, so the line's count and the group's are the same number, each opening its rows.
    expect(b.getAllByRole('link', { name: '2 tracks, (Ada Vey or played in 2025)' }).map((x) => x.getAttribute('href')))
      .toEqual(['/library/playlists/rows?ref=night-lines&line=b', '/library/playlists/rows?ref=night-lines&line=b&path=all.0']);
    expect(b.getByRole('link', { name: '1 track, played in 2025' })).toBeTruthy();
  });

  it('shows the three switches with where each comes from', async () => {
    open('/library/playlists/night-lines');
    const card = within((await screen.findByText('Where it goes')).closest('section') as HTMLElement);
    expect(card.getByText(/Set in jimbo-dj · Last pushed 2026-11-05/)).toBeTruthy();
    expect(card.getAllByText('Off, set from P6')).toHaveLength(2);
  });

  it('says how many tracks have a copy on each server, naming the missing ones (T25)', async () => {
    open('/library/playlists/night-lines');
    const sw = within((await screen.findByText('Where it goes')).closest('section') as HTMLElement);
    expect(sw.getAllByRole('link', { name: '4 of 4 tracks have a copy, tracks with a copy on Plex' })).toHaveLength(1);
    const miss = sw.getByRole('link', { name: '1 track without: path hidden 1, tracks with a copy on Navidrome' });
    expect(miss.getAttribute('href')).toBe('/library/playlists/copies?ref=night-lines&server=navidrome&missing=true');
  });

  it('opens the tracks without a copy, each with its reason', async () => {
    open('/library/playlists/copies?ref=night-lines&server=navidrome&missing=true');
    expect(await screen.findByRole('heading', { level: 1, name: 'Tracks without a copy' })).toBeTruthy();
    expect(screen.getByText('Navidrome · 1 track')).toBeTruthy();
    expect(screen.getByRole('link', { name: 'Coil' })).toBeTruthy();
    expect(screen.getByText(/Navidrome has no copy: The server gives no real path/)).toBeTruthy();
  });

  it('lists the stored tracks in play order, marking one no longer in the library', async () => {
    open('/library/playlists/gone-grey');
    expect(await screen.findByText(/0 tracks still in the library/)).toBeTruthy();
    expect(screen.queryByRole('link', { name: 'Old Signal' })).toBeNull();
  });

  it('opens the rows behind a condition', async () => {
    open('/library/playlists/rows?ref=night-lines&line=b&path=all.0');
    expect(await screen.findByText('Line b · Ada Vey or played in 2025 · 2 tracks')).toBeTruthy();
    expect(screen.getByRole('link', { name: 'Coil' }).getAttribute('href')).toBe('/library/track/105');
  });
});

describe('T25 the Junction', () => {
  it('routes the Junction, its rows and a switch\'s copies', () => {
    expect(parseRoute('/library/junction')).toEqual({ page: 'module', module: 'L', sub: 'junction' });
    expect(parseRoute('/library/junction/rows')).toEqual({ page: 'module', module: 'L', sub: 'junctionRows' });
    expect(parseRoute('/library/playlists/copies')).toEqual({ page: 'module', module: 'L', sub: 'playlistCopies' });
    expect(treeQuery('?b=style:punk~5&x=1&n=10')).toBe('b=style%3Apunk%7E5&n=10');
    expect(junctionApi('?b=style:punk&ref=x')).toBe('/api/junction?b=style%3Apunk');
    expect(sourceRowsHref({ tree: 'b=style:punk' }, 'a', 'got')).toBe('/library/junction/rows?b=style%3Apunk&line=a&which=got');
    expect(sourceRowsHref({ ref: 'night-lines' }, 'a', 'available')).toBe('/library/playlists/rows?ref=night-lines&line=a&which=available');
    expect(rowsApi('?b=style:punk&line=a&which=got')).toBe('/api/junction/rows?b=style%3Apunk&line=a&limit=200&which=got');
    expect(copiesHref('night-lines', 'plex')).toBe('/library/playlists/copies?ref=night-lines&server=plex');
    expect(copiesApi('?ref=night-lines&server=plex&missing=true')).toBe('/api/playlists/night-lines/copies?server=plex&limit=200&missing=true');
  });

  it('shows what the lines pick: numbers with their rows, the drawing\'s summary, read-only levers', async () => {
    open('/library/playlists/night-lines');
    const nums = within(await screen.findByRole('list', { name: 'What the lines pick' }));
    expect(nums.getByRole('link', { name: '4 tracks of 20' }).getAttribute('href')).toBe('/library/playlists/rows?ref=night-lines&line=&which=picked');
    expect(nums.getByRole('link', { name: '4 tracks' }).getAttribute('href')).toBe('/library/playlists/rows?ref=night-lines&line=&which=total');
    expect(nums.getByText('0 songs, 1 artist, 0 styles')).toBeTruthy();
    expect(screen.getByText(/3 lines meet in one playlist of 4 tracks, out of 20 asked for\. Line a · Ringbahn, not sad brings 1 track of its share of 8/)).toBeTruthy();
    const b = within(screen.getByRole('list', { name: 'Numbers for Line b' }));
    expect(b.getByRole('link', { name: '2 tracks, Matches, Line b' }).getAttribute('href')).toBe('/library/playlists/rows?ref=night-lines&line=b');
    expect(b.getByRole('link', { name: '1 track, Got, Line b' }).getAttribute('href')).toBe('/library/playlists/rows?ref=night-lines&line=b&which=got');
    expect(b.getByRole('link', { name: '2 tracks, Could choose from, Line b' }).getAttribute('href')).toBe('/library/playlists/rows?ref=night-lines&line=b&which=available');
    expect(screen.queryAllByRole('slider')).toHaveLength(0); // read-only levers
    expect(screen.getByText('At most per artist')).toBeTruthy();
    expect(screen.getByRole('link', { name: 'Open in the Junction' }).getAttribute('href')).toBe(`/library/junction?${TREE}`);
  });

  it('shows each picked track with the line that brought it in (B3)', async () => {
    open('/library/playlists/night-lines');
    const picked = (await screen.findByText('Picked tracks · 4 tracks')).closest('section') as HTMLElement;
    const rows = within(picked).getAllByRole('link').map((x) => x.textContent);
    expect(rows).toEqual(['Ostkreuz', 'Coil', 'Westkreuz', 'Harbour Lights']);
    expect(within(picked).getAllByText(/Brought in by Line c/, { selector: '*' }).length).toBeGreaterThan(0);
  });

  it('previews any tree in jimbo-dj\'s URL form at /library/junction', async () => {
    const f = open(`/library/junction?${TREE}`);
    expect(await screen.findByRole('heading', { level: 1, name: 'Junction' })).toBeTruthy();
    expect(await screen.findByRole('list', { name: 'What the lines pick' })).toBeTruthy();
    const b = within(screen.getByRole('list', { name: 'Numbers for Line b' }));
    expect(b.getByRole('link', { name: '2 tracks, Matches, Line b' }).getAttribute('href')).toBe(`/library/junction/rows?${TREE}&line=b`);
    expect(f.mock.calls.every(([, init]) => !init?.method || init.method === 'GET')).toBe(true);
  });

  it('opens the pool a line could choose from, most played first', async () => {
    open(`/library/junction/rows?${TREE}&line=b&which=available`);
    expect(await screen.findByRole('heading', { level: 1, name: 'Tracks the line could choose from' })).toBeTruthy();
    expect(screen.getAllByRole('link').filter((x) => x.getAttribute('href')?.startsWith('/library/track/')).map((x) => x.textContent))
      .toEqual(['Ostkreuz', 'Coil']);
    expect(screen.getByRole('link', { name: 'Back to the Junction' }).getAttribute('href')).toBe(`/library/junction?${TREE}`);
  });

  it('explains an empty Junction', async () => {
    open('/library/junction');
    expect(await screen.findByText(/No lines in the address yet/)).toBeTruthy();
  });
});
