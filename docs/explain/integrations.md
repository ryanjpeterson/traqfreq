# Integrations

## Summary

One required: jimbo-dj's database, read-only. Jellyfin and Navidrome are optional (P3, read-only, not read yet). Nothing leaves the tailnet.

## Services

| Name | Kind | What for | Direction | Required | Auth |
|-|-|-|-|-|-|
| jimbo-dj | jimbo | its SQLite: library, listening history, stored stats (and through it Plex's library) | read | yes | file mount, read-only |
| Plex | self-hosted | the library and Plex plays, only as jimbo-dj synced them; never called directly until P6 | read | yes (via jimbo-dj) | none in traqfreq |
| Jellyfin | self-hosted | P3: map each song to its Jellyfin item (T17) | read | no | API key (`TRAQFREQ_JELLYFIN_KEY`) |
| Navidrome | self-hosted | P3: map each song to its Navidrome song over Subsonic (T18) | read | no | user and password (`TRAQFREQ_NAVIDROME_USER`, `TRAQFREQ_NAVIDROME_PASSWORD`), token auth |
| Tailscale | self-hosted | the only way in | read | yes | tailnet |

Later phases add Plex directly, Last.fm, MusicBrainz, setlist.fm, the local language server and ntfy (planned in `.env.example`); all free.

## jimbo standards

- jimbo-deploy: `deploy.json` (port 4492, service `web`).
- jimbo-explain 0.1.0: these docs, `jimbo-explain.json`.
- Not jimbo-ui: traqfreq has its own design system, Berlin · Gelb (`docs/specs/brand.md`, `tokens/berlin.json`).

## Secrets and config

In `.env` next to `docker-compose.yml` on the Mac mini, never committed; `.env.example` lists every setting by phase. Secrets: `TRAQFREQ_JELLYFIN_KEY`, `TRAQFREQ_NAVIDROME_PASSWORD` (never shown on a page or logged). Other settings: `JIMBODJ_DATA_DIR`, `TRAQFREQ_DATA_DIR`, `TRAQFREQ_PORT`, `TRAQFREQ_MODULES`, `TZ`, `TRAQFREQ_PLEX_ROOTS`, `TRAQFREQ_JELLYFIN_URL`, `TRAQFREQ_JELLYFIN_USER`, `TRAQFREQ_NAVIDROME_URL`, `TRAQFREQ_NAVIDROME_USER`.

## When one is down

- jimbo-dj's database missing: the API answers 503 and pages say so; SETUP still loads.
- jimbo-dj stopped but its database there: traqfreq keeps showing the last synced data.
- Jellyfin or Navidrome not set up or down: their column says so; every page works without them.
