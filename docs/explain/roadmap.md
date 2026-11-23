# Roadmap

The phases and sessions are planned in [docs/specs/README.md](../specs/README.md); each phase's spec is in `docs/specs/`.

## Now

- **P3 SERVERS, T16: reading servers.** The GET-only client base (timeouts, paging, no retries, the server's own error shown) and snapshot refresh (`POST /api/servers/{server}/refresh`, writing only traqfreq's database, one at a time, logged with its counts); plays on other servers shown beside, never added. Spec: `docs/specs/t13-servers.md`.

## Next

1. **T17 Jellyfin, T18 Navidrome**: read their libraries (medium each; need their URLs and keys).
2. **T19** gate "One song, three servers" on live data (small).
3. **P4 TAGS** read-only (4 sessions), **P5 PLAYLISTS** Junction preview (5 sessions). After P5, traqfreq shows everything jimbo-dj shows, read-only.

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
