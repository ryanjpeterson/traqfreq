import type { ReactNode } from 'react';
import { Band, Button, Card, NavItem, Status, StationRow, Text } from '../components/kit';
import { t, tf, type StringKey } from '../copy/t';
import { useGet } from '../app/api';
import { MODULE_PATH } from '../app/route';
import { dayLabel, duration, fmt, localTime, sourceName } from '../app/history';
import { count, fmt1, tracksHref } from '../app/library';
import {
  LIST_SORTS, albumHref, artistHref, kindLabel, listHref, parseListQuery, playsHref, trackHref,
  type Album, type Artist, type EntityList, type ListKind, type PageTrack, type Plays, type Summary, type Track,
} from '../app/entities';
import { TracksLink } from './Library';

type Nav = { navigate: (href: string) => void };

const day = (iso: string | null | undefined) => (iso ? dayLabel(iso.slice(0, 10)) : '');
const rule = (text: string | undefined) => `${t('library.rule')}: ${text ?? ''}`;
const len = (ms: number | null | undefined) => (ms != null ? duration(Math.round(ms / 1000)) : t('entity.none'));

/** A link that looks like quiet text: a name that opens its page. */
function PageLink({ href, children, navigate }: { href: string; children: ReactNode } & Nav) {
  return <Button variant="quiet" href={href} onClick={() => navigate(href)}>{children}</Button>;
}

/** A number of listens that opens them (W3): /library/plays?… */
function PlaysLink({ n, query, extra, navigate }: { n: number; query: string; extra?: Record<string, string | number | undefined> } & Nav) {
  if (n === 0) return <span className="hist-num">{count(n, 'play')}</span>;
  const href = playsHref(query, extra);
  return (
    <Button variant="quiet" href={href} onClick={() => navigate(href)}>
      {count(n, 'play')}
      <span className="visually-hidden">{`, ${t('entity.plays.show')}`}</span>
    </Button>
  );
}

/** One fact: a label, an optional line under it, and its value (or a link). */
function Fact({ label, sub, children, mono = false }: { label: string; sub?: string; children: ReactNode; mono?: boolean }) {
  return (
    <li>
      <span><strong>{label}</strong>{sub && <span className="sub">{sub}</span>}</span>
      <span className={mono ? 'mono lib-fact' : 'hist-num'}>{children}</span>
    </li>
  );
}

function Loading({ load, notFound, children }: {
  load: { state: 'loading' } | { state: 'ok' } | { state: 'failed'; status?: number }; notFound: StringKey; children: () => ReactNode;
}) {
  if (load.state === 'loading') return <Text>{t('library.loading')}</Text>;
  if (load.state === 'failed') {
    return (
      <Card>
        <div className="stack">
          <Status state="needs" label={t(load.status === 404 ? 'entity.notFound' : 'library.failed')} />
          <Text>{t(load.status === 404 ? notFound : 'entity.failed')}</Text>
        </div>
      </Card>
    );
  }
  return <>{children()}</>;
}

function Back({ navigate }: Nav) {
  return <div><Button variant="quiet" href={MODULE_PATH.L} onClick={() => navigate(MODULE_PATH.L)}>{t('library.rows.back')}</Button></div>;
}

/** Shares as bars (aria-hidden) in a list, with a one-line summary (L6). */
function ShareList({ label, items, summary, navigate }: {
  label: string; summary: string; items: { key: string; name: string; n: number; query?: string; extra?: Record<string, string | number> }[];
} & Nav) {
  const most = Math.max(1, ...items.map((i) => i.n));
  return (
    <div className="stack">
      <Text>{summary}</Text>
      <ul className="rows hist-top" aria-label={label}>
        {items.map((i) => (
          <li key={i.key}>
            <span className="hist-top-text">
              <strong>{i.name}</strong>
              <span className="hist-bar lib-bar" aria-hidden="true"><span style={{ width: `${(100 * i.n) / most}%` }} /></span>
            </span>
            {i.query != null ? <PlaysLink n={i.n} query={i.query} extra={i.extra} navigate={navigate} /> : <span className="hist-num">{count(i.n, 'play')}</span>}
          </li>
        ))}
      </ul>
    </div>
  );
}

