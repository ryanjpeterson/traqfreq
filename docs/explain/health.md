# Health

## Snapshot

Healthy and moving fast: P0–P3 done and gated on live data in three days. Used daily by one listener beside jimbo-dj. Upkeep is low (no jobs, cache only). Matching works on invented snapshots (T14), SETUP shows it (T15), the GET-only client and refresh are in place (T16), Jellyfin is read live (T17: 53,133 of 53,133 Plex copies matched by file, also from the deployed container) and so is Navidrome (T18: 52,712 of 53,133 by MusicBrainz ID and tags, since its paths are hidden); the P3 gate (T19) passed on live data on 2026-11-24 once Navidrome reported real paths: every pair one to one over 53,274 copies, 0 unmatched. P4 TAGS (T20–T23) is built. Checks 1 and 2 of its gate pass on live data. Check 3 does not pass, because jimbo-dj's stored `library.tags` is built from a background Library older than its stamp. That is jimbo-dj's side, and the check stays strict. P4's gate then passed (2026-11-24), and P5 PLAYLISTS (T24–T28) passed its gate on live data on 2026-11-26: 10 of 10 trees and 77 of 77 saved playlists the same as jimbo-dj. The most useful next thing is P6, the first cut-over.

## Risks

- **jimbo-dj changes how it counts or its schema** (medium): traqfreq's vendored copies drift. Softened by the gates and `tests/test_vendor.py`; re-vendor when it happens.
- **SMB working copy** (resolved 2026-11-27): sessions now work in a laptop clone; the server checkout only pulls.
- **One machine** (low): everything is on the Mac mini; traqfreq holds nothing precious yet (caches only).

## Tech debt

- Vendored code with stand-ins (`src/traqfreq/vendor/`): it must be re-copied by hand when jimbo-dj changes.
- `app.py` holds every route in one factory (about 700 lines); worth splitting per module before P6.
- Search is a placeholder page.

## Known issues

- Starlette's deprecation warning on the test client's httpx.
- On live data, jimbo-dj's `_pct` rounds 20 rated tracks to 0.0 %; shown as jimbo-dj shows it.

## Maintenance chores

- After each merge: run the `deploy traqfreq` snippet on the Mac mini.
- After each phase: run its gate script against the live app and record it in HANDOFF.
- After each session: update HANDOFF, CHANGELOG and the progress deck "traqfreq: build phases", then copy the deck into `docs/deck` and rebuild its page (`node scripts/build-deck.mjs`).

## Open questions

- P4 check 3: when will jimbo-dj's stored `library.tags` catch up with its own data? Live on 2026-11-24, 5 to 14 tags differed in MusicBrainz, track or sound counts, every time the row's stamp was fresh.

- Navidrome: will Report Real Path be turned on for the `traqfreq` player? Without it no Navidrome song matches by file (52,985 hidden paths on 2026-11-23). Its last scan also reports 'stat /music: bad file descriptor'.
- Audience and status are inferred (self, active); confirm if anything differs.
