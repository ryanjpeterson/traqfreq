# Roadmap

The phases and sessions are planned in [docs/specs/README.md](../specs/README.md); each phase's spec is in `docs/specs/`.

## Now

- **P5 PLAYLISTS, the Junction preview, T24–T28** ([spec](../specs/t24-playlists.md)).
  - T24 done: every saved playlist with its Plex, Jellyfin and Navidrome switches (read-only), and the lines of the ones with a tree. Each line's AND, OR and NOT conditions are counted with jimbo-dj's vendored rules, each count opening its rows.
  - T25 done: the Junction. jimbo-dj's picking vendored (shares, the cap per artist, line order, shuffle, Never in mixes); what any tree picks now, with each line's count, share, got and available, at `/library/junction?b=…`; the drawing with its list view and read-only levers; each switch with how many tracks have a copy on its server.
  - Next, T26 movements. Then T27 flow order and why, T28 the Ask box and the gate ("Same tracks as jimbo-dj").
  - After P5, traqfreq shows everything jimbo-dj shows, read-only.

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
