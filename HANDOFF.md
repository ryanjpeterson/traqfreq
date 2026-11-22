# Handoff

## Done (T1, 2026-11-22, branch `claude/t1-scaffold`)
- Python package `traqfreq` (src layout, setuptools, `uv.lock`), FastAPI factory `create_app()`, entry point `traqfreq` / `python -m traqfreq`.
- Settings from env: `TRAQFREQ_DATA_DIR`, `TRAQFREQ_LEGACY_DB`, `TRAQFREQ_PORT` (+ `TRAQFREQ_HOST`, default 0.0.0.0).
- `legacy.py`: read-only connection (`file:…?mode=ro`, `uri=True`, plus `PRAGMA query_only`). `GET /api/health`, `GET /api/legacy/summary` (row counts of key tables, missing tables, meta keys containing sync/import/scan).
- `scripts/make_fixture.py`: invented sample DB. Tests (12): writes raise and leave the file byte-identical, health, summary, settings. GitHub Actions `tests.yml`.
- Docs: CLAUDE.md, docs/specs/README.md, docs/specs/brand.md, CHANGELOG.md.

## Next: T2 web shell
Vite + React, Berlin token file → CSS variables, self-hosted Fira Sans, the brand fast checks (C1 literals, T2/T3 copy, K1 imports).

## Open questions
1. **Fixture schema is provisional.** This session could not attach jimbo-dj (the repo-attach tool was denied), so `make_fixture.py` guesses the table and column names (`tracks`, `albums`, `artists`, `listens`, `meta(key, value)`, `track_analysis`, `track_tags`). Before T5, read jimbo-dj's `src/jimbodj/db.py` and correct the fixture and `legacy.KEY_TABLES`. The summary already tolerates missing tables (`missing_tables` in the response).
2. **Reuse plan (jimbo-dj's pure functions).** Not added. Couldn't check if jimbo-dj is private. Options:
   - *Git dependency pinned to a tag/SHA* (`jimbo-dj @ git+https://github.com/ryanjpeterson/jimbo-dj@<sha>` in an optional group `legacy`). Clean, but if the repo is private, CI and the Docker build need a GitHub token (deploy key or build secret), and jimbo-dj must be importable without side effects (no DB open or config read at import).
   - *Vendor the few pure functions* (history dedupe, rules, flow, tags) into `src/traqfreq/legacy_fns/` with the source SHA in a header, plus parity tests. No token needed. Drift is caught by the parity tests.
   - Recommendation: vendor if private, git dependency if public. Decide in T5, when the first one (history dedupe) is needed.

## To check on the Mac mini
- Path of jimbo-dj's `data/jimbodj.sqlite`. In a container, mount it read-only too (`:ro`), not just as a URI flag. Note: SQLite `mode=ro` still needs the `-wal`/`-shm` files readable if jimbo-dj uses WAL. With a `:ro` mount, sharing the directory (not just the file) is safer.
- `uv run traqfreq` with `TRAQFREQ_LEGACY_DB` set, then `curl localhost:4491/api/legacy/summary`. Compare the counts with jimbo-dj.
- Port 4491 is free and reachable over Tailscale.
