# Specs: phases and sessions

One session = one 5-hour window = one pushed branch. P0–P5 (T1–T28) give a full read-only traqfreq beside jimbo-dj.

| Phase | What | Sessions | Gate |
|---|---|---|---|
| P0 | Shell | T1–T4 | Runs on the Mac mini at :4492 |
| P1 | HISTORY, read-only | T5–T8 | Counts match jimbo-dj |
| P2 | LIBRARY, read-only | T9–T12 | Counts match jimbo-dj |
| P3 | SERVERS: track identity, Jellyfin, Navidrome | T13–T19 | One song, three servers |
| P4 | TAGS, read-only | T20–T23 | Ladder and per-track tags right |
| P5 | PLAYLISTS: Junction preview | T24–T28 | Same tracks as jimbo-dj |
| P6 | Cut-overs, one writer at a time | T29–T44 | Each switched off in jimbo-dj for a week, nothing missed |
| P7 | DISCOVER, MIXES, FETCH, language loop | ~30 | Per module |
| P8 | Retire jimbo-dj; other nine directions as skins | ~5 | jimbo-dj off for a week |

## P0 Shell
- **T1** Repo: FastAPI app, legacy DB read-only, fixture generator, tests, CI, docs. *Done.*
- **T2** Web shell: Vite + React, Berlin token file → CSS variables, self-hosted Fira Sans, brand fast checks. *Done.*
- **T3** The eleven kit components, every state, tests. *Done.*
- **T4** Nav (top bar, phone bottom bar), map home, read-only SETUP, container on :4492. *Done.* **P0 gate passed 2026-11-22** (HANDOFF).

