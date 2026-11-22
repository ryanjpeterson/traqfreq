import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {
  ArtTile, Band, Button, Card, ConditionChip, LineBullet, LineLever, MODULE_IDS, NavItem, StationRow, Status, Text,
} from './index';

afterEach(cleanup);

describe('LineBullet', () => {
  it.each(MODULE_IDS)('module %s shows its badge and names the module', (m) => {
    render(<LineBullet module={m} />);
    const names = { L: 'LIBRARY', H: 'HISTORY', T: 'TAGS', D: 'DISCOVER', M: 'MIXES', F: 'FETCH', S: 'SETUP' };
    const nums = { L: 1, H: 2, T: 3, D: 4, M: 5, F: 6, S: 0 };
    const el = screen.getByRole('img', { name: names[m] });
    expect(el.textContent).toBe(`${m}${nums[m]}`);
    expect(el.className).toContain(`line-${m.toLowerCase()}`);
  });
  it.each([22, 24, 28, 36, 44] as const)('size %i', (size) => {
    render(<LineBullet module="H" size={size} />);
    expect(screen.getByRole('img').className).toContain(`kit-bullet-${size}`);
  });
  it('decorative bullets are hidden from screen readers', () => {
    const { container } = render(<LineBullet module="T" decorative />);
    expect(screen.queryByRole('img')).toBeNull();
    expect(container.firstElementChild!.getAttribute('aria-hidden')).toBe('true');
  });
});

describe('NavItem', () => {
  it('default: a real link, no aria-current', () => {
    render(<NavItem module="L" href="/library" />);
    const a = screen.getByRole('link', { name: 'LIBRARY' });
    expect(a.getAttribute('href')).toBe('/library');
    expect(a.getAttribute('aria-current')).toBeNull();
    expect(a.className).not.toContain('is-current');
  });
  it('current: aria-current=page and the module fill class', () => {
    render(<NavItem module="H" href="/history" current />);
    const a = screen.getByRole('link', { name: 'HISTORY' });
    expect(a.getAttribute('aria-current')).toBe('page');
    expect(a.className).toContain('is-current');
    expect(a.className).toContain('line-h');
  });
  it('onNavigate takes the click instead of a page load', async () => {
    const go = vi.fn();
    render(<NavItem module="S" href="/setup" onNavigate={go} />);
    await userEvent.click(screen.getByRole('link', { name: 'SETUP' }));
    expect(go).toHaveBeenCalledWith('/setup');
  });
});

describe('Status', () => {
  it.each([
    ['ready', 'Ready'],
    ['needs', 'Needs something'],
    ['off', 'Off'],
  ] as const)('%s: shape class and default word', (state, word) => {
    const { container } = render(<Status state={state} />);
    const el = container.firstElementChild!;
    expect(el.className).toContain(`is-${state}`);
    expect(el.textContent).toBe(word);
    expect(el.querySelector('.kit-status-mark')!.getAttribute('aria-hidden')).toBe('true');
  });
  it('takes its own word', () => {
    render(<Status state="needs" label="Needs a Plex token" />);
    expect(screen.getByText('Needs a Plex token')).toBeTruthy();
  });
});

describe('Band', () => {
  it('module name as a heading, with an optional screen name', () => {
    render(<Band module="T">Ladder</Band>);
    const h = screen.getByRole('heading', { level: 2 });
    expect(h.textContent).toBe('TAGS · Ladder');
  });
  it('name only', () => {
    const { container } = render(<Band module="F" />);
    expect(screen.getByRole('heading').textContent).toBe('FETCH');
    expect(container.firstElementChild!.className).toContain('line-f');
  });
});

