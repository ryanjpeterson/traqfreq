import { Band, Button, Card, Text } from '../components/kit';
import { t, tf } from '../copy/t';
import { useGet } from '../app/api';
import { MODULE_PATH } from '../app/route';
import { count, dayLabel, fmt, sourceName } from '../app/history';
import { topHref, wrappedHref, type Daily, type OnThisDay } from '../app/periods';
import { CacheNote, Failed, hours } from './HistoryWrapped';
import { RowsLink } from './History';

type Nav = { navigate: (href: string) => void };

/** Years (T8): every year's plays and hours, on this day in earlier years, and the overview's highlights. */
export function HistoryYears({ navigate }: Nav) {
  const load = useGet<Daily>('/api/history/years');
  return (
    <>
      <Band module="H">{t('years.sub')}</Band>
      <div className="page stack history">
        <div><Button variant="quiet" href={MODULE_PATH.H} onClick={() => navigate(MODULE_PATH.H)}>{t('counted.back')}</Button></div>
        <Text variant="title">{t('years.title')}</Text>
        {load.state === 'loading' && <Text>{t('history.loading')}</Text>}
        {load.state === 'failed' && <Failed />}
        {load.state === 'ok' && <YearsBody d={load.data} navigate={navigate} />}
      </div>
    </>
  );
}

function YearsBody({ d, navigate }: { d: Daily } & Nav) {
  const most = Math.max(1, ...d.years.map((y) => y.plays));
  const peak = d.years.reduce((a, y) => (y.plays > (a?.plays ?? -1) ? y : a), d.years[0]);
  const h = d.highlights;
  return (
    <>
      <section aria-labelledby="y-years" className="stack">
        <Text variant="label" id="y-years">{t('years.list')}</Text>
        <Text>
          {tf('years.summary', {
            n: fmt(d.years.length), plays: count(d.plays, 'play'), hours: hours(d.hours),
            peak: peak ? tf('years.peak', { year: peak.year, plays: count(peak.plays, 'play') }) : '',
          })}
        </Text>
        <ul className="rows hist-top" aria-labelledby="y-years">
          {[...d.years].reverse().map((y) => (
            <li key={y.year}>
              <span className="hist-top-text">
                <span>
                  <Button variant="quiet" href={wrappedHref(String(y.year))} onClick={() => navigate(wrappedHref(String(y.year)))}>
                    {String(y.year)}
                    <span className="visually-hidden">{`, ${t('years.wrapped')}`}</span>
                  </Button>
                </span>
                <span className="hist-bar" aria-hidden="true"><span style={{ width: `${(100 * y.plays) / most}%` }} /></span>
                <span className="sub">
                  {[hours(y.hours), Object.entries(y.by_source).map(([s, n]) => `${sourceName(s)} ${fmt(n)}`).join(' · ')].join(' · ')}
                </span>
              </span>
              <RowsLink n={y.plays} unit="play" filter={{ status: 'play', year: y.year }} navigate={navigate} />
            </li>
          ))}
        </ul>
        <Text variant="note">{tf('years.rule', { tz: d.timezone })}</Text>
      </section>

      <section aria-labelledby="y-otd" className="stack">
        <Text variant="label" id="y-otd">{tf('years.otd', { date: dayLabel(d.today).replace(/ \d{4}$/, '') })}</Text>
        <OnThisDayList days={d.on_this_day} today={d.today} navigate={navigate} />
        <Text variant="note">{t('years.otd.rule')}</Text>
      </section>

      {h && (
        <section aria-labelledby="y-high" className="stack">
          <Text variant="label" id="y-high">{t('years.highlights')}</Text>
          <Card>
            <ul className="rows" aria-labelledby="y-high">
              <li>
                <span><strong>{t('years.streak')}</strong>
                  <span className="sub">{h.streak.best_ended ? tf('years.streak.best', { n: count(h.streak.best, 'day'), date: dayLabel(h.streak.best_ended) }) : ''}</span>
                </span>
                <span className="hist-num">{count(h.streak.current, 'day')}</span>
              </li>
              <li>
                <span><strong>{t('years.busiest')}</strong></span>
                <span className="hist-actions">
                  <Button variant="quiet" href={wrappedHref(h.busiest_day.date)} onClick={() => navigate(wrappedHref(h.busiest_day.date))}>
                    {dayLabel(h.busiest_day.date)}
                  </Button>
                  <RowsLink n={h.busiest_day.plays} unit="play" filter={{ status: 'play', period: h.busiest_day.date }} navigate={navigate} />
                </span>
              </li>
              <li>
                <span><strong>{t('years.average')}</strong><span className="sub">{tf('years.daysPlayed', { pct: fmt(h.days_played_pct) })}</span></span>
                <span className="hist-num">{`${fmt(h.average_day)} ${t('unit.perDay')}`}</span>
              </li>
              <li>
                <span><strong>{t('years.artistsHeard')}</strong></span>
                <span className="hist-num">{count(h.artists_heard, 'artist')}</span>
              </li>
              {h.first_play && (
                <li>
                  <span><strong>{t('years.first')}</strong>
                    <span className="sub">{[h.first_play.artist, h.first_play.title].filter(Boolean).join(' · ')}</span>
                  </span>
                  <Button variant="quiet" href={wrappedHref(h.first_play.date)} onClick={() => navigate(wrappedHref(h.first_play!.date))}>
                    {dayLabel(h.first_play.date)}
                  </Button>
                </li>
              )}
            </ul>
          </Card>
          <Text variant="note">{t('years.highlights.rule')}</Text>
        </section>
      )}

      <div className="hist-actions">
        <Button href={topHref({})} onClick={() => navigate(topHref({}))}>{t('years.top')}</Button>
      </div>
      <CacheNote cache={d.cache} />
    </>
  );
}

/** Today's date in earlier years: plays that day and its top songs. */
export function OnThisDayList({ days, today, navigate }: { days: OnThisDay[]; today: string } & Nav) {
  if (days.length === 0) return <Text>{t('years.otd.none')}</Text>;
  const md = today.slice(4);
  return (
    <ul className="rows" aria-label={t('years.otd.list')}>
      {days.map((y) => {
        const day = `${y.year}${md}`;
        return (
          <li key={y.year}>
            <span>
              <Button variant="quiet" href={wrappedHref(day)} onClick={() => navigate(wrappedHref(day))}>{dayLabel(day)}</Button>
              <span className="sub">
                {y.top.map((s) => `${[s.artist, s.title].filter(Boolean).join(' · ')} (${count(s.plays, 'play')})`).join('; ')}
              </span>
            </span>
            <RowsLink n={y.plays} unit="play" filter={{ status: 'play', period: day }} navigate={navigate} />
          </li>
        );
      })}
    </ul>
  );
}

