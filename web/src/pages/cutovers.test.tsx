import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, within } from '@testing-library/react';
import { Shell } from '../App';
import { CORE_ONLY } from '../app/api';
import { rowText, unixUtc } from '../app/cutovers';
import ANSWERS from './cutovers.answers.json';

// T30: GET /api/cutovers on the fixture (invented rows), from scripts/cutovers_answers.py: before the copy; after the
// copy and one sync from the Plex stand-in ("clean"); and after a write on jimbo-dj's side ("moved").
const A = ANSWERS as Record<string, any>;  // eslint-disable-line @typescript-eslint/no-explicit-any

function api(cutovers: unknown) {
  vi.stubGlobal('fetch', vi.fn(async (url: string) => {
    if (url === '/api/modules') return { ok: true, status: 200, json: async () => ({ modules: CORE_ONLY }) };
    if (url === '/api/cutovers' && cutovers) return { ok: true, status: 200, json: async () => cutovers };
    return { ok: false, status: 503, json: async () => ({}) };
  }));
}

function open() {
  window.history.replaceState(null, '', '/setup');
  return render(<Shell />);
}

const card = async () => {
  const label = await screen.findByText('Cut-overs');
  return within(label.closest('.kit-card') as HTMLElement);
};

beforeEach(() => { window.scrollTo = vi.fn() as unknown as typeof window.scrollTo; });
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

describe('helpers', () => {
  it('formats unix seconds and rows as they are', () => {
    expect(unixUtc(1794200400, 'UTC')).toBe('2026-11-09 05:00 UTC');
    expect(unixUtc('1793844000', 'UTC')).toBe('2026-11-05 02:00 UTC');
    expect(unixUtc(null, 'UTC')).toBe('');
    expect(rowText({ id: 10, source: 'lastfm', album: null })).toBe('id 10 · source lastfm · album –');
  });
});

describe('the cut-overs card on SETUP', () => {
  it('before the copy: not copied, no check, no runs, the watcher off, the token never shown', async () => {
    api(A.before);
    open();
    const c = await card();
    expect(await c.findByText('Plex scan and play log')).toBeTruthy();
    expect(c.getByText('Not copied')).toBeTruthy();
    expect(c.getByText(/jimbo-dj still writes these tables/)).toBeTruthy();
    expect(c.queryByText('Switch-off check')).toBeNull();
    expect(c.getByText('No sync has run in traqfreq yet.')).toBeTruthy();
    expect(c.getByText('Off unless TRAQFREQ_WATCH=on.')).toBeTruthy();
    expect(c.getByText('http://plex.test:32400')).toBeTruthy();
    const sync = within(c.getByRole('list', { name: 'Plex sync' }));
    expect(sync.getByText('Set')).toBeTruthy();
    expect(document.body.textContent).not.toContain('invented-plex-token');
  });

  it('after the copy and a sync: traqfreq writes, nothing missed, the run with its reason and undo', async () => {
    api(A.clean);
    open();
    const c = await card();
    expect(await c.findByText('traqfreq writes')).toBeTruthy();
    expect(c.getByText('Nothing missed')).toBeTruthy();
    const runs = within(c.getByRole('list', { name: 'Runs' }));
    expect(runs.getByText('Done')).toBeTruthy();
    expect(runs.getByText(/^5 tracks read from Plex, 1 no longer there/)).toBeTruthy();
    expect(runs.getByText(/Why: Nightly sync · Undo: Nothing to undo/)).toBeTruthy();
  });

  it('after jimbo-dj wrote: names the new rows and the moved marks', async () => {
    api(A.moved);
    open();
    const c = await card();
    expect(await c.findByText('jimbo-dj wrote after the copy')).toBeTruthy();
    expect(c.getByText(/traqfreq has missed 1 new rows/)).toBeTruthy();
    const check = within(c.getByRole('list', { name: 'Switch-off check' }));
    expect(check.getAllByRole('listitem').map((li) => li.querySelector('strong')?.textContent))
      .toEqual(['listens', 'last_sync', 'max_listen_id']);
    expect(check.getByText('9 rows at the copy, 10 now · 1 new (id > … 9)')).toBeTruthy();
    expect(check.getByText('id 10 · source lastfm · started_at 1794200000 · artist Ada Vey · title Coil')).toBeTruthy();
    expect(check.getByText('1793844000 at the copy, 1794200200 now')).toBeTruthy();
  });

  it('says so when the cut-overs can\'t be read', async () => {
    api(null);
    open();
    expect(await screen.findByText('Can\'t read the cut-overs')).toBeTruthy();
  });
});
