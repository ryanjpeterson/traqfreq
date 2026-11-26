# History

## Timeline

| When | What happened |
|-|-|
| 2026-11 (before 22) | Planning in chat: a pitch deck, ten design directions, the Berlin · Gelb brand, and the decision to build beside jimbo-dj instead of inside it |
| 2026-11-22 | P0 shell: repo, read-only legacy DB, fixture, CI (T1); web shell and tokens (T2); the eleven kit components (T3); nav, map home, SETUP, container on :4492 (T4); deployed, gate passed |
| 2026-11-22 | P1 HISTORY: read API counted with jimbo-dj's vendored code (T5), overview (T6), counted once (T7), Years, Wrapped, Top and the gate (T8); gate passed, 862 of 862 numbers |
| 2026-11-22 | P2 LIBRARY: numbers and rows (T9), the page (T10), albums, artists and tracks (T11), plays from every source |
| 2026-11-23 | P2 gate built (T12) and passed on live data, 60 of 60 fields; P3 spec and track identity on the Plex side (T13); `.env.example`; jimbo-explain docs; matching on snapshots (T14); the SERVERS page and On servers (T15); the GET-only server client and refresh (T16); Jellyfin's reader (T17), checked live and from the deployed container; Navidrome's reader (T18), read live |
| 2026-11-24 | P3 gate built (T19) and passed on the deployed app once Navidrome reported real paths: every pair one to one over 53,274 copies |

## Milestones

- 2026-11-22, 2026.11.0: first deployable shell (P0 gate).
- 2026-11-22, PR #2/#3: P1 gate passed, HISTORY equal to jimbo-dj's.
- 2026-11-23, PR #9 (bbc6cf9): P2 gate, passed on live data the same day.
- 2026-11-23, PR #10 (341088e): P3 begins: one song across servers.
- 2026-11-23, PR #14 (bf15089): traqfreq can read servers: the GET-only client and snapshot refresh (T16).
- 2026-11-23, PR #16 (c76f665): Jellyfin read live, 53,133 of 53,133 Plex copies matched by file (T17).
- 2026-11-24, PR #18: P3 gate passed, one song on Plex, Jellyfin and Navidrome (53,274 of 53,274 on each pair).
- 2026-11-24, PR #25: P4 TAGS built (T20–T23: the ladder, tracks by source, the proposals inbox, tag pages, the genre map and movements). Its gate: checks 1 and 2 pass live, and check 3 waits on jimbo-dj's stored audit.
- 2026-11-24: P4 gate passed on the deployed app, all three checks, once jimbo-dj's stored audit caught up.
- 2026-11-24, T24: P5 begins, PLAYLISTS. The Junction preview's spec, the saved playlists with three switches each, and their lines counted with jimbo-dj's rules.
- 2026-11-25, T25: the Junction. jimbo-dj's picking vendored, any tree previewed at `/library/junction`, and each switch with its copies on that server.
- 2026-11-25, T26: rooted to roaming. Each line following its style tag along the ladder, the movements and the genre map, a read-only preview beside the Junction.
- 2026-11-25, T27: flow order and why this track. jimbo-dj's flow order vendored; each picked track with its conditions met or not and its transition.

## Pivots and renames

- Built beside jimbo-dj, not in it (planning, before 2026-11-22): a rewrite in place would risk jimbo-dj's database.
- 2026-11-22: sessions moved from a cloud container (T1, T2) to the laptop working in the server checkout over SMB (T3 on).
- 2026-11-22: reuse by vendoring jimbo-dj's pure functions unchanged instead of depending on its repo (it is private).

## By the numbers

First commit 2026-11-22 (84579ad), latest on `main` 2026-11-23 (c76f665, T17 merged). 76 commits, 31 on the main line, 16 pull requests. CHANGELOG versions 2026.11.0 and 2026.11.1; no tags. Built by Ryan with Claude Code sessions T1–T19.
