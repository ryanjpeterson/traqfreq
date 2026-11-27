# traqfreq

The redesign of jimbo-dj, run beside it on the Mac mini (jimbo-dj :4490, traqfreq :4492, over Tailscale). See `CLAUDE.md` for how to run and test, and `HANDOFF.md` for where the build stands.

How and why it works: [docs/explain](docs/explain/README.md)

## Deploy

Code is edited and committed on the laptop in `~/Development/traqfreq` and pushed with jimbo-deploy's `scripts/push.sh`, which pushes every branch to GitHub and Forgejo (`http://macmini:4470/ryanjpeterson/traqfreq`, a normal repo, not a mirror) at the same time. `origin` fetches from GitHub and pushes to both. The server checkout at `/Volumes/jimbos-sloppydrive/traqfreq` pulls from GitHub and runs compose; nothing is committed there. `ssh macmini` from the laptop is not set up, so run this as a Termius snippet on the mini, named `deploy traqfreq`:

```bash
cd /Volumes/jimbos-sloppydrive/traqfreq && git pull --ff-only && docker compose -f docker-compose.yml up -d --build && docker compose -f docker-compose.yml ps
```

Then check `http://macmini:4492/api/health` and open `http://macmini:4492/`.

The compose file mounts jimbo-dj's data folder read-only at `/legacy` (default `../jimbo-dj/data`, next to this checkout). Optional `.env` next to `docker-compose.yml` (copy `.env.example`, which lists every setting by phase, read now or planned): `JIMBODJ_DATA_DIR` (if jimbo-dj keeps its data elsewhere), `TRAQFREQ_MODULES` (modules to switch on besides LIBRARY and SETUP, e.g. `H,T`). From P3 (SERVERS, `docs/specs/t13-servers.md`), all optional: `TRAQFREQ_PLEX_ROOTS` (Plex's music folders, only if jimbo-dj stored none), `TRAQFREQ_JELLYFIN_URL`, `TRAQFREQ_JELLYFIN_KEY`, `TRAQFREQ_JELLYFIN_USER`, `TRAQFREQ_NAVIDROME_URL`, `TRAQFREQ_NAVIDROME_USER`, `TRAQFREQ_NAVIDROME_PASSWORD`. traqfreq only reads those servers (GET), and never shows the key or the password.
