import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Shell } from '../App';
import { parseRoute } from '../app/route';
import { LADDER_API, shown, type Ladder } from '../app/tags';
import ANSWERS from './tags.answers.json';

// T20: traqfreq's own answers on the fixture (invented tags, scripts/make_fixture.py TAGS), generated from its API.
const A = ANSWERS as Record<string, any>;  // eslint-disable-line @typescript-eslint/no-explicit-any
const L = A[LADDER_API] as Ladder;
const ON = { modules: ['L', 'H', 'T', 'D', 'M', 'F', 'S'].map((id) => ({ id, on: ['L', 'T', 'S'].includes(id), core: id === 'L' || id === 'S' })) };

function api(answers: Record<string, unknown>) {
  const f = vi.fn(async (url: string) => {
    if (!(url in answers)) return { ok: false, status: 503, json: async () => ({}) };
    return { ok: true, status: 200, json: async () => answers[url] };
  });
  vi.stubGlobal('fetch', f);
  return f;
}

function open(path: string, answers: Record<string, unknown> = A) {
  api({ '/api/modules': ON, ...answers });
  window.history.replaceState(null, '', path);
  return render(<Shell />);
}

beforeEach(() => { window.scrollTo = vi.fn() as unknown as typeof window.scrollTo; });
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

describe('TAGS routes', () => {
  it('parses the ladder and its rows pages', () => {
    expect(parseRoute('/tags')).toEqual({ page: 'module', module: 'T' });
    expect(parseRoute('/tags/albums')).toEqual({ page: 'module', module: 'T', sub: 'albums' });
    expect(parseRoute('/tags/artists')).toEqual({ page: 'module', module: 'T', sub: 'artists' });
    expect(parseRoute('/tags/list')).toEqual({ page: 'module', module: 'T', sub: 'list' });
  });
});

