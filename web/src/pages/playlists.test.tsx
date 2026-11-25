import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, within } from '@testing-library/react';
import { Shell } from '../App';
import { parseRoute } from '../app/route';
import { rowsApi, rowsHref } from '../app/playlists';
import ANSWERS from './playlists.answers.json';

// T24: traqfreq's own answers on the fixture (scripts/make_fixture.py SAVED, MIXES, CLUSTERS), generated from its API.
const A = ANSWERS as Record<string, unknown>;
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
    const a = within(screen.getByText('Line a · Ringbahn, not sad').closest('section') as HTMLElement);
    expect(a.getByRole('link', { name: '1 track, 2010s · not sad' }).getAttribute('href')).toBe('/library/playlists/rows?ref=night-lines&line=a');
    expect(a.getByText('NOT')).toBeTruthy();
    expect(a.getByRole('link', { name: '1 track, sad' }).getAttribute('href')).toBe('/library/playlists/rows?ref=night-lines&line=a&path=not.0');
    const b = within(screen.getByText('Line b').closest('section') as HTMLElement);
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

  it('lists the stored tracks in play order, marking one no longer in the library', async () => {
    open('/library/playlists/gone-grey');
    expect(await screen.findByText(/0 tracks still in the library/)).toBeTruthy();
    expect(screen.queryByRole('link', { name: 'Old Signal' })).toBeNull();
  });

  it('opens the rows behind a condition', async () => {
    open('/library/playlists/rows?ref=night-lines&line=b&path=all.0');
    expect(await screen.findByText('Ada Vey or played in 2025 · 2 tracks')).toBeTruthy();
    expect(screen.getByRole('link', { name: 'Coil' }).getAttribute('href')).toBe('/library/track/105');
  });
});
