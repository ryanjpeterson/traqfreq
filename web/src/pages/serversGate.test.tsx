import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Shell } from '../App';
import { CORE_ONLY } from '../app/api';
import { GATE_API } from '../app/servers';
import { ServersGateCard } from './ServersGate';
import ANSWERS from './serversGate.answers.json';

// T19: /api/servers/compare on the fixture (invented rows), generated from traqfreq itself with seed 19: as the
// fixture is (Navidrome hides four paths: not passed), and with Navidrome's real paths ("real:": passed).
const A = ANSWERS as Record<string, any>;  // eslint-disable-line @typescript-eslint/no-explicit-any

function api(answers: Record<string, unknown>) {
  const f = vi.fn(async (url: string) => {
    if (!(url in answers)) return { ok: false, status: 503, json: async () => ({}) };
    return { ok: true, status: 200, json: async () => answers[url] };
  });
  vi.stubGlobal('fetch', f);
  return f;
}

beforeEach(() => { window.scrollTo = vi.fn() as unknown as typeof window.scrollTo; });
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

describe('the P3 gate card', () => {
  it('says why it did not pass: Navidrome hides paths', async () => {
    api({ [GATE_API]: A[GATE_API] });
    render(<ServersGateCard navigate={() => {}} />);
    expect((await screen.findAllByText('Not passed')).length).toBe(3);  // the gate, checks 1 and 3
    expect(screen.getByText('5 live Plex copies, matched from the stored snapshots.')).toBeTruthy();
    const checks = within(screen.getByRole('list', { name: "The gate's three checks" }));
    expect(checks.getByText('1. One to one')).toBeTruthy();
    expect(checks.getByText('Plex and Jellyfin: 5 of 5 copies with a file the server has are matched; 5 matched in all; 0 without a real path.')).toBeTruthy();
    expect(checks.getByText('Not passed: Plex and Navidrome: 2 of 2 copies with a file the server has are matched; 4 matched in all; 4 without a real path.')).toBeTruthy();
    expect(checks.getByText(/^Plex and Navidrome: Plex 1 not matched \(Path hidden 1\), 4 matched of 5;/)).toBeTruthy();
    expect(screen.getByText(/^Navidrome gives no real path for 4 of 9 items/)).toBeTruthy();
    expect(checks.getAllByRole('link', { name: /^Show the rows/ })[0].getAttribute('href')).toBe('/setup/servers/matches?server=jellyfin');
  });

  it('opens the spot check sample, each answer said', async () => {
    api({ [GATE_API]: A[GATE_API] });
    render(<ServersGateCard navigate={() => {}} />);
    const n = A[GATE_API].checks[2].rows.length;
    await userEvent.click(await screen.findByRole('button', { name: `Show the sample (${n})` }));
    const rows = within(screen.getByRole('list', { name: "The spot check's sample" }));
    expect(rows.getAllByRole('listitem')).toHaveLength(n);
    expect(rows.getAllByText('Jellyfin (by file): same file, durations 0.0 s apart.').length).toBeGreaterThan(0);
    expect(rows.getAllByText(/^Navidrome \(.*\): no real path\.$/).length).toBeGreaterThan(0);
    expect(rows.getAllByText('Differs').length).toBe(A[GATE_API].checks[2].failed);
  });

  it('says passed when every check passes', async () => {
    api({ [GATE_API]: A[`real:${GATE_API}`] });
    render(<ServersGateCard navigate={() => {}} />);
    expect(await screen.findAllByText('Passed')).toHaveLength(4);  // the gate and its three checks
    expect(screen.queryByText('Not passed')).toBeNull();
  });

  it('says when it cannot run', async () => {
    api({});
    render(<ServersGateCard navigate={() => {}} />);
    expect(await screen.findByText("Can't run the gate. Open the servers page to check them, then reload.")).toBeTruthy();
  });

  it('is on SETUP', async () => {
    api({ '/api/modules': { modules: CORE_ONLY }, [GATE_API]: A[GATE_API] });
    window.history.replaceState(null, '', '/setup');
    render(<Shell />);
    expect(await screen.findByText('One song, three servers')).toBeTruthy();
    expect((await screen.findAllByText('Not passed')).length).toBeGreaterThan(0);
  });
});