/** jimbo-dj's summarise for some tracks: plays by source and year, first and last, the newest listens. */
function Listens({ h, query, label, rules, navigate }: { h: Summary; query: string; label: string; rules: Record<string, string> } & Nav) {
  if (!h.plays) {
    return (
      <Card label={label}>
        <div className="stack">
          <Text>{t('entity.hist.none')}</Text>
          <Text variant="note">{rule(rules.history ?? rules.song_history)}</Text>
        </div>
      </Card>
    );
  }
  const sources = h.sources ?? [];
  const years = h.years ?? [];
  const topSource = [...sources].sort((a, b) => b.plays - a.plays)[0];
  const topYear = [...years].sort((a, b) => b.plays - a.plays)[0];
  return (
    <Card label={label}>
      <div className="stack">
        <ul className="rows" aria-label={label}>
          <Fact label={t('entity.hist.plays')} sub={h.first && h.last ? tf('entity.hist.span', { first: day(h.first), last: day(h.last) }) : undefined}>
            <PlaysLink n={h.plays} query={query} navigate={navigate} />
          </Fact>
        </ul>
        <Text variant="label">{t('entity.hist.sources')}</Text>
        <ShareList
          label={t('entity.hist.sources')}
          summary={topSource ? tf('entity.hist.sourcesSummary', { n: count(sources.length, 'source'), top: sourceName(topSource.source), m: count(topSource.plays, 'play') }) : ''}
          items={sources.map((s) => ({ key: s.source, name: sourceName(s.source), n: s.plays, query, extra: { source: s.source } }))}
          navigate={navigate}
        />
        <Text variant="label">{t('entity.hist.years')}</Text>
        <ShareList
          label={t('entity.hist.years')}
          summary={topYear ? tf('entity.hist.yearsSummary', { n: count(years.length, 'year'), top: String(topYear.year), m: count(topYear.plays, 'play') }) : ''}
          items={years.map((y) => ({ key: String(y.year), name: String(y.year), n: y.plays }))}
          navigate={navigate}
        />
        {h.recent && h.recent.length > 0 && (
          <>
            <Text variant="label">{t('entity.hist.recent')}</Text>
            <ul className="rows" aria-label={t('entity.hist.recent')}>
              {h.recent.slice(0, 5).map((r, i) => (
                <li key={`${r.at}-${r.source}-${i}`}><span className="mono">{r.local}</span><span className="hist-num">{sourceName(r.source)}</span></li>
              ))}
            </ul>
          </>
        )}
        <Text variant="note">{`${rule(rules.history ?? rules.song_history)}. ${tf('entity.hist.zone', { tz: h.timezone ?? '' })}`}</Text>
      </div>
    </Card>
  );
}

/** Why a page's track is there (B3): its plays (plays_of), its copies, key and moods. */
export function pageTrackWhy(tr: PageTrack, top = false): string {
  const parts = [top && tr.versions && tr.versions > 1
    ? tf('entity.why.copies', { n: count(tr.plays, 'play'), v: fmt(tr.versions), a: count(tr.albums ?? 1, 'album') })
    : tf('entity.why.plays', { n: count(tr.plays, 'play'), plex: fmt(tr.view_count ?? 0) })];
  if (!top && tr.versions && tr.versions > 1) parts.push(tf('entity.why.versions', { n: fmt(tr.versions) }));
  parts.push(len(tr.duration_ms));
  if (tr.key) parts.push(tf('entity.why.key', { k: `${tr.key} ${tr.scale ?? ''}`.trim() }));
  if (tr.moods.length) parts.push(tf('entity.why.moods', { m: tr.moods.join(', ') }));
  return parts.join(' · ');
}

// --- Lists ---------------------------------------------------------------------------------------------