describe('the ladder', () => {
  it('shows the summary, each number opening its tags', async () => {
    open('/tags');
    const sum = within(await screen.findByRole('list', { name: 'In use' }));
    expect(sum.getByRole('link', { name: '12 tags in use' }).getAttribute('href')).toBe('/tags/list?show=tags');
    expect(sum.getByRole('link', { name: '5 broad tags' })).toBeTruthy();
    expect(sum.getByRole('link', { name: 'Deepest rung: 2' }).getAttribute('href')).toBe('/tags/list?show=deepest');
    expect(sum.getByRole('link', { name: '1 tag with more than one parent' })).toBeTruthy();
    expect(screen.getByText(/Not on the ladder: 1 tag the rules call not a genre/)).toBeTruthy();
  });

  it('puts the tags on rungs, broad to specific, shared parents under each', async () => {
    open('/tags');
    const ladder = within(await screen.findByRole('list', { name: 'Broad to specific' }));
    expect(ladder.getByText('Metal')).toBeTruthy();
    expect(ladder.getByRole('link', { name: '1 album missing it, Metal' }).getAttribute('href')).toBe('/tags/albums?tag=metal&set=missing');
    expect(ladder.getByRole('link', { name: '2 albums under it, Metal' }).getAttribute('href')).toBe('/tags/albums?tag=metal&set=under');
    await userEvent.click(ladder.getByRole('button', { name: 'Show the 3 below, Metal' }));
    const below = within(screen.getByRole('list', { name: 'Below Metal' }));
    expect(below.getAllByText('Under Metal, its broad tag · rung 1')).toHaveLength(2);  // Black and Death Metal
    expect(below.getByText('Under Metal, its broad tag · rung 1 · spelled Doom Metal, doom metal')).toBeTruthy();
    await userEvent.click(below.getByRole('button', { name: 'Show the 1 below, Black Metal' }));
    const black = within(screen.getByRole('list', { name: 'Below Black Metal' }));
    expect(black.getByText('Atmospheric Black Metal')).toBeTruthy();
    expect(black.getByText(/^Under Black Metal: its name ends in it · rung 2/)).toBeTruthy();
    await userEvent.click(below.getByRole('button', { name: 'Show the 1 below, Doom Metal' }));
    const doom = within(screen.getByRole('list', { name: 'Below Doom Metal' }));
    expect(doom.getByText('Under Death Metal, Doom Metal: its name holds each · rung 2 · also under Death Metal')).toBeTruthy();
  });

  it('says what stands alone and what names another broad tag', async () => {
    open('/tags');
    const alone = within(await screen.findByRole('list', { name: 'With no broad tag' }));
    expect(alone.getByText('Soundtrack')).toBeTruthy();
    expect(alone.getByText(/^jimbo-dj's rules give it no broad tag/)).toBeTruthy();
    const ladder = within(screen.getByRole('list', { name: 'Broad to specific' }));
    await userEvent.click(ladder.getByRole('button', { name: 'Show the 1 below, Rock' }));
    expect(screen.getByText('Under Rock, its broad tag · rung 1 · also names Punk, under another broad tag')).toBeTruthy();
  });

  it('agrees with jimbo-dj, with each broad tag behind a toggle', async () => {
    open('/tags');
    const card = within(await screen.findByRole('list', { name: "Same as jimbo-dj's families" }));
    expect(card.getByText("3 of 3 broad tags match jimbo-dj's rules, run here")).toBeTruthy();
    expect(card.getByText('8 of 8 ladders end at the broad tag jimbo-dj gives')).toBeTruthy();
    expect(card.getByText("3 of 3 broad tags match jimbo-dj's stored run")).toBeTruthy();
    expect(screen.getAllByText('All match')).toHaveLength(1);
    await userEvent.click(screen.getByRole('button', { name: 'Show the 3 broad tags' }));
    const rows = within(screen.getByRole('list', { name: "Broad tags next to jimbo-dj's stored run" }));
    expect(rows.getAllByText('jimbo-dj: 2 albums under it, carried by 1, 1 missing it, 4 tags below it with albums')).toHaveLength(1);
  });

  it('says when the tags cannot be read', async () => {
    open('/tags', {});
    expect(await screen.findByText("Can't read the tags")).toBeTruthy();
  });

  it('lists the tags behind a summary number', async () => {
    open('/tags/list?show=shared');
    expect(await screen.findByText('Death-Doom Metal')).toBeTruthy();
    expect(shown(L, 'deepest').map((n) => n.name)).toEqual(['Atmospheric Black Metal', 'Death-Doom Metal']);
    expect(shown(L, 'roots').map((n) => n.name)).toEqual(['Metal', 'Hip Hop', 'Punk', 'Electronic', 'Rock']);
  });
});

describe('the rows behind a tag', () => {
  it('lists the albums missing a broad tag, with why', async () => {
    open('/tags/albums?tag=metal&set=missing');
    expect(await screen.findByText('Albums missing Metal')).toBeTruthy();
    const link = screen.getByRole('link', { name: 'Low Tide Radio' });
    expect(link.getAttribute('href')).toBe('/library/album/202');
    await userEvent.click(screen.getByRole('button', { name: "Why it's here" }));
    expect(screen.getByText('Plex album tags: Death-Doom Metal, doom metal · under it through Death-Doom Metal, Doom Metal')).toBeTruthy();
    const sets = within(screen.getByRole('navigation', { name: 'Which albums' }));
    expect(sets.getByRole('link', { name: 'Under it' }).getAttribute('href')).toBe('/tags/albums?tag=metal&set=under');
  });

  it('offers no missing set for a tag that is not broad', async () => {
    open('/tags/albums?tag=black%20metal&set=carries');
    expect(await screen.findByText('Albums carrying Black Metal')).toBeTruthy();
    const sets = within(screen.getByRole('navigation', { name: 'Which albums' }));
    expect(sets.queryByRole('link', { name: 'Missing it' })).toBeNull();
  });

  it('lists the artists carrying a tag', async () => {
    open('/tags/artists?tag=death%20metal');
    expect(await screen.findByText('Artists carrying Death Metal')).toBeTruthy();
    expect(screen.getByRole('link', { name: 'The Paper Lanterns' }).getAttribute('href')).toBe('/library/artist/302');
  });
});
