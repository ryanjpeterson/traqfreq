// Brand fast checks (docs/specs/brand.md). No dependencies; exits 1 on any failure.
//   C1  no literal colours, fonts or radii outside tokens/
//   C7  nav/top-bar rules use chrome, chrome-ink or a module colour only
//   C2  exactly seven module colours, canonical values, never redefined per mode
//   C4  contrast of every text and mark pair, light and dark
//   T2 T3 W2  copy lint on every web/src/**/*strings.json
//   K1  pages use only the eleven kit components: kit imports by name, no other UI imports, no raw controls
//   W1  no copy literals in JSX outside the strings files (text nodes and text attributes)
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
  if (isCss) out.push(...lintNavRules(text, file), ...lintLineVars(text, file));
  return out;
}

// --line / --line-ink / --line-outline are the kit's per-module indirection: they may only point at module tokens.
export function lintLineVars(text, file) {
  const out = [];
  for (const m of text.matchAll(/--line(-ink|-outline)?\s*:\s*([^;}]+)/g)) {
    const want = m[1] === '-outline' ? /^var\(--mark-outline-[a-z]\)$/ : new RegExp(`^var\\(--mod-[a-z]${m[1] ?? ''}\\)$`);
    if (!want.test(m[2].trim())) out.push(['C7', `${file} --line${m[1] ?? ''} is "${m[2].trim()}"; it must point at a module token`]);
  }
  return out;
}

// ---------- K1 / W1 ----------
export const KIT = ['LineBullet', 'NavItem', 'Status', 'Band', 'Button', 'ConditionChip', 'LineLever', 'StationRow', 'Text', 'Card', 'ArtTile'];
const KIT_EXTRAS = ['MODULE_IDS', 'ModuleId', 'type ModuleId'];
const ALLOWED_PACKAGES = /^(?:react|react\/jsx-runtime|react-dom|react-dom\/client|@fontsource\/[\w./-]+)$/;
const RAW_CONTROLS = /<(button|input|select|textarea|a|img|svg|canvas)\b/g;

/** K1 for a page or app file (anything under web/src outside components/kit and tests). */
export function lintPageImports(text, file) {
  const out = [];
  for (const m of text.matchAll(/^\s*import\s+(?:type\s+)?(?:([\s\S]*?)\s+from\s+)?['"]([^'"]+)['"]/gm)) {
    const [, what = '', from] = m;
    if (from.startsWith('.')) {
      if (/(?:^|\/)components\//.test(from) && !/components\/kit$/.test(from)) {
        out.push(['K1', `${file} imports "${from}"; import the kit from components/kit`]);
      } else if (/components\/kit$/.test(from)) {
        const names = (what.match(/\{([^}]*)\}/)?.[1] ?? '').split(',').map((n) => n.trim().split(/\s+as\s+/)[0]).filter(Boolean);
        for (const n of names) if (!KIT.includes(n) && !KIT_EXTRAS.includes(n)) out.push(['K1', `${file} imports "${n}" from the kit; only the eleven components`]);
      }
    } else if (!ALLOWED_PACKAGES.test(from) && !from.endsWith('.css')) {
      out.push(['K1', `${file} imports the package "${from}"; UI comes from the kit only`]);
    }
  }
  if (file.endsWith('.tsx')) {
    text.split('\n').forEach((line, i) => {
      for (const m of line.matchAll(RAW_CONTROLS)) out.push(['K1', `${file}:${i + 1} raw <${m[1]}>; use a kit component`]);
    });
  }
  return out;
}

/** K1 for the kit folder itself: only the eleven components (plus their helpers and tests). */
export function lintKitFolder(names) {
  const helpers = new Set(['index.ts', 'modules.ts', 'kit.css']);
  return names
    .filter((n) => !helpers.has(n) && !/\.test\.tsx?$/.test(n) && !KIT.includes(n.replace(/\.tsx$/, '')))
    .map((n) => ['K1', `web/src/components/kit/${n} is not one of the eleven kit components`]);
}

const TEXT_ATTRS = /\b(aria-label|title|alt|placeholder|label|detail|why|aria-description)=(["'])([^"']*\p{L}[^"']*)\2/gu;