/** jimbo-dj's Library → Albums or Artists: tracks, plays, added and year, in four orders. */
export function LibraryList({ kind, query, navigate }: { kind: ListKind; query: string } & Nav) {
  const { sort, offset } = parseListQuery(query);
  const api = `/api/library/${kind}?sort=${sort}${offset ? `&offset=${offset}` : ''}`;
  const load = useGet<EntityList>(api);
  return (
    <>
      <Band module="L">{t(`entity.${kind}.sub` as StringKey)}</Band>
      <div className="page stack">
        <Back navigate={navigate} />
        <Text variant="heading">{t(`library.${kind}` as StringKey)}</Text>
        <nav className="hist-choices" aria-label={t('entity.list.sort')}>
          {LIST_SORTS.map((s) => (
            <NavItem key={s} label={t(`entity.list.sort.${s}` as StringKey)} href={listHref(kind, s)} current={sort === s} onNavigate={navigate} />
          ))}
        </nav>
        <Loading load={load} notFound="empty.L">{() => load.state === 'ok' && <ListBody l={load.data} navigate={navigate} />}</Loading>
      </div>
    </>
  );
}

function ListBody({ l, navigate }: { l: EntityList } & Nav) {
  const a = l.total ? l.offset + 1 : 0;
  const b = l.offset + l.items.length;
  const prev = l.offset > 0 ? listHref(l.kind, l.sort, Math.max(0, l.offset - l.limit)) : null;
  const next = b < l.total ? listHref(l.kind, l.sort, l.offset + l.limit) : null;
  const unit = l.kind === 'albums' ? 'album' : 'artist';
  return (
    <>
      <Text>{tf('library.rows.total', { n: count(l.total, unit), a: fmt(a), b: fmt(b), order: t(`entity.list.order.${l.sort}` as StringKey) })}</Text>
      {l.items.length === 0 ? <Text>{t('entity.list.none')}</Text> : (
        <ol className="rows lib-list" aria-label={t(`library.${l.kind}` as StringKey)}>
          {l.items.map((i, n) => {
            const href = l.kind === 'albums' ? albumHref(i.key) : artistHref(i.key);
            const sub = [l.kind === 'albums' && i.artist, i.year ? String(i.year) : t('entity.noYear'), i.added && tf('entity.list.added', { d: day(i.added) })]
              .filter(Boolean).join(' · ');
            return (
              <li key={i.key}>
                <span className="hist-top-name">
                  <span className="hist-rank">{l.offset + n + 1}</span>
                  <span className="lib-name">
                    <PageLink href={href} navigate={navigate}>{i.name || t('rows.untitled')}</PageLink>
                    <span className="sub">{sub}</span>
                  </span>
                </span>
                <span className="lib-nums">
                  <TracksLink text={count(i.tracks, 'track')} n={i.tracks} query={i.rows} navigate={navigate} />
                  <TracksLink text={count(i.plays, 'play')} n={i.plays} query={`${i.rows}&sort=plex_plays`} navigate={navigate} />
                </span>
              </li>
            );
          })}
        </ol>
      )}
      {(prev || next) && (
        <div className="hist-actions">
          <Button disabled={!prev} href={prev ?? undefined} onClick={prev ? () => navigate(prev) : undefined}>{t('library.rows.prev')}</Button>
          <Button disabled={!next} href={next ?? undefined} onClick={next ? () => navigate(next) : undefined}>{t('library.rows.next')}</Button>
        </div>
      )}
      <ul className="rows" aria-label={t('entity.rules')}>
        {(['total', 'tracks', 'plays', 'added', 'year', `sort.${l.sort}`] as const).map((k) => (
          <li key={k}><span><strong>{t(`entity.rule.${k.startsWith('sort.') ? 'order' : k}` as StringKey)}</strong><span className="sub">{l.rules[k]}</span></span></li>
        ))}
      </ul>
    </>
  );
}

// --- Album ---------------------------------------------------------------------------------------------

export function LibraryAlbum({ entityKey, navigate }: { entityKey: number } & Nav) {
  const load = useGet<Album>('/api/library/album/' + entityKey);
  return (
    <>
      <Band module="L">{t('entity.album.sub')}</Band>
      <div className="page stack history">
        <Back navigate={navigate} />
        <Loading load={load} notFound="entity.album.notFound">{() => load.state === 'ok' && <AlbumBody a={load.data} navigate={navigate} />}</Loading>
      </div>
    </>
  );
}

