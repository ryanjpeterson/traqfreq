# Changelog

All notable changes to this project are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions are CalVer (`YYYY.MM.N`).

## [Unreleased]

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
