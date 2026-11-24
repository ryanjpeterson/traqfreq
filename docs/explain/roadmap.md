# Roadmap

The phases and sessions are planned in [docs/specs/README.md](../specs/README.md); each phase's spec is in `docs/specs/`.

## Now

- **P4 TAGS read-only, T20–T23** ([spec](../specs/t20-tags.md)). T20 done: the ladder on jimbo-dj's vendored tag rules, checked against its families (live: 15 of 15 broad tags, 403 of 403 ladders). T21 done: albums tagged track by track, each track's tags by source, the analyzer's styles vendored, gate check 2. Next: T22 the proposals inbox (shown, not written), T23 genre pages, the genre map and the gate.

## Next

1. **P4 TAGS** read-only (4 sessions), **P5 PLAYLISTS** Junction preview (5 sessions). After P5, traqfreq shows everything jimbo-dj shows, read-only.

## Later

- **P6 cut-overs** (~15 sessions): imports, scans, analyzer, playlists, Fix in Plex, jobs, backups move from jimbo-dj one at a time, each switched off there.
- **P7 new modules** (~30): DISCOVER, MIXES, FETCH, the language loop.
- **P8** retire jimbo-dj; the other nine design directions ship as skins.

## Ideas

- Every playlist and mix gets three separate switches, Plex, Jellyfin and Navidrome, for which servers it goes to (Ryan, 2026-11-24): shown in P5, pushed in P6. Navidrome also has NaviBeat connected to it.
- Import Jellyfin and Navidrome plays as listens, under HISTORY's priority rules (needs a rule for overlaps first).
- A separate rule for Last.fm batch scrobbles before any burst check changes a count (T7 found the burst rule would hold about a fifth of plays).

## Decided against

- Rewriting jimbo-dj in place: risks its database and analysis.
- A git dependency on jimbo-dj: its repo is private; vendor instead.
- Album art in P2: it comes from Plex with jimbo-dj's token; traqfreq doesn't call Plex.
- Audio fingerprints to match tracks across servers: they would open the files.
