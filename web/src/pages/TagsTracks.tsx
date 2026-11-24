import { useState } from 'react';
import { Band, Button, Card, NavItem, Status, StationRow, Text } from '../components/kit';
import { t, tf, type StringKey } from '../copy/t';
import { useGet } from '../app/api';
import { albumHref, trackHref } from '../app/entities';
import { count as hcount, fmt } from '../app/history';
import { count, tracksHref } from '../app/library';
import {
  TAGS_PATH, TRACKS_CHECK_API, TRACK_SOURCES, albumsHref, params, tagAlbumApi, tagAlbumHref, tagTrackApi, tagTrackHref,
  type SourceBlock, type SourceTag, type TagAlbumPage, type TagTrack, type TagTrackRow, type TrackSource, type TrackTag,
  type TracksCheck,
} from '../app/tags';

/** T21: an album tagged track by track, a track's tags by source, and gate check 2 (every track against jimbo-dj). */

type Nav = { navigate: (href: string) => void };

function Num({ href, label, of, navigate }: { href: string; label: string; of?: string } & Nav) {
  return (
    <Button variant="quiet" href={href} onClick={() => navigate(href)}>
      {label}{of && <span className="visually-hidden">{`, ${of}`}</span>}
    </Button>
  );
}

function Back({ navigate }: Nav) {
  return <div><Button variant="quiet" href={TAGS_PATH} onClick={() => navigate(TAGS_PATH)}>{t('tags.back')}</Button></div>;
}

function Failed({ notFound }: { notFound?: StringKey }) {
  return (
    <Card>
      <div className="stack">
        <Status state="needs" label={t('tags.failed')} />
        <Text>{t(notFound ?? 'tags.failedWhy')}</Text>
      </div>
    </Card>
  );
}

const rungOf = (x: { rung: number | null; broad: string | null; on_ladder: boolean }) =>
  !x.on_ladder ? t('tags.track.notLadder')
    : [x.rung !== null && tf('tags.why.rung', { n: x.rung }), x.broad ?? t('tags.noBroad')].filter(Boolean).join(' · ');

const pct = (v: number) => tf('unit.pct', { n: fmt(Math.round(v * 100)) });
const fromNames = (s: TrackSource[]) => s.map((x) => t(`tags.from.${x}` as StringKey)).join(', ');

/** A tag's name, opening the albums that carry it when it is on the ladder. */
function TagName({ x, navigate }: { x: { key: string; name: string; on_ladder: boolean } } & Nav) {
  if (!x.on_ladder) return <strong>{x.name}</strong>;
  return <span><Num href={albumsHref(x.key)} label={x.name} of={t('tags.track.carries')} navigate={navigate} /></span>;
}

// --- an album, track by track ------------------------------------------------------------------------------

/** Why a track's row reads as it does: what it carries beyond its album, the styles it keeps, jimbo-dj's rule. */
export function trackRowWhy(tr: TagTrackRow): string {
  const styles = tr.styles.length ? tf('tags.album.styles', { s: tr.styles.map((s) => `${s.name} ${fmt(s.score ?? 0)}`).join(', ') })
    : t('tags.album.noStyles');
  const rule = tr.check.tags ? t('tags.track.checkOk') : tf('tags.track.checkDiffers', { s: tr.check.jimbodj_tags.join(', ') || t('tags.tracks.empty') });
  return [tr.differs.length ? tf('tags.album.differs', { s: tr.differs.map((d) => d.name).join(', ') }) : t('tags.album.same'), styles, rule].join(' · ');
}

export function TagAlbum({ entityKey, query, navigate }: { entityKey: number; query: string } & Nav) {
  const load = useGet<TagAlbumPage>(tagAlbumApi(entityKey));
  const differsOnly = params(query).get('show') === 'differs';
  return (
    <>
      <Band module="T">{t('tags.album.sub')}</Band>
      <div className="page stack history">
        <Back navigate={navigate} />
        {load.state === 'loading' && <Text>{t('rows.loading')}</Text>}
        {load.state === 'failed' && <Failed notFound={load.status === 404 ? 'tags.album.notFound' : undefined} />}
        {load.state === 'ok' && <AlbumBody a={load.data} differsOnly={differsOnly} navigate={navigate} />}
      </div>
    </>
  );
}

