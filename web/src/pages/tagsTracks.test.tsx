import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Shell } from '../App';
import { parseRoute } from '../app/route';
import { TRACKS_CHECK_API, type TagAlbumPage } from '../app/tags';
import { trackRowWhy } from './TagsTracks';
import ANSWERS from './tagsTracks.answers.json';
import LADDER from './tags.answers.json';

// T21: traqfreq's own answers on the fixture (scripts/make_fixture.py TAGS, STYLES, FILE_TAGS), generated from its API.
const A = { ...LADDER, ...ANSWERS } as Record<string, any>;  // eslint-disable-line @typescript-eslint/no-explicit-any
const ON = (t: boolean) => ({ modules: ['L', 'H', 'T', 'D', 'M', 'F', 'S'].map((id) => ({ id, on: ['L', 'S'].includes(id) || (t && id === 'T'), core: id === 'L' || id === 'S' })) });

function api(answers: Record<string, unknown>) {
  const f = vi.fn(async (url: string) => {
    if (!(url in answers)) return { ok: false, status: url.startsWith('/api/tags/') ? 404 : 503, json: async () => ({}) };
    return { ok: true, status: 200, json: async () => answers[url] };
  });
  vi.stubGlobal('fetch', f);
  return f;
}

function open(path: string, answers: Record<string, unknown> = A, tags = true) {
  api({ '/api/modules': ON(tags), ...answers });
  window.history.replaceState(null, '', path);
  return render(<Shell />);
}

beforeEach(() => { window.scrollTo = vi.fn() as unknown as typeof window.scrollTo; });
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

describe('T21 routes', () => {
  it('parses an album track by track and a track by source', () => {
    expect(parseRoute('/tags/album/201')).toEqual({ page: 'module', module: 'T', sub: 'album', key: 201 });
    expect(parseRoute('/tags/track/101')).toEqual({ page: 'module', module: 'T', sub: 'track', key: 101 });
    expect(parseRoute('/tags/track/x')).toEqual({ page: 'notFound' });
  });
});

