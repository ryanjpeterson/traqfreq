import { useEffect, useRef, useState, type CSSProperties } from 'react';
import { Band, Button, Card, Status, Text } from '../components/kit';
import { t, tf, type StringKey } from '../copy/t';
import { useGet } from '../app/api';
import { formatUtc } from '../app/time';
import {
  NOT_PLAYS, count, dayLabel, fmt, monthLabel, rowsHref, sourceName,
  type Heatmap, type Overview, type RowsFilter, type SourceRow,
} from '../app/history';
import { EmptyState } from './ModulePage';

type Nav = { navigate: (href: string) => void };
type Unit = Parameters<typeof count>[1];

/** A number that opens its rows (W3): "1,234 plays", a link to /history/listens with its filters. */
function RowsLink({ n, unit, filter, navigate }: { n: number; unit: Unit; filter: RowsFilter } & Nav) {
  const href = rowsHref(filter);
  if (n === 0) return <span className="hist-num">{count(n, unit)}</span>;  // no rows to show
  return (
    <Button variant="quiet" href={href} onClick={() => navigate(href)}>
      {count(n, unit)}
      <span className="visually-hidden">{`, ${t('history.rows')}`}</span>
    </Button>
  );
}

/** HISTORY's overview, read-only: plays, every listen counted once, a year of days, top artists, sources, years. */
export function History({ navigate }: Nav) {
  const load = useGet<Overview>('/api/history/overview');
  return (
    <>
      <Band module="H">{t('history.sub')}</Band>
      <div className="page stack history">
        {load.state === 'loading' && <Text>{t('history.loading')}</Text>}
        {/* A 404 means jimbo-dj's database has no listens table: an empty state pointing to SETUP (D1). */}
        {load.state === 'failed' && (load.status === 404
          ? <EmptyState body={t('empty.H')} navigate={navigate} />
          : (
            <Card>
              <div className="stack">
                <Status state="needs" label={t('history.failed')} />
                <Text>{t('history.failedBody')}</Text>
              </div>
            </Card>
          ))}
        {load.state === 'ok' && <OverviewBody o={load.data} navigate={navigate} />}
      </div>
    </>
  );
}

function OverviewBody({ o, navigate }: { o: Overview } & Nav) {
  const [heatYear, setHeatYear] = useState<number | null>(null);
  const heatRef = useRef<HTMLElement>(null);
  const jd = o.jimbodj;
  const compare = jd == null ? t('history.unstored') : jd.matches ? t('history.same') : tf('history.differs', { n: fmt(jd.plays) });
  return (
    <>
      <section className="hist-head" aria-labelledby="h-plays">
        <Text variant="label" id="h-plays">{t('history.plays')}</Text>
        <p className="hist-big">{count(o.plays, 'play')}</p>
        <Text variant="note">{`${t('history.plays.rule')} ${compare}`}</Text>
        <div>
          <Button variant="quiet" href={rowsHref({ status: 'play' })} onClick={() => navigate(rowsHref({ status: 'play' }))}>
            {t('history.plays.show')}
          </Button>
        </div>
      </section>

      <div className="hist-grid">
        <Card label={t('history.once')}>
          <div className="stack">
            <ul className="rows" aria-label={t('history.once')}>
              <li>
                <span>
                  <strong>{t('history.once.listens')}</strong>
                  <span className="sub">{t('history.once.listens.rule')}</span>
                </span>
                <span className="hist-num">{count(o.listens, 'listen')}</span>
              </li>
              {(['play', ...NOT_PLAYS] as const).map((k) => (
                <li key={k}>
                  <span>
                    <strong>{t(`history.once.${k}` as StringKey)}</strong>
                    <span className="sub">{t(`history.once.${k}.rule` as StringKey)}</span>
                  </span>
                  <RowsLink n={k === 'play' ? o.plays : o.not_plays[k]} unit="listen" filter={{ status: k }} navigate={navigate} />
                </li>
              ))}
            </ul>
            {o.adds_up ? <Text variant="note">{t('history.addsUp')}</Text> : (
              <div className="stack">
                <Status state="needs" label={t('history.addsUpNot')} />
                <Text>{t('history.addsUpNotBody')}</Text>
              </div>
            )}
          </div>
        </Card>

        <Card label={t('history.matched')}>
          <div className="stack">
            <Text variant="heading">{tf('history.matched.value', { pct: o.matched.pct.toFixed(1) })}</Text>
            <Text variant="note">{t('history.matched.rule')}</Text>
            <ul className="rows" aria-label={t('history.matched')}>
              <li>
                <span><strong>{t('history.matched')}</strong></span>
                <RowsLink n={o.matched.plays} unit="play" filter={{ status: 'play', matched: true }} navigate={navigate} />
              </li>
              <li>
                <span><strong>{t('history.matched.unmatched')}</strong></span>
                <RowsLink n={o.plays - o.matched.plays} unit="play" filter={{ status: 'play', matched: false }} navigate={navigate} />
              </li>
            </ul>
            {o.songs.heard != null && (
              <>
                <Text>{tf('history.songs', { heard: fmt(o.songs.heard), matched: fmt(o.songs.matched ?? 0) })}</Text>
                <Text variant="note">{t('history.songs.rule')}</Text>
              </>
            )}
          </div>
        </Card>
      </div>

      <section className="hist-heat" aria-labelledby="h-heat" ref={heatRef} tabIndex={-1}>
        <Text variant="label" id="h-heat">{t('history.heat')}</Text>
        <HeatSection year={heatYear} setYear={setHeatYear} years={o.years.map((y) => y.year)} navigate={navigate} />
      </section>

      <section aria-labelledby="h-top">
        <Text variant="label" id="h-top">{t('history.top')}</Text>
        <TopArtists o={o} navigate={navigate} />
      </section>

      <section aria-labelledby="h-sources">
        <Text variant="label" id="h-sources">{t('history.sources')}</Text>
        <div className="hist-sources">
          {o.sources.map((s) => <SourceCard key={s.source} s={s} navigate={navigate} />)}
        </div>
        <Text variant="note">{t('history.sources.rule')}</Text>
      </section>

      <section aria-labelledby="h-years">
        <Text variant="label" id="h-years">{t('history.years')}</Text>
        <ul className="rows" aria-labelledby="h-years">
          {[...o.years].reverse().map((y) => (
            <li key={y.year}>
              <span>
                <strong>{y.year}</strong>
                <span className="sub">
                  {Object.entries(y.by_source).map(([s, n]) => `${sourceName(s)} ${fmt(n)}`).join(' · ')}
                </span>
              </span>
              <span className="hist-actions">
                <Button variant="quiet" onClick={() => { setHeatYear(y.year); heatRef.current?.focus(); heatRef.current?.scrollIntoView?.(); }}>
                  {t('history.years.days')}
                  <span className="visually-hidden">{` ${y.year}`}</span>
                </Button>
                <RowsLink n={y.plays} unit="play" filter={{ status: 'play', year: y.year }} navigate={navigate} />
              </span>
            </li>
          ))}
        </ul>
        <Text variant="note">{tf('history.years.rule', { tz: o.timezone })}</Text>
      </section>

      {o.cache && (
        <Text variant="note">
          {tf('history.cache', { at: formatUtc(new Date(o.cache.built_at * 1000).toISOString()), s: o.cache.seconds })}
        </Text>
      )}
    </>
  );
}

