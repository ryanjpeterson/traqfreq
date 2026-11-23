import { Band, Button, Card, Status, Text } from '../components/kit';
import { t, tf } from '../copy/t';
import { useGet } from '../app/api';
import { formatUtc } from '../app/time';
import { count, fmt1, pct, tracksHref, valueLabel, type LibraryStats } from '../app/library';
import { EmptyState } from './ModulePage';

type Nav = { navigate: (href: string) => void };

/** A number that opens its rows (W3): its text links to /library/tracks with the number's query. */
export function TracksLink({ text, n, query, extra, navigate }: { text: string; n: number; query: string; extra?: Record<string, string> } & Nav) {
  if (n === 0) return <span className="hist-num">{text}</span>;  // no rows to show
  const href = tracksHref(query, extra);
  return (
    <Button variant="quiet" href={href} onClick={() => navigate(href)}>
      {text}
      <span className="visually-hidden">{`, ${t('library.rows')}`}</span>
    </Button>
  );
}

/** LIBRARY, read-only: jimbo-dj's library numbers (its library.stats), each with its rule, each opening its rows. */
export function Library({ navigate }: Nav) {
  const load = useGet<LibraryStats>('/api/library/stats');
  return (
    <>
      <Band module="L">{t('library.sub')}</Band>
      <div className="page stack history library">
        {load.state === 'loading' && <Text>{t('library.loading')}</Text>}
        {/* A 404 means jimbo-dj's database has no tracks table: an empty state pointing to SETUP (D1). */}
        {load.state === 'failed' && (load.status === 404
          ? <EmptyState body={t('empty.L')} navigate={navigate} />
          : (
            <Card>
              <div className="stack">
                <Status state="needs" label={t('library.failed')} />
                <Text>{t('library.failedBody')}</Text>
              </div>
            </Card>
          ))}
        {load.state === 'ok' && <LibraryBody s={load.data} navigate={navigate} />}
      </div>
    </>
  );
}

const q = (s: LibraryStats, k: string) => (typeof s.rows[k] === 'string' ? (s.rows[k] as string) : '');
const qOf = (s: LibraryStats, k: string, v: string) => (s.rows[k] as Record<string, string> | undefined)?.[v] ?? '';
const rule = (s: LibraryStats, k: string) => `${t('library.rule')}: ${s.rules[k] ?? ''}`;

