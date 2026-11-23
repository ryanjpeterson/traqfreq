import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Shell } from '../App';
import { CORE_ONLY } from '../app/api';
import { parseRoute } from '../app/route';
import { ageLabel, copiesTitle, copyQuery, matchQuery, matchesTitle } from '../app/servers';
import ANSWERS from './servers.answers.json';

// T15: the API's answers on the fixture (invented rows) with its invented Jellyfin and Navidrome snapshots, generated
// from traqfreq itself (snapshot ages pinned to 2 h). "nosnap:" answers come from a data dir with no snapshots.
const A = ANSWERS as Record<string, any>;  // eslint-disable-line @typescript-eslint/no-explicit-any
const MODULES = { modules: CORE_ONLY };

function api(answers: Record<string, unknown>) {
  const f = vi.fn(async (url: string) => {
    if (!(url in answers)) return { ok: false, status: 503, json: async () => ({}) };
    return { ok: true, status: 200, json: async () => answers[url] };
  });
  vi.stubGlobal('fetch', f);
  return f;
}

const all = (extra: Record<string, unknown> = {}) => ({ '/api/modules': MODULES, ...A, ...extra });
const noSnapshots = () => all({
  '/api/servers/matches': A['nosnap:/api/servers/matches'],
  '/api/servers/matches?rating_key=101': A['nosnap:/api/servers/matches?rating_key=101'],
  '/api/servers/matches?rating_key=105': A['nosnap:/api/servers/matches?rating_key=101'],
});

function open(path: string) {
  window.history.replaceState(null, '', path);
  return render(<Shell />);
}

beforeEach(() => { window.scrollTo = vi.fn() as unknown as typeof window.scrollTo; });
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

describe('routes and queries', () => {
  it('routes SERVERS and its rows pages to SETUP (no module of its own)', () => {
    expect(parseRoute('/setup/servers')).toEqual({ page: 'module', module: 'S', sub: 'servers' });
    expect(parseRoute('/setup/servers/copies')).toEqual({ page: 'module', module: 'S', sub: 'serverCopies' });
    expect(parseRoute('/setup/servers/matches/')).toEqual({ page: 'module', module: 'S', sub: 'serverMatches' });
    expect(parseRoute('/setup')).toEqual({ page: 'module', module: 'S' });
  });
  it('passes on only the filters the API knows', () => {
    expect(matchQuery('?server=navidrome&tier=tags&copy=4&offset=0')).toBe('server=navidrome&tier=tags');
    expect(matchQuery('?server=jellyfin', { offset: 50 })).toBe('server=jellyfin&offset=50');
    expect(copyQuery('?issue=multi_part&sort=x')).toBe('issue=multi_part');
  });
  it('titles a rows page by its filter', () => {
    expect(matchesTitle('?server=navidrome&tier=tags')).toBe('Plex and Navidrome · Matched by tags');
    expect(matchesTitle('?server=navidrome&reason=hidden_path')).toBe('Plex and Navidrome · Not matched · Path hidden');
    expect(matchesTitle('?reason=ambiguous')).toBe('Every pair · Not matched · Two candidates');
    expect(copiesTitle('?issue=multi_part')).toBe('Copies · with Multi-part');
    expect(copiesTitle('?has_file=true')).toBe('Copies · with a file key');
  });
  it('says how old a snapshot is', () => {
    expect(ageLabel(30)).toBe('30 s');
    expect(ageLabel(600)).toBe('10 min');
    expect(ageLabel(7200)).toBe('2 h');
    expect(ageLabel(86400 * 18)).toBe('18 days');
  });
});

