import { Band, Button, Card, NavItem, Status, StationRow, Text } from '../components/kit';
import { t, tf, type StringKey } from '../copy/t';
import { useGet } from '../app/api';
import { MODULE_PATH } from '../app/route';
import { albumHref, artistHref, trackHref } from '../app/entities';
import { dayLabel, duration, fmt, sourceName } from '../app/history';
import {
  SORTS, count, fmt1, parseTrackFilter, trackQuery, tracksHref, valueLabel,
  type TrackFilter, type TrackRow, type Tracks,
} from '../app/library';

type Props = { query: string; navigate: (href: string) => void };

const yesNo = (v: boolean | undefined, yes: StringKey, no: StringKey) => (v === true ? t(yes) : v === false ? t(no) : false);

/** The heading for a filter: "Tracks · codec flac · played". */
export function filterTitle(f: TrackFilter): string {
  return [
    t(f.removed ? 'library.rows.removed' : 'library.rows.tracks'),
    f.codec != null && tf('library.rows.codec', { v: valueLabel(f.codec) }),
    f.container != null && tf('library.rows.container', { v: valueLabel(f.container) }),
    f.bitrate && tf('library.rows.bitrate', { v: f.bitrate }),
    yesNo(f.played, 'library.rows.played', 'library.rows.unplayed'),
    yesNo(f.heard, 'library.rows.heard', 'library.rows.unheard'),
    f.source && tf('library.rows.source', { s: sourceName(f.source) }),
    yesNo(f.rated, 'library.rows.rated', 'library.rows.unrated'),
    yesNo(f.sonic, 'library.rows.sonic', 'library.rows.noSonic'),
    f.analysis && t(`library.rows.analysis.${f.analysis}` as StringKey),
    yesNo(f.mapped, 'library.rows.mapped', 'library.rows.unmapped'),
    yesNo(f.multi_part, 'library.rows.multiPart', 'library.rows.onePart'),
    f.artist_key != null && (f.name ?? tf('library.rows.artistKey', { k: f.artist_key })),
    f.album_key != null && tf('library.rows.albumKey', { k: f.album_key }),
    f.facet && f.value != null && tf('library.rows.facet', { facet: t(`library.facet.${f.facet}` as StringKey), v: valueLabel(f.value) }),
  ].filter(Boolean).join(' · ');
}

const day = (iso: string) => dayLabel(iso.slice(0, 10));

/** Why a track is in these rows, in one line (B3): its file facts, its analysis and its plays (plays_of). */
export function trackWhy(r: TrackRow): string {
  const file = [r.codec ?? t('library.none'), r.container && r.container !== r.codec ? tf('library.why.in', { c: r.container }) : '']
    .filter(Boolean).join(' ');
  const parts = [file];
  parts.push(r.bitrate != null ? tf('unit.kbps', { n: fmt(r.bitrate) }) : t('library.why.noBitrate'));
  if (r.file_size != null) parts.push(tf('unit.mb', { n: fmt1(r.file_size / 1e6) }));
  if (r.duration_ms != null) parts.push(duration(Math.round(r.duration_ms / 1000)));
  if (r.parts != null && r.parts > 1) parts.push(tf('library.why.parts', { n: r.parts }));
  parts.push(r.local_path ? tf('library.why.mapped', { p: r.local_path }) : tf('library.why.unmapped', { p: r.plex_path ?? '' }));
  parts.push(r.sonic_version != null ? t('library.why.sonic') : t('library.why.noSonic'));
  parts.push(r.analysis_status == null ? t('library.why.notAnalysed')
    : tf(`library.why.analysis.${r.analysis_status === 'ok' ? 'ok' : r.analysis_status === 'error' ? 'error' : 'other'}` as StringKey,
      { v: r.analysis_version ?? '' }));
  parts.push(tf('library.why.plays', { n: count(r.plays, 'play'), plex: fmt(r.view_count ?? 0), history: fmt(r.history_plays) }));
  if (r.last_played) parts.push(tf('library.why.last', { d: day(r.last_played) }));
  if (r.user_rating != null) parts.push(tf('library.why.rating', { n: r.user_rating }));
  if (r.added_at) parts.push(tf('library.why.added', { d: day(r.added_at) }));
  if (r.removed_at) parts.push(tf('library.why.removedAt', { d: day(r.removed_at) }));
  return parts.join(' · ');
}