function AlbumBody({ a, navigate }: { a: Album } & Nav) {
  const info = a.album;
  const mb = info.musicbrainz;
  const discs = new Set(a.tracks.map((x) => x.disc ?? 1)).size;
  return (
    <>
      <section className="hist-head" aria-labelledby="e-title">
        <Text variant="label">{t('entity.album.sub')}</Text>
        <Text variant="title" id="e-title">{info.title || t('rows.untitled')}</Text>
        {info.artist_key != null && (
          <div><PageLink href={artistHref(info.artist_key)} navigate={navigate}>{info.artist || t('rows.unknown')}</PageLink></div>
        )}
      </section>
      <div className="hist-grid">
        <Card label={t('entity.album.facts')}>
          <div className="stack">
            <ul className="rows" aria-label={t('entity.album.facts')}>
              <Fact label={t('entity.tracks')} sub={rule(a.rules.tracks)}>
                <TracksLink text={count(a.tracks.length, 'track')} n={a.tracks.length} query={a.rows.tracks} navigate={navigate} />
              </Fact>
              <Fact label={t('entity.plays')} sub={rule(a.rules.plays)}>
                <TracksLink text={count(a.plays, 'play')} n={a.plays} query={`${a.rows.tracks}&sort=plex_plays`} navigate={navigate} />
              </Fact>
              <Fact label={t('entity.album.year')} sub={rule(a.rules.year)}>{info.year ?? t('entity.none')}</Fact>
              <Fact label={t('entity.album.length')} sub={rule(a.rules.minutes)}>{tf('unit.min', { n: fmt(a.minutes) })}</Fact>
              {info.plex_year != null && <Fact label={t('entity.album.plexYear')}>{info.plex_year}</Fact>}
              {info.released && <Fact label={t('entity.album.released')}>{day(info.released)}</Fact>}
              {info.label && <Fact label={t('entity.album.label')}>{info.label}</Fact>}
            </ul>
          </div>
        </Card>
        <Card label={t('entity.mb')}>
          <div className="stack">
            {mb ? (
              <ul className="rows" aria-label={t('entity.mb')}>
                {mb.first_release && <Fact label={t('entity.mb.first')}>{day(mb.first_release)}</Fact>}
                {mb.date && <Fact label={t('entity.mb.date')}>{day(mb.date)}</Fact>}
                {mb.type && <Fact label={t('entity.mb.type')}>{[mb.type, ...mb.secondary].join(', ')}</Fact>}
                {mb.country && <Fact label={t('entity.mb.country')}>{mb.country}</Fact>}
                {mb.labels.length > 0 && <Fact label={t('entity.mb.labels')}>{mb.labels.join(', ')}</Fact>}
              </ul>
            ) : <Text>{t('entity.mb.none')}</Text>}
            <Text variant="note">{t('entity.mb.note')}</Text>
          </div>
        </Card>
      </div>
      <section aria-labelledby="e-tracks">
        <Text variant="label" id="e-tracks">{t('entity.tracks')}</Text>
        <ol className="hist-rows">
          {a.tracks.map((tr, i) => (
            <StationRow
              key={tr.rating_key}
              position={tr.track_no ?? i + 1}
              module="L"
              title={tr.title || t('rows.untitled')}
              artist={[discs > 1 && tf('entity.disc', { n: tr.disc ?? 1 }), tr.track_artist && tr.track_artist !== tr.artist ? tr.track_artist : null]
                .filter(Boolean).join(' · ') || (tr.artist ?? t('rows.unknown'))}
              musicalKey={tr.camelot ?? undefined}
              bpm={tr.bpm != null ? Math.round(tr.bpm) : undefined}
              why={pageTrackWhy(tr)}
              href={trackHref(tr.rating_key)}
              onNavigate={navigate}
            />
          ))}
        </ol>
        <Text variant="note">{`${rule(a.rules.tracks)}. ${t('library.rows.plays')}: ${a.rules.plays}. ${tf('entity.versionsRule', { r: a.rules.versions })}`}</Text>
      </section>
      <Listens h={a.history} query={a.rows.plays} label={t('entity.hist')} rules={a.rules} navigate={navigate} />
      <Text variant="note">{t('entity.notHere')}</Text>
    </>
  );
}