describe('Button', () => {
  it.each(['primary', 'secondary', 'quiet'] as const)('%s is a real button', async (variant) => {
    const click = vi.fn();
    render(<Button variant={variant} onClick={click}>Go</Button>);
    const b = screen.getByRole('button', { name: 'Go' });
    expect(b.className).toContain(`is-${variant}`);
    expect(b.getAttribute('type')).toBe('button');
    await userEvent.click(b);
    expect(click).toHaveBeenCalledOnce();
  });
  it('disabled does not fire', async () => {
    const click = vi.fn();
    render(<Button disabled onClick={click}>Go</Button>);
    const b = screen.getByRole('button', { name: 'Go' }) as HTMLButtonElement;
    expect(b.disabled).toBe(true);
    await userEvent.click(b);
    expect(click).not.toHaveBeenCalled();
  });
  it('href renders a link; disabled with href stays a disabled button', () => {
    render(<><Button href="/rows">Rows</Button><Button href="/rows" disabled>Off</Button></>);
    expect(screen.getByRole('link', { name: 'Rows' }).getAttribute('href')).toBe('/rows');
    expect((screen.getByRole('button', { name: 'Off' }) as HTMLButtonElement).disabled).toBe(true);
  });
  it('submit type', () => {
    render(<Button type="submit">Send</Button>);
    expect(screen.getByRole('button').getAttribute('type')).toBe('submit');
  });
});

describe('ConditionChip', () => {
  it.each(['AND', 'OR', 'NOT', 'true', 'false'] as const)('operator %s in its own span', (op) => {
    const { container } = render(<ConditionChip op={op}>genre is house</ConditionChip>);
    expect(container.querySelector('.kit-chip-op')!.textContent).toBe(op);
    expect(screen.queryByRole('button')).toBeNull();
  });
  it('removable', async () => {
    const remove = vi.fn();
    render(<ConditionChip op="AND" onRemove={remove}>loved</ConditionChip>);
    await userEvent.click(screen.getByRole('button', { name: 'Remove condition' }));
    expect(remove).toHaveBeenCalledOnce();
  });
});

describe('LineLever', () => {
  const base = { module: 'H' as const, title: 'Played often', detail: 'Top plays', share: 40, count: 12 };
  it('read-only: percent and count, no slider', () => {
    const { container } = render(<LineLever {...base} />);
    expect(screen.queryByRole('slider')).toBeNull();
    expect(container.querySelector('.kit-lever-pct')!.textContent).toBe('40%');
    expect(container.querySelector('.kit-lever-count')!.textContent).toBe('12 tracks');
    expect((container.querySelector('.kit-lever-bar > span') as HTMLElement).style.width).toBe('40%');
  });
  it('adjustable: a labelled range input that reports the share', () => {
    const change = vi.fn();
    render(<LineLever {...base} onChange={change} />);
    const s = screen.getByRole('slider', { name: 'Played often' }) as HTMLInputElement;
    expect(s.value).toBe('40');
    s.focus();
    // fire a change through the DOM, as a drag would
    const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!;
    setter.call(s, '55');
    s.dispatchEvent(new Event('input', { bubbles: true }));
    expect(change).toHaveBeenCalledWith(55);
  });
  it('clamps the share to 0–100', () => {
    const { container } = render(<LineLever {...base} share={140} />);
    expect(container.querySelector('.kit-lever-pct')!.textContent).toBe('100%');
  });
  it('off: dashed class, slider disabled', () => {
    const { container } = render(<LineLever {...base} onChange={() => {}} off />);
    expect(container.firstElementChild!.className).toContain('is-off');
    expect((screen.getByRole('slider') as HTMLInputElement).disabled).toBe(true);
  });
});

describe('StationRow', () => {
  const row = { position: 3, module: 'H' as const, title: 'A title', artist: 'An artist', musicalKey: '8A', bpm: 124, why: 'Played 14 times.' };
  it('shows position, line, title, artist, key and BPM', () => {
    render(<ol><StationRow {...row} /></ol>);
    const li = screen.getByRole('listitem');
    expect(within(li).getByRole('img', { name: 'HISTORY' })).toBeTruthy();
    expect(li.textContent).toContain('A title');
    expect(li.textContent).toContain('An artist');
    expect(li.textContent).toContain('8A');
    expect(li.textContent).toContain('124 BPM');
  });
  it('why is closed, then opens and closes (B3)', async () => {
    render(<ol><StationRow {...row} /></ol>);
    const b = screen.getByRole('button', { name: "Why it's here" });
    expect(b.getAttribute('aria-expanded')).toBe('false');
    expect(screen.getByText('Played 14 times.').hidden).toBe(true);
    await userEvent.click(b);
    expect(b.getAttribute('aria-expanded')).toBe('true');
    expect(b.textContent).toBe('Hide why');
    expect(screen.getByText('Played 14 times.').hidden).toBe(false);
    expect(b.getAttribute('aria-controls')).toBe(screen.getByText('Played 14 times.').id);
  });
  it('defaultOpen; key and BPM optional', () => {
    render(<ol><StationRow position={1} module="T" title="T" artist="A" why="Tagged." defaultOpen /></ol>);
    expect(screen.getByText('Tagged.').hidden).toBe(false);
    expect(screen.getByRole('listitem').textContent).not.toContain('BPM');
  });
});