function LibraryBody({ s, navigate }: { s: LibraryStats } & Nav) {
  const jd = s.jimbodj;
  const stored = jd == null ? t('library.unstored') : jd.fresh ? t('library.storedFresh') : t('library.storedStale');
  const ph = s.play_history;
  const p = s.paths;
  const unmapped = s.tracks - p.mapped;
  const head: { k: string; label: string; text: string; n: number }[] = [
    { k: 'albums', label: t('library.albums'), text: count(s.albums, 'album'), n: s.albums },
    { k: 'artists', label: t('library.artists'), text: count(s.artists, 'artist'), n: s.artists },
    { k: 'hours', label: t('library.hours'), text: tf('unit.hour', { n: fmt1(s.hours) }), n: s.tracks },
    { k: 'size_gb', label: t('library.size'), text: tf('unit.gb', { n: fmt1(s.size_gb) }), n: s.tracks },
  ];
  return (
    <>
      <section className="hist-head" aria-labelledby="l-tracks">
        <Text variant="label" id="l-tracks">{t('library.tracks')}</Text>
        <p className="hist-big">{count(s.tracks, 'track')}</p>
        <Text variant="note">{`${rule(s, 'tracks')}. ${stored}`}</Text>
        <div>
          <Button variant="quiet" href={tracksHref(q(s, 'tracks'))} onClick={() => navigate(tracksHref(q(s, 'tracks')))}>
            {t('library.tracks.show')}
          </Button>
        </div>
        <ul className="rows" aria-label={t('library.head')}>
          {head.map((h) => (
            <li key={h.k}>
              <span><strong>{h.label}</strong><span className="sub">{rule(s, h.k)}</span></span>
              <TracksLink text={h.text} n={h.n} query={q(s, h.k)} navigate={navigate} />
            </li>
          ))}
        </ul>
      </section>

      <section aria-labelledby="l-files">
        <Text variant="label" id="l-files">{t('library.files')}</Text>
        <div className="hist-grid">
          <Bars s={s} k="codecs" label={t('library.codecs')} values={s.codecs} navigate={navigate} />
          <Bars s={s} k="containers" label={t('library.containers')} values={s.containers} navigate={navigate} />
          <Bars s={s} k="bitrate_kbps" label={t('library.bitrate')} values={s.bitrate_kbps} ordered navigate={navigate} />
        </div>
      </section>

      <section aria-labelledby="l-plays">
        <Text variant="label" id="l-plays">{t('library.plays')}</Text>
        <div className="hist-grid">
          <Card label={t('library.plays.plex')}>
            <div className="stack">
              <ul className="rows" aria-label={t('library.plays.plex')}>
                <li>
                  <span><strong>{t('library.played')}</strong><span className="sub">{`${pct(ph.played_pct)} · ${rule(s, 'played_tracks')}`}</span></span>
                  <TracksLink text={count(ph.played_tracks, 'track')} n={ph.played_tracks} query={q(s, 'played_tracks')} navigate={navigate} />
                </li>
                <li>
                  <span><strong>{t('library.plexPlays')}</strong><span className="sub">{rule(s, 'total_plays')}</span></span>
                  <TracksLink text={count(ph.total_plays, 'play')} n={ph.played_tracks} query={q(s, 'total_plays')} navigate={navigate} />
                </li>
                <li>
                  <span><strong>{t('library.rated')}</strong><span className="sub">{`${pct(ph.rated_pct)} · ${rule(s, 'rated_tracks')}`}</span></span>
                  <TracksLink text={count(ph.rated_tracks, 'track')} n={ph.rated_tracks} query={q(s, 'rated_tracks')} navigate={navigate} />
                </li>
              </ul>
              <Text variant="note">{t('library.plays.note')}</Text>
            </div>
          </Card>
          <Card label={t('library.top')}>
            <TopArtists s={s} navigate={navigate} />
          </Card>
        </div>
      </section>

      <section aria-labelledby="l-analysis">
        <Text variant="label" id="l-analysis">{t('library.analysis')}</Text>
        <div className="hist-grid">
          <Card label={t('library.sonic')}>
            <div className="stack">
              <Text>{t('library.sonic.what')}</Text>
              <ul className="rows" aria-label={t('library.sonic')}>
                <li>
                  <span><strong>{t('library.analysed')}</strong><span className="sub">{pct(s.sonic_analysis.pct)}</span></span>
                  <TracksLink text={count(s.sonic_analysis.tracks, 'track')} n={s.sonic_analysis.tracks} query={q(s, 'sonic_analysis')} navigate={navigate} />
                </li>
              </ul>
              <Text variant="note">{rule(s, 'sonic_analysis')}</Text>
            </div>
          </Card>
          <Card label={t('library.analyzer')}>
            <div className="stack">
              <Text>{tf('library.analyzer.what', { v: s.analyzer.version })}</Text>
              <ul className="rows" aria-label={t('library.analyzer')}>
                <li>
                  <span><strong>{t('library.analysed')}</strong><span className="sub">{pct(s.analyzer.pct)}</span></span>
                  <TracksLink text={count(s.analyzer.tracks, 'track')} n={s.analyzer.tracks} query={q(s, 'analyzer')} navigate={navigate} />
                </li>
                <li>
                  <span><strong>{t('library.analyzer.errors')}</strong><span className="sub">{rule(s, 'analyzer_errors')}</span></span>
                  <TracksLink text={count(s.analyzer.errors, 'track')} n={s.analyzer.errors} query={q(s, 'analyzer_errors')} navigate={navigate} />
                </li>
              </ul>
              <Text variant="note">{rule(s, 'analyzer')}</Text>
            </div>
          </Card>
        </div>
      </section>

      <section aria-labelledby="l-paths">
        <Text variant="label" id="l-paths">{t('library.paths')}</Text>
        <div className="hist-grid">
          <Card label={t('library.paths.files')}>
            <div className="stack">
              <ul className="rows" aria-label={t('library.paths.files')}>
                <li>
                  <span><strong>{t('library.mapped')}</strong><span className="sub">{`${pct(p.mapped_pct)} · ${rule(s, 'mapped')}`}</span></span>
                  <TracksLink text={count(p.mapped, 'track')} n={p.mapped} query={q(s, 'mapped')} navigate={navigate} />
                </li>
                <li>
                  <span><strong>{t('library.unmapped')}</strong><span className="sub">{t('library.unmapped.rule')}</span></span>
                  <TracksLink text={count(unmapped, 'track')} n={unmapped} query={q(s, 'unmapped')} navigate={navigate} />
                </li>
                <li>
                  <span><strong>{t('library.multiPart')}</strong><span className="sub">{rule(s, 'multi_part_tracks')}</span></span>
                  <TracksLink text={count(p.multi_part_tracks, 'track')} n={p.multi_part_tracks} query={q(s, 'multi_part_tracks')} navigate={navigate} />
                </li>
                <li>
                  <span><strong>{t('library.removed')}</strong><span className="sub">{rule(s, 'removed_since_first_sync')}</span></span>
                  <TracksLink text={count(p.removed_since_first_sync, 'track')} n={p.removed_since_first_sync} query={q(s, 'removed_since_first_sync')} navigate={navigate} />
                </li>
              </ul>
              {p.unmapped_examples.length > 0 && (
                <>
                  <Text variant="label">{t('library.unmapped.examples')}</Text>
                  <ul className="rows lib-paths" aria-label={t('library.unmapped.examples')}>
                    {p.unmapped_examples.map((x) => <li key={x}><span className="mono">{x}</span></li>)}
                  </ul>
                </>
              )}
            </div>
          </Card>
          <Card label={t('library.folders')}>
            <div className="stack">
              <Status state="off" label={t('library.folders.notCompared')} />
              <Text>{t('library.folders.why')}</Text>
              {Object.keys(p.folders).length === 0 ? <Text>{t('library.folders.none')}</Text> : (
                <ul className="rows lib-paths" aria-label={t('library.folders')}>
                  {Object.entries(p.folders).map(([dir, f]) => (
                    <li key={dir}>
                      <span>
                        <strong className="mono">{dir}</strong>
                        <span className="sub">
                          {`${tf('library.folders.readFrom', { dir: f.read_from })} · ${f.readable_here ? t('library.folders.readable') : t('library.folders.unreadable')}`}
                        </span>
                      </span>
                      <span className="hist-num">{count(f.tracks, 'track')}</span>
                    </li>
                  ))}
                </ul>
              )}
              <Text variant="note">{rule(s, 'folders')}</Text>
            </div>
          </Card>
        </div>
      </section>

      {s.cache && (
        <Text variant="note">
          {tf('library.cache', { at: formatUtc(new Date(s.cache.built_at * 1000).toISOString()), s: s.cache.seconds })}
        </Text>
      )}
    </>
  );
}

