# Roadmap

The phases and sessions are planned in [docs/specs/README.md](../specs/README.md); each phase's spec is in `docs/specs/`.

## Now

- **P3 SERVERS: rerun the gate "One song, three servers" with Report Real Path on.** T19 built it (`scripts/p3_gate.py`, `GET /api/servers/compare`, the card on SETUP); on 2026-11-24 it did not pass, only because Navidrome hides all 52,985 paths. Turn on Report Real Path for traqfreq's Navidrome player, Refresh Navidrome, run the gate. Spec: `docs/specs/t13-servers.md`.

## Next

1. **P4 TAGS** read-only (4 sessions), **P5 PLAYLISTS** Junction preview (5 sessions). After P5, traqfreq shows everything jimbo-dj shows, read-only.

## Later

- **P6 cut-overs** (~15 sessions): imports, scans, analyzer, playlists, Fix in Plex, jobs, backups move from jimbo-dj one at a time, each switched off there.
- **P7 new modules** (~30): DISCOVER, MIXES, FETCH, the language loop.
- **P8** retire jimbo-dj; the other nine design directions ship as skins.

## Ideas

- Import Jellyfin and Navidrome plays as listens, under HISTORY's priority rules (needs a rule for overlaps first).
- A separate rule for Last.fm batch scrobbles before any burst check changes a count (T7 found the burst rule would hold about a fifth of plays).

## Decided against

- Rewriting jimbo-dj in place: risks its database and analysis.
- A git dependency on jimbo-dj: its repo is private; vendor instead.
- Album art in P2: it comes from Plex with jimbo-dj's token; traqfreq doesn't call Plex.
- Audio fingerprints to match tracks across servers: they would open the files.