function SourceCard({ s, navigate }: { s: SourceRow } & Nav) {
  const dups = Object.entries(s.duplicate_of);
  return (
    <Card label={s.name}>
      <div className="stack">
        {s.first && s.last && <Text variant="note">{tf('history.sources.span', { first: dayLabel(s.first.slice(0, 10)), last: dayLabel(s.last.slice(0, 10)) })}</Text>}
        <ul className="rows" aria-label={s.name}>
          <li>
            <span><strong>{t('history.once.listens')}</strong></span>
            <span className="hist-num">{count(s.listens, 'listen')}</span>
          </li>
          {(['play', 'too_short', 'repeat'] as const).map((k) => (
            <li key={k}>
              <span><strong>{t(`history.once.${k}` as StringKey)}</strong></span>
              <RowsLink n={s[k]} unit="listen" filter={{ status: k, source: s.source }} navigate={navigate} />
            </li>
          ))}
          <li>
            <span>
              <strong>{t('history.once.duplicate')}</strong>
              {dups.length > 0 && (
                <span className="sub">
                  {dups.map(([of, n]) => `${tf('history.sources.dupOf', { source: sourceName(of) })} ${fmt(n)}`).join(' · ')}
                </span>
              )}
            </span>
            <RowsLink n={s.duplicate} unit="listen" filter={{ status: 'duplicate', source: s.source }} navigate={navigate} />
          </li>
        </ul>
      </div>
    </Card>
  );
}

function TopArtists({ o, navigate }: { o: Overview } & Nav) {
  const most = o.top_artists[0]?.plays || 1;
  const jd = o.jimbodj;
  return (
    <>
      <ol className="rows hist-top">
        {o.top_artists.map((a, i) => (
          <li key={a.key}>
            <span className="hist-top-name">
              <span className="hist-rank">{i + 1}</span>
              <span className="hist-top-text">
                <strong>{a.name}</strong>
                <span className="hist-bar" aria-hidden="true"><span style={{ width: `${(100 * a.plays) / most}%` }} /></span>
              </span>
            </span>
            <RowsLink n={a.plays} unit="play" filter={{ status: 'play', artist: a.key, name: a.name }} navigate={navigate} />
          </li>
        ))}
      </ol>
      <Text variant="note">
        {[tf('history.top.rule', { n: fmt(o.artists_heard) }),
          jd?.top_artists_match === true ? t('history.top.matches') : jd?.top_artists_match === false ? t('history.top.differs') : '']
          .filter(Boolean).join(' ')}
      </Text>
    </>
  );
}