function AlbumBody({ a, differsOnly, navigate }: { a: TagAlbumPage; differsOnly: boolean } & Nav) {
  const rows = differsOnly ? a.tracks.filter((x) => x.differs.length) : a.tracks;
  return (
    <>
      <section className="hist-head" aria-labelledby="ta-title">
        <Text variant="label">{t('tags.album.sub')}</Text>
        <Text variant="title" id="ta-title">{a.title || t('rows.untitled')}</Text>
        <div className="hist-actions">
          <Text>{[a.artist || t('rows.unknown'), a.year].filter(Boolean).join(' · ')}</Text>
          <Num href={albumHref(a.album_key)} label={t('tags.album.toLibrary')} navigate={navigate} />
        </div>
      </section>
      <div className="hist-grid">
        <Card label={t('tags.album.tags')}>
          <div className="stack">
            {a.tags.length === 0 ? <Text>{t('tags.album.tagsNone')}</Text> : <Text>{a.tags.map((x) => x.name).join(', ')}</Text>}
            <Text variant="note">{t('tags.album.tagsNote')}</Text>
          </div>
        </Card>
        <Card label={t('tags.album.from')}>
          <div className="stack">
            {a.from_tracks.length === 0 ? <Text>{t('tags.album.fromNone')}</Text> : (
              <ul className="rows" aria-label={t('tags.album.from')}>
                {a.from_tracks.map((x) => (
                  <li key={x.key}>
                    <span className="tags-line">
                      <TagName x={x} navigate={navigate} />
                      <span className="sub">{[tf('tags.album.fromLine', { tracks: pct(x.tracks), files: pct(x.files) }), rungOf(x)].join(' · ')}</span>
                      <span className="sub">{[t(x.speaks ? 'tags.album.speaks' : 'tags.album.weak'), t(x.album ? 'tags.album.onAlbum' : 'tags.album.notOnAlbum')].join(' · ')}</span>
                    </span>
                  </li>
                ))}
              </ul>
            )}
            <Text variant="note">{`${t('rows.rule')}: ${a.rules.speaks}.`}</Text>
          </div>
        </Card>
      </div>
      <section aria-labelledby="ta-tracks" className="stack">
        <Text variant="heading" id="ta-tracks">{t('tags.album.tracks')}</Text>
        <nav className="hist-choices" aria-label={t('tags.album.which')}>
          <NavItem label={tf('tags.album.all', { n: count(a.tracks.length, 'track') })} href={tagAlbumHref(a.album_key)} current={!differsOnly} onNavigate={navigate} />
          <NavItem label={tf('tags.album.differ', { n: count(a.differ, 'track') })} href={tagAlbumHref(a.album_key, true)} current={differsOnly} onNavigate={navigate} />
        </nav>
        {rows.length === 0 ? <Text>{t(a.tracks.length ? 'tags.album.noDiffer' : 'tags.album.noTracks')}</Text> : (
          <ol className="hist-rows">
            {rows.map((tr, i) => (
              <StationRow key={tr.rating_key} position={tr.track_no ?? i + 1} module="T" title={tr.title || t('rows.untitled')}
                artist={tr.tags.map((x) => x.name).join(', ') || t('tags.album.noTags')}
                why={trackRowWhy(tr)} defaultOpen={tr.differs.length > 0}
                href={tagTrackHref(tr.rating_key)} onNavigate={navigate} />
            ))}
          </ol>
        )}
        <Text variant="note">{`${t('rows.rule')}: ${a.rules.tags}. ${a.rules.differs}.`}</Text>
        <Text variant="note">{tf('tags.album.check', { m: fmt(a.check.tags), n: count(a.check.tracks, 'track'), s: fmt(a.check.styles) })}</Text>
      </section>
    </>
  );
}

// --- a track, by source ----------------------------------------------------------------------------------

