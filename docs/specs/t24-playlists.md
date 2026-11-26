# T24–T28: PLAYLISTS, the Junction preview (P5)

**Gate: same tracks as jimbo-dj.** On the live data, with `scripts/p5_gate.py --url http://macmini:4492` (T28; exit 0 = passed, recorded in HANDOFF as P1–P4 were), for ten playlist trees:
1. **Lines.** For every line (jimbo-dj calls them branches), the tracks it matches (`count`), its share, how many it got and how many it could choose from (`available`), and the union's `total` equal jimbo-dj's.
2. **Tracks.** The same tracks in the same order, each brought in by the same line.
3. **Saved playlists.** traqfreq's list of jimbo-dj's saved playlists equals jimbo-dj's own: the same rows, kinds, titles, track counts, Plex switches and stale flags.

The ten trees: every saved playlist that has one (as `make.spec_of` reads it: a `rules` spec, an old Explore `filter`, a genre `blend`; 8 on 2026-11-24), then fixed trees from `src/traqfreq/p5_trees.json` until there are ten. The fixed ones are chosen so that between them the ten use AND, OR and NOT, a nested group, an `in:` scope, and at least one condition of each family (a chart bar, a sound filter, `genre`, `style`, `family`, `listened`).

jimbo-dj's side of checks 1 and 2 is `POST /api/rules/preview` with the same tree. That endpoint writes nothing. Read at 1d8a7cb, it builds the playlist and keeps the last 64 answers in process memory for a minute. It is the only non-GET call anything in traqfreq makes, and only the gate script makes it. Both sides are asked within seconds of each other. If jimbo-dj's data stamp moves in between, that tree is asked again once. Check 3 is `GET /api/saved`.

PLAYLISTS only reads. Saving, pushing to Plex, Keep fresh, the daily and weekly mixes and re-clustering all stay in jimbo-dj until P6. traqfreq never writes to jimbo-dj's database, to Plex, to Jellyfin or to Navidrome.

## Where it lives
The Junction is part of LIBRARY (L1), as jimbo-dj's branch builder is part of Library → Tracks. The pages are `/library/playlists` (the saved playlists), `/library/playlists/<id>` (one playlist and its lines) and, from T25, `/library/junction?b=…` (any tree, in jimbo-dj's URL form). No new module switch.

## What jimbo-dj stores and how it builds (read at jimbo-dj 1d8a7cb, `git show` only)
Source: `store.py`, `rules.py`, `make.py`, `facets.py`, `browse.py`, `flow.py`, `bans.py`, `mixes.py`, `clusters.py`, `playlists.py`, `refresh.py`, `routes/playlists.py`, `routes/library.py`. The word "Junction" isn't in jimbo-dj: it is traqfreq's name for the branch builder.

