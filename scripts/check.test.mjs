// node --test scripts/  — proves the brand checks catch what they should.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import {
  checkContrast, checkModules, contrast, lintCopy, lintJsxCopy, lintKitFolder, lintLineVars, lintNavRules, lintPageImports, lintStyleSource,
} from './check.mjs';
import { buildCss } from './build-tokens.mjs';

const berlin = JSON.parse(readFileSync(new URL('../tokens/berlin.json', import.meta.url)));
const rules = (ps) => ps.map(([r]) => r);

test('contrast maths', () => {
  assert.equal(contrast('#000000', '#FFFFFF').toFixed(1), '21.0');
  assert.ok(contrast('#FFFFFF', '#0079C2') >= 4.5);
});

test('Berlin tokens pass C2 and C4', () => {
  assert.deepEqual(checkModules(berlin), []);
  assert.deepEqual(checkContrast(berlin), []);
});

test('C2: an eighth colour or a retuned module fails', () => {
  const t = structuredClone(berlin);
  t.modules.X = { name: 'EXTRA', color: '#123456' };
  t.modules.H.color = '#0088DD';
  t.modes.dark.accent = '#FF00FF';
  assert.equal(rules(checkModules(t)).filter((r) => r === 'C2').length, 3);
});

test('C4: dark-mode MIXES and FETCH need their paper outline', () => {
  const t = structuredClone(berlin);
  delete t.modes.dark.markOutline;
  const msgs = checkContrast(t).map(([, m]) => m).join('\n');
  assert.match(msgs, /MIXES mark/);
  assert.match(msgs, /FETCH mark/);
  assert.doesNotMatch(msgs, /LIBRARY mark/);
});

test('C4: weak ink2 fails', () => {
  const t = structuredClone(berlin);
  t.modes.light.ink2 = '#999999';
  assert.ok(rules(checkContrast(t)).includes('C4'));
});

test('C1: literal colours, fonts and radii fail; tokens pass', () => {
  const bad = '.a { color: #333; background: rgb(0,0,0); font-family: Helvetica; border-radius: 4px; border: 1px solid red; }';
  assert.equal(lintStyleSource(bad, 'x.css').filter(([r]) => r === 'C1').length, 5);
  const good = '.a { color: var(--ink); font-family: var(--font); border-radius: var(--radius); border: 1px solid var(--rule); }';
  assert.deepEqual(lintStyleSource(good, 'x.css'), []);
  assert.equal(lintStyleSource("const s = { color: '#FF0000', fontFamily: 'Arial' };", 'x.tsx').length, 2);
});

test('C7: nav rules use chrome or module colours only', () => {
  assert.deepEqual(rules(lintStyleSource('.topbar { background: var(--card); }', 'x.css')), ['C7']);
  assert.deepEqual(lintStyleSource('.nav-item { background: var(--mod-h); color: var(--mod-h-ink); }', 'x.css'), []);
});

test('T2 T3 W2 copy lint', () => {
  const bad = {
    a: 'Open your Library', b: 'Update In Plex', c: 'UPDATE now', d: 'Oops! Download failed',
    e: 'Smart picks 🎧', f: 'Set-up is done',
  };
  const got = rules(lintCopy(bad));
  for (const r of ['T2', 'T3', 'W2']) assert.ok(got.includes(r), r);
  const good = {
    a: 'Update in Plex', b: 'LIBRARY · Browse', c: "Can't reach Plex. Pages show the last scan from 03:12.",
    d: 'Connect Plex, Jellyfin or Navidrome in SETUP to see your library here.', e: '1,932 plays merged',
  };
  assert.deepEqual(lintCopy(good), []);
});

test('token build writes light, dark and outline variables', () => {
  const css = buildCss(berlin);
  assert.match(css, /--chrome: #F0D722;/);
  assert.match(css, /--mod-s: var\(--ink\);/);
  assert.match(css, /prefers-color-scheme: dark[\s\S]*--mark-outline-m: 1px solid #FFFFFF;/);
  assert.match(css, /:root\[data-theme="dark"\][\s\S]*--mark-outline-f: 1px solid #FFFFFF;/);
  assert.match(css, /:root \{[\s\S]*--mark-outline-m: none;/);
});

test('C7 accepts the kit line indirection only when it points at module tokens', () => {
  assert.deepEqual(lintNavRules('.kit-nav.is-current { background: var(--line); color: var(--line-ink); }', 'k.css'), []);
  assert.deepEqual(rules(lintNavRules('.kit-nav { background: var(--card); }', 'k.css')), ['C7']);
  assert.deepEqual(lintLineVars('.line-m { --line: var(--mod-m); --line-ink: var(--mod-m-ink); --line-outline: var(--mark-outline-m); }', 'k.css'), []);
  assert.deepEqual(rules(lintLineVars('.line-x { --line: var(--card); --line-ink: var(--ink); --line-outline: 1px solid var(--ink); }', 'k.css')), ['C7', 'C7', 'C7']);
});

test('K1 catches non-kit imports, unknown kit names, UI packages and raw controls', () => {
  const ok = `import { useState } from 'react';\nimport { Button, Card, type ModuleId } from './components/kit';\nimport { t } from './copy/t';\nexport const A = () => <main><Button>{t('x')}</Button></main>;`;
  assert.deepEqual(lintPageImports(ok, 'App.tsx'), []);
  assert.deepEqual(rules(lintPageImports(`import { Fancy } from './components/fancy/Fancy';`, 'a.tsx')), ['K1']);
  assert.deepEqual(rules(lintPageImports(`import { Button, Modal } from './components/kit';`, 'a.tsx')), ['K1']);
  assert.deepEqual(rules(lintPageImports(`import { Dialog } from '@radix-ui/react-dialog';`, 'a.tsx')), ['K1']);
  assert.deepEqual(rules(lintPageImports(`export const A = () => <div><button>{t('x')}</button><a href="/">{t('y')}</a></div>;`, 'a.tsx')), ['K1', 'K1']);
});

test('K1 allows only the eleven components in the kit folder', () => {
  assert.deepEqual(lintKitFolder(['Button.tsx', 'Button.test.tsx', 'index.ts', 'modules.ts', 'kit.css']), []);
  assert.deepEqual(rules(lintKitFolder(['Button.tsx', 'Modal.tsx'])), ['K1']);
});

test('W1 catches copy literals in JSX text and text attributes', () => {
  assert.deepEqual(rules(lintJsxCopy(`const A = () => <p>Save the playlist</p>;`, 'a.tsx')), ['W1']);
  assert.deepEqual(rules(lintJsxCopy(`const A = () => <Button aria-label="Close">{t('x')}</Button>;`, 'a.tsx')), ['W1']);
  assert.deepEqual(rules(lintJsxCopy(`const A = () => <Card label="Last scan" />;`, 'a.tsx')), ['W1']);
  const ok = [
    `const [s, set] = useState<Summary | null>(null);`,
    `const A = () => <p>{t('x')}: {n}</p>;`,
    `const B = (e: Event) => e.preventDefault();`,
    `const C = () => <span aria-hidden="true">×</span>;`,
    `const D = () => <Status state="ready" />;`,
    `if (a > b && c < d) go();`,
  ].join('\n');
  assert.deepEqual(lintJsxCopy(ok, 'ok.tsx'), []);
});
