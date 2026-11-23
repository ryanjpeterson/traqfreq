import { Band, Button, Card, Status, Text } from '../components/kit';
import { t, tf } from '../copy/t';
import { useGet } from '../app/api';
import { MODULE_PATH } from '../app/route';
import { formatUtc } from '../app/time';
import { count, dayLabel, fmt, rowsHref, type RowsFilter } from '../app/history';
import {
  neighbours, partLabel, partPeriod, periodName, topHref, weekdayName, wrappedHref,
  type Cache, type Part, type Wrapped,
} from '../app/periods';
import { RowsLink } from './History';

type Nav = { navigate: (href: string) => void };
type Unit = Parameters<typeof count>[1];

export const hours = (h: number) => tf('unit.hour', { n: fmt(h) });

export function Failed() {
  return (
    <Card>
      <div className="stack">
        <Status state="needs" label={t('history.failed')} />
        <Text>{t('history.failedBody')}</Text>
      </div>
    </Card>
  );
}

export function CacheNote({ cache }: { cache?: Cache }) {
  if (!cache) return null;
  return (
    <Text variant="note">
      {tf('history.cache', { at: formatUtc(new Date(cache.built_at * 1000).toISOString()), s: cache.seconds })}
    </Text>
  );
}

/** One bar list (L6): each line a label, a share bar (aria-hidden) and its number, which opens its rows. The
 *  list is the drawing's list view; ``summary`` is its one-line summary. */
export function BarList({ label, items, summary, navigate }: {
  label: string; summary: string;
  items: { key: string; name: string; sub?: string; n: number; unit: Unit; filter: RowsFilter; href?: string; rank?: number; extra?: string }[];
} & Nav) {
  const most = Math.max(1, ...items.map((i) => i.n));
  return (
    <>
      <Text variant="note">{summary}</Text>
      <ol className="rows hist-top" aria-label={label}>
        {items.map((i) => (
          <li key={i.key}>
            <span className="hist-top-name">
              {i.rank != null && <span className="hist-rank">{i.rank}</span>}
              <span className="hist-top-text">
                {i.href
                  ? <span><Button variant="quiet" href={i.href} onClick={() => navigate(i.href!)}>{i.name}</Button></span>
                  : <strong>{i.name}</strong>}
                <span className="hist-bar" aria-hidden="true"><span style={{ width: `${(100 * i.n) / most}%` }} /></span>
                {(i.sub || i.extra) && <span className="sub">{[i.sub, i.extra].filter(Boolean).join(' · ')}</span>}
              </span>
            </span>
            <RowsLink n={i.n} unit={i.unit} filter={i.filter} navigate={navigate} />
          </li>
        ))}
      </ol>
    </>
  );
}

/** The busiest part of a list, for its summary: "Busiest: Nov, 5 plays." */
function busiest(parts: { name: string; n: number }[]): string {
  const top = parts.reduce<{ name: string; n: number } | null>((a, p) => (p.n > (a?.n ?? 0) ? p : a), null);
  return top ? tf('wrapped.busiest', { name: top.name, n: count(top.n, 'play') }) : t('wrapped.nothing');
}

const thisYear = () => String(new Date().getFullYear());

/** Wrapped (T8) for a year, a month or a day: the same numbers as jimbo-dj's Wrapped, each opening its rows. */
export function HistoryWrapped({ query, navigate }: { query: string } & Nav) {
  const asked = new URLSearchParams(query).get('period') || thisYear();
  const period = /^\d{4}(-\d{2}(-\d{2})?)?$/.test(asked) ? asked : thisYear();
  const url = `/api/history/wrapped?period=${period}`;
  const load = useGet<Wrapped>(url);
  const n = neighbours(period);
  const go = (p: string) => () => navigate(wrappedHref(p));
  return (
    <>
      <Band module="H">{t('wrapped.sub')}</Band>
      <div className="page stack history">
        <div><Button variant="quiet" href={MODULE_PATH.H} onClick={() => navigate(MODULE_PATH.H)}>{t('counted.back')}</Button></div>
        <div className="hist-heat-head">
          <Text variant="title">{tf('wrapped.title', { period: periodName(period) })}</Text>
          <span className="hist-actions">
            <Button href={wrappedHref(n.prev)} onClick={go(n.prev)}>{t('wrapped.prev')}</Button>
            <Button href={wrappedHref(n.next)} onClick={go(n.next)}>{t('wrapped.next')}</Button>
            {n.up && <Button variant="quiet" href={wrappedHref(n.up)} onClick={go(n.up)}>{tf('wrapped.up', { period: periodName(n.up) })}</Button>}
          </span>
        </div>
        {load.state === 'loading' && <Text>{t('history.loading')}</Text>}
        {load.state === 'failed' && <Failed />}
        {load.state === 'ok' && <WrappedBody w={load.data} navigate={navigate} />}
      </div>
    </>
  );
}

