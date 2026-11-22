# Changelog

All notable changes to this project are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions are CalVer (`YYYY.MM.N`).

## [Unreleased]

## [2026.11.0] - 2026-11-22
### Added
- T1 scaffold: `traqfreq` package, FastAPI app, env settings, uvicorn entry point on :4491.
- Read-only legacy DB access to jimbo-dj's SQLite; `GET /api/health`, `GET /api/legacy/summary`.
- Fixture generator `scripts/make_fixture.py` (invented rows, provisional schema).
- pytest suite and GitHub Actions workflow.
- CLAUDE.md, HANDOFF.md, docs/specs (phases, brand summary).
