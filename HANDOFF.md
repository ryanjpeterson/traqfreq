# Handoff

## Where sessions run
T1 and T2 ran in a cloud container. **T3 ran on the laptop, directly in the server checkout over SMB** (`/Volumes/jimbos-sloppydrive/traqfreq`; Ryan's call, use this mount and not `jimbos-sloppydrive-1`). Pushes go to GitHub; Forgejo mirrors it. The GitHub repo is **public** and its default branch is **`main`** (2026-11-22, at f06a60f = `claude/t3-kit`); session branches are pushed beside it, and only Ryan moves `main`.

Working over SMB, as T3 did:
- Git and in-place edits work, but SMB now and then refuses a rename: `fatal: unable to write new index file` or `sed: rename(): Resource busy`. Retry once; edit files with in-place writes (Python `r+`, the Edit tool), not `sed -i`.
- Keep `node_modules` off the drive. T3 ran npm, Vite, Vitest and the build in a scratch copy (`rsync` the repo there without `node_modules`, `npm ci`), then copied sources back with `rsync --inplace`.
- uv isn't on the laptop; pytest ran in a scratch venv (Python 3.14). CI runs 3.12.

The alternative, still open: a session on the Mac mini itself, in its own clone:
1. Clone: `git clone https://github.com/ryanjpeterson/traqfreq ~/traqfreq` (not inside a hidden folder under home or in ~/Library), then check out the newest `claude/tN-…` branch.
2. Start the session there: Claude desktop app → Claude Code with that folder, or `claude remote-control` in `~/traqfreq`. Drive it from the laptop.
3. Remotes: `origin` = GitHub only (fetch and push). Forgejo is a **pull mirror** of GitHub (`http://macmini:4470/ryanjpeterson/traqfreq`), so the mini needs no Forgejo credentials. Optional read-only check: `git remote add forgejo http://macmini:4470/ryanjpeterson/traqfreq.git`.
4. Tools: `uv` (Python 3.12) and Node 22+.

## Done
- **T1** (2026-11-22, `claude/t1-scaffold`): Python package, FastAPI factory, env settings, read-only legacy DB (`mode=ro` + `query_only`), `/api/health`, `/api/legacy/summary`, fixture generator, pytest, CI, docs.
- **T2** (2026-11-22, `claude/t2-web-shell`, from T1):
  - `web/`: Vite 8 + React 19 + TypeScript, versions pinned in `web/package-lock.json`. Dev: `npm run dev` (proxies `/api` to :4492).
  - `tokens/berlin.json`: Berlin · Gelb tokens (paper/ink/ink2, chrome `#F0D722` + ink, square badges, radius 2px, dense 24px, h1 34/700, Fira Sans, seven modules, dark mode with a 1px paper outline on MIXES and FETCH marks). `scripts/build-tokens.mjs` → `web/src/styles/tokens.css` (generated, git-ignored, runs on `npm run dev`/`build`). Variables: `--paper --ink --ink2 --rule --card --chrome --chrome-ink --font --label-font --radius --card-radius --h1* --label-* --pad --mod-<l…s> --mod-<x>-ink --mark-outline-<x>`. Dark mode follows `prefers-color-scheme`; `data-theme="light|dark"` on `<html>` overrides it.
  - Fira Sans self-hosted via `@fontsource/fira-sans` (latin 400/500/700). Vite bundles the woff2 files into `dist/assets`, so no CDN at runtime.
  - FastAPI serves `web/dist` at `/` (`TRAQFREQ_WEB_DIR` overrides). Unknown non-API paths fall back to `index.html`; `/api/*` is never shadowed. Without a build, only the API runs.
  - `scripts/check.mjs`: brand fast checks C1, C2, C4 (every text pair + 3:1 marks, with outline fallback), C7, plus copy lint T2/T3/W2 on `web/src/copy/strings.json`. `scripts/check.test.mjs` proves each check catches violations. Both run in CI (new `web` job, which also builds).
  - Placeholder shell screen (chrome bar + legacy row counts). Replaced by the kit and nav in T3/T4.

- **Deploy setup** (2026-11-22, laptop session, on `claude/t2-web-shell`): jimbo-deploy applied. `deploy.json` (port **4492**, service `web`, compose `docker-compose.yml`, server checkout `/Volumes/jimbos-sloppydrive/traqfreq`, code edited in `~/traqfreq` on the mini). Port moved from 4491 because `jimbodj-text` (jimbo-dj's CLAP analyzer, native on the mini) already listens there and jimbo-dj's compose points at it. GitHub made private (made public again 2026-11-22, see below). Forgejo mirrors GitHub (pull mirror, set up by Ryan in the Forgejo UI); `origin` pushes to GitHub only. README has the `deploy traqfreq` Termius snippet; it works once T4 adds the Dockerfile and `docker-compose.yml`.

- **T3** (2026-11-22, `claude/t3-kit`, from T2 + deploy setup):
  - `web/src/components/kit/`: the eleven components, one file each, exported from `index.ts`; styles in `kit.css` (tokens only). Module data in `modules.ts` (badge `L1`…`S0`, name from strings, class `line-<x>`). Each `.line-<x>` class sets `--line`, `--line-ink`, `--line-outline` from the module tokens; components colour themselves through those.
  - States: LineBullet (7 modules × sizes 22/24/28/36/44, decorative); NavItem (default, current = module fill + `aria-current="page"`, optional `onNavigate`); Status (ready filled, needs outlined, off dashed; own word or default); Band (name, name · screen); Button (primary ink, secondary outline, quiet link; disabled dashed; `href` link; submit); ConditionChip (AND OR NOT true false; removable); LineLever (read-only bar, adjustable range input, off dashed + disabled; clamps 0–100); StationRow (key/BPM optional, why toggle with `aria-expanded`, B3); Text (title h1, heading h2, body, label); Card (label, off dashed); ArtTile (art or "No artwork", code chip key · BPM).
  - Bullets on their own colour (band, current nav item) invert: white square, module-coloured text, same contrast pair. Only text-free marks (the lever's share bar) use `outline: var(--line-outline)`, per the dark-mode rule.
  - Kit copy in `strings.json` (`module.*`, `kit.*`). Phone (≤ 480 px): station rows put key and BPM under the artist.
  - Tests: Vitest 5 + Testing Library + jsdom, `web/src/components/kit/kit.test.tsx`, 51 tests (`cd web && npm test`). In CI.
  - `check.mjs` adds **K1** (pages import the kit only by its eleven names, no other UI packages, no raw `<button> <a> <input> <select> <textarea> <img> <svg> <canvas>` outside the kit; the kit folder holds only the eleven) and **W1** (no copy literals in JSX text or in `aria-label title alt placeholder label detail why` attributes). C7 accepts `--line`/`--line-ink` and checks every `--line*` points at a module token. Copy lint covers every `*strings.json`. 13 self-tests.
  - Kit board at `/kit`, **dev only** (`npm run dev`): every component in every state. Its sample copy is in `web/src/dev/board.strings.json`, so none of it reaches `dist` (checked: D1). Looked at in light, dark and 375 px.
- **T4** (2026-11-22, `claude/t4-nav-setup`, from T3; laptop over SMB like T3):
  - Shell (`web/src/App.tsx`, `web/src/app/`): History API router (`route.ts`; `/`, `/library` … `/setup`, `/search`, not found), `useGet`/`useModules` (`api.ts`). Top bar in the chrome built from `NavItem`: wordmark (map home), LIBRARY, switched-on modules, SETUP, then Search (L1). Off modules: no nav item, their path is "No such page" (L2). Tablet (600–1023 px): compact bar, names hidden except the current item (L4). Phone (< 600 px): top bar keeps wordmark + Search; bottom bar 76 px of five at most: LIBRARY, up to two modules, Map, SETUP (L3); the map reaches the rest.
  - Pages (`web/src/pages/`): map home (lines drawn with CSS from `LineBullet`s, off lines dashed; visually hidden summary; card list with `Status` and Open buttons; L6), SETUP read-only, module empty states and Search pointing to SETUP (D1), not found.
  - API: `GET /api/modules` (`TRAQFREQ_MODULES`, letters or names, LIBRARY + SETUP always on; default none else), `GET /api/legacy/activity` (last scan, jobs). **Found in jimbo-dj's code:** its jobs live in process memory (`jobs.py`), not in the DB. SETUP shows the DB's record instead: last scan = `meta.last_sync` (Unix seconds, set after each Plex sync, `library.py`) and finished history imports (`history_imports`, `history.py`). The fixture now has both, with the real shapes.
  - Kit changes (still eleven): `NavItem` takes `label` without `module` (plain item, fills chrome-ink when current) and `wordmark`; `Button` with `href` + `onClick` routes client-side (modified clicks still follow the link); `Text` variant `note` (13 px ink2, for "where this number comes from", W3). On the `/kit` board.
  - Container: `Dockerfile` (node 22 builds `web/dist`, then uv + Python 3.12, `uv run traqfreq`, healthcheck), `docker-compose.yml` (service `web`, `4492:4492`, `${JIMBODJ_DATA_DIR:-../jimbo-dj/data}:/legacy:ro`, `./data:/data`), `.dockerignore`. Docker wasn't running on the laptop, so **the image has not been built yet**; the first deploy builds it. Checked instead: read-only open of a WAL database in a read-only folder (with `-wal` and `-shm` present) reads rows still in the WAL.
  - Tests: pytest 23 (7 new in `tests/test_setup.py`), Vitest 72 (`web/src/app/app.test.tsx`: routes, nav order, bottom bar, client navigation, L2, map list + summary, SETUP states). Checked in the browser against the fixture: light, dark, 375 px, tablet.

## P0 gate: passed 2026-11-22
Deployed from `main` (30f380e) with the `deploy traqfreq` snippet; the image built on the mini. Checked from the laptop over Tailscale:
- `http://macmini:4492/api/health`: ok, `legacy_db_present: true`. jimbo-dj at :4490 still answers.
- `/`: yellow bar with LIBRARY and SETUP only; map with five dashed lines. `/setup`: "Readable", row counts, last scan, history imports (276 so far), modules.
- **Last scan matches jimbo-dj exactly** (`meta.last_sync` 1795381464 = 2026-11-22 21:04 UTC, same as jimbo-dj's `/api/stats`). The read-only `:ro` mount of the WAL database works.
- **Counts are raw row counts, not jimbo-dj's numbers:** tracks 54,355 rows vs jimbo-dj's 52,779 (it counts `removed_at IS NULL`), albums 4,443 vs 4,306 and artists 1,311 vs 1,297 (it counts distinct `album_key` / `artist_key` among live tracks); listens 350,953. P1 and P2 must use jimbo-dj's definitions (`library.py` stats) for "counts match".
- "Tables not found: track_analysis, track_tags" on real data: the fixture names are wrong (open question 2).
To redeploy: the server checkout is on `main`; get the change onto `main`, then run the snippet.

## T5 done (2026-11-22, `claude/t5-history`, from `claude/t4-nav-setup`)
- **Fixture = jimbo-dj's schema** (read at jimbo-dj 1d8a7cb: `db.py`, `history.py`, `statcache.py`). Invented rows chosen so each rule differs from a raw count: one removed track on its own album and artist; 9 listens, 6 plays (one too short, one Plex duplicate of Last.fm, one Spotify repeat); one unmatched play; one play that is 2025 in America/Denver but 2026 in UTC. jimbo-dj's `stats` rows (`library.stats`, `history.overview`) are in it too.
- **Counts the way jimbo-dj does:** `legacy.MEASURES` (tracks `removed_at IS NULL`, distinct `album_key` / `artist_key` of those, plays `counted = 1`). `/api/legacy/summary` adds `measures` (value, SQL rule, jimbo-dj's stored value from its `stats` table, `matches`); `counts` stays (raw rows). SETUP shows the four with their rule and "Same as jimbo-dj's stored count", then rows per table.
- **HISTORY read API** (`src/traqfreq/history.py`): `GET /api/history/overview`, `GET /api/history/listens?status=play|too_short|repeat|duplicate&source=&year=`. traqfreq reads jimbo-dj's `counted`/`dup_of` flags and never recomputes them; `adds_up` checks plays + the three reasons = listens. Years use meta `history_tz`, else `TZ`, else America/Denver (jimbo-dj's order).
- **Open question 3 decided: vendor.** `gh repo view ryanjpeterson/jimbo-dj`: private. Pure functions copied unchanged into `src/traqfreq/vendor/jimbodj_history.py`; `tests/test_vendor.py` checks them against stored match keys.
- Tests: pytest 40, Vitest 73, brand checks and 13 self-tests pass. Checked SETUP in the browser against the fixture.
- **Mount note:** during T5 macOS remounted the SMB share as `/Volumes/jimbos-sloppydrive-1` (the plain path vanished; same share, same checkout). T5's later edits went through `-1`. Use whichever path exists; check `mount | grep sloppy`.

## T5 deployed and checked: 2026-11-22
Deployed from `main` with the snippet. Checked from the laptop over Tailscale against jimbo-dj at :4490:
- SETUP measures, all `matches: true`: tracks 52,779, albums 4,306, artists 1,297 (jimbo-dj `/api/stats` the same), plays 167,180. No tables missing.
- `/api/history/overview`: 350,953 listens = 167,180 plays + 140,580 too short + 18,169 repeats + 25,024 duplicates (`adds_up: true`). Matched 67.4 %, songs 81,923 heard / 22,568 matched, time zone America/New_York (jimbo-dj's `history_tz`). **Every year 2011–2026 and every source's listens, plays, repeats and duplicates equal jimbo-dj's `/api/history`.**
- The overview answers in about 0.6 s on live data. T6's stats cache is still worth it for the heatmap and top artists.

## Next: T6
Overview (spec: `docs/specs/t5-history.md`, T6): the HISTORY page with counts, the year heatmap and top artists, and a stats cache in traqfreq's own database. Then T7 counted once (duplicates, held bursts, bot checks, read-only) and T8 years, Wrapped, this day, top and the P1 gate.

## Open questions
1. ~~**Forgejo mirror**~~ *Done 2026-11-22:* Forgejo is live as a pull mirror of GitHub (`http://macmini:4470/ryanjpeterson/traqfreq`, syncs every 10 minutes, default branch `main`).
2. ~~**Fixture schema is provisional**~~ *Done in T5:* fixture and `KEY_TABLES` match jimbo-dj 1d8a7cb. When jimbo-dj's schema changes, update `scripts/make_fixture.py` the same way.
3. ~~**Reuse plan**~~ *Decided in T5: vendor* (jimbo-dj is private). `src/traqfreq/vendor/`, copied unchanged with the commit noted.
4. Copy lint's sentence-case check uses an allowlist of proper nouns and acronyms (`PROPER`, `ACRONYMS` in check.mjs). Add to it when copy needs a new name.

## To check on the Mac mini
- `cd web && npm ci && npm run build`, then `uv run traqfreq` with `TRAQFREQ_LEGACY_DB` pointing at jimbo-dj's `data/jimbodj.sqlite`. Open `http://macmini:4492/`: the yellow bar and row counts from jimbo-dj. Compare the counts with jimbo-dj.
- In any container, mount jimbo-dj's data directory read-only (`:ro`). If jimbo-dj uses WAL, `mode=ro` still needs the `-wal`/`-shm` files readable.
- Port 4492 is free (checked from the laptop 2026-11-22: no answer on 4492–4494, not in any compose file) and reachable over Tailscale.
- T4's container: compose service `web`, host port `4492`, jimbo-dj's data dir mounted `:ro`. The README snippet deploys it; first build not yet run (see the P0 gate above).
