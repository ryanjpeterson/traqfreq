# Roadmap

The phases and sessions are planned in [docs/specs/README.md](../specs/README.md); each phase's spec is in `docs/specs/`.

## Now

- **P5 PLAYLISTS, the Junction preview, T24–T28** ([spec](../specs/t24-playlists.md)). Done: **the P5 gate passed on live data on 2026-11-26.**
  - T24 done: every saved playlist with its Plex, Jellyfin and Navidrome switches (read-only), and the lines of the ones with a tree. Each line's AND, OR and NOT conditions are counted with jimbo-dj's vendored rules, each count opening its rows.
  - T25 done: the Junction. jimbo-dj's picking vendored (shares, the cap per artist, line order, shuffle, Never in mixes); what any tree picks now, with each line's count, share, got and available, at `/library/junction?b=…`; the drawing with its list view and read-only levers; each switch with how many tracks have a copy on its server.
  - T26 done: rooted to roaming. A line follows the tag of each style condition it needs; a read-only slider shows four stops (the tag alone, its ladder, its movement, its neighbours on the genre map), each counted with jimbo-dj's style rule and opening its rows. New in traqfreq, a preview, not in the gate.
  - T27 done: flow order and why this track. jimbo-dj's `flow.py` vendored, so the picked tracks come in its play order and gate check 2 covers the order as well as the set; every picked track shows its line's conditions as true or false and its transition from the track before.
  - T28 done: the Ask box (words to a line: typed parts, by sound through jimbo-dj's CLAP text server, by a local Ollama when it's on) and the gate "Same tracks as jimbo-dj": `scripts/p5_gate.py`, `GET /api/playlists/compare`, `p5_trees.json`, check 3 (the saved list) and the gate card on LIBRARY and SETUP. Live: 10 of 10 trees, 77 of 77 saved playlists.
  - With P5, traqfreq shows everything jimbo-dj shows, read-only.

## Next

1. **P6 cut-overs**: one writer at a time, starting where Ryan chooses. The playlists cut-over pushes each playlist and mix to the servers its switches name.

## Later

- **P6 cut-overs** (~15 sessions): imports, scans, analyzer, playlists, Fix in Plex, jobs and backups move from jimbo-dj one at a time, each switched off there.
- **P7 new modules** (~30): DISCOVER, MIXES, FETCH, the language loop.
- **P8** retire jimbo-dj; the other nine design directions ship as skins.

## Ideas

- Before the Navidrome push (P6), look at what NaviBeat reads from Navidrome's playlists.
- Import Jellyfin and Navidrome plays as listens, under HISTORY's priority rules (needs a rule for overlaps first).
- A separate rule for Last.fm batch scrobbles before any burst check changes a count (T7 found the burst rule would hold about a fifth of plays).

## Decided against

- Rewriting jimbo-dj in place: risks its database and analysis.
- A git dependency on jimbo-dj: its repo is private; vendor instead.
- Album art in P2: it comes from Plex with jimbo-dj's token; traqfreq doesn't call Plex.
- Audio fingerprints to match tracks across servers: they would open the files.
