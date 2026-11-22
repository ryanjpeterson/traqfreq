// Turns tokens/<direction>.json into CSS custom properties (web/src/styles/tokens.css).
// Usage: node scripts/build-tokens.mjs [tokens/berlin.json] [out.css]
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const MODE_KEYS = ['paper', 'ink', 'ink2', 'rule', 'card', 'chrome', 'chromeInk'];
const kebab = (s) => s.replace(/[A-Z]/g, (c) => '-' + c.toLowerCase());

function modeBlock(tokens, mode) {
  const m = tokens.modes[mode];
  const lines = MODE_KEYS.map((k) => `  --${kebab(k)}: ${m[k]};`);
  const outlined = new Set(m.markOutline?.modules ?? []);
  for (const letter of Object.keys(tokens.modules)) {
    const o = outlined.has(letter) ? `${m.markOutline.width} solid ${m.markOutline.color}` : 'none';
    lines.push(`  --mark-outline-${letter.toLowerCase()}: ${o};`);
  }
  return lines.join('\n');
}

export function buildCss(tokens) {
  const base = [
    `  --font: ${tokens.font};`,
    `  --label-font: ${tokens.labelFont};`,
    `  --radius: ${tokens.radius};`,
    `  --card-radius: ${tokens.cardRadius};`,
    `  --h1: ${tokens.h1};`,
    `  --h1-weight: ${tokens.h1Weight};`,
    `  --h1-tracking: ${tokens.h1Tracking};`,
    `  --label-case: ${tokens.labelCase};`,
    `  --label-tracking: ${tokens.labelTracking};`,
    `  --pad: ${tokens.padding};`,
    `  --top-rule: ${tokens.topRule};`,
  ];
  for (const [letter, mod] of Object.entries(tokens.modules)) {
    const v = mod.color === 'ink' ? 'var(--ink)' : mod.color;
    base.push(`  --mod-${letter.toLowerCase()}: ${v};`);
    // Text on a line colour: white; on SETUP's ink: paper (C4).
    base.push(`  --mod-${letter.toLowerCase()}-ink: ${mod.color === 'ink' ? 'var(--paper)' : '#FFFFFF'};`);
  }
  // Heatmap levels (D2: the module's colour): 0 = no plays (an empty mode colour), 1-4 = the module colour
  // mixed into paper, so each mode gets its own tints from the same token.
  if (tokens.heat) {
    const mod = `var(--mod-${tokens.heat.module.toLowerCase()})`;
    base.push(`  --heat-0: var(--${kebab(tokens.heat.empty)});`);
    tokens.heat.levels.forEach((pct, i) => {
      base.push(`  --heat-${i + 1}: ${pct >= 100 ? mod : `color-mix(in srgb, ${mod} ${pct}%, var(--paper))`};`);
    });
  }
  return [
    `/* Generated from tokens (${tokens.name} ${tokens.version}) by scripts/build-tokens.mjs. Do not edit. */`,
    `:root {\n${base.join('\n')}\n${modeBlock(tokens, 'light')}\n  color-scheme: light;\n}`,
    `@media (prefers-color-scheme: dark) {\n  :root:not([data-theme="light"]) {\n${modeBlock(tokens, 'dark').replace(/^/gm, '  ')}\n    color-scheme: dark;\n  }\n}`,
    `:root[data-theme="dark"] {\n${modeBlock(tokens, 'dark')}\n  color-scheme: dark;\n}`,
    '',
  ].join('\n\n');
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const src = resolve(ROOT, process.argv[2] ?? 'tokens/berlin.json');
  const out = resolve(ROOT, process.argv[3] ?? 'web/src/styles/tokens.css');
  mkdirSync(dirname(out), { recursive: true });
  writeFileSync(out, buildCss(JSON.parse(readFileSync(src, 'utf8'))));
  console.log(`tokens → ${out}`);
}
