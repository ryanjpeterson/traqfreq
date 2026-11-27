# Roadmap

The phases and sessions are planned in [docs/specs/README.md](../specs/README.md); each phase's spec is in `docs/specs/`.

## Now

- **P6 cut-overs, one writer at a time, T29–T44** ([spec](../specs/t29-cutovers.md)). Order (Ryan, 2026-11-27): Plex scan and play log, history imports, analyzer, playlists, Fix in Plex, jobs and log, backups. Each: switched off in jimbo-dj, copied once into traqfreq's `library.sqlite` and checked by count, then read and written there; gate a week with jimbo-dj's switch off and nothing missed.
  - T29 done: the spec; `library.sqlite`, the cut-over registry, the reading connection (traqfreq's copy in front of jimbo-dj's database, every reader unchanged), the one-time copy with its count check, rollback, `traqfreq-cutover`, `GET /api/cutovers`. On the fixture; nothing copied live yet.
- **P5 PLAYLISTS, the Junction preview, T24–T28** ([spec](../specs/t24-playlists.md)): done, gate passed on live data 2026-11-26. With P5, traqfreq shows everything jimbo-dj shows, read-only.

## Next

1. **T30**: the Plex sync and the watcher (vendored), the runs log, the switch-off check on SETUP.
2. **T31**: the play log (Last.fm API, Plex history) and MusicBrainz; deploy, copy, jimbo-dj's sync job off; the first cut-over's gate.

## Later

- **P6, cut-overs 2–7** (T32–T44): history uploads and ListenBrainz, analyzer, playlists (three switches pushing), Fix in Plex, jobs and log, backups.
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
