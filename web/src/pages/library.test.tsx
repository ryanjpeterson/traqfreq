import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Shell } from '../App';
import { CORE_ONLY } from '../app/api';
import { parseRoute } from '../app/route';
import { parseTrackFilter, trackQuery, tracksHref } from '../app/library';
import { filterTitle, trackWhy } from './LibraryRows';

// Invented numbers, shaped like the fixture's /api/library/stats answer (never real data).
const STATS = {
  server: { name: 'Fixture Plex' }, last_sync: 1793844000,
  tracks: 5, artists: 3, albums: 3, hours: 0.4, size_gb: 0.1,
  codecs: { mp3: 2, flac: 2, aac: 1 },
  containers: { mp3: 2, mp4: 1, flac: 1, '?': 1 },
  bitrate_kbps: { '<192k': 1, '192-255k': 0, '256-319k': 1, '320k': 1, '>320k (lossless)': 1 },
  play_history: {
    played_tracks: 2, played_pct: 40.0, total_plays: 5, rated_tracks: 2, rated_pct: 40.0,
    top_artists: { 'Kollektiv Nord': 3, 'The Paper Lanterns': 2 },
  },
  sonic_analysis: { tracks: 3, pct: 60.0 },
  paths: {
    folders: { '/music': { read_from: '/srv/music', readable_here: true, tracks: 5 } }, folders_compared: false,
    mapped: 4, mapped_pct: 80.0, unmapped_examples: ['/music/Ada Vey/Quiet Engines/01 Coil.flac'],
    multi_part_tracks: 1, removed_since_first_sync: 1,
  },
  analyzer: { version: 2, tracks: 2, pct: 40.0, errors: 1 },
  top_artist_keys: [{ artist: 'Kollektiv Nord', artist_key: 301, plays: 3 }, { artist: 'The Paper Lanterns', artist_key: 302, plays: 2 }],
  plays_all: {
    played_tracks: 5, played_pct: 100.0, plays: 8, history_plays: 5,
    by_source: { lastfm: 2, plex: 1, spotify: 1, applemusic: 1 }, tracks_by_source: { lastfm: 2, plex: 1, spotify: 1, applemusic: 1 },
    top_artists: [{ artist: 'Kollektiv Nord', artist_key: 301, plays: 4 }, { artist: 'The Paper Lanterns', artist_key: 302, plays: 3 },
      { artist: 'Ada Vey', artist_key: 303, plays: 1 }],
  },
  rules: {
    tracks: 'COUNT(*) WHERE removed_at IS NULL', albums: 'COUNT(DISTINCT album_key) WHERE removed_at IS NULL',
    codecs: "the 10 most common COALESCE(codec, '?') WHERE removed_at IS NULL",
    sonic_analysis: 'sonic_version IS NOT NULL AND removed_at IS NULL (Plex sonic analysis)',
    analyzer: "analysis a.status = 'ok' AND a.version >= 2 AND removed_at IS NULL (jimbo-dj's analyzer, version 2)",
    folders: 'shown as jimbo-dj stored them, not compared',
  },
  rows: {
    tracks: '', albums: '', artists: '', hours: '', size_gb: '',
    codecs: { mp3: 'codec=mp3', flac: 'codec=flac', aac: 'codec=aac' },
    containers: { mp3: 'container=mp3', mp4: 'container=mp4', flac: 'container=flac', '?': 'container=%3F' },
    bitrate_kbps: { '<192k': 'bitrate=%3C192k', '192-255k': 'bitrate=192-255k', '256-319k': 'bitrate=256-319k', '320k': 'bitrate=320k',
      '>320k (lossless)': 'bitrate=%3E320k+%28lossless%29' },
    played_tracks: 'played=true', total_plays: 'played=true&sort=plex_plays', rated_tracks: 'rated=true',
    top_artists: { 301: 'artist_key=301&played=true&sort=plex_plays', 302: 'artist_key=302&played=true&sort=plex_plays' },
    sonic_analysis: 'sonic=true', analyzer: 'analysis=ok', analyzer_errors: 'analysis=error',
    mapped: 'mapped=true', unmapped: 'mapped=false', multi_part_tracks: 'multi_part=true', removed_since_first_sync: 'removed=true',
    'all.played_tracks': 'heard=true&sort=plays', 'all.plays': 'heard=true&sort=plays',
    'all.by_source': { lastfm: 'source=lastfm&sort=plays', plex: 'source=plex&sort=plays', spotify: 'source=spotify&sort=plays', applemusic: 'source=applemusic&sort=plays' },
    'all.top_artists': { 301: 'artist_key=301&heard=true&sort=plays', 302: 'artist_key=302&heard=true&sort=plays', 303: 'artist_key=303&heard=true&sort=plays' },
  },
  jimbodj: { source: 'stats.library.stats', built_at: '2026-11-05T02:01:00Z', stamp: '[]', fresh: true },
  cache: { name: 'library.stats', key: 'v1', built_at: 1793847960, seconds: 0.01, hit: true },
};

