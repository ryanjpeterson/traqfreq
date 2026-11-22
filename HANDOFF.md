# Handoff

## Where sessions run (from T3 on)
All code is produced **on the Mac mini**, in a Claude Code session running there and driven from the laptop. Pushes go to GitHub, and to Forgejo too once that remote exists. T1 and T2 ran in a cloud container because the Mac mini didn't offer a traqfreq folder to the session. Before T3, on the Mac mini:
1. Clone: `git clone https://github.com/ryanjpeterson/traqfreq ~/traqfreq` (not inside a hidden folder under home or in ~/Library), then `git checkout claude/t2-web-shell`.
2. Start the session there: Claude desktop app → Claude Code with that folder, or `claude remote-control` in `~/traqfreq`. Drive it from the laptop.
3. Remotes (jimbo-deploy standard; GitHub primary, Forgejo copy):
   ```
   git remote set-url --add --push origin https://github.com/ryanjpeterson/traqfreq.git
   git remote set-url --add --push origin http://macmini:4470/ryanjpeterson/traqfreq.git
   git remote add forgejo http://macmini:4470/ryanjpeterson/traqfreq.git
   ```
   Pushing to Forgejo from the mini needs the Forgejo token in the mini's keychain (`git credential-osxkeychain store`, host `macmini:4470`, user `ryanjpeterson`); see open question 1.
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

- **Deploy setup** (2026-11-22, laptop session, on `claude/t2-web-shell`): jimbo-deploy applied. `deploy.json` (port **4492**, service `web`, compose `docker-compose.yml`, server checkout `/Volumes/jimbos-sloppydrive/traqfreq`, code edited in `~/traqfreq` on the mini). Port moved from 4491 because `jimbodj-text` (jimbo-dj's CLAP analyzer, native on the mini) already listens there and jimbo-dj's compose points at it. GitHub made private. Forgejo repo created (private) with both branches; the server checkout's `origin` pushes to both. README has the `deploy traqfreq` Termius snippet; it works once T4 adds the Dockerfile and `docker-compose.yml`.

## Next: T3, the kit
The eleven components (LineBullet, NavItem, Status, Band, Button, ConditionChip, LineLever, StationRow, Text, Card, ArtTile), every state, tests. Pick a component test runner (Vitest + Testing Library is the obvious fit). Marks use `outline: var(--mark-outline-<x>)`. Extend check.mjs with K1 (pages import only from the kit) and W1 (no string literals in JSX).

## Open questions
1. **Forgejo from the mini:** the repo exists at `http://macmini:4470/ryanjpeterson/traqfreq`, and `origin` pushes to GitHub + Forgejo. The mini has no Forgejo credentials yet, so a session in `~/traqfreq` either stores the token there once, or pushes to GitHub only and Forgejo is caught up later.
2. **Fixture schema is provisional** (from T1). jimbo-dj couldn't be attached, so table and column names are guesses. Correct `scripts/make_fixture.py` and `legacy.KEY_TABLES` against jimbo-dj's `src/jimbodj/db.py` before T5. On the Mac mini this is just a read of the local jimbo-dj checkout.
3. **Reuse plan** (from T1): vendor jimbo-dj's pure functions if the repo is private, use a pinned git dependency if public. Decide in T5.
4. Copy lint's sentence-case check uses an allowlist of proper nouns and acronyms (`PROPER`, `ACRONYMS` in check.mjs). Add to it when copy needs a new name.

## To check on the Mac mini
- `cd web && npm ci && npm run build`, then `uv run traqfreq` with `TRAQFREQ_LEGACY_DB` pointing at jimbo-dj's `data/jimbodj.sqlite`. Open `http://macmini:4492/`: the yellow bar and row counts from jimbo-dj. Compare the counts with jimbo-dj.
- In any container, mount jimbo-dj's data directory read-only (`:ro`). If jimbo-dj uses WAL, `mode=ro` still needs the `-wal`/`-shm` files readable.
- Port 4492 is free (checked from the laptop 2026-11-22: no answer on 4492–4494, not in any compose file) and reachable over Tailscale.
- T4's container: compose service `web`, host port `4492`, jimbo-dj's data dir mounted `:ro`. Then the README snippet deploys it.