function WrappedBody({ w, navigate }: { w: Wrapped } & Nav) {
  const p = w.period;
  const base: RowsFilter = { status: 'play', period: p };
  if (!w.plays) {
    return (
      <>
        <Text>{tf('wrapped.none', { period: periodName(p) })}</Text>
        <Text variant="note">{tf('wrapped.rule', { tz: w.timezone })}</Text>
      </>
    );
  }
  const isDay = w.day != null;
  const parts = (w.by_part ?? []).map((x: Part) => {
    const sub = partPeriod(p, x.part ?? 0);
    return {
      key: `p${x.part}`, name: partLabel(p, x), n: x.value, unit: 'play' as Unit,
      filter: isDay ? { ...base, hour: x.part } : { ...base, period: sub ?? p },
      href: !isDay && sub && x.value ? wrappedHref(sub) : undefined,
    };
  });
  const hoursOfDay = (w.hours_of_day ?? []).map((x, i) => ({
    key: `h${i}`, name: tf('rows.title.hour', { h: x.label }), n: x.value, unit: 'play' as Unit, filter: { ...base, hour: i },
  }));
  const weekdays = (w.weekdays ?? []).map((x, i) => ({
    key: `w${i}`, name: weekdayName(i), n: x.value, unit: 'play' as Unit, filter: { ...base, weekday: i },
  }));
  const top = p.length <= 7 ? topHref({ period: p }) : null;
  return (
    <>
      <section className="hist-head" aria-labelledby="w-plays">
        <Text variant="label" id="w-plays">{t('history.plays')}</Text>
        <p className="hist-big">{count(w.plays, 'play')}</p>
        <Text variant="note">{tf('wrapped.rule', { tz: w.timezone })}</Text>
      </section>

      <div className="hist-grid">
        <Card label={t('wrapped.totals')}>
          <ul className="rows" aria-label={t('wrapped.totals')}>
            <li><span><strong>{t('history.plays')}</strong></span><RowsLink n={w.plays} unit="play" filter={base} navigate={navigate} /></li>
            <li>
              <span><strong>{t('wrapped.hours')}</strong><span className="sub">{t('wrapped.hours.rule')}</span></span>
              <span className="hist-num">{hours(w.hours ?? 0)}</span>
            </li>
            <li><span><strong>{t('wrapped.artists')}</strong></span><span className="hist-num">{count(w.artists ?? 0, 'artist')}</span></li>
            <li><span><strong>{t('wrapped.songs')}</strong></span><span className="hist-num">{count(w.songs ?? 0, 'song')}</span></li>
            <li>
              <span><strong>{t('wrapped.new')}</strong>
                <span className="sub">{(w.new_artist_names ?? []).join(', ')}</span>
              </span>
              <span className="hist-num">{count(w.new_artists ?? 0, 'artist')}</span>
            </li>
            <li>
              <span><strong>{t('history.matched')}</strong><span className="sub">{t('history.matched.rule')}</span></span>
              <Button variant="quiet" href={rowsHref({ ...base, matched: true })} onClick={() => navigate(rowsHref({ ...base, matched: true }))}>
                {tf('history.matched.value', { pct: (w.in_library_pct ?? 0).toFixed(1) })}
                <span className="visually-hidden">{`, ${t('history.rows')}`}</span>
              </Button>
            </li>
          </ul>
        </Card>

        <Card label={t('history.sources')}>
          <ul className="rows" aria-label={t('history.sources')}>
            {(w.sources ?? []).map((s) => (
              <li key={s.source}>
                <span><strong>{s.name}</strong></span>
                <RowsLink n={s.plays} unit="play" filter={{ ...base, source: s.source }} navigate={navigate} />
              </li>
            ))}
            {w.busiest_day && !isDay && (
              <li>
                <span><strong>{t('years.busiest')}</strong></span>
                <span className="hist-actions">
                  <Button variant="quiet" href={wrappedHref(w.busiest_day.date)} onClick={() => navigate(wrappedHref(w.busiest_day!.date))}>
                    {dayLabel(w.busiest_day.date)}
                  </Button>
                  <RowsLink n={w.busiest_day.plays} unit="play" filter={{ status: 'play', period: w.busiest_day.date }} navigate={navigate} />
                </span>
              </li>
            )}
          </ul>
        </Card>
      </div>

      <section aria-labelledby="w-artists" className="stack">
        <Text variant="label" id="w-artists">{t('history.top')}</Text>
        <BarList label={t('history.top')} navigate={navigate}
          summary={tf('wrapped.top.summary', { n: count(w.top_artists?.length ?? 0, 'artist'), of: count(w.artists ?? 0, 'artist') })}
          items={(w.top_artists ?? []).map((a, i) => ({ key: a.key, rank: i + 1, name: a.name, n: a.plays, unit: 'play',
            filter: { ...base, artist: a.key, name: a.name } }))} />
      </section>
      <section aria-labelledby="w-songs" className="stack">
        <Text variant="label" id="w-songs">{t('wrapped.topSongs')}</Text>
        <BarList label={t('wrapped.topSongs')} navigate={navigate}
          summary={tf('wrapped.top.summary', { n: count(w.top_songs?.length ?? 0, 'song'), of: count(w.songs ?? 0, 'song') })}
          items={(w.top_songs ?? []).map((s, i) => ({ key: s.key, rank: i + 1, name: s.title, sub: s.artist, n: s.plays, unit: 'play',
            filter: { ...base, song: s.key, name: s.title } }))} />
      </section>
      <section aria-labelledby="w-albums" className="stack">
        <Text variant="label" id="w-albums">{t('wrapped.topAlbums')}</Text>
        <BarList label={t('wrapped.topAlbums')} navigate={navigate}
          summary={tf('wrapped.albums.summary', { n: count(w.top_albums?.length ?? 0, 'album') })}
          items={(w.top_albums ?? []).map((a, i) => ({ key: a.key, rank: i + 1, name: a.album, sub: a.artist, n: a.plays, unit: 'play',
            filter: { ...base, album: a.key, name: a.album } }))} />
      </section>
      {top && (
        <div><Button variant="quiet" href={top} onClick={() => navigate(top)}>{tf('wrapped.allTop', { period: periodName(p) })}</Button></div>
      )}

      <section aria-labelledby="w-parts" className="stack">
        <Text variant="label" id="w-parts">{t(isDay ? 'wrapped.byHour' : w.month ? 'wrapped.byDay' : 'wrapped.byMonth')}</Text>
        <BarList label={t(isDay ? 'wrapped.byHour' : w.month ? 'wrapped.byDay' : 'wrapped.byMonth')} navigate={navigate}
          summary={busiest(parts)} items={parts} />
      </section>
      {!isDay && (
        <div className="hist-grid">
          <section aria-labelledby="w-hours" className="stack">
            <Text variant="label" id="w-hours">{t('wrapped.hoursOfDay')}</Text>
            <BarList label={t('wrapped.hoursOfDay')} navigate={navigate} summary={busiest(hoursOfDay)} items={hoursOfDay} />
          </section>
          <section aria-labelledby="w-week" className="stack">
            <Text variant="label" id="w-week">{t('wrapped.weekdays')}</Text>
            <BarList label={t('wrapped.weekdays')} navigate={navigate} summary={busiest(weekdays)} items={weekdays} />
          </section>
        </div>
      )}

      {w.every_play && (
        <section aria-labelledby="w-every" className="stack">
          <Text variant="label" id="w-every">{t('wrapped.every')}</Text>
          <ol className="rows" aria-labelledby="w-every">
            {w.every_play.map((e, i) => (
              <li key={i}>
                <span>
                  <strong>{`${e.time} ${[e.artist, e.title].filter(Boolean).join(' · ')}`}</strong>
                  <span className="sub">{[e.album, e.source].filter(Boolean).join(' · ')}</span>
                </span>
                <span className="hist-num">{tf('unit.min', { n: fmt(e.minutes) })}</span>
              </li>
            ))}
          </ol>
          <div><Button variant="quiet" href={rowsHref(base)} onClick={() => navigate(rowsHref(base))}>{t('history.plays.show')}</Button></div>
        </section>
      )}

      <Text variant="note">{tf('wrapped.notInP1', { what: Object.values(w.not_in_p1).join('; ') })}</Text>
      <CacheNote cache={w.cache} />
    </>
  );
}