describe('an album, track by track', () => {
  it('shows the track that differs from its album', async () => {
    open('/tags/album/201');
    expect(await screen.findByRole('heading', { name: 'Ringbahn' })).toBeTruthy();
    const west = screen.getByRole('link', { name: 'Westkreuz' });
    expect(west.getAttribute('href')).toBe('/tags/track/101');
    // Westkreuz's row is open: it differs (an ambient intro on a black metal album).
    expect(screen.getByText(/^Beyond the album: Ambient · styles kept: Black Metal 0.62, Ambient 0.48, Dark Ambient 0.3 · Same as jimbo-dj's per-track rule$/)).toBeTruthy();
    const which = within(screen.getByRole('navigation', { name: 'Which tracks' }));
    expect(which.getByRole('link', { name: 'All: 2 tracks' }).getAttribute('aria-current')).toBe('page');
    expect(which.getByRole('link', { name: 'Differ from the album: 1 track' }).getAttribute('href')).toBe('/tags/album/201?show=differs');
    expect(screen.getByText("jimbo-dj's per-track rule: 2 of 2 tracks the same. Styles: 2 of 2 tracks the same as its strict test.")).toBeTruthy();
  });

  it('lists only the tracks that differ when asked', async () => {
    open('/tags/album/201?show=differs');
    expect(await screen.findByRole('link', { name: 'Westkreuz' })).toBeTruthy();
    expect(screen.queryByRole('link', { name: 'Ostkreuz' })).toBeNull();
  });

  it('shows the tags its tracks speak for, each opening its albums', async () => {
    open('/tags/album/201');
    const from = within(await screen.findByRole('list', { name: 'From its tracks' }));
    expect(from.getByRole('link', { name: 'Ambient, Albums carrying it' }).getAttribute('href')).toBe('/tags/albums?tag=ambient&set=carries');
    expect(from.getByText("on 50 % of its tracks' Plex genres, 50 % of its files · rung 1 · Electronic")).toBeTruthy();
    expect(from.getAllByText('speaks for the album · not on the album')).toHaveLength(1);
  });

  it('says when every track matches its album', async () => {
    open('/tags/album/202?show=differs');
    expect(await screen.findByText("Every track carries the album's tags and no other.")).toBeTruthy();
    const from = within(screen.getByRole('list', { name: 'From its tracks' }));
    expect(from.getByText('Drone')).toBeTruthy();  // a file's tag, on no rung
    expect(from.getByText("on 0 % of its tracks' Plex genres, 50 % of its files · not on the ladder")).toBeTruthy();
  });

  it('says when the album is not there', async () => {
    open('/tags/album/999');
    expect(await screen.findByText("No album has this key in jimbo-dj's tags. Open LIBRARY to find it again.")).toBeTruthy();
  });

  it('explains a row in one line', () => {
    const a = A['/api/tags/album/201'] as TagAlbumPage;
    expect(trackRowWhy(a.tracks[1])).toBe("Same as the album · styles kept: Black Metal 0.7 · Same as jimbo-dj's per-track rule");
  });
});

describe('a track, by source', () => {
  it('lists its tags on their rungs, with the sources that name them', async () => {
    open('/tags/track/101');
    expect(await screen.findByRole('heading', { name: 'Westkreuz' })).toBeTruthy();
    const tags = within(screen.getByRole('list', { name: 'Its tags' }));
    expect(tags.getByText('rung 2 · Metal · from album')).toBeTruthy();
    expect(tags.getByText('rung 1 · Electronic · from track, file, sound')).toBeTruthy();
    expect(tags.getAllByText('not on its album')).toHaveLength(1);
    expect(screen.getByText("Same as jimbo-dj's per-track rule")).toBeTruthy();
    expect(screen.getByText("Styles the same as jimbo-dj's strict test")).toBeTruthy();
    expect(screen.getByRole('link', { name: 'The track in LIBRARY' }).getAttribute('href')).toBe('/library/track/101');
    expect(screen.getByRole('link', { name: 'Its album, track by track' }).getAttribute('href')).toBe('/tags/album/201');
  });

  it("shows the analyzer's styles with their scores, kept or not", async () => {
    open('/tags/track/101');
    const sound = within(await screen.findByRole('list', { name: "The analyzer's styles" }));
    expect(sound.getByText('rung 1 · Metal · score 0.62 · kept')).toBeTruthy();
    expect(sound.getByText('not on the ladder · score 0.3 · kept')).toBeTruthy();  // Dark Ambient
    expect(sound.getByText('rung 0 · Punk · score 0.2 · not kept')).toBeTruthy();
    expect(screen.getAllByText("Not in jimbo-dj's MusicBrainz cache.")).toHaveLength(2);
  });

  it('shows MusicBrainz votes', async () => {
    open('/tags/track/103');
    const rel = within(await screen.findByRole('list', { name: 'MusicBrainz, the release' }));
    expect(rel.getByText('rung 2 · Metal · 3 votes · “death-doom metal”')).toBeTruthy();
    const art = within(screen.getByRole('list', { name: 'MusicBrainz, the artist' }));
    expect(art.getByText('rung 1 · Rock · 2 votes · “post-punk”')).toBeTruthy();
  });

  it("says why a source is empty and what isn't a genre", async () => {
    open('/tags/track/105');
    expect(await screen.findByText('File not read: unreadable')).toBeTruthy();
    expect(screen.getByText('No styles: not analysed yet.')).toBeTruthy();
    const album = within(screen.getByRole('list', { name: "The album's Plex genres" }));
    expect(album.getByText('2010s')).toBeTruthy();
    expect(album.getByText('not a genre (decades)')).toBeTruthy();
  });

  it('says when the track is not a live one', async () => {
    open('/tags/track/106');
    expect(await screen.findByText(/^No live track has this key/)).toBeTruthy();
  });
});

describe('gate check 2 on TAGS', () => {
  it('shows every track next to jimbo-dj, each number opening its tracks', async () => {
    open('/tags');
    const card = within(await screen.findByRole('list', { name: 'Track by track, same as jimbo-dj' }));
    expect(card.getByRole('link', { name: "5 of 5 tracks have jimbo-dj's per-track tags" }).getAttribute('href')).toBe('/library/tracks');
    expect(card.getByRole('link', { name: "5 of 5 tracks keep the styles jimbo-dj's strict test keeps" })).toBeTruthy();
    expect(card.getByText(/3 with the analyzer's styles, 3 keeping at least one$/)).toBeTruthy();
    expect(screen.queryByRole('button', { name: /that differ$/ })).toBeNull();
  });

  it('lists the tracks that differ, with both answers', async () => {
    const c = structuredClone(A[TRACKS_CHECK_API]);
    c.passed = false;
    c.tags.matches = false;
    c.tags.ok = 4;
    c.tags.differ = 1;
    c.tags.items = [{ rating_key: 102, title: 'Ostkreuz', artist: 'Kollektiv Nord', traqfreq: ['black metal'], jimbodj: [] }];
    open('/tags', { ...A, [TRACKS_CHECK_API]: c });
    await userEvent.click(await screen.findByRole('button', { name: 'Show the 1 that differ' }));
    const rows = within(screen.getByRole('list', { name: 'Tracks that differ' }));
    expect(rows.getByRole('link', { name: 'Ostkreuz' }).getAttribute('href')).toBe('/tags/track/102');
    expect(screen.getAllByText('Some differ').length).toBeGreaterThan(0);
  });
});

describe('LIBRARY links to TAGS', () => {
  it('links an album and a track to their tags only while TAGS is on', async () => {
    const ent = (await import('./entities.answers.json')).default as Record<string, unknown>;
    const albumUrl = Object.keys(ent).find((u) => u.startsWith('/api/library/album/'))!;
    const key = albumUrl.split('/').pop();
    open(`/library/album/${key}`, ent);
    expect((await screen.findByRole('link', { name: 'Its tags, track by track' })).getAttribute('href')).toBe(`/tags/album/${key}`);
    cleanup();
    open(`/library/album/${key}`, ent, false);
    expect(await screen.findByRole('heading', { level: 1 })).toBeTruthy();
    expect(screen.queryByRole('link', { name: 'Its tags, track by track' })).toBeNull();
    cleanup();
    const trackUrl = Object.keys(ent).find((u) => u.startsWith('/api/library/track/') && (ent[u] as { live?: boolean }).live)!;
    const tk = trackUrl.split('/').pop();
    open(`/library/track/${tk}`, ent);
    expect((await screen.findByRole('link', { name: 'Its tags by source' })).getAttribute('href')).toBe(`/tags/track/${tk}`);
  });
});
