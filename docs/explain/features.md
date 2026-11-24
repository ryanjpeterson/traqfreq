# Features

## Summary

Read-only views of jimbo-dj's data in the Berlin · Gelb look, each number with its rule and its rows, and a gate page per module comparing traqfreq with what jimbo-dj stored. 32 features in 5 areas.

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

### SERVERS (P3, on SETUP)

| Feature | What it does | Where | Status |
|-|-|-|-|
| Server status | Plex through jimbo-dj's DB; Jellyfin and Navidrome set up or not (secrets never shown) | `GET /api/servers`, `src/traqfreq/servers.py` | new |
| Track identity | Plex's music folders, each copy's file key, loose key, song and match key, and its issues | `GET /api/servers/identity`, `src/traqfreq/identity.py` | new |
| Identity rows | The copies behind each count: by issue, song, file | `GET /api/servers/copies` | new |
| Server snapshots | Jellyfin `/Items` and Navidrome `search3` answers in one item shape, stored per server with when read and the server's stamp (read by each server's reader, T17 and T18, with the server's name, version and whose plays) | `src/traqfreq/snapshots.py`, `snapshots` table | new |
| Matches | Each Plex copy matched to one Jellyfin item and one Navidrome song (file, MusicBrainz ID, tags; one to one), Jellyfin to Navidrome, every miss with its reason; one copy's rows by `rating_key` | `GET /api/servers/matches`, `src/traqfreq/matching.py` | new |
| Snapshot refresh | Read a set-up server whole with GET requests only (timeouts, paging, no retries, the server's own error shown, secrets never shown), store its snapshot in traqfreq's database, one at a time, each refresh logged with its counts; Jellyfin's reader (T17: System/Info, folders, paged `/Items`, one user's play counts), Navidrome's (T18: ping, folders, scan status, albums, `search3`; a read a scan tore is not stored; `TRAQFREQ_NAVIDROME_ROOTS`) | `POST /api/servers/{server}/refresh`, `GET /api/servers/{server}/refreshes`, `src/traqfreq/reading.py`, `refreshes` table | new |
| SERVERS page | The three servers with status and snapshot age, Plex's identity counts, each pair's matches by tier and by reason (lists with bars and a summary), a song's three IDs; a refresh per server with the last refresh and its log; every count opens its rows | `/setup/servers`, `/setup/servers/copies`, `/setup/servers/matches`, `web/src/pages/Servers.tsx` | new |
| P3 gate | One to one per server, reasons that add up, a spot check asking each server by ID (file, duration within 2 s); `scripts/p3_gate.py`; the gate card on SETUP | `GET /api/servers/compare`, `src/traqfreq/servers_gate.py`, `web/src/pages/ServersGate.tsx` | new |
| On servers | On a track's page: its Jellyfin item and Navidrome song with the tier, and each server's own play count, labelled and never added | `/library/track/<key>` | new |

### TAGS (module T, switched on by `TRAQFREQ_MODULES`; P4, read-only)

| Feature | What it does | Where | Status |
|-|-|-|-|
| The ladder | Every genre tag in use on its rungs, broad to specific, any depth, shared parents: jimbo-dj's tag rules (vendored) name each tag and its broad tag, the rungs between come from the tags' names under the same broad tag; tags with no broad tag listed apart | `/tags`, `GET /api/tags/ladder`, `src/traqfreq/tags.py` | new |
| Same as jimbo-dj's families | Each broad tag's albums under it, carrying it, missing it and its children, next to jimbo-dj's rules run here and its stored `library.tags`; every ladder ends at jimbo-dj's broad tag | `/tags` | new |
| Tag rows | The albums carrying a tag, under it or missing it, and the artists carrying it, each saying why; the tags behind each summary number | `/tags/albums`, `/tags/artists`, `/tags/list`, `GET /api/tags/albums`, `GET /api/tags/artists` | new |
| A track by source | A track's tags from each source (its own and its file's genres, its album's and artist's Plex genres, MusicBrainz votes, the analyzer's styles with their scores, kept or not by jimbo-dj's strict test), each on its rung; its tags by jimbo-dj's per-track rule; linked from LIBRARY's track page | `/tags/track/<key>`, `GET /api/tags/track/{key}` | new |
| An album, track by track | Its tracks with their tags, the ones that differ from the album marked (and listed on their own), and the tags its tracks and files carry that speak for it (half its tracks); linked from LIBRARY's album page | `/tags/album/<key>`, `GET /api/tags/album/{key}` | new |
| The proposals inbox | Every album's proposed tag change from jimbo-dj's audit, grouped by kind of issue, by fix and by suggested genre (jimbo-dj's `fixes()` and `suggestions()`), each count opening its albums before and after Fix in Plex's preview (vendored); traqfreq's own ladder proposals and rule questions, labelled. Shown, never applied: Fix in Plex stays in jimbo-dj until P6, linked | `/tags/proposals`, `/tags/proposals/albums`, `GET /api/tags/proposals`, `GET /api/tags/proposals/albums`, `src/traqfreq/proposals.py` | new |
| The audit, same as jimbo-dj's stored run | Gate check 3: every tag's numbers, the album issue counts, the top fixes and suggestions against jimbo-dj's stored `library.tags` (a differing row passes only when stale) | `/tags/proposals`, `GET /api/tags/proposals` | new |
| A page per tag | A tag's ladders up to its broad tag (every path), its children, the rule that gives its broad tag, its spellings and the rules that made them; its albums, artists, tracks (jimbo-dj's per-track rule) and plays (HISTORY's counted plays of those tracks, jimbo-dj's Top genres rule), its sound (albums by the analyzer's styles; what its plays sounded like, jimbo-dj's `sound_of`), and its movements; every number opening its rows | `/tags/tag/<key>`, `/tags/tracks`, `GET /api/tags/tag/{key}`, `GET /api/tags/tracks`, `src/traqfreq/tagpages.py` | new |
| The genre map | The whole ladder drawn as lines like the map home, one per broad tag, its tags as stations on their rungs (a shared tag on both branches), with a visually hidden summary | `/tags/map`, `GET /api/tags/map` | new |
| Movements | Named sets of tags across broad tags (Blackgaze with Shoegaze, post-punk, industrial, emo, doom and drone), read from `movements.json`; shown on the map and each tag's page; they change no ladder and no count | `src/traqfreq/movements.json` | new |
| P4 gate | Checks 1–3 (ladders, per-track tags, the audit) in one answer; `scripts/p4_gate.py`; the gate card on TAGS and SETUP | `GET /api/tags/compare`, `src/traqfreq/tags_gate.py`, `web/src/pages/TagsGenre.tsx` | new |
| Track by track, same as jimbo-dj | Gate check 2: every live track's tags against jimbo-dj's `_genre_tags` and its kept styles against `genres.Styles` (both vendored, run here), the tracks that differ with both answers | `/tags`, `GET /api/tags/tracks/check` | new |

### Throughout

| Feature | What it does | Where | Status |
|-|-|-|-|
| Rules and rows | Every number carries its rule (W3) and a link to its rows | API `rules` and `rows` maps | stable |
| Stats cache | Built summaries kept in traqfreq's own SQLite, keyed by jimbo-dj's data stamps | `src/traqfreq/store.py` | stable |
| Brand checks | Copy, tokens and kit rules checked in CI | `scripts/check.mjs` | stable |

## Removed or retired

None yet.
