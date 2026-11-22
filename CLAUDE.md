# traqfreq

The redesign of jimbo-dj (ryanjpeterson/jimbo-dj), a self-hosted music app. traqfreq runs **beside** jimbo-dj on the Mac mini (jimbo-dj :4490, traqfreq :4492, both over Tailscale) and takes over one module at a time. jimbo-dj is never changed for this work. Python 3.12 + FastAPI (`src/traqfreq`); Vite + React + TypeScript in `web/`, built to `web/dist` and served by FastAPI. Test: `uv sync && uv run pytest`, `node scripts/check.mjs` (brand), `node --test scripts/check.test.mjs`, `cd web && npm test` (kit, Vitest). Build web: `cd web && npm ci && npm run build`. Serve: `uv run traqfreq`. Env: `TRAQFREQ_DATA_DIR` (./data), `TRAQFREQ_LEGACY_DB` (jimbo-dj's data/jimbodj.sqlite), `TRAQFREQ_PORT` (4492; 4491 is jimbodj-text). Deploy: jimbo-deploy standard, `deploy.json`, snippet in README.

## Side-by-side rules
- The legacy DB is **read-only**: only `traqfreq.legacy.connect()` opens it (`mode=ro` URI + `query_only`). Never write to it.
- One writer at a time: jimbo-dj keeps every write (imports, scans, analyzer, playlists, Fix in Plex, jobs, backups) until that module's cut-over (P6), when it is switched off in jimbo-dj.
- Tests run only against the fixture from `scripts/make_fixture.py` (invented rows). Never against real data.

## Product rules
Self-hosted. Transparent (every number can show its rows; every automatic change is logged with reason and undo). No paid APIs. Never change Plex metadata, except genre tags through an explicit, previewed, undoable Fix. Audio files are read-only. Nothing counts twice.

## Design: Berlin · Gelb
Yellow chrome `#F0D722` with black text; square module badges **L1 H2 T3 D4 M5 F6 S0**; Fira Sans (self-hosted). Module colours: L `#E60012` · H `#0079C2` · T `#00843A` · D `#7354C2` · M `#B0006E` · F `#6D4C2F` · S ink. Dark mode: M and F marks on dark grounds get a 1 px paper outline (colours unchanged; white-text fills unaffected). Only the eleven kit components (LineBullet, NavItem, Status, Band, Button, ConditionChip, LineLever, StationRow, Text, Card, ArtTile). Brand rules C/T/L/K/W/D/B: `docs/specs/brand.md`. Tokens live only in `tokens/berlin.json`; `scripts/build-tokens.mjs` generates `web/src/styles/tokens.css` (never edit it). All copy goes in `web/src/copy/strings.json`. The kit is `web/src/components/kit` (pages import only from it, K1); `/kit` in `npm run dev` shows every state (dev only).

## Session protocol
- **Where:** on the laptop in the server checkout `/Volumes/jimbos-sloppydrive/traqfreq` (SMB; see HANDOFF for its quirks), or in a session on the Mac mini. Not in a cloud container. Push every branch to GitHub (`origin`); Forgejo mirrors GitHub.
- One session = one 5-hour usage window = one pushed branch (`claude/tN-<slug>`). Read only CLAUDE.md, HANDOFF.md and the one spec you need (`docs/specs/README.md` lists them).
- Stop at the last green commit if the window runs low.
- At the end: tests green, push, update HANDOFF.md and CHANGELOG.md, then update the progress deck (Slides artifact "traqfreq: build phases": `status`, the phase slide, `log`).
