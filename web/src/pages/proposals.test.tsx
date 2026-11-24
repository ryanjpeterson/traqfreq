import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Shell } from '../App';
import { parseRoute } from '../app/route';
import { fixInPlexHref, type Inbox, type ProposalAlbums } from '../app/tags';
import { changeWords, fixWords, proposalWhy, questionWords } from './TagsProposals';
import ANSWERS from './proposals.answers.json';
import LADDER from './tags.answers.json';

// T22: traqfreq's own answers on the fixture (scripts/make_fixture.py TAGS, TAGS_STORED), generated from its API.
const A = { ...LADDER, ...ANSWERS } as Record<string, any>;  // eslint-disable-line @typescript-eslint/no-explicit-any
const INBOX = A['/api/tags/proposals'] as Inbox;
const ON = { modules: ['L', 'H', 'T', 'D', 'M', 'F', 'S'].map((id) => ({ id, on: ['L', 'S', 'T'].includes(id), core: id === 'L' || id === 'S' })) };

function api(answers: Record<string, unknown>) {
  const f = vi.fn(async (url: string, init?: RequestInit) => {
    if (init?.method && init.method !== 'GET') throw new Error(`${init.method} ${url}: the inbox only reads`);
    if (!(url in answers)) return { ok: false, status: url.startsWith('/api/tags/') ? 404 : 503, json: async () => ({}) };
    return { ok: true, status: 200, json: async () => answers[url] };
  });
  vi.stubGlobal('fetch', f);
  return f;
}

function open(path: string, answers: Record<string, unknown> = A) {
  const f = api({ '/api/modules': ON, ...answers });
  window.history.replaceState(null, '', path);
  render(<Shell />);
  return f;
}

beforeEach(() => { window.scrollTo = vi.fn() as unknown as typeof window.scrollTo; });
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

describe('T22 routes', () => {
  it('parses the inbox and its albums', () => {
    expect(parseRoute('/tags/proposals')).toEqual({ page: 'module', module: 'T', sub: 'proposals' });
    expect(parseRoute('/tags/proposals/albums')).toEqual({ page: 'module', module: 'T', sub: 'proposalAlbums' });
  });
});

