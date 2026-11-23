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
| P6 | Cut-overs, one writer at a time | ~15 | Each switched off in jimbo-dj |
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
## P3 SERVERS
- T13–T16 track identity · T17 Jellyfin · T18 Navidrome · T19 gate.
## P4 TAGS read-only: T20–T23
## P5 PLAYLISTS Junction preview: T24–T28
## P6 Cut-overs (~15)
Imports, scans, analyzer, playlists, Fix in Plex, jobs, backups. Each is switched off in jimbo-dj as traqfreq takes the write.
## P7 New modules
DISCOVER, MIXES, FETCH, language loop.
## P8 Retire jimbo-dj
The other nine design directions ship as skins.

Per-session specs (`tN-<slug>.md`) are added here by the session before.