/** W1: copy in JSX comes from strings.json via t(), never a literal. */
export function lintJsxCopy(text, file) {
  const out = [];
  const src = text.replace(/\/\*[\s\S]*?\*\//g, (c) => c.replace(/[^\n]/g, ' '));
  src.split('\n').forEach((raw, i) => {
    const line = raw.replace(/^\s*\/\/.*$/, '');
    const at = `${file}:${i + 1}`;
    // A text node: after a tag's closing > (not =>) up to the next < or {, holding a letter.
    for (const m of line.matchAll(/(?<=[\w"'}\/])(?<![=-])>([^<>{}]*\p{L}[^<>{}]*)(?=<|\{|$)/gu)) {
      const s = m[1].trim();
      if (s && !/^[)\]};,.:&|?]/.test(s) && !/[;=]\s*$/.test(s) && !/^(?:as|extends|from)\b/.test(s)) out.push(['W1', `${at} copy literal "${s}" in JSX; use t()`]);
    }
    for (const m of line.matchAll(TEXT_ATTRS)) out.push(['W1', `${at} ${m[1]}="${m[3]}" is a copy literal; use t()`]);
  });
  return out;
}

export function lintNavRules(text, file) {
  const out = [];
  for (const m of text.matchAll(/([^{}]+)\{([^{}]*)\}/g)) {
    const selector = m[1].trim();
    if (!/\b(?:nav|topbar|rail|bottombar|strip|dock)\b/i.test(selector.replace(/[.#]/g, ' '))) continue;
    for (const d of m[2].matchAll(/(background(?:-color)?|color)\s*:\s*([^;]+)/gi)) {
      for (const v of d[2].matchAll(/var\(--([\w-]+)\)/g)) {
        if (!/^(?:chrome|chrome-ink|mod-[a-z](?:-ink)?|line|line-ink)$/.test(v[1])) {
          out.push(['C7', `${file} "${selector}" uses --${v[1]} for ${d[1]}; nav uses chrome, chrome-ink or a module colour`]);
        }
      }
    }
  }
  return out;
}

// ---------- T2 / T3 / W2 ----------
const PROPER = new Set(['Plex', 'Jellyfin', 'Navidrome', 'Tailscale', 'Last.fm', 'Mixxx', 'Ollama', 'Soulseek', 'Fira', 'Sans',
  'Berlin', 'Gelb', 'Mac', 'Junction', 'Apple', 'Music', 'Spotify', 'MusicBrainz', 'Discogs', 'I']);
const ACRONYMS = new Set(['API', 'BPM', 'DB', 'URL', 'ID', 'KB/s', 'MB', 'GB', 'FLAC', 'MP3', 'AAC', 'OK', 'UTC', 'CSV', 'JSON', 'SQLite', 'AND', 'OR', 'NOT', 'LUFS', 'EP']);
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
  const isTest = (p) => /\.test\.tsx?$/.test(p) || p.includes(`${join('src', 'test')}`);
  const kitDir = join(root, 'web', 'src', 'components', 'kit');
  for (const f of walk(join(root, 'web', 'src'), ['.css', '.ts', '.tsx'], generated)) {
    const text = readFileSync(f, 'utf8');
    const rel = relative(root, f);
    problems.push(...lintStyleSource(text, rel));
    if (isTest(f) || f.endsWith('.css')) continue;
    if (!f.startsWith(kitDir)) problems.push(...lintPageImports(text, rel));
    if (f.endsWith('.tsx')) problems.push(...lintJsxCopy(text, rel));
  }
  if (existsSync(kitDir)) problems.push(...lintKitFolder(readdirSync(kitDir)));
  for (const copy of walk(join(root, 'web', 'src'), ['strings.json'], () => false)) {
    problems.push(...lintCopy(JSON.parse(readFileSync(copy, 'utf8')), relative(root, copy)));
  }
  return problems;
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const i = process.argv.indexOf('--root');
  const root = resolve(i > 0 ? process.argv[i + 1] : join(dirname(fileURLToPath(import.meta.url)), '..'));
  const problems = runAll(root);
  for (const [rule, msg] of problems) console.log(`${rule}  ${msg}`);
  console.log(problems.length ? `\n${problems.length} brand problem(s).` : 'Brand checks: C1 C2 C4 C7 T2 T3 W1 W2 K1 pass.');
  process.exit(problems.length ? 1 : 0);
}