## P1 HISTORY read-only: T5–T8
Spec: [t5-history.md](t5-history.md).
- **T5** Fixture and key tables match jimbo-dj's schema; SETUP counts the way jimbo-dj counts; reuse decided (vendor); HISTORY read API (overview, listens). *Done.*
- **T6** Overview: counts, the year heatmap, top artists; a stats cache in traqfreq's database. *Done.*
- **T7** Counted once: duplicates and held bursts with their reasons; new bot checks, read-only. *Done.*
- **T8** Years, Wrapped, This day, Top; gate script, gate on the Mac mini. *Done.* **P1 gate passed 2026-11-22** (HANDOFF).
## P2 LIBRARY read-only: T9–T12
Spec: [t9-library.md](t9-library.md).
- **T9** Library numbers (jimbo-dj's `library.stats`) and the rows behind them. *Done* (API only; the page is T10).
- **T10** LIBRARY page. *Done.*
- **T11** Albums, artists, a track. *Done.*
- **T12** Gate script and `GET /api/library/compare`, the compare page, the gate card on SETUP and LIBRARY. *Done.* **P2 gate passed 2026-11-23** (HANDOFF).
## P3 SERVERS: T13–T19
Spec: [t13-servers.md](t13-servers.md).
- **T13** Track identity, the Plex side: file key, song and match key of every copy, its problems; the three servers' settings and status. *Done* (API only; the page is T15).
- **T14** Matching on snapshots: file, MusicBrainz ID, tags; one to one; every unmatched copy and item with its reason. *Done* (API only, on invented snapshots).
- **T15** SERVERS page on SETUP; "On servers" on LIBRARY's track page. *Done* (on invented snapshots; `rating_key` filter on `/api/servers/matches`).
- **T16** Reading servers: the GET-only client, snapshot refresh, plays on other servers shown beside, never added. *Done* (client, refresh and its log, the button on SERVERS; the readers are T17 and T18).
- **T17** Jellyfin. *Done* (the reader: System/Info, folders, paged `/Items`, one user's play counts; name and version on SERVERS; live: 53,133 of 53,133 Plex copies by file, also from the deployed container).
- **T18** Navidrome. *Done* (the reader: ping, folders, scan status, albums, `search3`; torn reads refused; name and version on SERVERS; `TRAQFREQ_NAVIDROME_ROOTS`; live: 52,985 songs, paths hidden (Report Real Path off), 52,712 of 53,133 Plex copies by MBID and tags: HANDOFF).
- **T19** Gate "One song, three servers": `scripts/p3_gate.py`, `GET /api/servers/compare`, run on live data. *Done* (the three checks, the gate card on SETUP). **P3 gate passed 2026-11-24** on the deployed app, after Report Real Path was turned on for traqfreq's Navidrome player: every pair one to one (53,274 of 53,274), 0 unmatched, spot check 44 of 44 answers ok (HANDOFF).
## P4 TAGS read-only: T20–T23
Spec: [t20-tags.md](t20-tags.md).
- **T20** The ladder: broad to specific, any depth, shared parents, on jimbo-dj's vendored tag rules; the ladder's agreement with jimbo-dj's families; the TAGS page. *Done.*
- **T21** Albums tagged track by track (per-track tags by source, the analyzer's styles vendored). *Done* (the album and track pages on TAGS, linked from LIBRARY; gate check 2 in `GET /api/tags/tracks/check`).
- **T22** Proposals inbox: jimbo-dj's audit and suggestions, shown, not written. *Done.*
- **T23** Genre pages, the genre map, movements; gate script `scripts/p4_gate.py`, run on live data. *Done* (a page per tag, the map, `movements.json`, `GET /api/tags/compare`, the gate card on TAGS and SETUP). **P4 gate passed 2026-11-24** on the deployed app, all three checks, once jimbo-dj's stored `library.tags` had caught up with its own data (checked strictly, never loosened; HANDOFF).
## P5 PLAYLISTS Junction preview: T24–T28
Spec: [t24-playlists.md](t24-playlists.md). Gate: the same lines give the same tracks as jimbo-dj's builder (`POST /api/rules/preview`, which writes nothing) for ten trees, and the same list of saved playlists.
- **T24** Lines: every saved playlist with its three switches (read-only), the lines of the ones with a tree (AND, OR, NOT, nested groups), each line's and each condition's count as jimbo-dj counts it, the rows behind each (vendored `rules.py` Shape, Words, URL form, Matching). *Done.*
- **T25** The Junction and its levers: picking (shares, cap per artist, priority, shuffle, Never in mixes), the drawing, `/library/junction?b=…`; each switch with how many tracks have a copy on its server. *Done* (picking vendored, `junction.py`, the Junction page, copies per switch, gate check 1 and check 2's set in `playlists_gate.py`, on the fixture).
- **T26** Movements, rooted to roaming (preview only, not in the gate). *Done* (`reach.py`: a line follows the tag of each style condition it needs; four stops, rooted, ladder, movement, roaming, each counted with jimbo-dj's style rule; the read-only slider on the Junction, `/library/junction/reach` rows).
- **T27** Flow order and why this track (B3). *Done* (`flow.py` and `mixes.latest` vendored; the picked tracks in jimbo-dj's flow order, gate check 2 in full in `playlists_gate.py`; each picked track with its line's conditions met or not and its transition).
- **T28** The Ask box; the gate script `scripts/p5_gate.py`, `GET /api/playlists/compare`, the gate card, a live run. *Done* (`ask.py`: typed parts, by sound through jimbodj-text, by Ollama when it's on; `p5_trees.json`, check 3, the compare endpoints, the gate card on LIBRARY and SETUP). **P5 gate passed 2026-11-26** on live data: 10 of 10 trees with the same lines and the same tracks in the same order, 77 of 77 saved playlists the same (HANDOFF).
**Ryan's requirement (2026-11-24), for every playlist and mix:** three separate switches, *Plex*, *Jellyfin* and *Navidrome*, each deciding whether that playlist is on that server; any mix of them, none implied by another. Navidrome also has NaviBeat connected to it (to look at when the Navidrome push is built: what it reads from Navidrome's playlists). P5 shows the switches read-only (where each playlist would go); P6 makes them push.
## P6 Cut-overs: T29–T44
Spec: [t29-cutovers.md](t29-cutovers.md). Order confirmed by Ryan 2026-11-27. Each cut-over: one copy into traqfreq's `library.sqlite`, checked by count; traqfreq reads and writes its copy; that job is switched off in jimbo-dj (Ryan, at deploy); gate = a week with it off and nothing missed. jimbodj-text and the native analyzer stay as they are.
- **1. Plex scan and play log** (scan, Plex plays, Last.fm API, MusicBrainz; one switch-off):
  - **T29** Spec; `library.sqlite`, the cut-over registry, the reading connection, the one-time copy with its count check, rollback, status (`own.py`, `traqfreq-cutover`), on the fixture. *Done.*
  - **T30** Plex sync and the watcher, the runs log, the switch-off check on SETUP.
  - **T31** Play log (Last.fm API, Plex history, dedupe, rematch), MusicBrainz; deploy, copy, switch-off; gate script.
- **2. History imports:** **T32** uploads with undo per import; **T33** ListenBrainz; **T34** imports page, time zone, gate.
- **3. Analyzer:** **T35** copy, queue, the agent's endpoints; **T36** the agent pointed at :4492, progress, gate.
- **4. Playlists:** **T37** NaviBeat first, copy, saving, the three switches stored; **T38** push to Plex, Jellyfin, Navidrome (preview, log, undo); **T39** scheduled mixes, Keep fresh, re-cluster, gate.
- **5. Fix in Plex:** **T40** copy, plan, apply, undo; **T41** files too, file tags job, gate.
- **6. Jobs and log:** **T42** the scheduler and its tables; **T43** the log page, leftover jobs.
- **7. Backups:** **T44** nightly online backups, restore check, jimbo-backup job, gate.
## P7 New modules
DISCOVER, MIXES, FETCH, language loop.
## P8 Retire jimbo-dj
The other nine design directions ship as skins.

Per-session specs (`tN-<slug>.md`) are added here by the session before.