// --- Artist --------------------------------------------------------------------------------------------

export function LibraryArtist({ entityKey, navigate }: { entityKey: number } & Nav) {
  const load = useGet<Artist>('/api/library/artist/' + entityKey);
  return (
    <>
      <Band module="L">{t('entity.artist.sub')}</Band>
      <div className="page stack history">
        <Back navigate={navigate} />
        <Loading load={load} notFound="entity.artist.notFound">{() => load.state === 'ok' && <ArtistBody a={load.data} navigate={navigate} />}</Loading>
      </div>
    </>
  );
}

function ArtistBody({ a, navigate }: { a: Artist } & Nav) {
  const own = a.albums.filter((x) => !x.appears_on).length;
  return (
    <>
      <section className="hist-head" aria-labelledby="e-title">
        <Text variant="label">{t('entity.artist.sub')}</Text>
        <Text variant="title" id="e-title">{a.artist.name || t('rows.unknown')}</Text>
        <ul className="rows" aria-label={t('entity.artist.facts')}>
          <Fact label={t('entity.tracks')} sub={rule(a.rules.tracks)}>
            <TracksLink text={count(a.tracks, 'track')} n={a.tracks} query={a.rows.tracks} navigate={navigate} />
          </Fact>
          <Fact label={t('entity.plays')} sub={rule(a.rules.plays)}>
            <TracksLink text={count(a.plays, 'play')} n={a.plays} query={`${a.rows.tracks}&sort=plex_plays`} navigate={navigate} />
          </Fact>
        </ul>
      </section>
      <section aria-labelledby="e-albums">
        <Text variant="label" id="e-albums">{t('library.albums')}</Text>
        <Text>{tf('entity.artist.albumsSummary', { n: count(own, 'album'), on: fmt(a.albums.length - own) })}</Text>
        <ol className="rows lib-list" aria-label={t('library.albums')}>
          {a.albums.map((x) => (
            <li key={x.album_key}>
              <span className="lib-name">
                <PageLink href={albumHref(x.album_key)} navigate={navigate}>{x.title || t('rows.untitled')}</PageLink>
                <span className="sub">{[x.year ?? t('entity.noYear'), x.appears_on && tf('entity.artist.appearsOn', { artist: x.artist ?? '' })].filter(Boolean).join(' · ')}</span>
              </span>
              <span className="lib-nums">
                <TracksLink text={count(x.tracks, 'track')} n={x.tracks} query={x.rows} navigate={navigate} />
                <span className="hist-num">{count(x.plays, 'play')}</span>
              </span>
            </li>
          ))}
        </ol>
        <Text variant="note">{rule(a.rules.albums)}</Text>
      </section>
      <section aria-labelledby="e-top">
        <Text variant="label" id="e-top">{t('entity.artist.top')}</Text>
        {a.top_tracks.length === 0 ? <Text>{t('entity.artist.topNone')}</Text> : (
          <ol className="hist-rows">
            {a.top_tracks.map((tr, i) => (
              <StationRow
                key={tr.rating_key}
                position={i + 1}
                module="L"
                title={tr.title || t('rows.untitled')}
                artist={tr.album ?? ''}
                musicalKey={tr.camelot ?? undefined}
                bpm={tr.bpm != null ? Math.round(tr.bpm) : undefined}
                why={pageTrackWhy(tr, true)}
                href={trackHref(tr.rating_key)}
                onNavigate={navigate}
              />
            ))}
          </ol>
        )}
        <Text variant="note">{rule(a.rules.top)}</Text>
      </section>
      <Listens h={a.history} query={a.rows.plays} label={t('entity.hist')} rules={a.rules} navigate={navigate} />
      <Text variant="note">{t('entity.artist.notHere')}</Text>
    </>
  );
}

// --- Track ---------------------------------------------------------------------------------------------

export function LibraryTrack({ entityKey, navigate }: { entityKey: number } & Nav) {
  const load = useGet<Track>('/api/library/track/' + entityKey);
  return (
    <>
      <Band module="L">{t('entity.track.sub')}</Band>
      <div className="page stack history">
        <Back navigate={navigate} />
        <Loading load={load} notFound="entity.track.notFound">{() => load.state === 'ok' && <TrackBody d={load.data} navigate={navigate} />}</Loading>
      </div>
    </>
  );
}

