import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Shell } from '../App';
import { parseRoute } from '../app/route';
import { stationsOf, tagHref, type GenreMapData, type TagPageData, type TagsGate } from '../app/tags';
import ANSWERS from './tagsGenre.answers.json';
import LADDER from './tags.answers.json';

// T23: traqfreq's own answers on the fixture (scripts/make_fixture.py TAGS, STYLES, LISTENS), generated from its API.
const A = { ...LADDER, ...ANSWERS } as Record<string, any>;  // eslint-disable-line @typescript-eslint/no-explicit-any
const MAP = A['/api/tags/map'] as GenreMapData;
const GATE = A['/api/tags/compare'] as TagsGate;
const mods = (on: string[]) => ({ modules: ['L', 'H', 'T', 'D', 'M', 'F', 'S'].map((id) => ({ id, on: on.includes(id), core: id === 'L' || id === 'S' })) });

function api(answers: Record<string, unknown>) {
  const f = vi.fn(async (url: string, init?: RequestInit) => {
    if (init?.method && init.method !== 'GET') throw new Error(`${init.method} ${url}: TAGS only reads`);
    if (!(url in answers)) return { ok: false, status: url.startsWith('/api/tags/') ? 404 : 503, json: async () => ({}) };
    return { ok: true, status: 200, json: async () => answers[url] };
  });
  vi.stubGlobal('fetch', f);
  return f;
}

function open(path: string, answers: Record<string, unknown> = A, on = ['L', 'S', 'T']) {
  const f = api({ '/api/modules': mods(on), ...answers });
  window.history.replaceState(null, '', path);
  render(<Shell />);
  return f;
}

beforeEach(() => { window.scrollTo = vi.fn() as unknown as typeof window.scrollTo; });
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

describe('T23 routes', () => {
  it('parses a tag page (its key URL-encoded), the map and a tag\'s tracks', () => {
    expect(parseRoute('/tags/tag/death-doom%20metal')).toEqual({ page: 'module', module: 'T', sub: 'tag', tag: 'death-doom metal' });
    expect(parseRoute(tagHref('r&b'))).toEqual({ page: 'module', module: 'T', sub: 'tag', tag: 'r&b' });
    expect(parseRoute('/tags/tag/%E0%A4%A')).toEqual({ page: 'notFound' });
    expect(parseRoute('/tags/map')).toEqual({ page: 'module', module: 'T', sub: 'map' });
    expect(parseRoute('/tags/tracks')).toEqual({ page: 'module', module: 'T', sub: 'tracks' });
  });
});