- **Saved playlists** (`saved_playlists`, store.py): every playlist jimbo-dj makes, in Plex or not. `kind` is one of mix, cluster, like, explore, blend, setlist, plex or history. `title` is the full Plex title with its emoji (🪩 cluster, 🎧 mix and blend, 🔁 more like this, 🧭 explore, 🎤 setlist). `keys` is the tracks in play order (JSON rating keys). `source` (JSON) is what made it: `make` (a make.py spec), `from` (the page), `parts` (a blend), `mix`, `cluster_id`, `seed`. Then `in_plex` (the one switch jimbo-dj has, Plex only), `plex_key`, `pushed_at`, `plex_error`, `stale` and `stale_in_plex`. Its slug comes from the title without the emoji (`store.slugs`). Live on 2026-11-24: 77 rows (54 clusters, 6 mixes, 6 explore, 4 like, 3 blends, 2 setlists, 2 history).
- **A tree** (`rules.py`): `{n, per_artist, shuffle, branches: [{id, label?, share, match}]}`. `match` is a group: tracks in every `all`, in any `any`, in no `not`, nesting at most 3 deep, 8 branches and 12 conditions a branch. A condition `{f, v}` is a chart bar (`facets.KEYS`: file, time, place, label, family, style, artist, listened), a sound filter (`bpm`, `key`, `mood`, `genre`) or a scope (`in`: `cluster:`, `saved:`, `mix:`, `artist:`, `album:`). `clean` checks it and turns the shares into whole track counts adding up to `n` (`quotas`, largest remainder). `describe`, `name` and `summary` put it in words. `to_query`/`from_query` give its URL form (`b=style:progressive metal,(style:black metal|label:Profound Lore),!style:depressive black metal~20`).
- **Matching:** `leaf_keys` gives one condition's tracks, counted the way the chart that shows it counts (`facets.members`, `browse._where`, `genres.Styles.genre_members`, `facets.scope`). They are cached per data stamp, except `in` and `listened`. `evaluate` combines them, and `branch_sets` keeps only live tracks.
- **Picking** (`rules.build`): each line's tracks are ranked by plays (`rank`, every source's plays, as Library sorts), up to `max(6n, 400)`. `make.details` drops what's in Never in mixes (`bans`: songs, artists, styles). Shuffle reorders each pool with a jitter seeded by the tree. Then the lines take turns toward their shares (`pick`): a track two lines share goes to the first that takes it, a song (artist and title) goes in once, at most `per_artist` each. A line that runs short leaves the rest to the lines furthest under their share. The picked tracks are ordered for flow (`flow.order`: Camelot keys, tempo, loudness and energy) and each gets a `transition` in words.
- **Where trees come from** (`make.spec_of`): a `rules` spec, or an old Explore `filter` (one line), or a blend's `parts` (`rules.from_blend`: one line per style). Mixes (`mixes.py`: favourites, overlooked, new, rediscover, unplayed, seeded by the day or week), clusters (`clusters.py`: UMAP and HDBSCAN on the embeddings), Radio (`similar.more_like`), setlists and history playlists are made another way, and P5 doesn't rebuild them.
- **Keep fresh** (`refresh.py`) rebuilds a playlist daily or weekly and leaves out tracks played in the last week when a line can spare them. That changes jimbo-dj's stored tracks, not the preview.
- **Writing** (`playlists.py`, `store.sync`): only to Plex, only playlists whose title starts with one of the emoji. jimbo-dj has no Jellyfin or Navidrome playlists.

## Three switches per playlist and mix (Ryan, 2026-11-24)
Every playlist and mix gets three separate switches: Plex, Jellyfin and Navidrome. Each one decides whether that playlist is on that server, and none implies another.
- **P5 shows them, read-only.** Plex is jimbo-dj's `in_plex`, with `pushed_at` and `plex_error`. Jellyfin and Navidrome are shown as off, "Set in P6", because jimbo-dj has nowhere to keep them (T24). From T25 each switch also says where the playlist would go: how many of its tracks have a copy on that server (P3's matches, so a missing copy is named, not dropped).
- **P6 makes them push.** traqfreq keeps the three switches in its own database, pushes each playlist and mix to the servers that are on and takes it off a server whose switch goes off. Each push is previewed, logged and undoable (B2). The Plex switch moves over from jimbo-dj at that cut-over, and jimbo-dj stops pushing.
- **NaviBeat** is connected to Navidrome. Before the Navidrome push is built (P6), look at what NaviBeat reads from Navidrome's playlists, so a playlist traqfreq writes there doesn't surprise it.