/** Tracks by one value (codec, container, bitrate bucket): a list with share bars (aria-hidden) and a summary (L6). */
function Bars({ s, k, label, values, ordered = false, navigate }: {
  s: LibraryStats; k: string; label: string; values: Record<string, number>; ordered?: boolean;
} & Nav) {
  const items = Object.entries(values);
  const most = Math.max(1, ...items.map(([, n]) => n));
  const top = [...items].sort((a, b) => b[1] - a[1])[0];
  const inAny = items.reduce((a, [, n]) => a + n, 0);
  const summary = top && top[1] > 0
    ? tf('library.bars.summary', { top: valueLabel(top[0]), n: count(top[1], 'track'), pct: pct((100 * top[1]) / (s.tracks || 1)) })
    : t('library.bars.none');
  const outside = s.tracks - inAny;
  return (
    <Card label={label}>
      <div className="stack">
        <Text>{summary}</Text>
        <ul className="rows hist-top" aria-label={label}>
          {(ordered ? items : [...items].sort((a, b) => b[1] - a[1])).map(([v, n]) => (
            <li key={v}>
              <span className="hist-top-text">
                <strong>{valueLabel(v)}</strong>
                <span className="hist-bar lib-bar" aria-hidden="true"><span style={{ width: `${(100 * n) / most}%` }} /></span>
              </span>
              <TracksLink text={count(n, 'track')} n={n} query={qOf(s, k, v)} navigate={navigate} />
            </li>
          ))}
        </ul>
        {outside > 0 && <Text variant="note">{tf(k === 'bitrate_kbps' ? 'library.bars.noBitrate' : 'library.bars.rest', { n: count(outside, 'track') })}</Text>}
        <Text variant="note">{rule(s, k)}</Text>
      </div>
    </Card>
  );
}

/** Plex top artists (SUM(view_count) by artist_key), with share bars; each opens that artist's played tracks. */
function TopArtists({ s, navigate }: { s: LibraryStats } & Nav) {
  const top = s.top_artist_keys;
  const most = top[0]?.plays || 1;
  return (
    <div className="stack">
      {top.length === 0 ? <Text>{t('library.top.none')}</Text> : (
        <ol className="rows hist-top" aria-label={t('library.top')}>
          {top.map((a, i) => (
            <li key={a.artist_key}>
              <span className="hist-top-name">
                <span className="hist-rank">{i + 1}</span>
                <span className="hist-top-text">
                  <strong>{a.artist}</strong>
                  <span className="hist-bar lib-bar" aria-hidden="true"><span style={{ width: `${(100 * a.plays) / most}%` }} /></span>
                </span>
              </span>
              <TracksLink text={count(a.plays, 'play')} n={a.plays} query={qOf(s, 'top_artists', String(a.artist_key))}
                extra={{ name: a.artist }} navigate={navigate} />
            </li>
          ))}
        </ol>
      )}
      <Text variant="note">{`${rule(s, 'top_artists')}. ${t('library.top.note')}`}</Text>
    </div>
  );
}