describe('the SERVERS page', () => {
  it('shows the three servers, each with its status and snapshot age', async () => {
    api(all());
    open('/setup/servers');
    const plex = (await screen.findByText('Fixture Plex')).closest('section')!;
    expect(within(plex).getByText('Read through jimbo-dj')).toBeTruthy();
    expect(within(plex).getByText('5 copies')).toBeTruthy();
    expect(screen.getAllByText('Not set up')).toHaveLength(2);
    expect(screen.getByText('Snapshot 2 h old: 14 items')).toBeTruthy();
    expect(screen.getByText('Snapshot 2 h old: 9 items')).toBeTruthy();
    expect(screen.getByText(/4 items without a real path/)).toBeTruthy();
    expect(screen.queryByText(/TRAQFREQ_JELLYFIN_KEY.*set \(not shown\)/)).toBeNull();
  });

  it('shows the identity counts, each opening its copies', async () => {
    api(all());
    const user = userEvent.setup();
    open('/setup/servers');
    expect(await screen.findByText('5 copies, 5 files and 5 songs; 4 copies with no issue.')).toBeTruthy();
    const issues = screen.getByRole('list', { name: 'Issues' });
    const multi = within(issues).getByRole('link', { name: /show the rows: Multi-part/ });
    expect(multi.getAttribute('href')).toBe('/setup/servers/copies?issue=multi_part');
    expect(within(issues).queryByRole('link', { name: /No path/ })).toBeNull();  // zero opens nothing
    await user.click(multi);
    expect(window.location.pathname + window.location.search).toBe('/setup/servers/copies?issue=multi_part');
    expect(await screen.findByText('Copies · with Multi-part')).toBeTruthy();
    expect(screen.getByText('Static Gulls')).toBeTruthy();
    expect(screen.getByText(/Rule: live copies, with multi_part/)).toBeTruthy();
  });

  it('shows each pair by tier and by reason (bars as a list with a summary), each count opening its rows', async () => {
    api(all());
    open('/setup/servers');
    expect(await screen.findByText('4 matched: 5 Plex copies to 4 of 9 Navidrome items. Not matched: 1 Plex copy, 5 Navidrome items.')).toBeTruthy();
    const tiers = screen.getByRole('list', { name: 'Plex and Navidrome: matched by tier' });
    expect(within(tiers).getAllByRole('listitem')).toHaveLength(3);
    expect(within(tiers).getByRole('link', { name: /By tags/ }).getAttribute('href')).toBe('/setup/servers/matches?server=navidrome&tier=tags');
    const reasons = screen.getByRole('list', { name: 'Plex and Navidrome: not matched by reason' });
    const hidden = within(reasons).getByRole('link', { name: /Path hidden/ });
    expect(hidden.textContent).toMatch(/^3/);
    expect(within(reasons).getByText('1 Plex copy, 2 Navidrome items')).toBeTruthy();
    expect(screen.getByRole('list', { name: 'Jellyfin and Navidrome: matched by tier' })).toBeTruthy();
    expect(document.querySelectorAll('.srv-bar[aria-hidden="true"]').length).toBeGreaterThan(0);
  });

  it('opens the rows behind a reason, each saying why', async () => {
    api(all());
    const user = userEvent.setup();
    open('/setup/servers/matches?server=navidrome&reason=hidden_path');
    expect(await screen.findByText('Plex and Navidrome · Not matched · Path hidden')).toBeTruthy();
    expect(screen.getByText('3 rows, 1–3.')).toBeTruthy();
    expect(screen.getByText('Only on Plex · Ada Vey · Quiet Engines')).toBeTruthy();
    expect(screen.getAllByText(/^Only on Navidrome/)).toHaveLength(2);
    await user.click(screen.getAllByRole('button', { name: "Why it's here" })[0]);
    expect(screen.getByText(/Plex 105: Ada Vey\/Quiet Engines\/01 Coil.flac · Not matched: Path hidden/)).toBeTruthy();
  });

  it("gives a song's three IDs, with the tier or the reason on each server", async () => {
    api(all());
    const user = userEvent.setup();
    open('/setup/servers');
    const pick = await screen.findByRole('navigation', { name: 'Copies to pick from' });
    expect(within(pick).getAllByRole('link')).toHaveLength(5);
    const first = await screen.findByText(/rating key 105/);
    const card = first.closest('section')!;
    expect(within(card).getByText(/Path hidden: The server gives no real path/)).toBeTruthy();  // Navidrome hides 105
    await user.click(within(pick).getByRole('link', { name: 'Static Gulls · The Paper Lanterns' }));
    expect(window.location.search).toBe('?copy=104');
    expect(await screen.findByText(/matched by tags \(multi-part\) · path hidden/)).toBeTruthy();
    expect(screen.getByText('a0000000000000000000000000000068')).toBeTruthy();
    expect(screen.getByText('b0000000000000000000000000000068')).toBeTruthy();
    expect(within(pick).getByRole('link', { name: 'Static Gulls · The Paper Lanterns' }).getAttribute('aria-current')).toBe('page');
  });

  it('with no snapshot, says so in each server and each pair', async () => {
    api(noSnapshots());
    open('/setup/servers');
    expect(await screen.findAllByText('No snapshot of Jellyfin yet, so nothing on it is matched.')).not.toHaveLength(0);
    expect(screen.getByText('No snapshot of Jellyfin yet, so this pair isn\'t matched.')).toBeTruthy();
    expect(screen.getByText('No snapshot of Navidrome yet, so this pair isn\'t matched.')).toBeTruthy();
    expect(screen.getByText('No snapshot of Jellyfin, Navidrome yet, so this pair isn\'t matched.')).toBeTruthy();
    expect(screen.queryByRole('list', { name: /matched by tier/ })).toBeNull();
  });

  it('offers no refresh for a server that is not set up (T16)', async () => {
    const f = api(all());
    open('/setup/servers');
    const jf = (await screen.findByRole('button', { name: 'Refresh Jellyfin' })) as HTMLButtonElement;
    expect(jf.disabled).toBe(true);
    expect((screen.getByRole('button', { name: 'Refresh Navidrome' }) as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByText('Set up Jellyfin to refresh it (the settings above).')).toBeTruthy();
    expect(screen.getAllByText('Never refreshed.')).toHaveLength(2);
    expect(screen.queryByRole('button', { name: 'Refresh Plex' })).toBeNull();  // Plex is jimbo-dj's sync
    expect((f.mock.calls as unknown[][]).some((c) => (c[1] as RequestInit | undefined)?.method === 'POST')).toBe(false);
  });

  it('refreshes a set-up server, then shows the last refresh and its log (T16)', async () => {
    const answers: Record<string, unknown> = all({
      '/api/servers': A['setup:/api/servers'],
      '/api/servers/jellyfin/refreshes?limit=5': A['setup:/api/servers/jellyfin/refreshes?limit=5'],
      '/api/servers/navidrome/refreshes?limit=5': A['setup:/api/servers/navidrome/refreshes?limit=5'],
    });
    const posts: string[] = [];
    let next: 'ok' | 'failed' = 'ok';
    vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
      if (init?.method === 'POST') {
        posts.push(url);
        const body = A[`setup:refresh-${next}`];
        return { ok: next === 'ok', status: next === 'ok' ? 200 : 502, json: async () => body };
      }
      if (!(url in answers)) return { ok: false, status: 503, json: async () => ({}) };
      return { ok: true, status: 200, json: async () => answers[url] };
    }));
    const user = userEvent.setup();
    open('/setup/servers');
    const jf = await screen.findByRole('button', { name: 'Refresh Jellyfin' });
    expect((jf as HTMLButtonElement).disabled).toBe(false);
    expect(screen.getByText(/Only reads Jellyfin, page by page.*Nothing is written to Jellyfin\./)).toBeTruthy();
    const log = await screen.findByRole('list', { name: 'Jellyfin refresh log' });
    expect(within(log).getAllByRole('listitem')).toHaveLength(2);
    expect(within(log).getByText('14 items in 2 pages and 3 requests; 14 new, 0 gone; 0.0 s')).toBeTruthy();
    expect(within(log).getByText('Jellyfin answered 500 Internal Server Error (GET /Items): Database is locked')).toBeTruthy();
    expect(screen.getByText(/^Last refresh .*: failed, the snapshot before it is kept$/)).toBeTruthy();
    await user.click(jf);
    expect(posts).toEqual(['/api/servers/jellyfin/refresh']);
    expect(await screen.findByText('Refreshed: 14 items')).toBeTruthy();
    next = 'failed';
    await user.click(screen.getByRole('button', { name: 'Refresh Jellyfin' }));
    expect(await screen.findByText('Refresh failed')).toBeTruthy();
    expect(screen.getAllByText('Jellyfin answered 500 Internal Server Error (GET /Items): Database is locked').length).toBeGreaterThan(1);
  });

  it('SETUP has a servers card opening the page', async () => {
    api(all());
    open('/setup');
    const link = await screen.findByRole('link', { name: 'Open servers' });
    expect(link.getAttribute('href')).toBe('/setup/servers');
  });
});

