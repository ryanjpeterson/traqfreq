# Roadmap

The phases and sessions are planned in [docs/specs/README.md](../specs/README.md); each phase's spec is in `docs/specs/`.

## Now

- **P3 SERVERS, T18: Navidrome.** Fill `reading.READERS["navidrome"]` (Subsonic `ping`, `getMusicFolders`, every song through `search3`, OpenSubsonic fields), refresh on live data and check the matches. Needs Navidrome's URL, a user and Report Real Path in the deploy's `.env`. Spec: `docs/specs/t13-servers.md`.
- **Jellyfin from the container**: T17 read it live from the laptop (53,133 of 53,133 Plex copies matched by file); after the deploy, press Refresh Jellyfin on SERVERS to check `host.docker.internal` from inside the container.

## Next

1. **T19** gate "One song, three servers" on live data (small).
2. **P4 TAGS** read-only (4 sessions), **P5 PLAYLISTS** Junction preview (5 sessions). After P5, traqfreq shows everything jimbo-dj shows, read-only.

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