describe('Text', () => {
  it.each([
    ['title', 'H1'],
    ['heading', 'H2'],
    ['body', 'P'],
    ['label', 'P'],
    ['note', 'P'],
  ] as const)('%s renders %s', (variant, tag) => {
    const { container } = render(<Text variant={variant}>Words</Text>);
    expect(container.firstElementChild!.tagName).toBe(tag);
    expect(container.firstElementChild!.className).toContain(`is-${variant}`);
  });
});

describe('Card', () => {
  it('on: label on top', () => {
    const { container } = render(<Card label="Last scan">Body</Card>);
    expect(container.querySelector('.kit-card-label')!.textContent).toBe('Last scan');
    expect(container.firstElementChild!.className).not.toContain('is-off');
  });
  it('off: dashed', () => {
    const { container } = render(<Card label="Jellyfin" off>Off</Card>);
    expect(container.firstElementChild!.className).toContain('is-off');
  });
  it('no label', () => {
    const { container } = render(<Card>Body</Card>);
    expect(container.querySelector('.kit-card-label')).toBeNull();
  });
});

describe('ArtTile', () => {
  it('with art and code chip', () => {
    const { container } = render(<ArtTile title="A" artist="B" src="/art.jpg" musicalKey="8A" bpm={124} />);
    expect(container.querySelector('img')!.getAttribute('src')).toBe('/art.jpg');
    expect(container.querySelector('.kit-art-code')!.textContent).toBe('8A · 124 BPM');
    expect(container.querySelector('figcaption')!.textContent).toBe('AB');
  });
  it('without art: a word, not a blank', () => {
    const { container } = render(<ArtTile title="A" artist="B" />);
    expect(container.querySelector('img')).toBeNull();
    expect(screen.getByText('No artwork')).toBeTruthy();
    expect(container.querySelector('.kit-art-code')).toBeNull();
  });
  it('BPM only', () => {
    const { container } = render(<ArtTile title="A" artist="B" bpm={98} />);
    expect(container.querySelector('.kit-art-code')!.textContent).toBe('98 BPM');
  });
});

describe('NavItem, plain and wordmark (T4)', () => {
  it('a plain item has no bullet and fills with chrome-ink when current', () => {
    render(<NavItem label="Search" href="/search" current />);
    const a = screen.getByRole('link', { name: 'Search' });
    expect(a.className).toContain('is-plain');
    expect(a.className).toContain('is-current');
    expect(a.querySelector('.kit-bullet')).toBeNull();
  });
  it('wordmark', () => {
    render(<NavItem label="traqfreq" href="/" wordmark />);
    expect(screen.getByRole('link', { name: 'traqfreq' }).className).toContain('is-wordmark');
  });
  it('modified clicks follow the link instead of onNavigate', async () => {
    const nav = vi.fn();
    render(<NavItem module="T" href="/tags" onNavigate={nav} />);
    const a = screen.getByRole('link', { name: 'TAGS' });
    const plain = new MouseEvent('click', { bubbles: true, cancelable: true, button: 0 });
    a.dispatchEvent(plain);
    expect(nav).toHaveBeenCalledWith('/tags');
    expect(plain.defaultPrevented).toBe(true);
    const meta = new MouseEvent('click', { bubbles: true, cancelable: true, button: 0, metaKey: true });
    a.dispatchEvent(meta);
    expect(nav).toHaveBeenCalledTimes(1);
    expect(meta.defaultPrevented).toBe(false);
    meta.preventDefault(); // keep jsdom from trying to navigate
  });
});

describe('Button link with onClick (T4)', () => {
  it('routes client-side', async () => {
    const go = vi.fn();
    render(<Button href="/setup" onClick={go}>Open</Button>);
    await userEvent.click(screen.getByRole('link', { name: 'Open' }));
    expect(go).toHaveBeenCalledTimes(1);
  });
});
