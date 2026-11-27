# Stack

## Summary

Python 3.12 + FastAPI API, React 19 + Vite + TypeScript web served by FastAPI, SQLite (jimbo-dj's read-only, traqfreq's own for caches), Docker on the Mac mini.

## Runtime and hosting

Docker compose on the Mac mini (service `web`, port 4492), deployed with jimbo-deploy (`deploy.json`). One container: the web build is baked into the image and served by uvicorn (`uv run traqfreq`). jimbo-dj's data folder is mounted read-only at `/legacy`; traqfreq's data at `/data`.

## Languages and frameworks

- Python 3.12 (CI and image; the laptop runs tests on 3.14): FastAPI for the API.
- TypeScript 5.9, React 19, Vite 8: the web app (`web/`).
- Node 22: the build, the token generator and brand checks.

## Data and storage

- jimbo-dj's SQLite (`jimbodj.sqlite`, about 600 MB, mostly embeddings): read-only.
- `data/traqfreq.sqlite`: traqfreq's own `stats` table of built summaries (rebuildable at any time), server `snapshots` and the `refreshes` log.
- `tokens/berlin.json`: the design tokens, generated into `web/src/styles/tokens.css`.

## Dependencies

### Python (`pyproject.toml`)

| Package | Version | Why it's here |
|-|-|-|
| fastapi | >=0.115 | the API and static file serving |
| uvicorn | >=0.30 | the server |
| httpx | >=0.27 | the GET-only server client (T16) and FastAPI's test client; the Ask box's calls to jimbodj-text and Ollama (T28) |
| numpy | >=1.26 | the Ask box (T28): a CLAP text vector against every track's CLAP vector, as jimbo-dj's prompt Radio does |
| pytest (dev) | >=8 | tests |

### Web (`web/package.json`)

| Package | Version | Why it's here |
|-|-|-|
| react, react-dom | 19.3.1 | the UI |
| @fontsource/fira-sans | 5.3.0 | Fira Sans, self-hosted |
| vite, @vitejs/plugin-react | 8.3.8, 6.3.0 | build and dev server |
| typescript, @types/react, @types/react-dom | 5.9.3, 19.3.0 | types |
| vitest, jsdom | 5.1.1, 31.0.1 | component and page tests |
| @testing-library/react, dom, user-event | 16.3.3, 10.4.2, 14.6.13 | tests |

### Vendored

`src/traqfreq/vendor/`: jimbo-dj's pure functions copied unchanged from jimbo-dj 1d8a7cb (`history.py`, `songs.py`, `library.py`, parts of `pages.py`, `insights.py`, `facets.py`), each with `VENDORED_FROM` and marked stand-ins. They must be re-copied when jimbo-dj's counting changes.

## Tooling

- `uv sync && uv run pytest` (API), `cd web && npm test` (Vitest), `node scripts/check.mjs` and `node --test scripts/check.test.mjs` (brand checks).
- `cd web && npm ci && npm run build` (runs `scripts/build-tokens.mjs` first).
- `scripts/make_fixture.py`: the invented test database. `scripts/p1_gate.py`, `scripts/p2_gate.py`: the gates.
- CI: GitHub Actions, pytest on 3.12 and the web job (checks, tests, build).

## Upgrade watch

- Vendored jimbo-dj code is pinned to 1d8a7cb: if jimbo-dj changes how it counts, the gates show it and the copies need re-vendoring.
- Starlette warns that its test client's httpx use is deprecated (`httpx2`); harmless for now.
