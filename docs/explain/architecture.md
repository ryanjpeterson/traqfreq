# Architecture

## Shape

    browser → traqfreq web (React, served by FastAPI :4492) → API (src/traqfreq/app.py)
                                                              ├→ jimbo-dj's SQLite (read-only, /legacy)
                                                              ├→ traqfreq.sqlite (caches, snapshots, refresh log, /data)
                                                              └→ Jellyfin, Navidrome (GET only, on refresh; readers T17, T18)

- `src/traqfreq/app.py`: the FastAPI app and every route; serves `web/dist`.
- `legacy.py` (the read-only connection), `history.py`, `counted.py`, `periods.py` (HISTORY), `library.py`, `entities.py`, `library_gate.py` (LIBRARY), `identity.py`, `servers.py`, `snapshots.py`, `matching.py`, `reading.py` (the GET-only server client and refresh), `servers_gate.py` (the P3 gate) (SERVERS), `tags.py` (TAGS: the ladder), `store.py` (cache, server snapshots and the refresh log), `vendor/` (jimbo-dj's code).
- `web/src/pages` (pages, importing only from `web/src/components/kit`), `web/src/app` (nav, routes, API calls), `web/src/copy/strings.json` (all copy).

## Data flow

1. jimbo-dj syncs Plex, imports history and analyses audio into its database.
2. A traqfreq request opens that database read-only, runs jimbo-dj's vendored counting on it, and stores the result in `traqfreq.sqlite` keyed by jimbo-dj's stamps (last sync, history version, analyzer results).
3. The next request with the same stamps reads the cache; a new sync or import changes the key and the summary is rebuilt.
4. Gate pages put jimbo-dj's stored `stats` rows next to traqfreq's numbers.

## Where data lives

- jimbo-dj's `data/jimbodj.sqlite` (with `-wal`, `-shm`): precious, owned and backed up by jimbo-dj; traqfreq never writes it.
- `data/traqfreq.sqlite` in the server checkout: caches and server snapshots (`snapshots`, one row per server), all rebuildable by reading again; nothing precious yet.

## Jobs and schedules

None. traqfreq does nothing on its own; every number is built on request.

## Deploy

jimbo-deploy: merge to `main` on GitHub, then the `deploy traqfreq` snippet on the Mac mini (in the README): `git pull --ff-only` in `/Volumes/jimbos-sloppydrive/traqfreq`, `docker compose up -d --build`. No migrations (the cache table is created on start). Rollback: check out the previous commit and run it again.
