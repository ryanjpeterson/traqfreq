# T13–T19: SERVERS, one song on three servers (P3)

**Gate: one song, three servers.** For every live track in the library, traqfreq names the matching item on Plex, Jellyfin and Navidrome, or says why there isn't one, and shows how it decided (W3). On the live servers:
1. Every copy whose file each server can see is matched to exactly one item on that server, and no item is matched twice (one to one, per server).
2. Every copy left unmatched has a reason (no such file on that server, two candidates, the server hides paths, …), and the reasons add up to the unmatched count.
3. A spot check: `scripts/p3_gate.py` takes a sample of songs (every case below, plus 20 at random), asks each server for its item by ID, and checks that the file and the duration (within 2 s) agree with Plex's.

`scripts/p3_gate.py --url http://macmini:4492` prints it; exit 0 = passed. As in P1 and P2, the gate is recorded in HANDOFF.

traqfreq only reads. It never writes to Plex, Jellyfin or Navidrome (no playlists, no play counts, no scrobbles, no tags), never opens audio files, and never writes to jimbo-dj's database. Only GET requests leave traqfreq; the client code has no other verb. No paid APIs; MusicBrainz is used only as IDs the servers already hold in their tags (no lookups).

## How jimbo-dj identifies a track today (read at jimbo-dj 1d8a7cb, `git show` only)
Source: `src/jimbodj/db.py` (`tracks`, `albums`, `artists`), `plex.py` (`track_row`, `map_path`), `songs.py` (vendored in T11 as `vendor/jimbodj_songs.py`), `history.py` (`norm_artist`, `norm_title`, `match_key`, `rematch`; vendored in T8 as `vendor/jimbodj_history.py`).