describe('the proposals inbox', () => {
  it('says nothing is applied and links to Fix in Plex in jimbo-dj', async () => {
    const f = open('/tags/proposals');
    expect(await screen.findByText('Not applied')).toBeTruthy();
    expect(screen.getByText(/Fix in Plex stays in jimbo-dj until P6/)).toBeTruthy();
    const link = screen.getByRole('link', { name: 'In jimbo-dj: Fix in Plex' });
    expect(link.getAttribute('href')).toBe(`${window.location.protocol}//${window.location.hostname}:4490/library/tags`);
    // No accept buttons: every button on the page is a link or a show/hide toggle, and nothing but GET is sent.
    for (const b of screen.queryAllByRole('button')) expect(b.textContent).toMatch(/^(Show|Hide)/);
    expect(f.mock.calls.every(([, init]) => !init || !(init as RequestInit).method || (init as RequestInit).method === 'GET')).toBe(true);
  });

  it('groups like jimbo-dj, each count opening its albums', async () => {
    open('/tags/proposals');
    expect((await screen.findByRole('link', { name: '3 albums with a proposed change' })).getAttribute('href')).toBe('/tags/proposals/albums?group=all');
    const kinds = within(screen.getByRole('list', { name: 'By kind of issue' }));
    expect(kinds.getByRole('link', { name: '2 albums, Missing its broad tag' }).getAttribute('href')).toBe('/tags/proposals/albums?group=kind&value=broad');
    expect(kinds.getByRole('link', { name: '2 albums, Too niche' })).toBeTruthy();
    const fixes = within(screen.getByRole('list', { name: 'By fix' }));
    const metal = INBOX.fixes.find((x) => x.tag === 'Metal')!;
    expect(fixes.getByRole('link', { name: '1 album, Add Metal' }).getAttribute('href')).toBe(`/tags/proposals/albums?group=fix&value=${metal.id}`);
    expect(fixes.getByText('Rename doom metal to Doom Metal')).toBeTruthy();
    const recs = within(screen.getByRole('list', { name: 'Suggested genres' }));
    expect(recs.getByRole('link', { name: '1 album, Drone' }).getAttribute('href')).toBe('/tags/proposals/albums?group=suggest&value=drone');
    expect(recs.getByText('not in use yet')).toBeTruthy();
    const ladder = within(screen.getByRole('list', { name: 'Ladder proposals' }));
    expect(ladder.getByText('Add Death Metal')).toBeTruthy();
    expect(ladder.getByRole('link', { name: '1 album, Death Metal' }).getAttribute('href')).toBe('/tags/proposals/albums?group=ladder&value=death%20metal');
    expect(screen.getAllByText(/^traqfreq's own, not jimbo-dj's\./).length).toBe(2);
    expect(screen.getByText(/^None: every broad tag rests on a tag's last word/)).toBeTruthy();
  });

  it('shows gate check 3 against the stored run', async () => {
    open('/tags/proposals');
    const card = within(await screen.findByRole('list', { name: "The audit, same as jimbo-dj's stored run" }));
    expect(card.getByText('13 of 13 tags have the same numbers')).toBeTruthy();
    expect(card.getByText('7 of 7 kinds of issue have the same album counts')).toBeTruthy();
    expect(card.getByText('4 of 4 top fixes the same')).toBeTruthy();
    expect(card.getByText('4 of 4 top suggestions the same')).toBeTruthy();
    expect(screen.getAllByText('All match').length).toBeGreaterThan(0);
  });

  it('lists the tags that differ, and passes a stale row', async () => {
    const c = structuredClone(INBOX.check);
    c.passed = true; c.fresh = false; c.matches = false;
    c.tags!.ok = 12; c.tags!.differ = 1; c.tags!.matches = false;
    c.tags!.differing = [{ key: 'black metal', name: 'Black Metal',
      traqfreq: { key: 'black metal', name: 'Black Metal', albums: 1, artists: 1, tracks: 2, musicbrainz: 0, sound: 1, issues: [] },
      jimbodj: { key: 'black metal', name: 'Black Metal', albums: 1, artists: 1, tracks: 3, musicbrainz: 0, sound: 1, issues: [] } }];
    open('/tags/proposals', { ...A, '/api/tags/proposals': { ...INBOX, check: c } });
    expect(await screen.findByText('12 of 13 tags have the same numbers')).toBeTruthy();
    expect(screen.getByText(/stored before jimbo-dj's latest data/)).toBeTruthy();
    await userEvent.click(screen.getByRole('button', { name: 'Show the 1 tags that differ' }));
    const rows = within(screen.getByRole('list', { name: 'Each tag that differs' }));
    expect(rows.getByText('jimbo-dj: 1 albums, 1 artists, 3 tracks, 0 MusicBrainz, 1 sound, 0 issues')).toBeTruthy();
  });

  it('is linked from the ladder', async () => {
    open('/tags');
    expect((await screen.findByRole('link', { name: 'Open the proposals inbox' })).getAttribute('href')).toBe('/tags/proposals');
  });
});

describe('the albums behind a number', () => {
  it('shows each album before and after, the way Fix in Plex previews it', async () => {
    open('/tags/proposals/albums?group=all');
    expect(await screen.findByRole('heading', { name: 'Every album with a proposed change' })).toBeTruthy();
    expect(screen.getByRole('link', { name: 'Low Tide Radio' }).getAttribute('href')).toBe('/tags/album/202');
    expect(screen.getByText(/^Before: Death-Doom Metal, doom metal · after: Death-Doom Metal, Doom Metal, Metal · changes: Rename doom metal to Doom Metal; Add Metal \(for Death-Doom Metal, Doom Metal\)/)).toBeTruthy();
    expect(screen.getByText(/suggested: Death Metal \(the artist's Plex genres, MusicBrainz artist 4 votes\)/)).toBeTruthy();
    expect(screen.getByText(/traqfreq's ladder: Death Metal \(for Death-Doom Metal\)/)).toBeTruthy();
    expect(screen.getByText(/^After: Fix in Plex's preview with these kinds of fix: missing its broad tag, non-standard spelling, odd casing/)).toBeTruthy();
  });

  it('keeps before and after the same for a kind Fix in Plex has no fix for', async () => {
    open('/tags/proposals/albums?group=kind&value=niche');
    expect(await screen.findByRole('heading', { name: 'Albums with an issue: Too niche' })).toBeTruthy();
    expect(screen.getByText(/^After: Fix in Plex has no fix for this kind/)).toBeTruthy();
    expect(screen.getAllByText(/unchanged: Fix in Plex has no fix for it/).length).toBe(2);
  });

  it('opens one fix', async () => {
    const metal = INBOX.fixes.find((x) => x.tag === 'Metal')!;
    open(`/tags/proposals/albums?group=fix&value=${metal.id}`);
    expect(await screen.findByRole('heading', { name: 'Albums this fix changes: Add Metal' })).toBeTruthy();
    expect(screen.getByText('1 album.')).toBeTruthy();
  });
});

describe('words', () => {
  it('says each fix and change', () => {
    expect(fixWords({ op: 'rename', tag: 'Techno/Breaks', to: ['Techno', 'Breaks'] })).toBe('Rename Techno/Breaks to Techno + Breaks');
    expect(fixWords({ op: 'add', tag: null, to: [] })).toBe('Give it a genre');
    expect(changeWords({ kind: 'broad', op: 'add', tag: 'Metal', because: ['Black Metal'] })).toBe('Add Metal (for Black Metal)');
    expect(questionWords({ key: 'drill and bass', tag: 'Drill and Bass', broad: 'Hip Hop', family: 'Hip hop', match: 'drill', last: 'Bass', albums: 1, artists: 0 }))
      .toBe('Hip Hop, from the word “drill”; Bass, its last word, has no broad tag. A question for the rules, not a fix.');
    const a = (A['/api/tags/proposals/albums?group=all'] as ProposalAlbums).items[0];
    expect(proposalWhy(a)).toMatch(/^Before: Lo-Fi Hip Hop, Soundtrack, 2010s · after: Lo-Fi Hip Hop, Soundtrack, Hip Hop · changes: Remove 2010s; Add Hip Hop \(for Lo-Fi Hip Hop\) · also: too niche: Remove Lo-Fi Hip Hop; too niche: Remove Soundtrack/);
    expect(fixInPlexHref(INBOX.fix_in_plex, { protocol: 'http:', hostname: 'macmini' })).toBe('http://macmini:4490/library/tags');
  });
});