const num = (v: unknown) => (typeof v === 'number' ? v : null);
const str = (v: unknown) => (typeof v === 'string' ? v : null);

function TrackBody({ d, navigate }: { d: Track } & Nav) {
  const tr = d.track;
  const f = d.features;
  const an = d.analysis;
  const kind = kindLabel(d.kind);
  const p = d.plays;
  const size = num(tr.file_size);
  const bitrate = num(tr.bitrate);
  const depth = num(tr.bit_depth);
  const rate = num(tr.sample_rate);
  const parts = num(tr.parts);
  const analysisLine = !an ? t('entity.analysis.none')
    : an.current ? tf('entity.analysis.current', { v: an.version })
      : an.status === 'error' ? tf('entity.analysis.error', { v: an.version, e: an.error ?? '' })
        : tf('entity.analysis.older', { s: an.status, v: an.version, cur: d.analyzer_version });
  return (
    <>
      <section className="hist-head" aria-labelledby="e-title">
        <Text variant="label">{d.song.copies > 1 && kind ? `${t('entity.track.sub')} · ${kind}` : t('entity.track.sub')}</Text>
        <Text variant="title" id="e-title">{tr.title || t('rows.untitled')}</Text>
        <div className="hist-actions">
          {tr.artist_key != null && <PageLink href={artistHref(tr.artist_key)} navigate={navigate}>{tr.track_artist || tr.artist || t('rows.unknown')}</PageLink>}
          {tr.album_key != null && d.live && <PageLink href={albumHref(tr.album_key)} navigate={navigate}>{tr.album || t('rows.untitled')}</PageLink>}
        </div>
        {!d.live && <Status state="off" label={tf('entity.track.removed', { d: day(tr.removed_at) })} />}
      </section>
      <div className="hist-grid">
        <Card label={t('entity.plays')}>
          <div className="stack">
            <p className="hist-big">{count(p.plays, 'play')}</p>
            <Text variant="note">{rule(d.rules.plays)}</Text>
            <ul className="rows" aria-label={t('entity.plays')}>
              <Fact label={t('entity.track.plex')} sub={t('entity.track.plexWhat')}>{count(p.plex, 'play')}</Fact>
              <Fact label={t('entity.track.history')} sub={rule(d.rules.history)}>
                <PlaysLink n={p.history} query={d.rows.plays} navigate={navigate} />
              </Fact>
              <Fact label={t('entity.track.last')}>{p.last_played ? day(p.last_played) : t('entity.never')}</Fact>
            </ul>
          </div>
        </Card>
        <Listens h={d.history} query={d.rows.plays} label={d.song.copies > 1 ? t('entity.hist.copy') : t('entity.hist')} rules={d.rules} navigate={navigate} />
        {d.song.copies > 1 && (
          <Card label={t('entity.song')}>
            <div className="stack">
              <Text>{tf('entity.song.what', { title: d.song.title, artist: d.song.artist, n: fmt(d.song.copies) })}</Text>
              <ul className="rows" aria-label={t('entity.song')}>
                {d.song.versions.map((v) => (
                  <li key={v.rating_key}>
                    <span className="lib-name">
                      <PageLink href={trackHref(v.rating_key)} navigate={navigate}>{v.title || t('rows.untitled')}</PageLink>
                      <span className="sub">{[v.album, v.year, kindLabel(v.kind)].filter(Boolean).join(' · ')}</span>
                    </span>
                    <span className="hist-num">{count(v.plays, 'play')}</span>
                  </li>
                ))}
                {d.song.history && (
                  <Fact label={t('entity.song.plays')} sub={rule(d.rules.song_history)}>
                    <PlaysLink n={d.song.history.plays} query={d.rows.song ?? d.rows.plays} navigate={navigate} />
                  </Fact>
                )}
              </ul>
              <Text variant="note">{rule(d.rules.versions)}</Text>
            </div>
          </Card>
        )}
        <Card label={t('entity.file')}>
          <ul className="rows lib-paths" aria-label={t('entity.file')}>
            <Fact label={t('entity.file.codec')}>{[str(tr.codec) ?? t('library.none'), str(tr.container) && tr.container !== tr.codec ? tf('library.why.in', { c: String(tr.container) }) : ''].filter(Boolean).join(' ')}</Fact>
            <Fact label={t('entity.file.bitrate')}>{bitrate != null ? tf('unit.kbps', { n: fmt(bitrate) }) : t('library.why.noBitrate')}</Fact>
            {depth != null && <Fact label={t('entity.file.depth')}>{tf('unit.bit', { n: depth })}</Fact>}
            {rate != null && <Fact label={t('entity.file.rate')}>{tf('unit.khz', { n: fmt1(rate / 1000) })}</Fact>}
            {num(tr.channels) != null && <Fact label={t('entity.file.channels')}>{fmt(num(tr.channels)!)}</Fact>}
            <Fact label={t('entity.file.size')}>{size != null ? tf('unit.mb', { n: fmt1(size / 1e6) }) : t('entity.none')}</Fact>
            <Fact label={t('entity.file.length')}>{len(num(tr.duration_ms))}</Fact>
            <Fact label={t('entity.file.parts')}>{fmt(parts ?? 1)}</Fact>
            <Fact label={t('entity.file.plexPath')} mono>{str(tr.plex_path) ?? t('entity.none')}</Fact>
            <Fact label={t('entity.file.localPath')} mono>{str(tr.local_path) ?? t('entity.file.unmapped')}</Fact>
            <Fact label={t('entity.file.sonic')}>{tr.sonic_version != null ? t('entity.yes') : t('entity.no')}</Fact>
            {num(tr.user_rating) != null && <Fact label={t('entity.file.rating')}>{fmt(num(tr.user_rating)!)}</Fact>}
            {str(tr.added_at) && <Fact label={t('entity.file.added')}>{day(str(tr.added_at))}</Fact>}
            {str(tr.updated_at) && <Fact label={t('entity.file.updated')}>{day(str(tr.updated_at))}</Fact>}
          </ul>
        </Card>
        <Card label={t('entity.analysis')}>
          <div className="stack">
            <Text>{analysisLine}</Text>
            {(f || an?.analyzed_at) && (
              <ul className="rows" aria-label={t('entity.analysis')}>
                {an?.analyzed_at && <Fact label={t('entity.analysis.at')}>{day(an.analyzed_at)}</Fact>}
                {f?.key && <Fact label={t('entity.feat.key')}>{`${f.key} ${f.scale ?? ''}`.trim()}</Fact>}
                {f?.camelot && <Fact label={t('entity.feat.camelot')}>{String(f.camelot)}</Fact>}
                {num(f?.bpm) != null && <Fact label={t('entity.feat.bpm')}>{fmt1(num(f?.bpm)!)}</Fact>}
                {num(f?.loudness_lufs) != null && <Fact label={t('entity.feat.loudness')}>{tf('unit.lufs', { n: fmt1(num(f?.loudness_lufs)!) })}</Fact>}
                {num(f?.danceability) != null && <Fact label={t('entity.feat.dance')}>{fmt1(num(f?.danceability)!)}</Fact>}
                {f && f.moods.length > 0 && <Fact label={t('entity.feat.moods')}>{f.moods.join(', ')}</Fact>}
              </ul>
            )}
            {f && an && !an.current && <Text variant="note">{tf('entity.feat.older', { v: an.version })}</Text>}
            <Text variant="note">{rule(d.rules.analysis)}</Text>
          </div>
        </Card>
      </div>
      <Text variant="note">{t('entity.track.notHere')}</Text>
    </>
  );
}

