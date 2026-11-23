# Health

## Snapshot

Healthy and moving fast: P0–P2 done and gated on live data in two days, P3 under way. Used daily by one listener beside jimbo-dj. Upkeep is low (no jobs, cache only). The most useful next thing is P3's matching (T14), then the Jellyfin and Navidrome details from Ryan.

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
- After each session: update HANDOFF, CHANGELOG and the progress deck "traqfreq: build phases".

## Open questions

- Jellyfin and Navidrome: do they run on the Mac mini, at which URLs, with which keys and user (needed before T17 and T18)?
- Audience and status are inferred (self, active); confirm if anything differs.
