import { Band, Button, Card, Status, Text } from '../components/kit';
import { t, tf } from '../copy/t';
import { useGet, type Load } from '../app/api';
import { HISTORY_COMPARE, MODULE_PATH } from '../app/route';
import { count, fmt } from '../app/history';
import { periodName, wrappedHref, type Compare, type CompareField, type CompareRow } from '../app/periods';
import { CacheNote, Failed } from './HistoryWrapped';

type Nav = { navigate: (href: string) => void };

const short = (v: unknown) => {
  const s = JSON.stringify(v);
  return s && s.length > 120 ? `${s.slice(0, 117)}...` : String(s);
};

/** The P1 gate in one card, for SETUP and the HISTORY overview: how many stored numbers match jimbo-dj's. */
export function CompareCard({ load, navigate }: { load: Load<Compare> } & Nav) {
  return (
    <Card label={t('compare.card')}>
      {load.state === 'loading' && <Text>{t('compare.loading')}</Text>}
      {load.state === 'failed' && <Status state="needs" label={t('history.failed')} />}
      {load.state === 'ok' && (
        <div className="stack">
          <Status state={load.data.passed ? 'ready' : 'needs'} label={t(load.data.passed ? 'compare.passed' : 'compare.notPassed')} />
          <Text>{summary(load.data)}</Text>
          <div>
            <Button variant="quiet" href={HISTORY_COMPARE} onClick={() => navigate(HISTORY_COMPARE)}>{t('compare.open')}</Button>
          </div>
        </div>
      )}
    </Card>
  );
}

function summary(c: Compare): string {
  return tf('compare.summary', {
    rows: count(c.stored, 'row'), matching: fmt(c.matching), fields: count(c.fields, 'field'), mf: fmt(c.matching_fields),
    stale: c.differ ? tf('compare.staleNote', { differ: fmt(c.differ), explained: fmt(c.explained) }) : '',
  });
}

/** Every number jimbo-dj stored for HISTORY next to traqfreq's (P1 gate, T8). */
export function HistoryCompare({ navigate }: Nav) {
  const load = useGet<Compare>('/api/history/compare');
  return (
    <>
      <Band module="H">{t('compare.sub')}</Band>
      <div className="page stack history">
        <div><Button variant="quiet" href={MODULE_PATH.H} onClick={() => navigate(MODULE_PATH.H)}>{t('counted.back')}</Button></div>
        <Text variant="title">{t('compare.title')}</Text>
        <Text>{t('compare.intro')}</Text>
        {load.state === 'loading' && <Text>{t('compare.loading')}</Text>}
        {load.state === 'failed' && <Failed />}
        {load.state === 'ok' && (
          <>
            <Status state={load.data.passed ? 'ready' : 'needs'} label={t(load.data.passed ? 'compare.passed' : 'compare.notPassed')} />
            <Text>{summary(load.data)}</Text>
            <Text variant="note">{`${load.data.rules.fresh}. ${load.data.rules.passed}.`}</Text>
            {load.data.stored === 0 && <Text>{t('compare.none')}</Text>}
            <ul className="rows" aria-label={t('compare.title')}>
              {load.data.rows.map((r) => <CompareLine key={`${r.name}-${r.params}`} r={r} navigate={navigate} />)}
            </ul>
            <Text variant="note">{tf('wrapped.notInP1', { what: Object.values(load.data.not_in_p1).join('; ') })}</Text>
            <CacheNote cache={load.data.cache} />
          </>
        )}
      </div>
    </>
  );
}

function CompareLine({ r, navigate }: { r: CompareRow } & Nav) {
  const name = r.name === 'history.overview' ? t('compare.overview') : tf('compare.wrapped', { period: periodName(r.params) });
  const href = r.name === 'history.wrapped' ? wrappedHref(r.params) : MODULE_PATH.H;
  const state = r.matches ? t('compare.match') : r.fresh ? t('compare.differs') : t('compare.differsStale');
  const bad = r.fields.filter((f) => f.matches === false);
  return (
    <li>
      <span>
        <Button variant="quiet" href={href} onClick={() => navigate(href)}>{name}</Button>
        <span className="sub">
          {[tf('compare.fields', { m: fmt(r.matching), n: count(r.compared, 'field') }),
            r.fresh ? t('compare.fresh') : t('compare.stale')].join(' · ')}
        </span>
        {bad.map((f) => <span key={f.field} className="sub mono">{diff(f)}</span>)}
      </span>
      <Status state={r.matches ? 'ready' : r.fresh ? 'needs' : 'off'} label={state} />
    </li>
  );
}

function diff(f: CompareField): string {
  if ('first_diff' in f) return `${f.field}: ${short(f.first_diff)}`;
  return tf('compare.diff', { field: f.field, jd: short(f.jimbodj), tq: short(f.traqfreq) });
}