describe('a tag\'s page', () => {
  it('shows both ladders of a tag with two parents, each rung opening its page', async () => {
    open('/tags/tag/death-doom%20metal');
    expect(await screen.findByRole('heading', { level: 1, name: 'Death-Doom Metal' })).toBeTruthy();
    const ladders = within(screen.getByRole('list', { name: 'Its ladders, broad tag first' }));
    expect(ladders.getByRole('list', { name: 'Ladder: Metal, Death Metal, Death-Doom Metal' })).toBeTruthy();
    expect(ladders.getByRole('list', { name: 'Ladder: Metal, Doom Metal, Death-Doom Metal' })).toBeTruthy();
    expect(ladders.getAllByRole('link', { name: 'Metal' })[0].getAttribute('href')).toBe('/tags/tag/metal');
    expect(screen.getByText(/jimbo-dj's rules find the Metal family in “doom”/)).toBeTruthy();
  });

  it('opens every number\'s rows, and shows a zero without a link', async () => {
    open('/tags/tag/black%20metal');
    const nums = within(await screen.findByRole('list', { name: 'Its numbers' }));
    expect(nums.getByRole('link', { name: 'Carried by 1 album, Black Metal' }).getAttribute('href')).toBe('/tags/albums?tag=black%20metal&set=carries');
    expect(nums.getByRole('link', { name: '2 tracks carrying it, Black Metal' }).getAttribute('href')).toBe('/tags/tracks?tag=black%20metal&sort=album');
    expect(nums.getByRole('link', { name: '2 plays of those tracks, Black Metal' }).getAttribute('href')).toBe('/tags/tracks?tag=black%20metal');
    const sound = within(screen.getByRole('list', { name: 'Its sound' }));
    expect(sound.getByRole('link', { name: '1 album by the analyzer\'s styles, Black Metal' }).getAttribute('href')).toBe('/tags/albums?tag=black%20metal&set=sound');
    expect(screen.getByText('Too few analysed plays to say what its plays sounded like.')).toBeTruthy();
    cleanup();
    open('/tags/tag/hip%20hop', { ...A, '/api/tags/tag/hip%20hop': { ...A['/api/tags/tag/metal'], key: 'hip hop', name: 'Hip Hop', numbers: { ...A['/api/tags/tag/metal'].numbers, plays: 0 } } });
    const zero = within(await screen.findByRole('list', { name: 'Its numbers' }));
    expect(zero.getByText('0 plays of those tracks')).toBeTruthy();
    expect(zero.queryByRole('link', { name: /0 plays/ })).toBeNull();
  });

  it('names its spellings and the rules that made them, and links its issue to the inbox', async () => {
    open('/tags/tag/doom%20metal');
    const names = within(await screen.findByRole('list', { name: 'Its spellings and rules' }));
    expect(names.getByText('doom metal')).toBeTruthy();
    expect(names.getByText(/rules: /)).toBeTruthy();
    expect(screen.getByRole('link', { name: 'In the proposals inbox: non-standard spelling' }).getAttribute('href'))
      .toBe('/tags/proposals/albums?group=kind&value=spelling');
  });

  it('shows its movement, with the movement\'s other tags', async () => {
    open('/tags/tag/doom%20metal');
    expect(await screen.findByRole('heading', { name: 'Doom and drone' })).toBeTruthy();
    const tags = within(screen.getByRole('list', { name: 'The tags of Doom and drone' }));
    expect(tags.getByText('Sludge Metal')).toBeTruthy();
    expect(tags.getAllByText(/not in use/).length).toBeGreaterThan(0);
  });

  it('says a junk tag is not a genre, and an unknown tag has no page', async () => {
    open('/tags/tag/2010s');
    expect(await screen.findByText('Decades aren\'t genres')).toBeTruthy();
    expect(screen.getByText(/jimbo-dj's rules call it not a genre/)).toBeTruthy();
    cleanup();
    open('/tags/tag/polka');
    expect(await screen.findByText(/No such tag in use/)).toBeTruthy();
  });

  it('shows the sound of its plays when there are enough', async () => {
    const p = A['/api/tags/tag/black%20metal'] as TagPageData;
    open('/tags/tag/black%20metal', { ...A, '/api/tags/tag/black%20metal': { ...p, profile: { bpm: 142.5, danceability: 0.4, loudness_lufs: -9.1, plays: 24 } } });
    const s = within(await screen.findByRole('list', { name: 'Its plays\' sound' }));
    expect(s.getByText('Tempo (BPM)')).toBeTruthy();
    expect(s.getByText('-9.1 LUFS')).toBeTruthy();
    expect(screen.getByText('What its plays sounded like (24 plays)')).toBeTruthy();
  });
});

describe('the tracks behind a tag', () => {
  it('lists each track with its plays, by plays or by album', async () => {
    open('/tags/tracks?tag=doom%20metal');
    expect(await screen.findByText('Tracks carrying Doom Metal')).toBeTruthy();
    expect(screen.getByText('2 tracks, 2 plays in all.')).toBeTruthy();
    expect(screen.getByRole('link', { name: 'Static Gulls' }).getAttribute('href')).toBe('/library/track/104');
    expect(screen.getByRole('link', { name: 'Static Gulls: its 1 play' }).getAttribute('href')).toBe('/library/plays?track=104');
    expect(screen.getByRole('link', { name: 'Most plays' }).getAttribute('aria-current')).toBe('page');
  });
});

describe('the genre map', () => {
  it('draws one line per broad tag, with a summary for screen readers', async () => {
    open('/tags/map');
    expect(await screen.findByRole('heading', { level: 1, name: 'The genre map' })).toBeTruthy();
    await screen.findByRole('list', { name: 'Stations on Metal' });
    const drawing = document.querySelector('.gm-drawing') as HTMLElement;
    expect(drawing.getAttribute('aria-hidden')).toBe('true');
    expect(drawing.querySelectorAll('.map-line')).toHaveLength(MAP.lines.length);
    expect(drawing.querySelectorAll('.map-line.is-off')).toHaveLength(MAP.lines.filter((l) => !l.under).length);
    expect(drawing.querySelectorAll('.kit-bullet[data-module="T"]')).toHaveLength(MAP.lines.length);
    expect(screen.getByText(/^5 lines, one per broad tag: Metal, 2 albums under it, 5 tags;/).className).toBe('visually-hidden');
  });

  it('lists every station on its line, a shared tag on both branches', async () => {
    open('/tags/map');
    const metal = within(await screen.findByRole('list', { name: 'Stations on Metal' }));
    expect(metal.getAllByRole('link', { name: 'Death-Doom Metal' })).toHaveLength(2);
    expect(metal.getByText('also under Death Metal')).toBeTruthy();
    expect(metal.getByText('also under Doom Metal')).toBeTruthy();
    expect(metal.getByRole('link', { name: 'Atmospheric Black Metal' }).getAttribute('href')).toBe('/tags/tag/atmospheric%20black%20metal');
    const total = MAP.lines.reduce((n, l) => n + stationsOf(l.stations).length, 0);
    expect(total).toBe(MAP.lines.reduce((n, l) => n + l.stops, 0));
  });

  it('marks movement stations and lists the movements across the lines', async () => {
    open('/tags/map');
    const metal = within(await screen.findByRole('list', { name: 'Stations on Metal' }));
    expect(metal.getAllByText(/in Doom and drone/).length).toBeGreaterThan(0);
    expect(document.querySelector('.gm-station.is-interchange')).toBeTruthy();
    expect(screen.getByRole('heading', { name: 'Blackgaze' })).toBeTruthy();
    expect(screen.getByRole('link', { name: '5 movements' }).getAttribute('href')).toBe('#gm-movements');
    expect(screen.getByRole('link', { name: '1 tag with no broad tag' }).getAttribute('href')).toBe('/tags/list?show=alone');
  });

  it('shows all stations of a long line on request', async () => {
    const many = { ...MAP, lines: [{ ...MAP.lines[0], stations: Array.from({ length: 11 }, (_, i) => ({ ...MAP.lines[0].stations[0], key: `t${i}`, name: `Tag ${i}`, stations: [] })) }] };
    open('/tags/map', { ...A, '/api/tags/map': many });
    const line = await screen.findByRole('list', { name: 'Stations on Metal' });
    expect(within(line).getAllByRole('listitem')).toHaveLength(8);
    await userEvent.click(screen.getByRole('button', { name: 'Show all 11 stations, Metal' }));
    expect(within(line).getAllByRole('listitem')).toHaveLength(11);
  });
});

describe('the P4 gate card', () => {
  it('is on TAGS and on SETUP (when TAGS is on), each check opening its page', async () => {
    open('/tags');
    const card = await screen.findByText('Ladders and per-track tags right');
    expect(card).toBeTruthy();
    expect(await screen.findByText('jimbo-dj\'s rules run here: 3 of 3 broad tags match.')).toBeTruthy();
    expect(screen.getByText('Track tags: 5 of 5 tracks match jimbo-dj\'s per-track rule.')).toBeTruthy();
    expect(screen.getByRole('link', { name: 'Show the rows, 3. The audit' }).getAttribute('href')).toBe('/tags/proposals');
    cleanup();
    open('/setup');
    expect(await screen.findByText('Ladders and per-track tags right')).toBeTruthy();
    cleanup();
    open('/setup', A, ['L', 'S']);
    await screen.findByText('One song, three servers');
    expect(screen.queryByText('Ladders and per-track tags right')).toBeNull();
  });

  it('names each tag that differs from the stored audit, with both numbers', async () => {
    const aud = { ...GATE.checks[2], passed: false,
      tags: { ...GATE.checks[2].tags!, ok: 12, differ: 1, matches: false,
        differing: [{ key: 'metal', name: 'Metal', fields: { musicbrainz: [2898, 2883] as [unknown, unknown] } }] } };
    open('/tags', { ...A, '/api/tags/compare': { ...GATE, passed: false, checks: [GATE.checks[0], GATE.checks[1], aud] } });
    const diff = within(await screen.findByRole('list', { name: 'The tags that differ' }));
    expect(diff.getByRole('link', { name: 'Metal' }).getAttribute('href')).toBe('/tags/tag/metal');
    expect(diff.getByText('MusicBrainz: 2,898 here, 2,883 stored')).toBeTruthy();
    expect(screen.getAllByText('Not passed').length).toBeGreaterThan(0);
  });
});