/** The tracks behind a LIBRARY number, 50 a page, with the rule that selected them (W3). */
export function LibraryRows({ query, navigate }: Props) {
  const f = parseTrackFilter(query);
  const qs = trackQuery({ ...f, name: undefined });
  const api = qs ? `/api/library/tracks?${qs}` : '/api/library/tracks';
  const load = useGet<Tracks>(api);
  const go = (href: string) => () => navigate(href);
  return (
    <>
      <Band module="L">{t('library.rows.sub')}</Band>
      <div className="page stack">
        <div><Button variant="quiet" href={MODULE_PATH.L} onClick={go(MODULE_PATH.L)}>{t('library.rows.back')}</Button></div>
        <Text variant="heading">{filterTitle(f)}</Text>
        {(f.artist_key != null || f.album_key != null) && (
          <div className="hist-actions">
            {f.artist_key != null && <Button variant="quiet" href={artistHref(f.artist_key)} onClick={go(artistHref(f.artist_key))}>{t('entity.rows.artist')}</Button>}
            {f.album_key != null && <Button variant="quiet" href={albumHref(f.album_key)} onClick={go(albumHref(f.album_key))}>{t('entity.rows.album')}</Button>}
          </div>
        )}
        <nav className="hist-choices" aria-label={t('library.rows.sort')}>
          {SORTS.map((s) => {
            const href = tracksHref(trackQuery({ ...f, sort: s, offset: undefined }));
            return <NavItem key={s} label={t(`library.rows.sort.${s}` as StringKey)} href={href} current={(f.sort ?? 'artist') === s} onNavigate={navigate} />;
          })}
        </nav>
        {load.state === 'loading' && <Text>{t('rows.loading')}</Text>}
        {load.state === 'failed' && (
          <Card>
            <div className="stack">
              <Status state="needs" label={t('library.failed')} />
              <Text>{t('library.rows.failed')}</Text>
            </div>
          </Card>
        )}
        {load.state === 'ok' && <RowsBody l={load.data} f={f} go={go} navigate={navigate} />}
      </div>
    </>
  );
}

function RowsBody({ l, f, go, navigate }: { l: Tracks; f: TrackFilter; go: (href: string) => () => void; navigate: (href: string) => void }) {
  const a = l.total ? l.offset + 1 : 0;
  const b = l.offset + l.rows.length;
  const prev = l.offset > 0 ? tracksHref(trackQuery({ ...f, offset: Math.max(0, l.offset - l.limit) })) : null;
  const next = b < l.total ? tracksHref(trackQuery({ ...f, offset: l.offset + l.limit })) : null;
  return (
    <>
      <Text>{tf('library.rows.total', { n: count(l.total, 'track'), a: fmt(a), b: fmt(b), order: t(`library.rows.order.${l.sort}` as StringKey) })}</Text>
      <Text variant="note">{`${t('rows.rule')}: ${l.rule}${l.params.length ? ` [${l.params.join(', ')}]` : ''}. ${t('library.rows.plays')}: ${l.plays_rule}. ${t('library.rows.code')}`}</Text>
      {l.rows.length === 0 ? <Text>{t('library.rows.none')}</Text> : (
        <ol className="hist-rows">
          {l.rows.map((r, i) => (
            <StationRow
              key={r.rating_key}
              position={l.offset + i + 1}
              module="L"
              title={r.title || t('rows.untitled')}
              artist={[r.track_artist || r.artist || t('rows.unknown'), r.album].filter(Boolean).join(' · ')}
              musicalKey={r.camelot ?? undefined}
              bpm={r.bpm != null ? Math.round(r.bpm) : undefined}
              why={trackWhy(r)}
              href={trackHref(r.rating_key)}
              onNavigate={navigate}
            />
          ))}
        </ol>
      )}
      {(prev || next) && (
        <div className="hist-actions">
          <Button disabled={!prev} href={prev ?? undefined} onClick={prev ? go(prev) : undefined}>{t('library.rows.prev')}</Button>
          <Button disabled={!next} href={next ?? undefined} onClick={next ? go(next) : undefined}>{t('library.rows.next')}</Button>
        </div>
      )}
    </>
  );
}
