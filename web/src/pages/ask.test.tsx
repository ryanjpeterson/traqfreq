import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Shell } from '../App';
import { parseRoute } from '../app/route';
import { askApi, askRowsApi, askRowsHref } from '../app/playlists';
import ANSWERS from './ask.answers.json';

// T28: traqfreq's own answers on the fixture, generated from its API: the Ask box on a scratch copy with invented
// CLAP vectors (as tests/test_ask.py builds it), jimbodj-text and Ollama as stand-ins; the gate card's
// /api/playlists/compare on the fixture with the invented snapshots loaded.
const A = ANSWERS as Record<string, unknown>;
const Q = A._q as string;
const mods = (on: string[]) => ({ modules: ['L', 'H', 'T', 'D', 'M', 'F', 'S'].map((id) => ({ id, on: on.includes(id), core: id === 'L' || id === 'S' })) });

function open(path: string, answers: Record<string, unknown> = A) {
  const f = vi.fn(async (url: string, init?: RequestInit) => {
    if (init?.method && init.method !== 'GET') throw new Error(`${init.method} ${url}: the Ask box and the gate card only read`);
    const all: Record<string, unknown> = { '/api/modules': mods(['L', 'S']), ...answers };
    if (!(url in all)) return { ok: false, status: 503, json: async () => ({}) };
    return { ok: true, status: 200, json: async () => all[url] };
  });
  vi.stubGlobal('fetch', f);
  window.history.replaceState(null, '', path);
  render(<Shell />);
  return f;
}

beforeEach(() => { window.scrollTo = vi.fn() as unknown as typeof window.scrollTo; });
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

describe('T28 routes', () => {
  it('parses the nearest tracks page and builds its API', () => {
    expect(parseRoute('/library/junction/ask')).toEqual({ page: 'module', module: 'L', sub: 'askRows' });
    expect(askApi(Q)).toBe('/api/junction/ask?q=frozen+forest+at+night%2C+decade%3A2010s');
    expect(askRowsHref('frozen forest at night', 'death metal')).toBe('/library/junction/ask?q=frozen+forest+at+night&style=death+metal');
    expect(askRowsApi('?q=frozen+forest+at+night&style=death+metal')).toBe('/api/junction/ask/rows?q=frozen+forest+at+night&limit=200&style=death+metal');
  });
});

describe('the Ask box', () => {
  it('turns words into lines: typed, by sound and by Ollama, each with its counts and a way into the Junction', async () => {
    const f = open('/library/junction');
    const box = await screen.findByRole('searchbox', { name: 'Ask for a line' });
    expect(screen.getByText('No lines in the address yet.', { exact: false })).toBeTruthy();
    await userEvent.type(box, `${Q}{Enter}`);
    const lines = within(await screen.findByRole('region', { name: 'Lines from your words' }));
    expect(lines.getByText('Typed · 2010s · 2 tracks')).toBeTruthy();
    expect(lines.getByText('By sound · (atmospheric black metal or death metal) · 2010s · 2 tracks')).toBeTruthy();
    expect(lines.getByText('By Ollama · black metal · 2010s · 2 tracks')).toBeTruthy();
    // the sound line opens in the Junction
    const openSound = lines.getByRole('link', { name: 'Open in the Junction, By sound' });
    expect(openSound.getAttribute('href')).toBe('/library/junction?b=%28style%3Aatmospheric+black+metal%7Cstyle%3Adeath+metal%29%2Cdecade%3A2010s%7E60%7Efrozen+forest+at+night');
    // every number opens its rows (W3): the nearest tracks, and the ones each style is on
    expect(lines.getByRole('link', { name: '4 nearest tracks' }).getAttribute('href')).toBe('/library/junction/ask?q=frozen+forest+at+night');
    expect(lines.getByRole('link', { name: 'on 2 of the 4 nearest tracks, atmospheric black metal' }).getAttribute('href'))
      .toBe('/library/junction/ask?q=frozen+forest+at+night&style=atmospheric+black+metal');
    expect(lines.getByText('Kept: style:black metal, decade:2010s')).toBeTruthy();
    expect(lines.getByText('Dropped, not in the library: style:Shoegaze Polka, mood:glorious')).toBeTruthy();
    expect(f.mock.calls.every(([, init]) => !init || !(init as RequestInit).method || (init as RequestInit).method === 'GET')).toBe(true);
  });

  it('says when sound and Ollama are off', async () => {
    open('/library/junction');
    await userEvent.type(await screen.findByRole('searchbox', { name: 'Ask for a line' }), 'storm');
    await userEvent.click(screen.getByRole('button', { name: 'Ask' }));
    expect(await screen.findByText('No line came from those words.', { exact: false })).toBeTruthy();
    expect(screen.getByText(/the address of jimbo-dj's text server isn't set/)).toBeTruthy();
    expect(screen.getByText(/Ollama is off/)).toBeTruthy();
  });

  it('lists the nearest tracks with their scores', async () => {
    open('/library/junction/ask?q=frozen+forest+at+night');
    expect(await screen.findByText('“frozen forest at night” · 4 tracks')).toBeTruthy();
    expect(screen.getAllByText(/^Score [0-9.]+ for “frozen forest at night”\.$/)).toHaveLength(4);
    expect(screen.getAllByText('Score 1 for “frozen forest at night”.').length).toBeGreaterThan(0);
  });
});

describe('the P5 gate card', () => {
  it('shows the ten trees with their numbers, their coverage and how the gate is run (SETUP; LIBRARY shows the same card)', async () => {
    for (const path of ['/setup']) {
      open(path);
      const trees = within(await screen.findByRole('list', { name: 'The ten trees' }));
      expect(trees.getAllByRole('listitem')).toHaveLength(10);
      const night = trees.getByRole('link', { name: 'Night lines' });
      expect(night.getAttribute('href')).toBe('/library/playlists/night-lines');
      const row = within(night.closest('li') as HTMLElement);
      expect(row.getByText('Saved playlist · 3 lines')).toBeTruthy();
      expect(row.getByRole('link', { name: '4 tracks matched, Night lines' }).getAttribute('href')).toContain('/library/junction/rows?');
      expect(row.getByRole('link', { name: '4 tracks picked, Night lines' }).getAttribute('href')).toContain('which=picked');
      expect(trees.getByRole('link', { name: 'Every kind of condition' }).getAttribute('href')).toContain('/library/junction?b=');
      expect(screen.getByText('10 trees: every kind of condition is used.')).toBeTruthy();
      expect(screen.getByText('Compared by the gate script')).toBeTruthy();
      expect(screen.getByText(/Check 3 compares 10 playlists with jimbo-dj's own list/)).toBeTruthy();
      cleanup();
    }
  });
});