- **One server.** jimbo-dj has no Jellyfin or Navidrome code: its README and roadmap list them as "next" ("read the library and its play history from Navidrome (the Subsonic API) and Jellyfin, map their tracks to the same files and analysis"). Plex is the only source of the library.
- **A copy is a Plex track:** `tracks.rating_key` (Plex's `ratingKey`), the primary key everything hangs from (analysis, features, embeddings, `listens.rating_key`, `listen_matches`). Plex's `guid` (`plex://track/…`) is stored but never used to match. No track MusicBrainz ID is stored; albums and artists have Plex's MusicBrainz release and artist IDs (`albums.mbid`, `artists.mbid`).
- **The file:** `plex_path` is the first part's `file` as Plex sees it (a multi-part track keeps only its first part; `parts` counts them). `local_path` is `plex_path` moved from a Plex folder to jimbo-dj's folder by `PATH_MAP` (`map_path`); NULL when outside every mapped folder. jimbo-dj's configured Plex folders are the keys of its stored `library.stats` `paths.folders`.
- **A song** (songs.py) is the artist and the title with the version stripped: `squash(song_slug(track_artist or artist, title))`. Its copies (the album track, a live take, a compilation, a single) are one song on pages; `Index.best` picks the one a song page opens on (the original, then the most played).
- **A listen** is matched by `match_key` = `norm_artist(artist)|norm_title(title)` (folded, `the` and `feat.` dropped, brackets and " - Live …" suffixes dropped). `rematch` gives each key a default copy (`listen_matches`) and a play that names its album or a live take its own copy (`listens.rating_key`); Plex plays carry their rating key.

## What P3 needs
A track's identity on a server is that server's item ID. traqfreq maps each Plex copy to one Jellyfin item and one Navidrome song, kept in traqfreq's own database, never in jimbo-dj's. All three servers read the same music folder (on the Mac mini), so **the file is the anchor**, and tags only stand in where a server hides its paths.

- **File key:** the path below the server's music folder: Unicode NFC, `/` separators, no leading slash, case kept (`Kollektiv Nord/Ringbahn/01 Westkreuz.flac`). Each server has its own folders (Plex: jimbo-dj's `PATH_MAP` folders, else `TRAQFREQ_PLEX_ROOTS`, else the folder every path shares; Jellyfin: its library's folders, `/Library/VirtualFolders`; Navidrome: `getMusicFolders` plus its real path). The **loose key** is the file key case-folded, for a server on a case-insensitive disk.
- **Match tiers**, in order, each said on the match (W3):
  1. `file`: the same file key (then the same loose key, when only one item has it).
  2. `mbid`: the same MusicBrainz recording ID and release (the servers read it from the tags; Plex has none per track, so this tier matches Jellyfin and Navidrome to each other and inherits Plex's file match).
  3. `tags`: the same `match_key`, the same album (`norm_title`), the same disc and track number, durations within 2 s; only when exactly one candidate is left.
  Nothing else: no fuzzy titles, no audio fingerprints (they would open the files).
- **One to one:** an item matched by one copy is not offered to another. Two Plex copies of one file (`shared_file`) both point at the one item and say so; a multi-part Plex track matches the item of its first part and lists the other parts as not matched (`multi_part`).
- **Reasons** an item or a copy is unmatched: `no_path` (Plex gives no file), `outside_roots` (the file is outside the known music folders), `not_on_server` (no item with that file or tags), `ambiguous` (more than one candidate at the first tier that has any), `hidden_path` (the server gives no real path: Navidrome without "Report Real Path"), `not_in_plex` (an item no copy matched: a file Plex doesn't list).
- **Snapshots:** each server's item list is read whole (paged), stored in traqfreq's database with when it was read and the server's own stamp (Jellyfin's item count and newest `DateCreated`, Navidrome's `lastScan`), and matched from there. A refresh is a read; the page says how old each snapshot is.
- **Plays on other servers** (Jellyfin `UserData.PlayCount`, Navidrome `playCount`) are shown beside a track, labelled with their server. They are never added to the history or to `plays_of` (nothing counts twice); importing them as listens is P6 or later, under HISTORY's priority rules.
- **Settings** (environment; secrets never shown, logged or sent anywhere but their own server):
  - `TRAQFREQ_PLEX_ROOTS`: Plex's music folders, comma-separated, only if jimbo-dj stored none.
  - `TRAQFREQ_JELLYFIN_URL`, `TRAQFREQ_JELLYFIN_KEY` (an API key from Jellyfin's Dashboard → API Keys), `TRAQFREQ_JELLYFIN_USER` (optional: the user whose play counts are shown).
  - `TRAQFREQ_NAVIDROME_URL`, `TRAQFREQ_NAVIDROME_USER`, `TRAQFREQ_NAVIDROME_PASSWORD` (Subsonic token auth: `t = md5(password + salt)`, a new salt per request). For file matching, Navidrome must report real paths (`ND_SUBSONIC_DEFAULTREPORTREALPATH=true`, or the player's "Report Real Path"); without it every Navidrome song falls to the `mbid` and `tags` tiers and the page says `hidden_path`.
  - A server with no URL is "not set up": every page works without it, and its column says so.
  - **Needed from Ryan before T17/T18:** whether Jellyfin and Navidrome run on the Mac mini, their URLs, a Jellyfin API key, and a Navidrome user (read-only use) with Report Real Path on. Put them in the deploy's `.env`, never in the repo.

## Reuse
Vendored already, unchanged: `songs.py` (song keys, `Index`) and history.py's `norm_artist`, `norm_title`, `match_key`. Nothing new to vendor: jimbo-dj has no server code beyond Plex. The Jellyfin and Navidrome readers are traqfreq's own (`httpx`, GET only, a timeout, paging; tests use `httpx.MockTransport` with recorded-shape answers, invented).

## Sessions
### T13: track identity, the Plex side
- `src/traqfreq/identity.py`: Plex's music folders (where they come from, said), the file key and loose key of every live copy, its song (`songs.py`) and match key (history.py), and its problems: `no_path`, `outside_roots`, `shared_file`, `loose_clash` (two files equal once case-folded), `multi_part`, `no_duration`. Kept in memory per library state.
- `src/traqfreq/servers.py`: the three servers' settings and status (Plex = jimbo-dj's database: server name, version, last sync, tracks; Jellyfin and Navidrome: set up or not, with which settings, never the secrets).
- API: `GET /api/servers` (status), `GET /api/servers/identity` (every count with its rule and its rows, cached as `servers.identity`), `GET /api/servers/copies?issue=&song=&file=&offset=&limit=` (the rows). API only; the page is T15.
- Tests on the fixture, with the problem cases added to a scratch copy (two copies of one file, a file outside the folders, no path, a decomposed path, a case clash).
### T14: matching on snapshots
- The server item shape (`server`, `id`, file key, title, artist, album artist, album, disc, track, duration, MusicBrainz recording and release IDs, size, play count) and a `snapshots` table in traqfreq's database (server, read at, stamp, items).
- `match(copies, items)`: the tiers above, one to one, every unmatched copy and item with its reason; Plex ↔ Jellyfin, Plex ↔ Navidrome, and Jellyfin ↔ Navidrome where both fall to tags.
- Fixture: invented Jellyfin and Navidrome snapshots (JSON in each API's shape) covering every tier and every reason. API: `GET /api/servers/matches?server=&tier=&reason=`.
### T15: SERVERS page
- On SETUP (`/setup/servers`; SERVERS is not a new module badge): the three servers with status and snapshot age; the identity counts and the match counts by tier and by reason, each opening its rows (W3); a song's three IDs. LIBRARY's track page gains "On servers" (each server's item, tier and play count, labelled). Bars as lists with a summary (L6). Light, dark, 375 px.
### T16: reading servers
- The read-only client base: GET only, timeouts, paging, retries off, errors shown with the server's own message; snapshot refresh (`POST /api/servers/{server}/refresh` writes only traqfreq's database), one refresh at a time per server, logged with its counts.
- Plays on other servers shown beside Plex's and the history's, never added.
### T17: Jellyfin
- `/System/Info/Public` (name, version), `/Library/VirtualFolders` (folders), `/Items?IncludeItemTypes=Audio&Recursive=true&Fields=Path,ProviderIds,MediaSources,ParentId&StartIndex=&Limit=` (T17 adds `DateCreated` for the stamp; `Authorization: MediaBrowser Token="…"`; Jellyfin 12 refuses the old `X-Emby-Token`), user data from `/Users/{id}/Items` when a user is set. Snapshot, match, check on live data (needs the URL and key).
### T18: Navidrome
- Subsonic: `ping`, `getMusicFolders`, every song through `search3` (empty query, `songCount`/`songOffset` paging), OpenSubsonic fields (`musicBrainzId`, `path`, `played`, `playCount`). Snapshot, match, check on live data (needs the URL, user and Report Real Path).
### T19: gate
- `scripts/p3_gate.py` (`--url`, read-only) and `GET /api/servers/compare`: the three checks above; the gate card on SETUP. Gate run on live data, recorded in HANDOFF.

## Not in P3
Writing to any server (playlists, play counts, scrobbles, tags, Fix in Plex): P5–P6. Importing Jellyfin or Navidrome plays as listens: later, under HISTORY's priority rules. Fingerprints or opening audio files. MusicBrainz lookups. Making Jellyfin or Navidrome the library's source instead of Plex (Plex stays the source until P8). Changing jimbo-dj.