describe("LIBRARY's track page: On servers", () => {
  it("shows each server's item, tier and play count, labelled, never added", async () => {
    api(all());
    open('/library/track/101');
    const label = await screen.findByText('On servers');
    const card = label.closest('section')!;
    const list = await within(card).findByRole('list', { name: 'On servers' });
    expect(await within(list).findByText(/matched by file · Kollektiv Nord\/Ringbahn\/01 Westkreuz.flac · 5 min 12 s · 4 plays on Jellyfin/)).toBeTruthy();
    expect(within(list).getByText(/2 plays on Navidrome/)).toBeTruthy();
    expect(within(list).getByText(/3 plays on Plex/)).toBeTruthy();
    expect(within(card).getByText(/never added to traqfreq's plays: nothing counts twice/)).toBeTruthy();
    // the page's own plays stay traqfreq's (3): Jellyfin's 4 and Navidrome's 2 aren't added to them
    expect(document.querySelector('.hist-big')!.textContent).toBe('3 plays');
    expect(within(card).getByRole('link', { name: 'Show how it was matched' }).getAttribute('href')).toBe('/setup/servers/matches?rating_key=101');
  });

  it('with no snapshot, each server says so', async () => {
    api(noSnapshots());
    open('/library/track/101');
    const list = await screen.findByRole('list', { name: 'On servers' });
    expect(within(list).getAllByText(/No snapshot of (Jellyfin|Navidrome) yet/)).toHaveLength(2);
  });
});
