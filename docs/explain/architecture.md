# Architecture

## Shape

    browser → traqfreq web (React, served by FastAPI :4492) → API (src/traqfreq/app.py)
                                                              ├→ jimbo-dj's SQLite (read-only, /legacy)
                                                              ├→ traqfreq.sqlite (caches, snapshots, refresh log, /data)
                                                              ├→ library.sqlite (P6: traqfreq's own copy of each cut-over's tables, /data)
                                                              ├→ Jellyfin, Navidrome (GET only, on refresh; readers T17, T18)
                                                              ├→ Plex (T30: GET only, traqfreq's sync and watcher into library.sqlite, once plex is owned)
                                                              └→ jimbodj-text, Ollama (the Ask box, T28: words to numbers)
    scripts/p5_gate.py → traqfreq (GET) and jimbo-dj (GET /api/saved, POST /api/rules/preview: a preview, writes nothing)

- `src/traqfreq/app.py`: the FastAPI app and every route; serves `web/dist`.
- `legacy.py` (the read-only connection), `history.py`, `counted.py`, `periods.py` (HISTORY), `library.py`, `entities.py`, `library_gate.py` (LIBRARY), `identity.py`, `servers.py`, `snapshots.py`, `matching.py`, `reading.py` (the GET-only server client and refresh), `servers_gate.py` (the P3 gate) (SERVERS), `tags.py` (TAGS: the ladder, tracks by source, gate check 2), `playlists.py`, `junction.py`, `reach.py`, `ask.py` (the Ask box), `playlists_compare.py` and `playlists_gate.py` (the P5 gate) (PLAYLISTS), `store.py` (cache, server snapshots and the refresh log), `own.py` (P6: `library.sqlite`, the cut-over registry, the reading connection, the one-time copy and rollback, the switch-off check, the `runs` log; the `traqfreq-cutover` command), `plexsync.py` (T30: the only way into jimbo-dj's vendored Plex sync and watcher, with traqfreq's checks), `vendor/` (jimbo-dj's code).
- `web/src/pages` (pages, importing only from `web/src/components/kit`), `web/src/app` (nav, routes, API calls), `web/src/copy/strings.json` (all copy).

## Data flow

1. jimbo-dj syncs Plex, imports history and analyses audio into its database.
2. A traqfreq request opens that database read-only (from P6 through `own.reader`, with traqfreq's copy of every cut-over's tables in front of it), runs jimbo-dj's vendored counting on it, and stores the result in `traqfreq.sqlite` keyed by jimbo-dj's stamps (last sync, history version, analyzer results).
3. The next request with the same stamps reads the cache; a new sync or import changes the key and the summary is rebuilt.
4. Gate pages put jimbo-dj's stored `stats` rows next to traqfreq's numbers.

## Where data lives

- jimbo-dj's `data/jimbodj.sqlite` (with `-wal`, `-shm`): precious, owned and backed up by jimbo-dj; traqfreq never writes it.
- `data/traqfreq.sqlite` in the server checkout: caches and server snapshots (`snapshots`, one row per server), all rebuildable by reading again.
- `data/library.sqlite` (P6, from the first copy): traqfreq's own copy of each cut-over's tables, plus `cutovers`, `cutover_log` and `runs` (every sync, from T30). Precious from the copy on: once jimbo-dj's job is off, nowhere else has it (backed up from cut-over 7). Never opened over SMB.

## Jobs and schedules

Until cut-over 1 is copied, none: every number is built on request. From T30, the watcher (jimbo-dj's, vendored; off unless `TRAQFREQ_WATCH=on`) looks at Plex every `TRAQFREQ_WATCH_INTERVAL` seconds and syncs when the library changed, waiting while Plex scans; it writes nothing until the `plex` cut-over is owned. `traqfreq-cutover sync --reason …` runs one sync by hand. The nightly sync and imports come with T31.

## Deploy

jimbo-deploy: merge to `main` on GitHub, then the `deploy traqfreq` snippet on the Mac mini (in the README): `git pull --ff-only` in `/Volumes/jimbos-sloppydrive/traqfreq`, `docker compose up -d --build`. No migrations (the cache table is created on start). Rollback: check out the previous commit and run it again.
