# T29–T44: Cut-overs, one writer at a time (P6)

**Goal (Ryan):** move the library, the listening history and the analysis into traqfreq, so jimbo-dj can be taken down. P0–P5 built a full traqfreq that only reads: it reads jimbo-dj's SQLite file (`traqfreq.legacy.connect()`, read-only), so stopping jimbo-dj would freeze its data. P6 moves jimbo-dj's writes over one at a time.

**Order (confirmed by Ryan 2026-11-27, T29):**
1. Plex scan and play log
2. History imports
3. Analyzer

After these three, the library, listens and analysis live in traqfreq.

4. Playlists
5. Fix in Plex
6. Jobs and log
7. Backups

**Native services (Ryan, 2026-11-27):** jimbodj-text (the CLAP text server on :4491 that the Ask box uses) and the native analyzer (`jimbodj-analyze` and its launchd agent) stay on the mini as they are. traqfreq takes only the server side of the analyzer: the queue and storing results.

**Every cut-over takes the same steps:**
1. **Build.** traqfreq's writer for the cut-over is deployed. It writes only once the cut-over is owned.
2. **Switch off.** That job is switched off in jimbo-dj. This is Ryan's step at deploy, and it comes before the copy, so no write can fall between them.
3. **Copy once.** The data is copied into traqfreq's own database and checked by count (`traqfreq-cutover copy <name>`).
4. **Read and write the copy.** From the copy on, traqfreq reads its own copy and writes it.
5. **Gate.** A week with jimbo-dj's switch off and nothing missed.

## Rules for every cut-over
- **One writer.** A table has one writer at a time. Until a cut-over is deployed and its jimbo-dj switch is off, jimbo-dj writes that table and traqfreq only reads it. From the copy on, traqfreq writes its own copy, and jimbo-dj must write nothing that traqfreq would miss. The legacy DB stays read-only forever: only `traqfreq.legacy.connect()` opens it, with `mode=ro` and `query_only`.
- **Tables move whole.** jimbo-dj's code writes a table from more than one place. So a cut-over owns whole tables, plus a few `meta` keys by name. It never owns a table's rows split by source.
- **The jimbo-dj schema, unchanged.** traqfreq's copy of a table has jimbo-dj's schema: the `CREATE` statement and its indexes come from jimbo-dj's `sqlite_master` at copy time. So every vendored reader works on the copy as it is. traqfreq's own columns and tables come later, beside jimbo-dj's, never in place of them.
- **Transparent.** Every automatic change is logged with its reason and how to undo it: a copy, a sync, an import, a push, a Fix or a rollback. Every number can show its rows.
- **No paid APIs.** Plex, Jellyfin and Navidrome are local. Last.fm, ListenBrainz and MusicBrainz are free and throttled the way jimbo-dj throttles them.
- **Hands off the music.** Audio files are read-only. Plex metadata changes only through the previewed, undoable genre Fix (cut-over 5).
- **Nothing counts twice.** jimbo-dj's dedupe and priority rules (`history.py`) are vendored unchanged. A play read twice, or from two sources, still counts once.
- **Tests use only the fixture** (`scripts/make_fixture.py`, invented rows), never real data. A live copy runs only at deploy, on the mini, by Ryan's command.

## traqfreq's library database
- **The file:** `TRAQFREQ_DATA_DIR/library.sqlite`, in the container `/data/library.sqlite` (`./data` on the server checkout).
- **Kept apart from `traqfreq.sqlite`.** That file holds caches, snapshots and refresh logs, and all of it can be rebuilt. `library.sqlite` holds data that exists nowhere else once jimbo-dj is off, so it is the file to back up (cut-over 7).
- **Like jimbo-dj's `db.connect`:** WAL, no memory-mapped reads. Never open it over SMB from the laptop: a checkpoint from another host is how jimbo-dj's database broke on 2026-11-10 (`dbheal.py`).
- **Tables:**
  - The owned tables, copied with jimbo-dj's schema.
  - `meta (key, value)`: only the keys a cut-over owns.
  - `cutovers (name, state, copied_at, stamp, counts, note)`: one row per cut-over. `state` is `owned` or `rolled_back`.
  - `cutover_log (id, at, name, action, reason, detail)`: every copy, refused copy and rollback, with its reason.