// --- The listens behind a page's history numbers ------------------------------------------------------------

export function LibraryPlays({ query, navigate }: { query: string } & Nav) {
  const q = new URLSearchParams(query);
  const pick = (k: string) => (q.get(k) && /^\d+$/.test(q.get(k)!) ? Number(q.get(k)) : undefined);
  const track = pick('track');
  const album = pick('album');
  const artist = pick('artist');
  const source = q.get('source') ?? undefined;
  const song = q.get('song') === 'true';
  const offset = pick('offset') ?? 0;
  const base = new URLSearchParams();
  if (track != null) base.set('track', String(track));
  else if (album != null) base.set('album', String(album));
  else if (artist != null) base.set('artist', String(artist));
  if (song) base.set('song', 'true');
  const baseQ = base.toString();
  const api = `/api/library/plays?${playsHref(baseQ, { source, offset }).replace(/^[^?]*\?/, '')}`;
  const load = useGet<Plays>(api);
  const back = track != null ? trackHref(track) : album != null ? albumHref(album) : artist != null ? artistHref(artist) : MODULE_PATH.L;
  const what = track != null ? (song ? 'song' : 'track') : album != null ? 'album' : 'artist';
  return (
    <>
      <Band module="L">{t('entity.plays.sub')}</Band>
      <div className="page stack">
        <div><Button variant="quiet" href={back} onClick={() => navigate(back)}>{t(`entity.plays.back.${what === 'song' ? 'track' : what}` as StringKey)}</Button></div>
        <Text variant="heading">{[
          what === 'artist' ? tf('entity.plays.title.artist', { name: load.state === 'ok' ? load.data.name ?? '' : '' }) : t(`entity.plays.title.${what}` as StringKey),
          source && sourceName(source),
        ].filter(Boolean).join(' · ')}</Text>
        <Loading load={load} notFound="entity.plays.notFound">{() => load.state === 'ok' && (
          <PlaysBody l={load.data} baseQ={baseQ} source={source} navigate={navigate} />
        )}</Loading>
      </div>
    </>
  );
}