const ROW = {
  rating_key: 101, title: 'Westkreuz', artist: 'Kollektiv Nord', track_artist: null, album: 'Ringbahn', album_key: 201,
  artist_key: 301, disc: null, track_no: 1, year: 2019, duration_ms: 312000,
  plex_path: '/music/Kollektiv Nord/Ringbahn/01 Westkreuz.flac', local_path: '/srv/music/Kollektiv Nord/Ringbahn/01 Westkreuz.flac',
  parts: 1, file_size: 39400000, container: 'flac', codec: 'flac', bitrate: 1011, view_count: 3,
  last_viewed_at: '2026-10-30T18:00:00Z', user_rating: null, sonic_version: 1, added_at: '2025-03-01T10:00:00Z', removed_at: null,
  analysis_status: 'ok', analysis_version: 2, camelot: '8A', bpm: 128.0, plays: 3, history_plays: 1, last_played: '2026-11-01T20:15:00Z',
};
const UNANALYSED = {
  ...ROW, rating_key: 103, title: 'Coil', artist: 'Ada Vey', album: 'Quiet Engines', local_path: null, bitrate: null,
  plex_path: '/music/Ada Vey/Quiet Engines/01 Coil.flac', sonic_version: null, view_count: 0, plays: 1, history_plays: 1,
  analysis_status: 'error', camelot: null, bpm: null, parts: 2,
};

function tracks(rows: object[], extra: object = {}) {
  return {
    filters: {}, sort: 'plex_plays', total: rows.length, limit: 50, offset: 0,
    rule: 'tracks WHERE removed_at IS NULL AND view_count > 0', params: [],
    plays_rule: "max(Plex view_count, history plays), never the sum (jimbo-dj's plays_of)", rows, ...extra,
  };
}

function api(answers: Record<string, unknown>) {
  const f = vi.fn(async (url: string) => {
    if (answers[url] === 404) return { ok: false, status: 404, json: async () => ({}) };
    if (!(url in answers)) return { ok: false, status: 503, json: async () => ({}) };
    return { ok: true, status: 200, json: async () => answers[url] };
  });
  vi.stubGlobal('fetch', f);
  return f;
}

const MODULES = { modules: CORE_ONLY };

function open(path: string) {
  window.history.replaceState(null, '', path);
  return render(<Shell />);
}

beforeEach(() => { window.scrollTo = vi.fn() as unknown as typeof window.scrollTo; });
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

