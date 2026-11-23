import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Shell } from '../App';
import { CORE_ONLY } from '../app/api';
import { parseRoute } from '../app/route';
import { listHref, parseListQuery, playsHref } from '../app/entities';
import { pageTrackWhy } from './LibraryEntities';
import ANSWERS from './entities.answers.json';

// The API's answers on the fixture (invented rows), generated from traqfreq itself.
const A = ANSWERS as Record<string, any>;  // eslint-disable-line @typescript-eslint/no-explicit-any
const MODULES = { modules: CORE_ONLY };

function api(answers: Record<string, unknown>) {
  const f = vi.fn(async (url: string) => {
    if (answers[url] === 404) return { ok: false, status: 404, json: async () => ({}) };
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

describe('routes', () => {
  it('routes the lists, the pages and the listens to LIBRARY', () => {
    expect(parseRoute('/library/albums')).toEqual({ page: 'module', module: 'L', sub: 'albums' });
    expect(parseRoute('/library/artists?sort=name')).toEqual({ page: 'module', module: 'L', sub: 'artists' });
    expect(parseRoute('/library/album/202')).toEqual({ page: 'module', module: 'L', sub: 'album', key: 202 });
    expect(parseRoute('/library/artist/302/')).toEqual({ page: 'module', module: 'L', sub: 'artist', key: 302 });
    expect(parseRoute('/library/track/101')).toEqual({ page: 'module', module: 'L', sub: 'track', key: 101 });
    expect(parseRoute('/library/plays?album=202')).toEqual({ page: 'module', module: 'L', sub: 'plays' });
    expect(parseRoute('/library/track/abc')).toEqual({ page: 'notFound' });
  });
  it('writes list and listens addresses', () => {
    expect(listHref('albums')).toBe('/library/albums');
    expect(listHref('artists', 'name', 50)).toBe('/library/artists?sort=name&offset=50');
    expect(parseListQuery('?sort=year&offset=x')).toEqual({ sort: 'year', offset: 0 });
    expect(parseListQuery('?sort=colour')).toEqual({ sort: 'plays', offset: 0 });
    expect(playsHref('album=202', { source: 'plex', offset: 0 })).toBe('/library/plays?album=202&source=plex');
  });
});

describe('album and artist lists', () => {
  it('lists albums with tracks and plays, each opening its rows and its page (W3)', async () => {
    api({ '/api/modules': MODULES, '/api/library/albums?sort=plays': A['/api/library/albums?sort=plays'] });
    open('/library/albums');
    const list = await screen.findByRole('list', { name: 'Albums' });
    const items = within(list).getAllByRole('listitem');
    expect(items).toHaveLength(3);
    expect(within(items[0]).getByRole('link', { name: 'Ringbahn' }).getAttribute('href')).toBe('/library/album/201');
    expect(within(items[0]).getByRole('link', { name: '2 tracks, show the tracks' }).getAttribute('href')).toBe('/library/tracks?album_key=201');
    expect(within(items[0]).getByRole('link', { name: '4 plays, show the tracks' }).getAttribute('href'))
      .toBe('/library/tracks?album_key=201&sort=plex_plays');
    expect(items[0].textContent).toContain('Kollektiv Nord · 2019 · added 1 Mar 2025');
    expect(screen.getByText('3 albums in all, most plays first. Showing 1 to 3.')).toBeTruthy();
    expect(screen.getByRole('link', { name: 'Most plays' }).getAttribute('aria-current')).toBe('page');
    expect(screen.getByRole('link', { name: 'By name' }).getAttribute('href')).toBe('/library/albums?sort=name');
    const rules = screen.getByRole('list', { name: 'Rules' });
    expect(rules.textContent).toContain('SUM(plays_of) over its live tracks');
    expect(rules.textContent).toContain('plays, most first');
  });

  it('sorts artists by name and opens an artist page on click, without a page load', async () => {
    const f = api({
      '/api/modules': MODULES, '/api/library/artists?sort=name': A['/api/library/artists?sort=name'],
      '/api/library/artist/302': A['/api/library/artist/302'],
    });
    open('/library/artists?sort=name');
    const list = await screen.findByRole('list', { name: 'Artists' });
    expect(within(list).getAllByRole('listitem').map((li) => li.querySelector('.lib-name a')!.textContent))
      .toEqual(['Ada Vey', 'Kollektiv Nord', 'The Paper Lanterns']);
    expect(screen.getByRole('link', { name: 'By name' }).getAttribute('aria-current')).toBe('page');
    await userEvent.click(within(list).getByRole('link', { name: 'The Paper Lanterns' }));
    expect(window.location.pathname).toBe('/library/artist/302');
    expect(await screen.findByRole('heading', { name: 'The Paper Lanterns' })).toBeTruthy();
    expect(f).toHaveBeenCalledWith('/api/library/artist/302');
  });
});

describe('album page', () => {
  const answers = { '/api/modules': MODULES, '/api/library/album/202': A['/api/library/album/202'] };
  it('lists tracks in disc and track order, each title opening its track page', async () => {
    api(answers);
    open('/library/album/202');
    expect(await screen.findByRole('heading', { name: 'Low Tide Radio' })).toBeTruthy();
    const rows = document.querySelectorAll('.hist-rows .kit-station');
    expect([...rows].map((r) => r.querySelector('.kit-station-title')!.textContent)).toEqual(['Static Gulls', 'Harbour Lights']);
    expect(rows[0].textContent).toContain('disc 1');
    expect(rows[1].textContent).toContain('disc 2');
    expect(screen.getByRole('link', { name: 'Harbour Lights' }).getAttribute('href')).toBe('/library/track/103');
    expect(rows[1].textContent).toContain('5B');
    expect(screen.getByRole('link', { name: 'The Paper Lanterns' }).getAttribute('href')).toBe('/library/artist/302');
  });
  it("gives jimbo-dj's year with its rule, Plex's year beside it, and MusicBrainz as cached", async () => {
    api(answers);
    open('/library/album/202');
    const facts = await screen.findByRole('list', { name: 'The album' });
    expect(within(facts).getByText('2020')).toBeTruthy();
    expect(within(facts).getByText('2021')).toBeTruthy();
    expect(facts.textContent).toContain("MusicBrainz's first release year");
    expect(within(facts).getByRole('link', { name: '3 plays, show the tracks' })).toBeTruthy();
    expect(within(facts).getByText('8 min')).toBeTruthy();
    const mb = screen.getByRole('list', { name: 'MusicBrainz' });
    expect(within(mb).getByText('1 Oct 2020')).toBeTruthy();
    expect(screen.getByText(/album art \(jimbo-dj fetches it from Plex\)/)).toBeTruthy();
  });
  it('shows its listens by source and year as lists with a summary (L6), each opening the listens', async () => {
    api(answers);
    open('/library/album/202');
    const card = (await screen.findByRole('list', { name: 'Listens' })).closest('section')!;
    expect(within(card).getByRole('link', { name: '2 plays, show the listens' }).getAttribute('href')).toBe('/library/plays?album=202');
    expect(within(card).getByText('2 sources; most from Plex, 1 play.')).toBeTruthy();
    const sources = within(card).getByRole('list', { name: 'By source' });
    expect(sources.querySelectorAll('.lib-bar[aria-hidden="true"]')).toHaveLength(2);
    expect(within(sources).getAllByRole('link')[1].getAttribute('href')).toBe('/library/plays?album=202&source=spotify');
    expect(within(card).getByText('1 year; most in 2026, 2 plays.')).toBeTruthy();
    expect(within(card).getByText('first 1 Nov 2026, last 2 Nov 2026')).toBeTruthy();  // in America/Denver
  });
  it('says when there is no such album', async () => {
    api({ '/api/modules': MODULES, '/api/library/album/204': 404 });
    open('/library/album/204');
    expect(await screen.findByText(/No live album has this key/)).toBeTruthy();
  });
});

describe('artist page', () => {
  it('shows tracks, plays, albums and top songs, each with its rule', async () => {
    api({ '/api/modules': MODULES, '/api/library/artist/302': A['/api/library/artist/302'] });
    open('/library/artist/302');
    const facts = await screen.findByRole('list', { name: 'The artist' });
    expect(within(facts).getByRole('link', { name: '2 tracks, show the tracks' }).getAttribute('href'))
      .toBe('/library/tracks?artist_key=302&name=The+Paper+Lanterns');
    expect(within(facts).getByRole('link', { name: '3 plays, show the tracks' })).toBeTruthy();
    const albums = screen.getByRole('list', { name: 'Albums' });
    expect(within(albums).getByRole('link', { name: 'Low Tide Radio' }).getAttribute('href')).toBe('/library/album/202');
    expect(screen.getByText('1 album of its own, and on 0 of other people\'s.')).toBeTruthy();
    const top = [...document.querySelectorAll('.hist-rows .kit-station-title')].map((x) => x.textContent);
    expect(top).toEqual(['Static Gulls', 'Harbour Lights']);
    expect(screen.getByText(/every copy's plays_of added up/)).toBeTruthy();
    expect(screen.getByRole('link', { name: '2 plays, show the listens' }).getAttribute('href')).toBe('/library/plays?artist=302');
  });
});

describe('track page', () => {
  const answers = { '/api/modules': MODULES, '/api/library/track/101': A['/api/library/track/101'] };
  it('shows plays_of with Plex and history beside it, file facts and analysis', async () => {
    api(answers);
    open('/library/track/101');
    expect(await screen.findByRole('heading', { name: 'Westkreuz' })).toBeTruthy();
    expect(screen.getByText('3 plays', { selector: '.hist-big' })).toBeTruthy();
    const plays = screen.getByRole('list', { name: 'Plays' });
    expect(within(plays).getByText('3 plays')).toBeTruthy();  // Plex
    expect(within(plays).getAllByRole('link', { name: '1 play, show the listens' })[0].getAttribute('href')).toBe('/library/plays?track=101');
    const file = screen.getByRole('list', { name: 'File' });
    expect(within(file).getByText('1,011 kbps')).toBeTruthy();
    expect(within(file).getByText('39.4 MB')).toBeTruthy();
    expect(within(file).getByText('/srv/music/Kollektiv Nord/Ringbahn/01 Westkreuz.flac')).toBeTruthy();
    expect(screen.getByText('Analysed at version 2, the current one.')).toBeTruthy();
    const an = screen.getByRole('list', { name: "Analysis (jimbo-dj's analyzer)" });
    expect(within(an).getByText('A minor')).toBeTruthy();
    expect(within(an).getByText('-7.1 LUFS')).toBeTruthy();
    expect(within(an).getByText('party, aggressive, happy')).toBeTruthy();
    expect(screen.queryByText('Other copies of this song')).toBeNull();
    expect(screen.getByRole('link', { name: 'Ringbahn' }).getAttribute('href')).toBe('/library/album/201');
  });
  it("lists the song's other copies, and says a removed track is removed", async () => {
    const t = A['/api/library/track/101'];
    const copy = {
      ...t, kind: 'live', live: false, track: { ...t.track, rating_key: 107, title: 'Westkreuz (Live)', removed_at: '2026-11-05T02:00:00Z' },
      song: { ...t.song, copies: 2, history: { ...t.history, plays: 2 },
        versions: [{ rating_key: 101, title: 'Westkreuz', album: 'Ringbahn', album_key: 201, artist: 'Kollektiv Nord', year: 2019, kind: null, plays: 3 }] },
      rows: { plays: 'track=107', song: 'track=107&song=true' },
    };
    api({ '/api/modules': MODULES, '/api/library/track/107': copy });
    open('/library/track/107');
    const song = await screen.findByRole('list', { name: 'Other copies of this song' });
    expect(within(song).getByRole('link', { name: 'Westkreuz' }).getAttribute('href')).toBe('/library/track/101');
    expect(song.textContent).toContain('Ringbahn · 2019 · original');
    expect(within(song).getByRole('link', { name: '2 plays, show the listens' }).getAttribute('href')).toBe('/library/plays?track=107&song=true');
    expect(screen.getByText('Track · live')).toBeTruthy();
    expect(screen.getByText(/Removed 5 Nov 2026/)).toBeTruthy();
  });
});

describe('listens page', () => {
  it("lists an artist's listens with the rule, sources to pick from and track links", async () => {
    api({ '/api/modules': MODULES, '/api/library/plays?artist=302': A['/api/library/plays?artist=302'] });
    open('/library/plays?artist=302');
    expect(await screen.findByRole('heading', { name: 'Listens of The Paper Lanterns' })).toBeTruthy();
    expect(screen.getByText('2 plays in all, newest first. Showing 1 to 2.')).toBeTruthy();
    expect(screen.getByText(/match key starts with its normalised name/)).toBeTruthy();
    expect(screen.getByRole('link', { name: 'All sources' }).getAttribute('aria-current')).toBe('page');
    expect(screen.getByRole('link', { name: 'Spotify' }).getAttribute('href')).toBe('/library/plays?artist=302&source=spotify');
    expect(screen.getByRole('link', { name: 'Static Gulls (Remastered 2024)' }).getAttribute('href')).toBe('/library/track/104');
    expect(screen.getByRole('link', { name: 'Back to the artist' }).getAttribute('href')).toBe('/library/artist/302');
  });
});

describe('links from T10', () => {
  it("each track row's title opens its track page; an artist's rows open its page", async () => {
    const row = A['/api/library/track/101'].track;
    api({
      '/api/modules': MODULES,
      '/api/library/tracks?artist_key=301': {
        filters: {}, sort: 'artist', total: 1, limit: 50, offset: 0, rule: 'tracks WHERE removed_at IS NULL', params: [],
        plays_rule: 'plays_of', rows: [{ ...row, analysis_status: 'ok', analysis_version: 2, camelot: '8A', bpm: 128, plays: 3, history_plays: 1, last_played: null }],
      },
    });
    open('/library/tracks?artist_key=301&name=Kollektiv+Nord');
    expect((await screen.findByRole('link', { name: 'Westkreuz' })).getAttribute('href')).toBe('/library/track/101');
    expect(screen.getByRole('link', { name: 'Artist page' }).getAttribute('href')).toBe('/library/artist/301');
  });
});

describe('why', () => {
  it('a top song says its plays across copies', () => {
    const tr = { ...A['/api/library/artist/302'].top_tracks[0], plays: 5, versions: 2, albums: 2 };
    expect(pageTrackWhy(tr, true)).toMatch(/^5 plays across 2 copies on 2 albums · 4 min 5 s/);
    expect(pageTrackWhy({ ...tr, versions: 1 })).toMatch(/^5 plays \(Plex 2, or the history's if more\)/);
  });
});