- **Code:** `src/traqfreq/own.py`.
  - `CUTOVERS` is the registry: each cut-over's tables (required or optional) and `meta` keys.
  - `copy(legacy_db, data_dir, name, reason)` makes the one-time copy and its check.
  - `rollback(data_dir, name, reason)` hands the tables back to jimbo-dj's copy.
  - `status(data_dir)` reports each cut-over's state.
  - `reader(settings)` opens the reading connection.
  - The command is `traqfreq-cutover status | copy <name> | rollback <name> --reason "…"`.

### The reading connection
Every page and API read goes through one connection (`own.reader`). It is jimbo-dj's database, opened read-only by `legacy.connect()`, with `library.sqlite` attached read-only as `own`. For each table an owned cut-over holds, the connection gets a TEMP VIEW with the table's name over `own.<table>`. SQLite looks up an unqualified name in `temp` first, so every reader sees traqfreq's copy without being changed. For the `meta` table, the TEMP VIEW takes traqfreq's keys first and jimbo-dj's for the rest.

- **The connection is still read-only.** `query_only` stays on, and the legacy file is still `mode=ro`.
- **Table checks still work.** `sqlite_master` is still jimbo-dj's, and jimbo-dj keeps its now-frozen copy of every table. So the 45 places that check whether a table exists still find it. `PRAGMA table_info` sees the view's columns, which are the copy's.
- **Before any copy,** the reading connection is exactly the legacy connection. A rolled-back cut-over's tables are not viewed.

### The one-time copy and its count check
`copy` writes only `library.sqlite`. It attaches jimbo-dj's file read-only (`mode=ro`). In one transaction, so jimbo-dj's side is read as one snapshot, it does this:
1. Creates each owned table and its indexes from jimbo-dj's `CREATE` statements.
2. Copies every row (`INSERT … SELECT *`).
3. Copies the owned `meta` keys.
4. Checks the copy:
   - **Per table:** the row counts are equal, and no row differs either way (`EXCEPT` both ways, so 0 and 0).
   - **The numbers jimbo-dj shows** (`legacy.MEASURES`: tracks, albums and artists counted its way, and plays) are equal through the reading connection and on jimbo-dj's side.
   - **Every owned `meta` key** is equal.
5. Records the stamp of what was copied: jimbo-dj's `last_sync`, the highest listen id, each table's count, and the newest `history_imports.at`. Commits.

Any failed check rolls the whole transaction back, so nothing is half-copied. The refusal and its reason go to `cutover_log`. A cut-over already owned is refused, so a second copy can't overwrite traqfreq's own writes. After a rollback, `copy` can run again. The tables put aside by the rollback stay in the file under their own names, for looking at later.

### Switch-off check ("nothing missed")
After the copy, jimbo-dj's copy of an owned table must not change. `GET /api/cutovers` compares jimbo-dj's side now with the stamp taken at copy time: counts, the highest id, `last_sync` and the newest import. Any change means jimbo-dj wrote after the switch-off (a manual Sync, an upload, a job left on). SETUP shows that with the rows that are new on jimbo-dj's side. Those rows are missed, never merged by themselves. The fix is to read them again into traqfreq. Each source can do that: Plex history from the last listen, Last.fm from the last scrobble, an upload again.

### Rollback (each cut-over)
1. **In traqfreq:** `traqfreq-cutover rollback <name> --reason "…"`. The owned tables are renamed `<table>__rolled_back_<unix time>`, the cut-over's `meta` keys go aside the same way, `state` becomes `rolled_back`, and the step is logged. Reads go back to jimbo-dj's copy at once.
2. **In jimbo-dj:** Ryan switches the job back on.
3. **Catching up:** jimbo-dj catches up by itself where its source allows it. Each cut-over below says how far.

What traqfreq wrote in the meantime stays in the put-aside tables and is never lost.

