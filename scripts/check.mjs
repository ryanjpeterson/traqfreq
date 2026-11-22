// Brand fast checks (docs/specs/brand.md). No dependencies; exits 1 on any failure.
//   C1  no literal colours, fonts or radii outside tokens/
//   C7  nav/top-bar rules use chrome, chrome-ink or a module colour only
//   C2  exactly seven module colours, canonical values, never redefined per mode
//   C4  contrast of every text and mark pair, light and dark
//   T2 T3 W2  copy lint on web/src/copy/strings.json
// Usage: node scripts/check.mjs [--root <dir>]
import { readFileSync, readdirSync, statSync, existsSync } from 'node:fs';
import { dirname, join, relative, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

export const CANONICAL_MODULES = {
  L: '#E60012', H: '#0079C2', T: '#00843A', D: '#7354C2', M: '#B0006E', F: '#6D4C2F', S: 'ink',
};
export const MODULE_NAMES = ['LIBRARY', 'HISTORY', 'TAGS', 'DISCOVER', 'MIXES', 'FETCH', 'SETUP'];
const MODE_KEYS = new Set(['paper', 'ink', 'ink2', 'rule', 'card', 'chrome', 'chromeInk', 'markOutline']);

// ---------- colour maths (WCAG 2.x) ----------
export function luminance(hex) {
  let h = hex.replace('#', '');
  if (h.length === 3) h = [...h].map((c) => c + c).join('');
  const [r, g, b] = [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16) / 255)
    .map((c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4));
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}
export function contrast(a, b) {
  const [x, y] = [luminance(a), luminance(b)].sort((p, q) => q - p);
  return (x + 0.05) / (y + 0.05);
}

// ---------- C2 ----------
export function checkModules(tokens) {
  const out = [];
  const keys = Object.keys(tokens.modules ?? {});
  const want = Object.keys(CANONICAL_MODULES);
  if (keys.length !== 7 || want.some((k) => !keys.includes(k))) {
    out.push(['C2', `modules must be exactly ${want.join(' ')}; got ${keys.join(' ') || 'none'}`]);
  }
  for (const [k, v] of Object.entries(tokens.modules ?? {})) {
    if (CANONICAL_MODULES[k] && String(v.color).toUpperCase() !== CANONICAL_MODULES[k].toUpperCase()) {
      out.push(['C2', `module ${k} is ${v.color}, must be ${CANONICAL_MODULES[k]}`]);
    }
  }
  for (const [mode, vals] of Object.entries(tokens.modes ?? {})) {
    for (const k of Object.keys(vals)) {
      if (!MODE_KEYS.has(k)) out.push(['C2', `mode ${mode} defines "${k}"; modes may not add or retune colours`]);
    }
  }
  return out;
}

// ---------- C4 ----------
export function checkContrast(tokens) {
  const out = [];
  const need = (mode, what, fg, bg, min) => {
    const r = contrast(fg, bg);
    if (r < min) out.push(['C4', `${mode}: ${what} ${fg} on ${bg} is ${r.toFixed(2)}:1, needs ${min}:1`]);
  };
  for (const [mode, m] of Object.entries(tokens.modes ?? {})) {
    need(mode, 'ink', m.ink, m.paper, 7);
    need(mode, 'ink on card', m.ink, m.card, 4.5);
    need(mode, 'ink2', m.ink2, m.paper, 4.5);
    need(mode, 'ink2 on card', m.ink2, m.card, 4.5);
    need(mode, 'chromeInk', m.chromeInk, m.chrome, 4.5);
    const outlined = new Set(m.markOutline?.modules ?? []);
    for (const [k, mod] of Object.entries(tokens.modules ?? {})) {
      const fill = mod.color === 'ink' ? m.ink : mod.color;
      const text = mod.color === 'ink' ? m.paper : '#FFFFFF';
      need(mode, `text on ${mod.name ?? k}`, text, fill, 4.5);
      // Marks (bullets, bands, chart marks) are non-text: 3:1 against the ground.
      if (contrast(fill, m.paper) >= 3) continue;
      if (outlined.has(k)) need(mode, `${mod.name ?? k} mark outline`, m.markOutline.color, m.paper, 3);
      else out.push(['C4', `${mode}: ${mod.name ?? k} mark ${fill} on ${m.paper} is ${contrast(fill, m.paper).toFixed(2)}:1 and has no outline`]);
    }
  }
  return out;
}

