# Features

## Summary

Read-only views of jimbo-dj's data in the Berlin · Gelb look, each number with its rule and its rows, and a gate page per module comparing traqfreq with what jimbo-dj stored. 26 features in 4 areas.

## Features

### Shell and SETUP

| Feature | What it does | Where | Status |
|-|-|-|-|
| Read-only legacy DB | Opens jimbo-dj's SQLite with `mode=ro` and `query_only` | `src/traqfreq/legacy.py` | stable |
| Nav | Top bar with module badges L1 H2 T3 D4 M5 F6 S0, phone bottom bar | `web/src/app/Nav.tsx` | stable |
| Map home | The modules as a line map, which are on | `web/src/pages/MapHome.tsx` | stable |
| SETUP | Last scan, history imports, modules switched on (`TRAQFREQ_MODULES`), counts as jimbo-dj counts them, the gate cards | `/setup`, `web/src/pages/Setup.tsx` | stable |
| Search | Search page placeholder | `/search` | beta |
| Kit board | Every state of the eleven kit components (dev only) | `/kit`, `web/src/components/kit` | stable |

### HISTORY (module H, switched on by `TRAQFREQ_MODULES`)

| Feature | What it does | Where | Status |
|-|-|-|-|
| Overview | Plays, hours, matched %, year heatmap, top artists, sources | `/history`, `src/traqfreq/history.py` | stable |
| Listens | The plays behind any number, filtered by source, year, status | `/history/listens` | stable |
| Counted once | Duplicates and held bursts with their reasons; read-only bot checks | `/history/counted`, `src/traqfreq/counted.py` | stable |
| Years and On this day | Every year's plays and hours, this day in earlier years, highlights | `/history/years` | stable |
| Wrapped | A year, month or day: totals, sources, tops, by hour and weekday | `/history/wrapped` | stable |
| Top | Artists, songs, albums for all time, 30 days, 12 months, a year or month, by plays or minutes | `/history/top`, `src/traqfreq/periods.py` | stable |
| P1 gate | Every stored overview and Wrapped field next to traqfreq's; `scripts/p1_gate.py` | `/history/compare` | stable |

### LIBRARY (always on)

| Feature | What it does | Where | Status |
|-|-|-|-|
| Library numbers | Tracks, albums, artists, hours, size, codecs, containers, bitrate, analysis, paths | `/library`, `src/traqfreq/library.py` | stable |
| Plays from every source | Played tracks and plays by `plays_of` beside jimbo-dj's Plex-only numbers | `/library` | stable |
| Track rows | 50 a page behind every number, with key and BPM where analysed | `/library/tracks` | stable |
| Albums and artists | Lists by plays, added, name or year | `/library/albums`, `/library/artists` | stable |
| Album, artist, track pages | Tracks, plays, copies of each song, listens by source and year | `/library/album/<key>`, `/artist/<key>`, `/track/<key>`, `src/traqfreq/entities.py` | stable |
| Listens behind a page | The counted plays behind an album's, artist's or track's numbers | `/library/plays` | stable |
| P2 gate | `library.stats` and `library.charts` next to jimbo-dj's, every bar opening its tracks; `scripts/p2_gate.py` | `/library/compare`, `src/traqfreq/library_gate.py` | stable |

### SERVERS (P3, API only so far)

| Feature | What it does | Where | Status |
|-|-|-|-|
| Server status | Plex through jimbo-dj's DB; Jellyfin and Navidrome set up or not (secrets never shown) | `GET /api/servers`, `src/traqfreq/servers.py` | new |
| Track identity | Plex's music folders, each copy's file key, loose key, song and match key, and its issues | `GET /api/servers/identity`, `src/traqfreq/identity.py` | new |
| Identity rows | The copies behind each count: by issue, song, file | `GET /api/servers/copies` | new |

### Throughout

| Feature | What it does | Where | Status |
|-|-|-|-|
| Rules and rows | Every number carries its rule (W3) and a link to its rows | API `rules` and `rows` maps | stable |
| Stats cache | Built summaries kept in traqfreq's own SQLite, keyed by jimbo-dj's data stamps | `src/traqfreq/store.py` | stable |
| Brand checks | Copy, tokens and kit rules checked in CI | `scripts/check.mjs` | stable |

## Removed or retired

None yet.
