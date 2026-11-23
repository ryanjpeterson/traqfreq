# traqfreq explained

traqfreq is Ryan's self-hosted music app: the redesign of jimbo-dj, in the Berlin · Gelb look. It runs beside jimbo-dj on the Mac mini, reads jimbo-dj's database read-only and takes over one module at a time. Today it shows the listening history and the library number for number as jimbo-dj counts them, and every number can show the rows behind it.

## At a glance

| | |
|-|-|
| What | jimbo-dj's successor, built beside it: listening history, library and servers, every number showing its rows |
| For | self |
| Status | active (P3 of nine phases) |
| Runs at | http://macmini:4492 (tailnet) |
| Built with | Python 3.12 + FastAPI, React 19 + Vite + TypeScript, SQLite, Docker |
| Leans on | jimbo-dj's database (read-only); Jellyfin and Navidrome from P3 |
| Started | 2026-11-22 |
| Docs checked | 2026-11-23 at 341088e |

## The docs

- [Overview](overview.md): what it is, why it exists, what it isn't
- [Audience](audience.md): who it's for and what that rules out
- [Features](features.md): everything it does, and where
- [History](history.md): how it got here
- [Roadmap](roadmap.md): now, next, later, and what's off the table
- [Stack](stack.md): what it's built on and every dependency
- [Integrations](integrations.md): every outside system it talks to
- [Architecture](architecture.md): the parts, the data, the deploy
- [Decisions](decisions.md): the choices that shaped it
- [Health](health.md): risks, debt, chores and open questions