## Reuse
Vendored unchanged at 1d8a7cb, as earlier phases did (`VENDORED_FROM`; stand-ins marked):
- `vendor/jimbodj_rules.py` (T24): rules.py's Shape, Words, URL form and Matching sections (T25 adds Picking). One import line differs, as in `vendor/tagwrite.py`: `from . import facets, flow` reads `jimbodj_facets` here.
- `vendor/browse.py` (T24): browse.py's `SOUND` and `_where`, used by `leaf_keys` for the sound filters.
- Stand-ins named like jimbo-dj's modules (as `vendor/genres.py` and `vendor/tags.py` are): `vendor/cache.py` (`data_stamp`), `vendor/analyzer_version.py`, `vendor/history.py` (`listened_keys` and `_range`, copied unchanged, over T8's `listen_tz`), and `scope` for `in:` (facets.py's, with the saved-playlist and cluster lookups read-only).
- Already here: `vendor/jimbodj_facets.py` (`members`), `vendor/genres.py` (`Styles`, `family`), `vendor/jimbodj_insights.py`. `insights.track_family` is added unchanged for the `family` condition.
- Later sessions: `flow.py` (T27, pure), `similar._public` and `_norm_title`, `make.details`, `bans.get` (T25).

## Sessions
### T24: lines
- `GET /api/playlists`: every saved playlist, read-only. Each row has its kind, title, slug, track count, where it came from, whether it has a tree, stale, and its three switches (Plex from `in_plex`, Jellyfin and Navidrome off until P6).
- `GET /api/playlists/{id}`: the playlist, its stored tracks (rows, W3) and, when it has a tree, its lines. Each line has its words (`describe`), its share and its conditions as a tree of AND, OR and NOT. Each condition and each line has the number of live tracks it matches, as jimbo-dj counts them. The union has its total.
- `GET /api/playlists/lines?b=…` (any tree in the URL form) and `GET /api/playlists/{id}/lines/{line}/tracks`: the rows behind every count.
- Pages: `/library/playlists` (grouped by kind, each with its switches) and `/library/playlists/<id>` (its lines as ConditionChips, AND, OR and NOT, each number opening its rows). A card on LIBRARY links to them. Kit only.
- Tests: the fixture gains invented saved playlists (one per kind, one stale, three with trees using AND, OR, NOT and a nested group), clusters, bans and a mix. Each count is recomputed the plain way in the test.

### T25: the Junction and its levers
`rules.build`'s picking (shares, the cap per artist, line priority = order, shuffle, Never in mixes), vendored. Each switch gains how many of the playlist's tracks have a copy on its server. The Junction drawing (lines meeting in one, L6 list view and summary) with read-only LineLevers for share and cap. `/library/junction?b=…` previews any tree. Gate check 1 and the set of tracks of check 2, on the fixture.
*Done 2026-11-25* (HANDOFF). Read at 1d8a7cb: `make.details` drops a banned track only when jimbo-dj's vectors index knows it (analysed at the current version), so a banned track the analyzer hasn't read can still be picked. traqfreq does the same, and the test says so.

### T26: movements, rooted to roaming
A line can follow a T23 movement or a ladder, with a read-only slider from rooted (the tag alone) to roaming (its movement and neighbours on the map). It is new in traqfreq, a preview only, and not part of the gate.
*Done 2026-11-25* (HANDOFF). How it reads (`src/traqfreq/reach.py`):
- A line follows the tag of each `style` condition it needs, in its `all` or `any` parts. A style under a `not` isn't followed, because widening it would shrink the line. Nor is a `genre` condition: those are Discogs genres, not on the ladder. The tag is the value through jimbo-dj's tag rules. It is followed only when it is on the ladder or in a movement.
- Four stops, each taking in the one before:
  - **rooted**: the tag alone, the line as it is, so its count is the Junction's;
  - **ladder**: every tag under it on its ladder;
  - **movement**: every tag of each movement naming one of those;
  - **roaming**: their neighbours on the genre map, one rung up or down, broad tags left out.
- At each stop, the followed condition matches any of the stop's tags, each counted as jimbo-dj counts a `style` condition (`rules.leaf_keys`). The rest of the line stays as it is.
- `GET /api/junction/reach?b=…` and `GET /api/junction/reach/rows?b=…&line=&stop=&which=count|added`. On the Junction (a saved playlist's page and `/library/junction`), each following line has a read-only slider with the line at rooted, a summary for screen readers and the list view. Each stop has its count, what it adds over rooted and the tags it takes in.

### T27: flow order and why this track
`flow.order` and `flow.describe` (vendored), the track details they read (the analyzer's features, as jimbo-dj's index has them), so the order matches (check 2 in full). Every row shows which line brought it in and why (B3): the conditions it meets, each ConditionChip true or false, and its transition from the track before.

### T28: the Ask box and the gate
The Ask box: words to a line, through jimbo-dj's CLAP text server (`jimbodj-text`, :4491, read-only), and Ollama lines when it's on (jimbo-dj's prompt.py). Then the gate: `src/traqfreq/playlists_gate.py`, `GET /api/playlists/compare` (traqfreq's own answers, for the card), `scripts/p5_gate.py --url` (the only caller of jimbo-dj's preview), `p5_trees.json`, the gate card on LIBRARY and SETUP, and a live run recorded in HANDOFF.

## Not in P5
- Any write: to jimbo-dj (no save, rename, delete, refresh or Keep fresh), to Plex, to Jellyfin, to Navidrome. The switches are shown, never set.
- Building mixes, clusters, Radio, setlists or history playlists. They are shown as jimbo-dj stored them.
- Covers (jimbo-dj makes and uploads them).
- Never in mixes: shown (T25), not edited.