export function TagTrack({ entityKey, navigate }: { entityKey: number } & Nav) {
  const load = useGet<TagTrack>(tagTrackApi(entityKey));
  return (
    <>
      <Band module="T">{t('tags.track.sub')}</Band>
      <div className="page stack history">
        <Back navigate={navigate} />
        {load.state === 'loading' && <Text>{t('rows.loading')}</Text>}
        {load.state === 'failed' && <Failed notFound={load.status === 404 ? 'tags.track.notFound' : undefined} />}
        {load.state === 'ok' && <TrackBody d={load.data} navigate={navigate} />}
      </div>
    </>
  );
}

function sourceLine(x: SourceTag, src: TrackSource): string {
  if (x.junk) return tf('tags.track.junk', { r: x.junk });
  const parts = [rungOf(x)];
  if (x.score !== undefined) parts.push(src === 'sound' ? tf('tags.track.score', { n: fmt(x.score) }) : hcount(x.score, 'vote'));
  if (src === 'sound') parts.push(t(x.kept ? 'tags.track.kept' : 'tags.track.dropped'));
  if (x.raw !== x.name && src !== 'sound') parts.push(`“${x.raw}”`);
  return parts.join(' · ');
}

function emptyLine(src: TrackSource, b: SourceBlock): string {
  if (src === 'file') return b.note ? t('tags.track.noFileTable') : b.error ? tf('tags.track.noFile', { e: b.error }) : b.read ? t('tags.track.none') : t('tags.track.notRead');
  if ((src === 'mb-release' || src === 'mb-artist') && !b.found) return t('tags.track.noMb');
  if (src === 'sound' && !b.analysed) return t('tags.track.notAnalysed');
  return t('tags.track.none');
}

function Source({ src, b, rule, navigate }: { src: TrackSource; b: SourceBlock; rule?: string } & Nav) {
  const label = t(`tags.source.${src}` as StringKey);
  return (
    <Card label={label}>
      <div className="stack">
        {b.tags.length === 0 ? <Text>{emptyLine(src, b)}</Text> : (
          <ul className="rows" aria-label={label}>
            {b.tags.map((x, i) => (
              <li key={`${x.raw}-${x.key}-${i}`}>
                <span className="tags-line">
                  {x.junk ? <strong>{x.raw}</strong> : <TagName x={x} navigate={navigate} />}
                  <span className="sub">{sourceLine(x, src)}</span>
                </span>
              </li>
            ))}
          </ul>
        )}
        {rule && <Text variant="note">{`${t('rows.rule')}: ${rule}.`}</Text>}
      </div>
    </Card>
  );
}

function TagLine({ x, navigate }: { x: TrackTag } & Nav) {
  return (
    <li>
      <span className="tags-line">
        <TagName x={x} navigate={navigate} />
        <span className="sub">{[rungOf(x), x.sources.length ? tf('tags.track.from', { s: fromNames(x.sources) }) : ''].filter(Boolean).join(' · ')}</span>
      </span>
      {!x.album && <Status state="needs" label={t('tags.track.notOnAlbum')} />}
    </li>
  );
}

function TrackBody({ d, navigate }: { d: TagTrack } & Nav) {
  return (
    <>
      <section className="hist-head" aria-labelledby="tt-title">
        <Text variant="label">{t('tags.track.sub')}</Text>
        <Text variant="title" id="tt-title">{d.title || t('rows.untitled')}</Text>
        <div className="hist-actions">
          <Text>{[d.artist || t('rows.unknown'), d.album || t('rows.untitled')].join(' · ')}</Text>
          <Num href={trackHref(d.rating_key)} label={t('tags.track.toLibrary')} navigate={navigate} />
          {d.album_key != null && <Num href={tagAlbumHref(d.album_key)} label={t('tags.track.toAlbum')} navigate={navigate} />}
        </div>
      </section>
      <Card label={t('tags.track.tags')}>
        <div className="stack">
          {d.tags.length === 0 ? <Text>{t('tags.track.tagsNone')}</Text> : (
            <ul className="rows" aria-label={t('tags.track.tags')}>
              {d.tags.map((x) => <TagLine key={x.key} x={x} navigate={navigate} />)}
            </ul>
          )}
          <Status state={d.check.tags ? 'ready' : 'needs'}
            label={d.check.tags ? t('tags.track.checkOk') : tf('tags.track.checkDiffers', { s: d.check.jimbodj_tags.join(', ') || t('tags.tracks.empty') })} />
          <Status state={d.check.styles ? 'ready' : 'needs'}
            label={d.check.styles ? t('tags.track.stylesOk') : tf('tags.track.stylesDiffer', { s: d.check.jimbodj_styles.join(', ') || t('tags.tracks.empty') })} />
          <Text variant="note">{`${t('rows.rule')}: ${d.rules.tags}.`}</Text>
        </div>
      </Card>
      <section aria-labelledby="tt-sources" className="stack">
        <Text variant="heading" id="tt-sources">{t('tags.track.bySource')}</Text>
        <div className="hist-grid">
          {TRACK_SOURCES.map((s) => <Source key={s} src={s} b={d.sources[s]} rule={d.rules[s]} navigate={navigate} />)}
        </div>
      </section>
    </>
  );
}

