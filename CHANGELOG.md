# Changelog

All notable changes to this project are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions are CalVer (`YYYY.MM.N`).

## [Unreleased]
### Added
- P0 gate passed: deployed on the Mac mini at :4492 from `main`, reading jimbo-dj's live database read-only.
- T4 shell: chrome top bar from `NavItem` (LIBRARY, switched-on modules, SETUP, search; L1/L2), compact top bar on tablets (L4), 76 px phone bottom bar of five (L3), client-side routing.
- Map home: the modules drawn as lines (off lines dashed), a screen-reader summary and a list view (L6).
- Read-only SETUP: legacy DB row counts, last scan (`meta.last_sync`), recent jobs (`history_imports`), each module's on/off `Status`. Empty module pages and search point to SETUP (D1).
- `GET /api/legacy/activity` and `GET /api/modules`; `TRAQFREQ_MODULES` switches modules on (LIBRARY and SETUP always on).
- `Dockerfile`, `docker-compose.yml` (service `web`, port 4492, jimbo-dj's data folder mounted `:ro`), `.dockerignore`.
- Kit: `NavItem` plain items (no module) and wordmark; `Button` links route client-side with `onClick`; `Text` variant `note`.
- Fixture: jimbo-dj's real `meta.last_sync` key and `history_imports` table.
- T3 kit: the eleven components in `web/src/components/kit` (LineBullet, NavItem, Status, Band, Button, ConditionChip, LineLever, StationRow, Text, Card, ArtTile), every state, styled from tokens only.
- Vitest + Testing Library component tests (51), in CI.
- Brand checks K1 (kit-only UI) and W1 (no copy literals in JSX); C7 covers the kit's `--line` indirection; copy lint covers every `*strings.json`.
- Dev-only kit board at `/kit`; its sample copy never ships.
### Changed
- Port 4491 → **4492** (4491 is jimbo-dj's `jimbodj-text` analyzer on the Mac mini): settings default, Vite proxy, docs, tests.
- GitHub repo was made private, then public again; default branch is `main` (at the T3 commit). Forgejo is live as a pull mirror of GitHub (10-minute sync).
### Added
- jimbo-deploy: `deploy.json`, README deploy snippet, Forgejo mirrors GitHub (pull mirror); `origin` pushes to GitHub only.

## [2026.11.1] - 2026-11-22
### Added
- T2 web shell: `web/` with Vite, React and TypeScript, served by FastAPI at `/` (SPA fallback; `TRAQFREQ_WEB_DIR`).
- `tokens/berlin.json` (Berlin · Gelb, light and dark) and `scripts/build-tokens.mjs` generating CSS custom properties.
- Self-hosted Fira Sans (bundled woff2, no CDN).
- `scripts/check.mjs` brand fast checks (C1, C2, C4, C7, T2, T3, W2) with self-tests; CI `web` job.
- Dark mode: 1 px paper outline on MIXES and FETCH marks.
### Changed
- Session protocol: code is produced on the Mac mini, driven from the laptop; pushed to GitHub and Forgejo.

## [2026.11.0] - 2026-11-22
### Added
- T1 scaffold: `traqfreq` package, FastAPI app, env settings, uvicorn entry point on :4491.
- Read-only legacy DB access to jimbo-dj's SQLite; `GET /api/health`, `GET /api/legacy/summary`.
- Fixture generator `scripts/make_fixture.py` (invented rows, provisional schema).
- pytest suite and GitHub Actions workflow.
- CLAUDE.md, HANDOFF.md, docs/specs (phases, brand summary).