describe('LIBRARY page', () => {
  const answers = { '/api/modules': MODULES, '/api/library/stats': STATS };

  it('shows the headline counts with their rules, each opening its rows (W3)', async () => {
    api(answers);
    open('/library');
    expect(await screen.findByText('5 tracks', { selector: '.hist-big' })).toBeTruthy();
    expect(screen.getByText(/COUNT\(\*\) WHERE removed_at IS NULL\. jimbo-dj's stored copy is from the same sync\./)).toBeTruthy();
    expect(screen.getByRole('link', { name: 'Show the tracks' }).getAttribute('href')).toBe('/library/tracks');
    const head = screen.getByRole('list', { name: 'The library in numbers' });
    expect(within(head).getByText(/COUNT\(DISTINCT album_key\)/)).toBeTruthy();
    const links = within(head).getAllByRole('link');
    // T11: albums and artists open their lists; hours and size open the tracks.
    expect(links.map((a) => a.textContent)).toEqual(['3 albums, all albums', '3 artists, all artists',
      '0.4 h, show the tracks', '0.1 GB, show the tracks']);
    expect(links.map((a) => a.getAttribute('href'))).toEqual(['/library/albums', '/library/artists', '/library/tracks', '/library/tracks']);
  });

  it('draws codecs, containers and bitrate as lists with share bars and a summary (L6)', async () => {
    api(answers);
    open('/library');
    const codecs = await screen.findByRole('list', { name: 'Codecs' });
    expect(within(codecs).getAllByRole('link', { name: '2 tracks, show the tracks' })[0].getAttribute('href')).toBe('/library/tracks?codec=mp3');
    expect(codecs.querySelectorAll('.lib-bar[aria-hidden="true"]')).toHaveLength(3);
    expect(screen.getAllByText('Most common: mp3, 2 tracks (40.0 % of all tracks).')).toHaveLength(2);
    const containers = screen.getByRole('list', { name: 'Containers' });
    expect(within(containers).getByText('none given')).toBeTruthy();
    expect(within(containers).getAllByRole('link').map((a) => a.getAttribute('href'))).toContain('/library/tracks?container=%3F');
    const bitrate = screen.getByRole('list', { name: 'Bitrate' });
    // Buckets keep jimbo-dj's order; an empty one is a number without a link.
    expect(within(bitrate).getAllByRole('listitem').map((li) => li.querySelector('strong')!.textContent))
      .toEqual(['<192k', '192-255k', '256-319k', '320k', '>320k (lossless)']);
    expect(within(bitrate).getByText('0 tracks').closest('a')).toBeNull();
    expect(within(bitrate).getAllByRole('link')[3].getAttribute('href')).toBe('/library/tracks?bitrate=%3E320k+%28lossless%29');
    expect(screen.getByText('1 track with no bitrate, in no bucket.')).toBeTruthy();
  });

  it('shows Plex play history and Plex top artists by key', async () => {
    api(answers);
    open('/library');
    const plex = await screen.findByRole('list', { name: "Plex only (jimbo-dj's numbers)" });
    expect(within(plex).getAllByText(/^40\.0 % · Rule/, { selector: '.sub' })).toHaveLength(2);  // played and rated
    expect(within(plex).getByRole('link', { name: '5 plays, show the tracks' }).getAttribute('href'))
      .toBe('/library/tracks?played=true&sort=plex_plays');
    const top = screen.getByRole('list', { name: 'Plex top artists' });
    expect(within(top).getByRole('link', { name: '3 plays, show the tracks' }).getAttribute('href'))
      .toBe('/library/tracks?artist_key=301&played=true&sort=plex_plays&name=Kollektiv+Nord');
  });

  it('shows play history from every source beside Plex, each number opening its tracks', async () => {
    api(answers);
    open('/library');
    const all = await screen.findByRole('list', { name: 'Every source' });
    expect(within(all).getByRole('link', { name: '5 tracks, show the tracks' }).getAttribute('href')).toBe('/library/tracks?heard=true&sort=plays');
    expect(within(all).getByRole('link', { name: '8 plays, show the tracks' })).toBeTruthy();
    const src = screen.getByRole('list', { name: 'Plays by source' });
    expect(within(src).getAllByRole('listitem').map((li) => li.querySelector('strong')!.textContent))
      .toEqual(['Last.fm', 'Plex', 'Spotify', 'Apple Music']);
    expect(within(src).getAllByRole('link', { name: 'on 1 track, show the tracks' })).toHaveLength(3);
    expect(within(src).getAllByRole('link')[2].getAttribute('href')).toBe('/library/tracks?source=spotify&sort=plays');
    expect(src.querySelectorAll('.lib-bar[aria-hidden="true"]')).toHaveLength(4);
    expect(screen.getByText('Most from Last.fm: 2 plays on 2 tracks.')).toBeTruthy();
    const top = screen.getByRole('list', { name: 'Top artists, every source' });
    expect(within(top).getByRole('link', { name: '4 plays, show the tracks' }).getAttribute('href'))
      .toBe('/library/tracks?artist_key=301&heard=true&sort=plays&name=Kollektiv+Nord');
    expect(within(top).getByRole('link', { name: 'Ada Vey' }).getAttribute('href')).toBe('/library/artist/303');
  });

  it('titles rows played anywhere or on one source', () => {
    expect(filterTitle(parseTrackFilter('heard=true&sort=plays'))).toBe('Tracks · played anywhere');
    expect(filterTitle(parseTrackFilter('source=applemusic'))).toBe('Tracks · played on Apple Music');
    expect(trackQuery(parseTrackFilter('sort=plays&source=spotify&heard=true'))).toBe('heard=true&source=spotify&sort=plays');
  });

  it("says which analysis is Plex's and which is jimbo-dj's", async () => {
    api(answers);
    open('/library');
    const sonic = await screen.findByRole('list', { name: 'Plex sonic analysis' });
    expect(within(sonic).getByRole('link', { name: '3 tracks, show the tracks' }).getAttribute('href')).toBe('/library/tracks?sonic=true');
    expect(screen.getByText(/Plex's own analysis/)).toBeTruthy();
    expect(screen.getByText(/jimbo-dj's own analysis of the audio files, version 2/)).toBeTruthy();
    const ours = screen.getByRole('list', { name: "jimbo-dj's analyzer" });
    expect(within(ours).getAllByRole('link').map((a) => a.getAttribute('href')))
      .toEqual(['/library/tracks?analysis=ok', '/library/tracks?analysis=error']);
  });

  it('shows paths, and folders as jimbo-dj stored them, not compared', async () => {
    api(answers);
    open('/library');
    const files = await screen.findByRole('list', { name: "Plex paths and jimbo-dj's files" });
    expect(within(files).getAllByRole('link').map((a) => a.getAttribute('href'))).toEqual([
      '/library/tracks?mapped=true', '/library/tracks?mapped=false', '/library/tracks?multi_part=true', '/library/tracks?removed=true']);
    expect(screen.getByText('/music/Ada Vey/Quiet Engines/01 Coil.flac')).toBeTruthy();
    expect(screen.getByText('Not compared')).toBeTruthy();
    const folders = screen.getByRole('list', { name: 'Music folders' });
    expect(within(folders).getByText('5 tracks').closest('a')).toBeNull();
    expect(within(folders).getByText(/read from \/srv\/music · readable by jimbo-dj/)).toBeTruthy();
  });

  it('points to SETUP when jimbo-dj has no tracks table (D1)', async () => {
    api({ ...answers, '/api/library/stats': 404 });
    open('/library');
    expect(await screen.findByText(/has no tracks table/)).toBeTruthy();
    expect(screen.getByRole('link', { name: 'Open SETUP' })).toBeTruthy();
  });

  it('opens rows on click, without a page load', async () => {
    const f = api({ ...answers, '/api/library/tracks?codec=mp3': tracks([ROW]) });
    open('/library');
    const codecs = await screen.findByRole('list', { name: 'Codecs' });
    await userEvent.click(within(codecs).getAllByRole('link', { name: '2 tracks, show the tracks' })[0]);
    expect(window.location.pathname + window.location.search).toBe('/library/tracks?codec=mp3');
    expect(await screen.findByText('Westkreuz')).toBeTruthy();
    expect(f).toHaveBeenCalledWith('/api/library/tracks?codec=mp3');
  });
});

describe('LIBRARY rows page', () => {
  it('lists tracks with key and BPM where analysed, the rule and the why (B3, W3)', async () => {
    const f = api({ '/api/modules': MODULES, '/api/library/tracks?played=true&sort=plex_plays': tracks([ROW, UNANALYSED]) });
    open('/library/tracks?played=true&sort=plex_plays');
    expect(await screen.findByText('Westkreuz')).toBeTruthy();
    expect(f).toHaveBeenCalledWith('/api/library/tracks?played=true&sort=plex_plays');
    expect(screen.getByRole('heading', { name: 'Tracks · played in Plex' })).toBeTruthy();
    expect(screen.getByText('2 tracks in all, most Plex plays first. Showing 1 to 2.')).toBeTruthy();
    expect(screen.getByText(/Rule: tracks WHERE removed_at IS NULL AND view_count > 0\. Plays: max\(Plex view_count/)).toBeTruthy();
    const items = screen.getAllByRole('listitem').filter((li) => li.classList.contains('kit-station'));
    expect(items[0].textContent).toContain('8A');
    expect(items[0].textContent).toContain('128 BPM');
    expect(items[1].textContent).not.toContain('BPM');
    await userEvent.click(within(items[0]).getByRole('button', { name: "Why it's here" }));
    expect(within(items[0]).getByText(/3 plays: Plex 3, history 1, the larger counts/)).toBeTruthy();
    const order = screen.getByRole('navigation', { name: 'Order' });
    expect(within(order).getByRole('link', { name: 'Most Plex plays' }).getAttribute('aria-current')).toBe('page');
    expect(within(order).getByRole('link', { name: 'By artist' }).getAttribute('href')).toBe('/library/tracks?played=true');
    expect(screen.getByRole('link', { name: 'Back to LIBRARY' }).getAttribute('href')).toBe('/library');
  });

  it('pages through 50 at a time', async () => {
    const page = tracks([ROW], { total: 120, offset: 50, sort: 'artist' });
    api({ '/api/modules': MODULES, '/api/library/tracks?codec=flac&offset=50': page });
    open('/library/tracks?codec=flac&offset=50');
    expect(await screen.findByText('120 tracks in all, by artist and album. Showing 51 to 51.')).toBeTruthy();
    expect(screen.getByRole('link', { name: 'Previous' }).getAttribute('href')).toBe('/library/tracks?codec=flac');
    expect(screen.getByRole('link', { name: 'Next' }).getAttribute('href')).toBe('/library/tracks?codec=flac&offset=100');
  });

  it('says when the rows cannot be read', async () => {
    api({ '/api/modules': MODULES });
    open('/library/tracks?analysis=ok');
    expect(await screen.findByText(/Can't read these tracks/)).toBeTruthy();
  });
});

describe('LIBRARY filters', () => {
  it('routes /library/tracks to LIBRARY', () => {
    expect(parseRoute('/library/tracks?codec=mp3')).toEqual({ page: 'module', module: 'L', sub: 'tracks' });
    expect(parseRoute('/library')).toEqual({ page: 'module', module: 'L' });
  });

  it('reads only the filters the API knows and writes them back in one order', () => {
    const f = parseTrackFilter('?bitrate=%3E320k+%28lossless%29&played=false&analysis=maybe&sort=added&artist_key=x&removed=false&container=%3F');
    expect(f).toMatchObject({ bitrate: '>320k (lossless)', played: false, sort: 'added', container: '?' });
    expect(f.analysis).toBeUndefined();
    expect(f.artist_key).toBeUndefined();
    expect(f.removed).toBeUndefined();
    expect(trackQuery(f)).toBe('container=%3F&bitrate=%3E320k+%28lossless%29&played=false&sort=added');
    expect(parseTrackFilter('?bitrate=999k').bitrate).toBeUndefined();
    expect(parseTrackFilter('?name=Someone').name).toBeUndefined();  // a name only labels an artist key
    expect(tracksHref('')).toBe('/library/tracks');
  });

  it('titles each filter in words', () => {
    expect(filterTitle({ container: '?', mapped: false })).toBe('Tracks · container none given · not mapped');
    expect(filterTitle({ removed: true })).toBe('Removed tracks');
    expect(filterTitle({ artist_key: 301, name: 'Kollektiv Nord', played: true })).toBe('Tracks · played in Plex · Kollektiv Nord');
    expect(filterTitle({ analysis: 'error' })).toBe("Tracks · jimbo-dj's analyzer failed");
  });

  it('gives each track its file facts and plays_of in the why', () => {
    expect(trackWhy(ROW)).toBe('flac · 1,011 kbps · 39.4 MB · 5 min 12 s · file /srv/music/Kollektiv Nord/Ringbahn/01 Westkreuz.flac'
      + ' · Plex sonic analysis · analysed by jimbo-dj, version 2 · 3 plays: Plex 3, history 1, the larger counts'
      + ' · last played 1 Nov 2026 · added 1 Mar 2025');
    const w = trackWhy(UNANALYSED);
    expect(w).toContain('no bitrate');
    expect(w).toContain('2 parts');
    expect(w).toContain('not mapped, Plex has /music/Ada Vey/Quiet Engines/01 Coil.flac');
    expect(w).toContain("jimbo-dj's analyzer failed, version 2");
    expect(w).toContain('1 play: Plex 0, history 1');
  });
});