## What jimbo-dj writes today (read at 1d8a7cb, `git show` only)
- **Plex sync** (`library.sync`, `plex.py`, `metadata.py`): every track into `tracks`, upserted, with `removed_at` set on tracks a sync no longer sees. Then `albums` and `artists` (genres, release date, label, MusicBrainz IDs), then the audio streams (bit depth, sample rate, the track's Plex genres and moods). It sets `meta.last_sync` and `meta.server`.
  - **When it runs:** nightly (schedule job `sync`, 02:00), when the watcher sees Plex change (`watcher.py`: every `WATCH_INTERVAL`, default 300 s; off with `JIMBODJ_WATCH=off`), or from Sync in the UI.
  - **After each sync** (`routes/work.py`): `_history_after_sync` imports new Last.fm scrobbles (API) and Plex's play history, in that order. Then the MusicBrainz enricher runs (`musicbrainz.enrich`: `mb_artists`, `mb_releases`, `mb_artist_names`; one request a second; `MUSICBRAINZ=0` turns it off). The enricher also runs when the app starts, if there is anything new.
- **Play log and history** (`history.py`): one table, `listens`, for every source: Last.fm, Plex, Spotify, Apple Music.
  - `_insert` keeps a listen out if it is already there.
  - `dedupe` decides what counts: Last.fm first, then Plex, Spotify, Apple Music, each within its time window.
  - `rematch` fills `listen_matches` and copy-level `rating_key` against the live tracks.
  - Each import is a row in `history_imports`. It bumps `meta.history_version` (and `match_version` when keys are recomputed).
  - Plex history is read from the last Plex listen minus a day. Last.fm's from the last scrobble. Uploads come through Settings (`routes/settings.py`).
- **Analyzer** (`analysis_store.py`, `analyzer_control.py`, `routes/library.py`): the native agent asks `POST /api/analysis/agent` every 20 s whether to run (`--api`, `config.native_api_url()`). The analyzer takes work from the web app and sends results to `POST /api/analysis/results`. The web app, the only writer, stores `analysis`, `features` and `embeddings`. `retagged` records files whose size changed only because a genre tag was written, so they aren't analysed again. Start, stop, the nightly window and the settings live in `meta`.
- **Playlists** (`store.py`, `playlists.py`, `mixes.py`, `clusters.py`, `refresh.py`, `bans.py`):
  - **Tables:** `saved_playlists`, `mixes`, `cluster_runs`, `clusters`, `cluster_members` and `bans`.
  - **Pushes:** only to Plex, only playlists whose title starts with one of its emoji. `in_plex` is its one switch.
  - **Jobs:** `daily_mix`, `weekly_mix`, `dig_mix`, `this_day`, `refresh` and `recluster` build and push.
- **Fix in Plex** (`tagwrite.py`):
  - **What it changes:** an album's genre field in Plex, locked afterwards, and optionally the track files' genre tag (only with `MUSIC_MOUNT_MODE=rw`).
  - **Logs:** before and after go in `tag_edits` and `tag_file_edits` by batch, with undo. Files whose size changed go in `retagged`.
  - **File tags:** the `file_tags` job reads the files' genre tags into `file_tags`. It reads the files and writes only the database.
- **Jobs** (`schedule.py`, `jobs.py`): a scheduler thread in the web process (`JIMBODJ_SCHEDULER=off` stops it). Settings are in `meta.schedule` (each job on or off). Each job's last run is in `meta.schedule_last`. Running jobs are kept in memory only.
  - **The jobs:** sync, daily_mix, weekly_mix, recluster, dig_mix, this_day, refresh, releases, journey, stats and file_tags.
- **Backups:** jimbo-dj has no scheduled backup. It has `GET /api/backup` (an SQLite online backup, on demand), the CLI's dated `.bak-YYYYMMDD` before a migration, and `dbheal.py`, which copies a corrupt database aside and recovers it. jimbo-backup (rsync jobs) covers the music and Immich, not jimbo-dj.
- **Not in P6** (caches and DISCOVER, P7): `mb_artist_pages`, `mb_related`, `setlist_cache`, `journey_events`, the `releases` check and jimbo-dj's `stats` cache. They are written on page views or by jobs whose module comes in P7. Until then they stay jimbo-dj's, and traqfreq reads them as now.

## The cut-overs

### 1. Plex scan and play log: T29–T31
jimbo-dj's `sync` job also imports Plex's plays and Last.fm's scrobbles, and the MusicBrainz lookups follow it. So these move together, with one switch-off. `listens` is one deduplicated table for every source, so it moves whole here. Uploads come in cut-over 2.
- **traqfreq holds** (registry name `plex`):
  - **Tables:** `tracks`, `albums`, `artists`, `listens`, `listen_matches`, `history_imports`, `mb_artists` and `mb_releases`, plus `mb_artist_names` if present.
  - **`meta` keys:** `last_sync`, `server`, `history_version`, `match_version`, `plex_history_version`, `history_tz`, `applemusic_utc` and `watch_fingerprint` (the watcher's, added in T30).
- **One-time copy:** `traqfreq-cutover copy plex`, run on the mini at deploy (T31), right after jimbo-dj's switch-off, with the check above. Live sizes for reference: 54,355 track rows and about 351,000 listens.
- **What traqfreq writes from then on:**
  - **Plex sync:** jimbo-dj's `library.sync`, `plex.track_row`, `metadata.sync_albums_artists` and `sync_streams`, vendored unchanged with a stand-in for its db module. It writes only `library.sqlite` and reads Plex only (GET).
  - **The watcher:** as jimbo-dj has it, but off unless `TRAQFREQ_WATCH=on` (every `TRAQFREQ_WATCH_INTERVAL` s, default 300).
  - **Built in T30** (`src/traqfreq/plexsync.py`, `vendor/plex.py`, `metadata.py`, `library.py`, `watcher.py`): settings `TRAQFREQ_PLEX_URL`, `TRAQFREQ_PLEX_TOKEN` (a secret, in a header, never shown or logged), `TRAQFREQ_PLEX_MUSIC_SECTION`, `TRAQFREQ_PLEX_PATH_MAP`. plexapi's `PlexServer` is a GET-only httpx stand-in; `vendor/db.py`'s `connect` opens only `library.sqlite` and refuses unless `plex` is owned. Before writing, the sync works out every stored track's `local_path` again with the path map and refuses if any differs (set it to jimbo-dj's `PLEX_PATH_MAP`, or `MUSIC_DIR_N=MUSIC_MOUNT/N`). `traqfreq-cutover sync --reason …` runs one by hand. Rows the switch-off check finds are listed on SETUP (the Cut-overs card) by a rule per table: `listens` by id, `history_imports` by `at`, `tracks`, `albums`, `artists` by `seen_at` after the copy's `last_sync`, the MusicBrainz tables by `fetched_at` after the copy; `listen_matches` by count.
  - **After each sync:** the Last.fm API import, then Plex's play history (`history.import_lastfm_api`, `import_plex`, `_insert`, `dedupe`, `rematch` and `_finish_import`, vendored unchanged). Then the MusicBrainz enricher.
  - **Logs:** every run goes in a `runs` table in `library.sqlite`, with its counts (cut-over 6 shows the log). Every import is a `history_imports` row.
  - **Undo:** a sync can't be undone and doesn't need to be, since the next sync reads Plex again. An import is undone by its `history_imports` id (cut-over 2 builds the button).
- **Switched off in jimbo-dj** (Ryan, at deploy):
  - Settings → Schedule: job **Sync the library from Plex** off. This also stops its Last.fm and Plex history imports.
  - `JIMBODJ_WATCH=off` and `MUSICBRAINZ=0` in jimbo-dj's `.env`, then a restart.
  - Don't press Sync or Import history in jimbo-dj any more. The switch-off check catches it if it happens.
- **Switching back:** the job back on, the two env lines removed, a restart. jimbo-dj then catches up by itself: a full Plex sync, Plex plays from its last listen minus a day, Last.fm from its last scrobble, MusicBrainz for what's new.
- **Rollback:** `traqfreq-cutover rollback plex --reason "…"`, then switch back as above.
- **What it costs until cut-overs 3 and 4** (known and accepted): jimbo-dj's own copy of the library freezes. New music isn't analysed (the queue reads jimbo-dj's `tracks`) and isn't in jimbo-dj's mixes until those cut-overs. This is why the analyzer comes third.
- **Gate:** a week with jimbo-dj's switch off and nothing missed.
  - The switch-off check stays clean all week: jimbo-dj's `last_sync`, listens and imports are unchanged.
  - Every track Plex lists is in traqfreq, live.
  - Every Plex play in Plex's history for the week is a listen in traqfreq.
  - Last.fm's own scrobble count for the week equals traqfreq's Last.fm listens.
  - The P1 and P2 numbers move only by what's new.
  - The run log shows a sync and an import every night.
  - `scripts/c1_gate.py --url`, recorded in HANDOFF.
- **Sessions:**
  - **T29:** this spec, `library.sqlite`, the registry, the reading connection, the one-time copy and its count check, rollback and status, all on the fixture.
  - **T30:** the Plex sync and the watcher (vendored; Plex reached through a stand-in in tests), the runs log, and the switch-off check on SETUP (`GET /api/cutovers`).
  - **T31:** the play log (Last.fm API, Plex history, dedupe, rematch) and MusicBrainz. Then the deploy: Ryan runs the copy and switches jimbo-dj off. The gate script.

### 2. History imports: T32–T34
- **traqfreq holds:** nothing new. `listens` and `history_imports` are already traqfreq's after cut-over 1.
- **What traqfreq writes:**
  - Uploads: Spotify's Extended Streaming History, Apple Music's export and Last.fm exports (`import_spotify`, `import_applemusic`, `import_lastfm_files`, vendored unchanged).
  - ListenBrainz: new, its free API, a user token if the listens are private. It gets a place in `PRIORITY` and a window, and is counted once with Last.fm. jimbo-dj never had it.
  - The listening time zone.
  - **Undo per import:** each import's added rows carry its `history_imports` id in a traqfreq column beside jimbo-dj's (`listens_import`). Undo removes exactly those rows, then runs dedupe and rematch again.
- **Switched off in jimbo-dj:** nothing new. Uploads to jimbo-dj stop at cut-over 1 (they'd land in a table traqfreq no longer reads). Any upload between cut-over 1 and T32 waits for traqfreq's upload page, or the switch-off check names it.
- **Rollback:** by import (undo). Rolling back cut-over 1 also hands history back.
- **Gate:** each source imported once on live data, with its counts matching the file or API, and nothing counted twice. Every import is undone and redone once on the fixture. A week with no new rows on jimbo-dj's side.
- **Sessions:**
  - **T32:** uploads and undo per import.
  - **T33:** ListenBrainz.
  - **T34:** the imports page on HISTORY and SETUP, the time zone setting, the gate.

### 3. Analyzer: T35–T36
- **traqfreq holds** (registry name `analysis`):
  - **Tables:** `analysis`, `features`, `embeddings` (about 600 MB, almost all of the file) and `retagged`.
  - **`meta`:** the analyzer's settings and window keys.
- **One-time copy:** `traqfreq-cutover copy analysis`, with the count check. Embeddings are compared by count and by the sum of `length(vec)` per kind, not by `EXCEPT` on the blobs.
- **What traqfreq writes:**
  - The server side of jimbo-dj's analyzer, vendored unchanged: the queue (`_NEEDS_WORK` against traqfreq's `tracks`) and `POST /api/analysis/agent`, `/results`, `/heartbeat`, `/start` and `/stop`.
  - Results are stored with `analysis_store`.
  - The nightly window and the settings.
- **Switched off in jimbo-dj:** the native agent is pointed at traqfreq. Its launchd job gets `--api http://localhost:4492` (the same install script, with the URL). jimbo-dj's Analyzer stays stopped. The analyzer binary and its models stay where they are (Ryan, 2026-11-27).
- **Switching back:** reinstall the agent with jimbo-dj's URL. jimbo-dj re-analyses what it hasn't seen.
- **Rollback:** `rollback analysis`, then switching back.
- **Gate:**
  - A week of nightly runs into traqfreq, and every track new since cut-over 1 analysed.
  - The Analysis numbers (done, errors, version) equal what jimbo-dj showed at the copy plus the new tracks.
  - Radio, the Ask box and flow order unchanged on the P5 trees (the P5 gate still passes against the copy).
- **Sessions:**
  - **T35:** copy, queue, endpoints.
  - **T36:** the agent pointed at traqfreq, progress on SETUP, the gate.

### 4. Playlists: T37–T39
- **traqfreq holds** (registry name `playlists`):
  - **Tables:** `saved_playlists`, `mixes`, `cluster_runs`, `clusters`, `cluster_members` and `bans`.
  - **traqfreq's own table** `playlist_servers (playlist_id, server, on, pushed_at, server_key, error)`, beside them.
- **What traqfreq writes:**
  - **Saving:** from the Junction.
  - **Three switches per playlist and mix** (Ryan, 2026-11-24): Plex, Jellyfin and Navidrome, each on its own.
  - **Pushes:** a playlist goes to each server whose switch is on and comes off a server whose switch goes off.
    - Only playlists traqfreq made (jimbo-dj's emoji rule), never a playlist someone else made.
    - Each push is previewed (tracks found and missing on that server, from P3's matches), logged and undoable: the server's list before the push is kept.
  - **Jobs:** the daily, weekly, dig and this-day mixes, Keep fresh and re-clustering.
  - **NaviBeat first** (T37): read what NaviBeat takes from Navidrome's playlists before the Navidrome push is built.
- **Switched off in jimbo-dj:** Settings → Schedule: `daily_mix`, `weekly_mix`, `dig_mix`, `this_day`, `refresh` and `recluster` off, and "push clusters" off. Don't use Push to Plex in jimbo-dj. Its emoji playlists in Plex are taken over as they are, by `plex_key`, with nothing deleted.
- **Switching back:** those jobs back on. jimbo-dj pushes its stored lists again.
- **Rollback:** `rollback playlists`, and every push undone from the log.
- **Gate:**
  - The P5 gate still passes on traqfreq's copy.
  - A week of mixes and Keep fresh on all three servers per the switches, and nothing pushed that a switch didn't name.
  - Every push in the log with its undo, and one undone and redone on live data.
- **Sessions:**
  - **T37:** NaviBeat, the copy, saving, the switches stored.
  - **T38:** pushing to Plex, Jellyfin and Navidrome, with preview, log and undo.
  - **T39:** the scheduled mixes, Keep fresh, re-clustering, the gate.

### 5. Fix in Plex: T40–T41
- **traqfreq holds** (registry name `tags`): `tag_edits`, `tag_file_edits` and `file_tags`. `retagged` is already traqfreq's, from cut-over 3.
- **What traqfreq writes:**
  - **Album genres:** the audit's fixes to album genre fields in Plex (`tagwrite.plan`, `apply` and `undo`, vendored unchanged).
    - Only an album's genre field, only from the page, previewed first.
    - Each album is checked to still have the tags the preview saw.
    - The field is locked after the change, and the batch is logged with undo.
  - **The files' genre tags:** only with the music mount read-write (`MUSIC_MOUNT_MODE=rw`), the one exception to audio files being read-only, as in jimbo-dj. traqfreq's compose keeps the music mount `:ro` unless Ryan changes it.
  - **The `file_tags` read:** reads the files, writes only the database.
- **Switched off in jimbo-dj:** the `file_tags` job off. Don't use Fix in Plex in jimbo-dj any more.
- **Switching back:** the job back on. Undo any traqfreq batch first if jimbo-dj should own them.
- **Rollback:** every batch undone, then `rollback tags`.
- **Gate:**
  - One live batch previewed, applied and undone, and Plex the same afterwards.
  - The P4 gate still passes.
  - A week of `file_tags` runs, with no rows new on jimbo-dj's side.
- **Sessions:**
  - **T40:** the copy, plan, apply and undo for Plex.
  - **T41:** files too, the file tags job, the gate.

### 6. Jobs and log: T42–T43
- **traqfreq holds:** `jobs` (each job's settings) and `runs` (every run: when, how long, ok or not, its note and counts, and what it changed with its undo), in `library.sqlite`. Started in T30 for the sync.
- **What traqfreq writes:** one scheduler in the one process (one writer), the jobs taken over so far, Run now, each job on or off. A job that was due while traqfreq was down runs once when it's back, as in jimbo-dj.
  - **The log page:** every automatic change with its reason and undo, on SETUP.
  - **What's left from jimbo-dj's list** (`releases`, `journey`, `stats`): each is either taken over here or named for P7.
- **Switched off in jimbo-dj:** `JIMBODJ_SCHEDULER=off`, then a restart. By then every job is off one by one anyway.
- **Switching back:** remove the line.
- **Gate:** a week with jimbo-dj's scheduler off, every job's runs in traqfreq's log, and none missed.
- **Sessions:**
  - **T42:** the scheduler and its tables.
  - **T43:** the log page and the leftover jobs.

### 7. Backups: T44
- **What traqfreq writes:** a nightly SQLite online backup of `library.sqlite` (and `traqfreq.sqlite`) into `TRAQFREQ_DATA_DIR/backups/`. It keeps 7 daily and 4 weekly. A restore check opens each backup and runs `PRAGMA integrity_check` and the count check against the live file. A jimbo-backup job copies that folder to the internal and external backup drives (a hook, as Immich's job has).
- **Switched off in jimbo-dj:** nothing; it never had scheduled backups. jimbo-dj's last database is kept as a final backup when P8 retires it.
- **Gate:** a restore of last night's backup on the laptop, the P1 to P5 gate numbers equal on it, and a week of backups in the log.

## After P6
jimbo-dj writes nothing. Every jimbo-dj table traqfreq reads is either its own copy or a P7 cache. P8's gate (jimbo-dj off for a week) then only stops a container that nobody reads any more. Detaching the legacy file entirely, so traqfreq runs with no `TRAQFREQ_LEGACY_DB`, is P8's last step.
