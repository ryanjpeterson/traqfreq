# Health

## Snapshot

Healthy and moving fast: P0–P2 done and gated on live data in two days, P3 under way. Used daily by one listener beside jimbo-dj. Upkeep is low (no jobs, cache only). Matching works on invented snapshots (T14), SETUP shows it (T15), the GET-only client and refresh are in place (T16), Jellyfin is read live (T17: 53,133 of 53,133 Plex copies matched by file, also from the deployed container) and so is Navidrome (T18: 52,712 of 53,133 by MusicBrainz ID and tags, since its paths are hidden); the P3 gate is built (T19) and ran live on 2026-11-24: not passed, only because Navidrome hides its paths (reasons add up, Plex ↔ Jellyfin one to one, no duration off). The most useful next thing is Report Real Path on for traqfreq's Navidrome player, then the gate again.

## Risks

- **jimbo-dj changes how it counts or its schema** (medium): traqfreq's vendored copies drift. Softened by the gates and `tests/test_vendor.py`; re-vendor when it happens.
- **SMB working copy** (low): renames sometimes fail on the server checkout; sessions retry and keep node_modules off the drive.
- **One machine** (low): everything is on the Mac mini; traqfreq holds nothing precious yet (caches only).

## Tech debt

- Vendored code with stand-ins (`src/traqfreq/vendor/`): it must be re-copied by hand when jimbo-dj changes.
- `app.py` holds every route in one factory (about 360 lines); worth splitting per module before P6.
- Search is a placeholder page.

## Known issues

- Starlette's deprecation warning on the test client's httpx.
- On live data, jimbo-dj's `_pct` rounds 20 rated tracks to 0.0 %; shown as jimbo-dj shows it.

## Maintenance chores

- After each merge: run the `deploy traqfreq` snippet on the Mac mini.
- After each phase: run its gate script against the live app and record it in HANDOFF.
- After each session: update HANDOFF, CHANGELOG and the progress deck "traqfreq: build phases", then copy the deck into `docs/deck` and rebuild its page (`node scripts/build-deck.mjs`).

## Open questions

- Navidrome: will Report Real Path be turned on for the `traqfreq` player? Without it no Navidrome song matches by file (52,985 hidden paths on 2026-11-23). Its last scan also reports 'stat /music: bad file descriptor'.
- Audience and status are inferred (self, active); confirm if anything differs.
