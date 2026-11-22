# traqfreq

The redesign of jimbo-dj, run beside it on the Mac mini (jimbo-dj :4490, traqfreq :4492, over Tailscale). See `CLAUDE.md` for how to run and test, and `HANDOFF.md` for where the build stands.

## Deploy

Code is pushed to GitHub; Forgejo (`http://macmini:4470/ryanjpeterson/traqfreq`) is a pull mirror of it. The server checkout at `/Volumes/jimbos-sloppydrive/traqfreq` pulls from GitHub and runs compose. `ssh macmini` from the laptop is not set up, so run this as a Termius snippet on the mini, named `deploy traqfreq`:

```bash
cd /Volumes/jimbos-sloppydrive/traqfreq && git pull --ff-only && docker compose -f docker-compose.yml up -d --build && docker compose -f docker-compose.yml ps
```

Then check `http://macmini:4492/api/health` and open `http://macmini:4492/`.

The compose file mounts jimbo-dj's data folder read-only at `/legacy` (default `../jimbo-dj/data`, next to this checkout). Optional `.env` next to `docker-compose.yml`: `JIMBODJ_DATA_DIR` (if jimbo-dj keeps its data elsewhere), `TRAQFREQ_MODULES` (modules to switch on besides LIBRARY and SETUP, e.g. `H,T`).
