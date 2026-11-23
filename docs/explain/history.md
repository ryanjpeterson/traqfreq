# History

## Timeline

| When | What happened |
|-|-|
| 2026-11 (before 22) | Planning in chat: a pitch deck, ten design directions, the Berlin · Gelb brand, and the decision to build beside jimbo-dj instead of inside it |
| 2026-11-22 | P0 shell: repo, read-only legacy DB, fixture, CI (T1); web shell and tokens (T2); the eleven kit components (T3); nav, map home, SETUP, container on :4492 (T4); deployed, gate passed |
| 2026-11-22 | P1 HISTORY: read API counted with jimbo-dj's vendored code (T5), overview (T6), counted once (T7), Years, Wrapped, Top and the gate (T8); gate passed, 862 of 862 numbers |
| 2026-11-22 | P2 LIBRARY: numbers and rows (T9), the page (T10), albums, artists and tracks (T11), plays from every source |
| 2026-11-23 | P2 gate built (T12) and passed on live data, 60 of 60 fields; P3 spec and track identity on the Plex side (T13); `.env.example`; jimbo-explain docs; matching on snapshots (T14); the SERVERS page and On servers (T15); the GET-only server client and refresh (T16) |

## Milestones

- 2026-11-22, 2026.11.0: first deployable shell (P0 gate).
- 2026-11-22, PR #2/#3: P1 gate passed, HISTORY equal to jimbo-dj's.
- 2026-11-23, PR #9 (bbc6cf9): P2 gate, passed on live data the same day.
- 2026-11-23, PR #10 (341088e): P3 begins: one song across servers.

## Pivots and renames

- Built beside jimbo-dj, not in it (planning, before 2026-11-22): a rewrite in place would risk jimbo-dj's database.
- 2026-11-22: sessions moved from a cloud container (T1, T2) to the laptop working in the server checkout over SMB (T3 on).
- 2026-11-22: reuse by vendoring jimbo-dj's pure functions unchanged instead of depending on its repo (it is private).

## By the numbers

First commit 2026-11-22 (84579ad), latest 2026-11-23 (341088e). 45 commits, 23 on the main line, 10 pull requests. CHANGELOG versions 2026.11.0 and 2026.11.1; no tags. Built by Ryan with Claude Code sessions T1–T16.
