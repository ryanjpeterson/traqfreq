import { Band, Button, NavItem, Text } from '../components/kit';
import { t, tf, type StringKey } from '../copy/t';
import { useGet } from '../app/api';
import { MODULE_PATH } from '../app/route';
import { count, fmt, type RowsFilter } from '../app/history';
import {
  TOP_KINDS, TOP_PERIODS, TOP_SORTS, periodFilter, periodName, topHref, wrappedHref,
  type TopKind, type TopPage, type TopSort,
} from '../app/periods';
import { BarList, CacheNote, Failed } from './HistoryWrapped';

type Nav = { navigate: (href: string) => void };

const PERIOD = /^(all|30d|12m|\d{4}(-\d{2})?)$/;

/** Top (T8): artists, songs or albums for a period (all, 30 days, 12 months, a year, a month), by plays or minutes. */
export function HistoryTop({ query, navigate }: { query: string } & Nav) {
  const q = new URLSearchParams(query);
  const period = PERIOD.test(q.get('period') ?? '') ? q.get('period')! : 'all';
  const kind = (TOP_KINDS as string[]).includes(q.get('kind') ?? '') ? (q.get('kind') as TopKind) : 'artists';
  const sort = (TOP_SORTS as string[]).includes(q.get('sort') ?? '') ? (q.get('sort') as TopSort) : 'plays';
  const page = Math.max(1, Number(q.get('page')) || 1);
  const url = `/api/history/top?period=${period}&kind=${kind}&sort=${sort}&page=${page}`;
  const load = useGet<TopPage>(url);
  const year = String(new Date().getFullYear());
  const periods = [...TOP_PERIODS, year, String(Number(year) - 1)];
  if (!periods.includes(period)) periods.push(period);
  const choice = (label: string, href: string, current: boolean) => (
    <NavItem key={href} label={label} href={href} current={current} onNavigate={navigate} />
  );
  return (
    <>
      <Band module="H">{t('top.sub')}</Band>
      <div className="page stack history">
        <div><Button variant="quiet" href={MODULE_PATH.H} onClick={() => navigate(MODULE_PATH.H)}>{t('counted.back')}</Button></div>
        <Text variant="title">{tf('top.title', { kind: t(`top.kind.${kind}` as StringKey), period: periodName(period) })}</Text>
        <nav className="hist-choices" aria-label={t('top.periods')}>
          {periods.map((p) => choice(periodName(p), topHref({ period: p, kind, sort }), p === period))}
        </nav>
        <nav className="hist-choices" aria-label={t('top.kinds')}>
          {TOP_KINDS.map((k) => choice(t(`top.kind.${k}` as StringKey), topHref({ period, kind: k, sort }), k === kind))}
        </nav>
        <nav className="hist-choices" aria-label={t('top.sorts')}>
          {TOP_SORTS.map((s) => choice(t(`top.sort.${s}` as StringKey), topHref({ period, kind, sort: s }), s === sort))}
        </nav>
        {load.state === 'loading' && <Text>{t('history.loading')}</Text>}
        {load.state === 'failed' && <Failed />}
        {load.state === 'ok' && <TopBody p={load.data} navigate={navigate} />}
      </div>
    </>
  );
}

function TopBody({ p, navigate }: { p: TopPage } & Nav) {
  const base: RowsFilter = { status: 'play', ...periodFilter(p.period, p.start, p.end) };
  const keyOf: Record<TopKind, 'artist' | 'song' | 'album'> = { artists: 'artist', songs: 'song', albums: 'album' };
  const unit = p.kind === 'artists' ? 'artist' : p.kind === 'songs' ? 'song' : 'album';
  const byMinutes = p.sort === 'minutes';
  const prev = p.page > 1 ? topHref({ period: p.period, kind: p.kind, sort: p.sort, page: p.page - 1 }) : null;
  const next = p.page < p.pages ? topHref({ period: p.period, kind: p.kind, sort: p.sort, page: p.page + 1 }) : null;
  const wrapped = /^\d{4}(-\d{2})?$/.test(p.period) ? wrappedHref(p.period) : null;
  return (
    <>
      <Text>
        {tf('top.summary', { n: count(p.total, unit), plays: count(p.plays, 'play'), a: fmt(p.items[0]?.rank ?? 0), b: fmt(p.items.at(-1)?.rank ?? 0) })}
      </Text>
      {p.items.length === 0 ? <Text>{t('top.none')}</Text> : (
        <BarList
          label={t(`top.kind.${p.kind}` as StringKey)}
          navigate={navigate}
          summary={byMinutes ? t('top.byMinutes') : t('top.byPlays')}
          items={p.items.map((it) => ({
            key: it.key, rank: it.rank, name: it.name ?? t('rows.untitled'), sub: it.sub ?? undefined,
            n: it.plays, unit: 'play',
            extra: [tf('unit.min', { n: fmt(it.minutes) }), !it.in_library && t('top.notInLibrary')].filter(Boolean).join(' · '),
            filter: { ...base, [keyOf[p.kind]]: it.key, name: it.name ?? undefined },
          }))}
        />
      )}
      {(prev || next) && (
        <div className="hist-actions">
          <Button disabled={!prev} href={prev ?? undefined} onClick={prev ? () => navigate(prev) : undefined}>{t('top.prev')}</Button>
          <Button disabled={!next} href={next ?? undefined} onClick={next ? () => navigate(next) : undefined}>{t('top.next')}</Button>
          <Text variant="note">{tf('top.page', { page: fmt(p.page), pages: fmt(p.pages) })}</Text>
        </div>
      )}
      {wrapped && <div><Button variant="quiet" href={wrapped} onClick={() => navigate(wrapped)}>{tf('top.wrapped', { period: periodName(p.period) })}</Button></div>}
      <Text variant="note">
        {[tf('top.rule', { tz: p.timezone }), tf('wrapped.notInP1', { what: Object.values(p.not_in_p1).join('; ') })].join(' ')}
      </Text>
      <CacheNote cache={p.cache} />
    </>
  );
}