// --- gate check 2 on TAGS ------------------------------------------------------------------------------------

/** Every live track's tags and styles next to jimbo-dj's per-track rule and strict test (gate check 2). */
export function TracksCheckCard({ navigate }: Nav) {
  const load = useGet<TracksCheck>(TRACKS_CHECK_API);
  const [open, setOpen] = useState(false);
  if (load.state === 'loading') return <Card label={t('tags.tracks.label')}><Text>{t('tags.tracks.loading')}</Text></Card>;
  if (load.state === 'failed') return <Card label={t('tags.tracks.label')}><Status state="needs" label={t('tags.failed')} /></Card>;
  const c = load.data;
  const items = [...c.tags.items, ...c.styles.items.filter((s) => !c.tags.items.some((x) => x.rating_key === s.rating_key))];
  const differ = c.tags.differ + c.styles.differ;
  const all = tracksHref('');
  return (
    <Card label={t('tags.tracks.label')}>
      <div className="stack">
        <Status state={c.passed ? 'ready' : 'needs'} label={t(c.passed ? 'compare.passed' : 'compare.notPassed')} />
        <ul className="rows" aria-label={t('tags.tracks.label')}>
          <li>
            <span>
              <Num href={all} label={tf('tags.tracks.tags', { m: fmt(c.tags.ok), n: count(c.tags.tracks, 'track') })} navigate={navigate} />
              <span className="sub">{c.tags.source}</span>
            </span>
            <Status state={c.tags.matches ? 'ready' : 'needs'} label={t(c.tags.matches ? 'compare.match' : 'compare.differs')} />
          </li>
          <li>
            <span>
              <Num href={all} label={tf('tags.tracks.styles', { m: fmt(c.styles.ok), n: count(c.styles.tracks, 'track') })} navigate={navigate} />
              <span className="sub">{`${c.styles.source} · ${tf('tags.tracks.analysed', { n: fmt(c.styles.analysed), k: fmt(c.styles.kept) })}`}</span>
            </span>
            <Status state={c.styles.matches ? 'ready' : 'needs'} label={t(c.styles.matches ? 'compare.match' : 'compare.differs')} />
          </li>
        </ul>
        <Text variant="note">{`${t('rows.rule')}: ${c.rule}.`}</Text>
        {differ > 0 && (
          <>
            <div>
              <Button variant="quiet" onClick={() => setOpen(!open)}>{tf(open ? 'tags.tracks.hide' : 'tags.tracks.show', { n: items.length })}</Button>
            </div>
            {open && (
              <ol className="hist-rows" aria-label={t('tags.tracks.differList')}>
                {items.map((x, i) => (
                  <StationRow key={x.rating_key} position={i + 1} module="T" title={x.title || t('rows.untitled')} artist={x.artist || t('rows.unknown')}
                    why={tf('tags.tracks.both', { a: x.traqfreq.join(', ') || t('tags.tracks.empty'), b: x.jimbodj.join(', ') || t('tags.tracks.empty') })}
                    href={tagTrackHref(x.rating_key)} onNavigate={navigate} />
                ))}
              </ol>
            )}
          </>
        )}
      </div>
    </Card>
  );
}
