import { Band, Button, Card, Status, StationRow, Text } from '../components/kit';
import { t, tf, type StringKey } from '../copy/t';
import { useGet } from '../app/api';
import { MODULE_PATH } from '../app/route';
import {
  count, dayLabel, fmt, localTime, monthLabel, rowsHref, sourceName,
  type ListenRow, type ListenStatus, type Listens, type RowsFilter,
} from '../app/history';

type Props = { query: string; navigate: (href: string) => void };

const STATUSES: ListenStatus[] = ['play', 'too_short', 'repeat', 'duplicate'];

/** The filters in /history/listens?…, kept to the ones the API knows. */
export function parseFilter(query: string): RowsFilter {
  const q = new URLSearchParams(query);
  const s = q.get('status') as ListenStatus | null;
  const num = (k: string) => (q.get(k) && /^\d+$/.test(q.get(k)!) ? Number(q.get(k)) : undefined);
  const m = q.get('matched');
  return {
    status: s && STATUSES.includes(s) ? s : 'play',
    source: q.get('source') || undefined,
    year: num('year'),
    period: q.get('period') || undefined,
    artist: q.get('artist') || undefined,
    matched: m === 'true' ? true : m === 'false' ? false : undefined,
    offset: num('offset'),
    name: (q.get('artist') && q.get('name')) || undefined,
  };
}

function periodLabel(p: string): string {
  return p.length === 10 ? dayLabel(p) : p.length === 7 ? monthLabel(p) : p;
}

/** Why a listen is (or isn't) a play, in one line (B3's "why it's here", for rows behind a number). */
function why(r: ListenRow, tz: string): string {
  const parts = [sourceName(r.source)];
  if (r.started_at) parts.push(`${localTime(r.started_at, tz)} ${tz}`);
  if (r.ms_played != null) {
    const s = Math.round(r.ms_played / 1000);
    parts.push(tf('rows.why.played', { min: Math.floor(s / 60), s: s % 60 }));
  } else {
    parts.push(t('rows.why.noLength'));
  }
  parts.push(r.rating_key != null ? tf('rows.why.track', { rk: r.rating_key }) : t('rows.why.noTrack'));
  if (r.dup_of && r.dup_of === r.source) parts.push(t('rows.why.repeat'));
  else if (r.dup_of) parts.push(tf('rows.why.dupOf', { source: sourceName(r.dup_of) }));
  return parts.join(' · ');
}

/** The listens behind a HISTORY number, newest first, 50 a page, with the rule that selected them (W3). */
export function HistoryRows({ query, navigate }: Props) {
  const f = parseFilter(query);
  const api = `/api/history/listens${rowsHref({ ...f, name: undefined }).replace(/^[^?]*/, '')}`;
  const load = useGet<Listens>(api);
  const go = (href: string) => () => navigate(href);
  const title = [
    t(`rows.title.${f.status}` as StringKey),
    f.source && sourceName(f.source),
    f.year != null && String(f.year),
    f.period && periodLabel(f.period),
    f.name,
    f.matched === true && t('rows.matchedYes'),
    f.matched === false && t('rows.matchedNo'),
  ].filter(Boolean).join(' · ');
  return (
    <>
      <Band module="H">{t('rows.sub')}</Band>
      <div className="page stack">
        <div><Button variant="quiet" href={MODULE_PATH.H} onClick={go(MODULE_PATH.H)}>{t('rows.back')}</Button></div>
        <Text variant="heading">{title}</Text>
        {load.state === 'loading' && <Text>{t('rows.loading')}</Text>}
        {load.state === 'failed' && (
          <Card>
            <div className="stack">
              <Status state="needs" label={t('history.failed')} />
              <Text>{t('rows.failed')}</Text>
            </div>
          </Card>
        )}
        {load.state === 'ok' && <RowsBody l={load.data} f={f} go={go} />}
      </div>
    </>
  );
}

function RowsBody({ l, f, go }: { l: Listens; f: RowsFilter; go: (href: string) => () => void }) {
  const a = l.total ? l.offset + 1 : 0;
  const b = l.offset + l.rows.length;
  const newer = l.offset > 0 ? rowsHref({ ...f, offset: Math.max(0, l.offset - l.limit) }) : null;
  const older = b < l.total ? rowsHref({ ...f, offset: l.offset + l.limit }) : null;
  return (
    <>
      <Text>{tf('rows.total', { n: count(l.total, 'listen'), a: fmt(a), b: fmt(b) })}</Text>
      <Text variant="note">{`${t('rows.rule')}: ${l.rule}${l.params.length ? ` [${l.params.join(', ')}]` : ''}`}</Text>
      {l.rows.length === 0 ? <Text>{t('rows.none')}</Text> : (
        <ol className="hist-rows">
          {l.rows.map((r, i) => (
            <StationRow
              key={r.id}
              position={l.offset + i + 1}
              module="H"
              title={r.title || t('rows.untitled')}
              artist={[r.artist || t('rows.unknown'), r.album].filter(Boolean).join(' · ')}
              why={why(r, l.timezone)}
            />
          ))}
        </ol>
      )}
      {(newer || older) && (
        <div className="hist-actions">
          <Button disabled={!newer} href={newer ?? undefined} onClick={newer ? go(newer) : undefined}>{t('rows.later')}</Button>
          <Button disabled={!older} href={older ?? undefined} onClick={older ? go(older) : undefined}>{t('rows.earlier')}</Button>
        </div>
      )}
    </>
  );
}
