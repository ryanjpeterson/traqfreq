# Overview

## What it is

A self-hosted music app for one listener: the listening history from every source (Last.fm, Plex, Spotify, Apple Music), the library (tracks, albums, artists, files, analysis), and from P3 the same song across Plex, Jellyfin and Navidrome. Every number says which rule it counts by and opens the rows it counts. It is jimbo-dj's redesign, built beside it rather than in it.

## Why it exists

jimbo-dj grew from a Plex playlist editor into the home of the whole listening history, and its look and structure stopped fitting. Rewriting it in place would risk the library and about 11 hours of analysis in its database. So traqfreq runs next to it, reads its database without ever writing, proves each module matches jimbo-dj's numbers (a gate per phase) and only then takes over that module's writes (P6), until jimbo-dj can be switched off (P8).

## What it is not

- Not a player and not a media server: Plex, Jellyfin and Navidrome stay the servers.
- Not a writer yet: until a module's cut-over (P6), jimbo-dj keeps every write (imports, scans, analyzer, playlists, Fix in Plex, jobs, backups).
- Not a tag editor: it never changes Plex metadata except genre tags through an explicit, previewed, undoable Fix (P6 and later).
- Not for anyone else: one listener, one library, tailnet only.

## Principles and hard rules

- jimbo-dj's database is read-only: only `traqfreq.legacy.connect()` opens it (`mode=ro` URI and `query_only`).
- One writer at a time: jimbo-dj keeps each write until that module's cut-over.
- Transparent: every number can show its rows; every automatic change is logged with its reason and an undo.
- Nothing counts twice (a play heard on two sources is one play; Plex's count and the history's are never added).
- No paid APIs. Audio files are read-only.
- Never write to Plex, Jellyfin or Navidrome in P3: GET requests only.
- Tests run only on the invented fixture (`scripts/make_fixture.py`), never on real data.
- Design: Berlin · Gelb, only the eleven kit components, tokens only from `tokens/berlin.json`, all copy in `web/src/copy/strings.json` (`docs/specs/brand.md`).

## Status

Active since 2026-11-22. P0 (shell), P1 (HISTORY), P2 (LIBRARY), P3 (SERVERS: one song on Plex, Jellyfin and Navidrome) and P4 (TAGS, read-only) are done and passed their gates on live data. P5 (PLAYLISTS, the Junction preview) is under way: T24 shows jimbo-dj's saved playlists, each with its three server switches, and the lines of each tree counted with jimbo-dj's rules. Done would be P8: jimbo-dj off for a week with traqfreq doing everything it did.