function PlaysBody({ l, baseQ, source, navigate }: { l: Plays; baseQ: string; source?: string } & Nav) {
  const a = l.total ? l.offset + 1 : 0;
  const b = l.offset + l.rows.length;
  const newer = l.offset > 0 ? playsHref(baseQ, { source, offset: Math.max(0, l.offset - l.limit) }) : null;
  const older = b < l.total ? playsHref(baseQ, { source, offset: l.offset + l.limit }) : null;
  return (
    <>
      {l.sources.length > 1 && (
        <nav className="hist-choices" aria-label={t('entity.plays.sources')}>
          <NavItem label={t('entity.plays.all')} href={playsHref(baseQ)} current={!source} onNavigate={navigate} />
          {l.sources.map((s) => (
            <NavItem key={s} label={sourceName(s)} href={playsHref(baseQ, { source: s })} current={source === s} onNavigate={navigate} />
          ))}
        </nav>
      )}
      <Text>{tf('rows.total', { n: count(l.total, 'play'), a: fmt(a), b: fmt(b) })}</Text>
      <Text variant="note">{`${t('rows.rule')}: ${l.rule}. ${tf('entity.hist.zone', { tz: l.timezone })}`}</Text>
      {l.rows.length === 0 ? <Text>{t('rows.none')}</Text> : (
        <ol className="hist-rows">
          {l.rows.map((r, i) => (
            <StationRow
              key={`${r.started_at}-${r.source}-${i}`}
              position={l.offset + i + 1}
              module="L"
              title={r.title || t('rows.untitled')}
              artist={[r.artist || t('rows.unknown'), r.album].filter(Boolean).join(' · ')}
              why={[
                r.started_at ? localTime(r.started_at, l.timezone) : '',
                sourceName(r.source),
                r.rating_key != null ? tf('rows.why.track', { rk: r.rating_key }) : t('rows.why.noTrack'),
              ].filter(Boolean).join(' · ')}
              href={r.rating_key != null ? trackHref(r.rating_key) : undefined}
              onNavigate={navigate}
            />
          ))}
        </ol>
      )}
      {(newer || older) && (
        <div className="hist-actions">
          <Button disabled={!newer} href={newer ?? undefined} onClick={newer ? () => navigate(newer) : undefined}>{t('rows.later')}</Button>
          <Button disabled={!older} href={older ?? undefined} onClick={older ? () => navigate(older) : undefined}>{t('rows.earlier')}</Button>
        </div>
      )}
    </>
  );
}