/** The year heatmap: a drawing (aria-hidden), its screen-reader summary, a legend and its list view by month (L6). */
function HeatSection({ year, setYear, years, navigate }: { year: number | null; setYear: (y: number | null) => void; years: number[] } & Nav) {
  const url = year == null ? '/api/history/heatmap' : `/api/history/heatmap?year=${year}`;
  const load = useGet<Heatmap>(url);
  const thisYear = new Date().getFullYear();
  const first = Math.min(...years, thisYear);
  return (
    <div className="stack">
      <div className="hist-heat-head">
        <Text variant="heading">{year == null ? t('history.heat.recent') : String(year)}</Text>
        <span className="hist-actions">
          <Button disabled={(year ?? thisYear) - 1 < first} onClick={() => setYear(year == null ? thisYear - 1 : year - 1)}>
            {t('history.heat.earlier')}
          </Button>
          <Button disabled={year == null} onClick={() => setYear(year != null && year + 1 < thisYear ? year + 1 : null)}>
            {year != null && year + 1 < thisYear ? t('history.heat.later') : t('history.heat.toRecent')}
          </Button>
        </span>
      </div>
      {load.state === 'loading' && <Text>{t('history.loading')}</Text>}
      {load.state === 'failed' && <Status state="needs" label={t('history.failed')} />}
      {load.state === 'ok' && <HeatBody h={load.data} navigate={navigate} />}
    </div>
  );
}

function HeatBody({ h, navigate }: { h: Heatmap } & Nav) {
  const scroller = useRef<HTMLDivElement>(null);
  useEffect(() => {
    // On a narrow screen the drawing scrolls sideways; start at its most recent weeks.
    const el = scroller.current;
    if (el) el.scrollLeft = el.scrollWidth;
  }, [h]);
  const offset = h.first ? (new Date(`${h.first}T00:00:00Z`).getUTCDay() + 6) % 7 : 0; // Monday = 0
  const weeks = Math.ceil((offset + h.cells.length) / 7);
  const labels: { col: number; text: string }[] = [];
  h.cells.forEach((c, i) => {
    const col = Math.floor((offset + i) / 7);
    if (c.date.endsWith('-01') || i === 0) labels.push({ col, text: monthLabel(c.date.slice(0, 7), 'short') });
  });
  const months = labels.filter((l, i) => !(i === 0 && labels[1] && labels[1].col - l.col < 3));
  const summary = h.first && h.last ? tf('history.heat.summary', {
    from: dayLabel(h.first), to: dayLabel(h.last), plays: fmt(h.plays), lit: fmt(h.days_played), days: fmt(h.days),
    busiest: h.busiest ? tf('history.heat.busiest', { date: dayLabel(h.busiest.date), n: fmt(h.busiest.plays) }) : t('history.heat.none'),
  }) : t('history.heat.none');
  return (
    <>
      <p className="visually-hidden">{summary}</p>
      <div className="heat-scroll" ref={scroller} aria-hidden="true">
        <div className="heat" style={{ '--weeks': weeks } as CSSProperties}>
          {months.map((l) => (
            <span key={`${l.col}-${l.text}`} className="heat-month" style={{ gridColumn: `${l.col + 1} / span 3` }}>{l.text}</span>
          ))}
          {h.cells.map((c, i) => (
            <span
              key={c.date}
              className="heat-cell"
              data-level={c.level}
              style={{ gridColumn: Math.floor((offset + i) / 7) + 1, gridRow: ((offset + i) % 7) + 2 }}
            />
          ))}
        </div>
      </div>
      <div className="heat-legend">
        <Text variant="label">{t('history.heat.legend')}</Text>
        <ul>
          {h.levels.map((lv) => (
            <li key={lv.level}>
              <span className="heat-cell" data-level={lv.level} aria-hidden="true" />
              {lv.level === 0 ? t('history.heat.level0')
                : lv.min > lv.max ? '–'
                  : `${lv.min === lv.max ? fmt(lv.min) : `${fmt(lv.min)}–${fmt(lv.max)}`} ${t('unit.perDay')}`}
            </li>
          ))}
        </ul>
      </div>
      <Text variant="note">
        {`${tf('history.heat.month', { plays: count(h.plays, 'play'), lit: fmt(h.days_played), days: fmt(h.days) })}. ${tf('history.heat.rule', { tz: h.timezone })}`}
      </Text>

      <Text variant="label">{t('history.heat.list')}</Text>
      <ul className="rows" aria-label={t('history.heat.list')}>
        {[...h.months].reverse().map((m) => (
          <li key={m.month}>
            <span>
              <strong>{monthLabel(m.month)}</strong>
              <span className="sub">
                {[tf('history.heat.month', { plays: count(m.plays, 'play'), lit: fmt(m.days_played), days: fmt(m.days) }),
                  m.busiest && tf('history.heat.monthBusiest', { date: dayLabel(m.busiest.date), n: count(m.busiest.plays, 'play') })]
                  .filter(Boolean).join(', ')}
              </span>
            </span>
            <RowsLink n={m.plays} unit="play" filter={{ status: 'play', period: m.month }} navigate={navigate} />
          </li>
        ))}
      </ul>
    </>
  );
}