// ---------- C1 / C7 ----------
const NAMED = 'aqua|black|blue|fuchsia|gray|grey|green|lime|maroon|navy|olive|orange|purple|red|silver|teal|white|yellow|pink|brown|gold';
const COLOUR_PROPS = /(?:^|[\s;{])((?:background(?:-color)?|color|border(?:-[a-z]+)*|outline(?:-color)?|fill|stroke|box-shadow|text-decoration-color)\s*:\s*([^;}]+))/gi;

export function lintStyleSource(text, file) {
  const out = [];
  const lines = text.split('\n');
  const isCss = file.endsWith('.css');
  lines.forEach((raw, i) => {
    const line = raw.replace(/\/\*.*?\*\//g, '').replace(/^\s*\/\/.*$/, '');
    const at = `${file}:${i + 1}`;
    if (/#[0-9a-fA-F]{3,8}\b/.test(line) && (isCss || /['"`][^'"`]*#[0-9a-fA-F]{3,8}\b/.test(line))) {
      out.push(['C1', `${at} literal hex colour`]);
    }
    if (/\b(?:rgba?|hsla?|hwb|lab|lch|oklab|oklch|color)\(/i.test(line)) out.push(['C1', `${at} literal colour function`]);
    const ff = line.match(/font-family\s*:\s*([^;}]+)|fontFamily\s*:\s*([^,}]+)/);
    if (ff && !/^\s*['"`]?\s*(?:var\(--[\w-]+\)|inherit)/.test(ff[1] ?? ff[2])) out.push(['C1', `${at} literal font family`]);
    const br = line.match(/border-radius\s*:\s*([^;}]+)|borderRadius\s*:\s*([^,}]+)/);
    if (br && !/^\s*['"`]?\s*(?:var\(--[\w-]+\)|0(?:px)?\b)/.test(br[1] ?? br[2])) out.push(['C1', `${at} literal radius`]);
    if (isCss) {
      for (const m of line.matchAll(COLOUR_PROPS)) {
        if (new RegExp(`\\b(?:${NAMED})\\b`, 'i').test(m[2])) out.push(['C1', `${at} named colour in "${m[1].trim()}"`]);
      }
    }
  });
  if (isCss) out.push(...lintNavRules(text, file));
  return out;
}

export function lintNavRules(text, file) {
  const out = [];
  for (const m of text.matchAll(/([^{}]+)\{([^{}]*)\}/g)) {
    const selector = m[1].trim();
    if (!/\b(?:nav|topbar|rail|bottombar|strip|dock)\b/i.test(selector.replace(/[.#]/g, ' '))) continue;
    for (const d of m[2].matchAll(/(background(?:-color)?|color)\s*:\s*([^;]+)/gi)) {
      for (const v of d[2].matchAll(/var\(--([\w-]+)\)/g)) {
        if (!/^(?:chrome|chrome-ink|mod-[a-z](?:-ink)?)$/.test(v[1])) {
          out.push(['C7', `${file} "${selector}" uses --${v[1]} for ${d[1]}; nav uses chrome, chrome-ink or a module colour`]);
        }
      }
    }
  }
  return out;
}

// ---------- T2 / T3 / W2 ----------
const PROPER = new Set(['Plex', 'Jellyfin', 'Navidrome', 'Tailscale', 'Last.fm', 'Mixxx', 'Ollama', 'Soulseek', 'Fira', 'Sans',
  'Berlin', 'Gelb', 'Mac', 'Junction', 'Spotify', 'MusicBrainz', 'Discogs', 'I']);
const ACRONYMS = new Set(['API', 'BPM', 'DB', 'URL', 'ID', 'KB/s', 'MB', 'GB', 'FLAC', 'MP3', 'AAC', 'OK', 'UTC', 'CSV', 'JSON', 'SQLite', 'AND', 'OR', 'NOT']);
const BANNED = ['magic', 'magical', 'smart', 'ai-powered', 'oops', 'whoops'];

export function lintCopy(strings, file = 'strings.json') {
  const out = [];
  for (const [key, s] of Object.entries(strings)) {
    const at = `${file} ${key}`;
    if (s.includes('!')) out.push(['W2', `${at}: no exclamation marks`]);
    if (/\p{Extended_Pictographic}/u.test(s)) out.push(['W2', `${at}: no emoji`]);
    for (const w of BANNED) if (new RegExp(`(?:^|[^\\w-])${w}(?![\\w-])`, 'i').test(s)) out.push(['W2', `${at}: banned word "${w}"`]);
    // Words with their position; a word after . ? : · or at the start begins a sentence.
    const words = [...s.matchAll(/[\p{L}][\p{L}\p{N}.'’/_-]*/gu)];
    words.forEach((m, i) => {
      const w = m[0].replace(/[.'’]+$/, '').replace(/['’]s$/, '');
      const before = s.slice(0, m.index).trimEnd();
      const starts = i === 0 || /[.?:·—]$/.test(before);
      const upper = w.toUpperCase();
      if (MODULE_NAMES.includes(upper)) {
        if (w !== upper && /^\p{Lu}/u.test(w)) out.push(['T2', `${at}: module name "${w}" must be ${upper}`]);
        return;
      }
      if (/[_\d]/.test(w) || ACRONYMS.has(w) || PROPER.has(w)) return;
      if (w.length > 1 && w === upper && /\p{Lu}/u.test(w)) { out.push(['T3', `${at}: "${w}" in capitals; only module names are`]); return; }
      if (!starts && /^\p{Lu}\p{Ll}/u.test(w)) out.push(['T3', `${at}: "${w}" should be lower case (sentence case)`]);
    });
  }
  return out;
}

// ---------- runner ----------
function walk(dir, exts, skip) {
  if (!existsSync(dir)) return [];
  return readdirSync(dir).flatMap((n) => {
    const p = join(dir, n);
    if (statSync(p).isDirectory()) return n === 'node_modules' || n === 'dist' ? [] : walk(p, exts, skip);
    return exts.some((e) => p.endsWith(e)) && !skip(p) ? [p] : [];
  });
}

export function runAll(root) {
  const problems = [];
  const tokenDir = join(root, 'tokens');
  for (const f of walk(tokenDir, ['.json'], (p) => p.endsWith('.schema.json'))) {
    const tokens = JSON.parse(readFileSync(f, 'utf8'));
    const rel = relative(root, f);
    problems.push(...[...checkModules(tokens), ...checkContrast(tokens)].map(([r, m]) => [r, `${rel}: ${m}`]));
  }
  const generated = (p) => p.endsWith(join('styles', 'tokens.css'));
  for (const f of walk(join(root, 'web', 'src'), ['.css', '.ts', '.tsx'], generated)) {
    problems.push(...lintStyleSource(readFileSync(f, 'utf8'), relative(root, f)));
  }
  const copy = join(root, 'web', 'src', 'copy', 'strings.json');
  if (existsSync(copy)) problems.push(...lintCopy(JSON.parse(readFileSync(copy, 'utf8')), relative(root, copy)));
  return problems;
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const i = process.argv.indexOf('--root');
  const root = resolve(i > 0 ? process.argv[i + 1] : join(dirname(fileURLToPath(import.meta.url)), '..'));
  const problems = runAll(root);
  for (const [rule, msg] of problems) console.log(`${rule}  ${msg}`);
  console.log(problems.length ? `\n${problems.length} brand problem(s).` : 'Brand checks: C1 C2 C4 C7 T2 T3 W2 pass.');
  process.exit(problems.length ? 1 : 0);
}
