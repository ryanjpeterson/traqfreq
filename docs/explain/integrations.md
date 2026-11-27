# Integrations

## Summary

One required: jimbo-dj's database, read-only. Jellyfin and Navidrome are optional (P3, read-only: GET requests only, on a refresh from SETUP; Jellyfin's reader since T17, Navidrome's since T18). The Ask box (T28) uses jimbo-dj's CLAP text server and, only when set, a local Ollama; both turn words into numbers or values and read nothing. Nothing leaves the tailnet.

## Services

| Name | Kind | What for | Direction | Required | Auth |
|-|-|-|-|-|-|
| jimbo-dj | jimbo | its SQLite: library, listening history, stored stats (and through it Plex's library) | read | yes | file mount, read-only |
| Plex | self-hosted | the library and Plex plays as jimbo-dj synced them; from T30, traqfreq's own sync and watcher (jimbo-dj's, vendored), GET only, writing only `library.sqlite` and only once the `plex` cut-over is owned (not live until T31's deploy) | read | yes (via jimbo-dj until cut-over 1) | token (`TRAQFREQ_PLEX_TOKEN`, in a header, never shown or logged), `TRAQFREQ_PLEX_URL`, `TRAQFREQ_PLEX_MUSIC_SECTION`, `TRAQFREQ_PLEX_PATH_MAP` |
| Jellyfin | self-hosted | P3: map each song to its Jellyfin item; server name and version, music folders, every audio item, one user's play counts (T17) | read | no | API key (`TRAQFREQ_JELLYFIN_KEY`), optional user (`TRAQFREQ_JELLYFIN_USER`) |
| Navidrome | self-hosted | P3: map each song to its Navidrome song over Subsonic; ping, music folders, scan status, every album and song, the user's play counts (T18) | read | no | user and password (`TRAQFREQ_NAVIDROME_USER`, `TRAQFREQ_NAVIDROME_PASSWORD`), token auth; optional `TRAQFREQ_NAVIDROME_ROOTS`; Report Real Path for file matching |
| jimbodj-text | jimbo | T28's Ask box: jimbo-dj's CLAP text server (native on the mini, :4491) turns words into a vector to compare with the tracks' CLAP vectors; `POST /embed`, which reads and changes nothing | read | no | none (`TRAQFREQ_TEXT_URL`) |
| Ollama | self-hosted | T28's Ask box, optional and off by default: reads words into styles, moods and decades the library has; `POST /api/chat` with a JSON schema | read | no | none (`TRAQFREQ_OLLAMA_URL`, `TRAQFREQ_OLLAMA_MODEL`) |
| Tailscale | self-hosted | the only way in | read | yes | tailnet |

Later phases add Last.fm, MusicBrainz, setlist.fm, the local language server and ntfy (planned in `.env.example`); all free.

## jimbo standards

- jimbo-deploy: `deploy.json` (port 4492, service `web`).
- jimbo-explain 0.1.0: these docs, `jimbo-explain.json`.
- Not jimbo-ui: traqfreq has its own design system, Berlin · Gelb (`docs/specs/brand.md`, `tokens/berlin.json`).

## Secrets and config

In `.env` next to `docker-compose.yml` on the Mac mini, never committed; `.env.example` lists every setting by phase. Secrets: `TRAQFREQ_JELLYFIN_KEY`, `TRAQFREQ_NAVIDROME_PASSWORD`, `TRAQFREQ_PLEX_TOKEN` (never shown on a page or logged). Other settings: `JIMBODJ_DATA_DIR`, `TRAQFREQ_DATA_DIR`, `TRAQFREQ_PORT`, `TRAQFREQ_MODULES`, `TZ`, `TRAQFREQ_PLEX_ROOTS`, `TRAQFREQ_JELLYFIN_URL`, `TRAQFREQ_JELLYFIN_USER`, `TRAQFREQ_NAVIDROME_URL`, `TRAQFREQ_NAVIDROME_USER`, `TRAQFREQ_TEXT_URL`, `TRAQFREQ_OLLAMA_URL`, `TRAQFREQ_OLLAMA_MODEL`, `TRAQFREQ_PLEX_URL`, `TRAQFREQ_PLEX_MUSIC_SECTION`, `TRAQFREQ_PLEX_PATH_MAP`, `TRAQFREQ_WATCH`, `TRAQFREQ_WATCH_INTERVAL`.

## When one is down

- jimbo-dj's database missing: the API answers 503 and pages say so; SETUP still loads.
- jimbo-dj stopped but its database there: traqfreq keeps showing the last synced data.
- Jellyfin or Navidrome not set up or down: their column says so; every page works without them.
- Plex down during traqfreq's sync (after cut-over 1): the run is logged as not done with the reason, and the next sync or watcher look reads Plex again.
- jimbodj-text or Ollama not set up or down: the Ask box says so and its typed parts still work.
