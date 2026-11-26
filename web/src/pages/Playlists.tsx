import type { CSSProperties } from 'react';
import { Band, Button, Card, ConditionChip, LineBullet, LineLever, Status, StationRow, Text } from '../components/kit';
import { t, tf, type StringKey } from '../copy/t';
import { useGet } from '../app/api';
import { trackHref } from '../app/entities';
import { formatUtc } from '../app/time';
import {
  PLAYLISTS_PATH, copiesApi, copiesHref, count, junctionApi, junctionHref, kindName, playlistApi,
  playlistHref, reachApi, reachRowsApi, reachRowsHref, rowsApi, serverName, sourceRowsHref, treeQuery,
  type Condition, type Copies, type CopyRows, type Group, type Line, type LineRows, type Lines, type Node,
  type PlaylistList, type PlaylistPage, type PlaylistRow, type Reach, type ReachLine, type ReachRows as ReachRowsData,
  type ReachTag, type Source, type Stop, type Switch, type TrackRow, type Which,
} from '../app/playlists';

/** T24: PLAYLISTS (P5), the Junction preview: jimbo-dj's saved playlists, their three switches and their lines,
 *  read-only. Every count opens its rows (W3). T25: what the lines pick now (the Junction: its drawing, list view and
 *  read-only levers), any tree at /library/junction?b=…, and how many tracks have a copy on each switch's server.
 *  T26: rooted to roaming, how far each line could reach if it followed its tag (a read-only slider, a preview). */

type Nav = { navigate: (href: string) => void };
type Operator = 'AND' | 'OR' | 'NOT';

function Num({ href, label, of, navigate }: { href: string; label: string; of?: string } & Nav) {
  return (
    <Button variant="quiet" href={href} onClick={() => navigate(href)}>
      {label}{of && <span className="visually-hidden">{`, ${of}`}</span>}
    </Button>
  );
}

function Failed({ why }: { why?: StringKey }) {
  return (
    <Card>
      <div className="stack">
        <Status state="needs" label={t('playlists.failed')} />
        <Text>{t(why ?? 'playlists.failedWhy')}</Text>
      </div>
    </Card>
  );
}

function Back({ href, label, navigate }: { href: string; label: string } & Nav) {
  return <div><Button variant="quiet" href={href} onClick={() => navigate(href)}>{label}</Button></div>;
}

// --- the switches -------------------------------------------------------------------------------------------

function switchState(s: Switch): { state: 'ready' | 'needs' | 'off'; label: string } {
  if (s.from === 'P6') return { state: 'off', label: t('playlists.switch.p6') };
  if (s.on && s.error) return { state: 'needs', label: t('playlists.switch.error') };
  return s.on ? { state: 'ready', label: t('playlists.switch.on') } : { state: 'off', label: t('playlists.switch.off') };
}

/** A switch's copies in words: "3 of 4 tracks", or that the server has no snapshot yet. */
function copiesText(c: Copies): string {
  return c.snapshot ? tf('playlists.copies.of', { n: c.count, of: count(c.of, 'track') }) : t('playlists.copies.noSnapshot');
}

/** The three switches in one line (the list): each server with its state in words (C6) and its copies (T25). */
function SwitchLine({ switches, slug, navigate }: { switches: Switch[]; slug: string } & Nav) {
  return (
    <span className="pl-switches">
      {switches.map((s) => (
        <span key={s.server} className="pl-switch">
          <Status state={switchState(s).state} label={tf('playlists.switch.summary', { name: serverName(s.server), state: switchState(s).label })} />
          {s.copies && s.copies.snapshot && (
            <Num href={copiesHref(slug, s.server)} label={copiesText(s.copies)}
              of={tf('playlists.copies.on', { name: serverName(s.server) })} navigate={navigate} />
          )}
        </span>
      ))}
    </span>
  );
}

const reasonName = (r: string) => t(`playlists.reason.${r}` as StringKey) ?? r;

/** One switch's copies on the playlist's page: how many have a copy (their rows) and which don't, and why. */
function CopiesLine({ s, slug, navigate }: { s: Switch; slug: string } & Nav) {
  const c = s.copies;
  if (!c) return null;
  if (!c.snapshot) return <span className="sub">{t('playlists.copies.noSnapshotWhy')}</span>;
  const why = Object.entries(c.reasons).map(([r, n]) => `${reasonName(r)} ${n}`).join(', ');
  return (
    <span className="pl-copies">
      <Num href={copiesHref(slug, s.server)} label={tf('playlists.copies.have', { n: c.count, of: count(c.of, 'track') })}
        of={tf('playlists.copies.on', { name: serverName(s.server) })} navigate={navigate} />
      {c.missing > 0 && (
        <Num href={copiesHref(slug, s.server, true)} label={tf('playlists.copies.missing', { n: count(c.missing, 'track'), why })}
          of={tf('playlists.copies.on', { name: serverName(s.server) })} navigate={navigate} />
      )}
    </span>
  );
}

/** The three switches with where each comes from (a playlist's page). */
function SwitchCard({ switches, slug, navigate }: { switches: Switch[]; slug: string } & Nav) {
  return (
    <Card label={t('playlists.switches')}>
      <div className="stack">
        <ul className="rows">
          {switches.map((s) => {
            const st = switchState(s);
            const sub = s.from === 'P6' ? s.rule
              : [t('playlists.switch.jimbodj'), s.pushed_at ? tf('playlists.switch.pushed', { at: formatUtc(new Date(s.pushed_at * 1000).toISOString()) })
                : t('playlists.switch.notPushed'), s.error].filter(Boolean).join(' · ');
            return (
              <li key={s.server}>
                <span>
                  <strong>{serverName(s.server)}</strong><span className="sub">{sub}</span>
                  <CopiesLine s={s} slug={slug} navigate={navigate} />
                </span>
                <Status state={st.state} label={st.label} />
              </li>
            );
          })}
        </ul>
        <Text variant="note">{t('playlists.switchesNote')}</Text>
        {switches.some((s) => s.copies) && <Text variant="note">{t('playlists.copies.note')}</Text>}
      </div>
    </Card>
  );
}

// --- the list -----------------------------------------------------------------------------------------------

export function Playlists({ navigate }: Nav) {
  const load = useGet<PlaylistList>('/api/playlists');
  return (
    <>
      <Band module="L">{t('playlists.sub')}</Band>
      <div className="page stack history playlists">
        <Back href="/library" label={t('library.rows.back')} navigate={navigate} />
        <Text variant="title">{t('playlists.title')}</Text>
        <Text>{t('playlists.intro')}</Text>
        {load.state === 'loading' && <Text>{t('playlists.loading')}</Text>}
        {load.state === 'failed' && <Failed why={load.status === 404 ? 'playlists.none' : undefined} />}
        {load.state === 'ok' && <ListBody p={load.data} navigate={navigate} />}
      </div>
    </>
  );
}

function ListBody({ p, navigate }: { p: PlaylistList } & Nav) {
  const head = [
    { k: 'count', label: t('playlists.saved'), text: count(p.count, 'playlist') },
    { k: 'with_lines', label: t('playlists.withLines'), text: count(p.with_lines, 'playlist') },
    { k: 'on', label: t('playlists.onPlex'), text: count(p.on.plex, 'playlist') },
    { k: 'stale', label: t('playlists.stale'), text: count(p.stale, 'playlist') },
  ];
  return (
    <>
      <ul className="rows" aria-label={t('playlists.saved')}>
        {head.map((h) => (
          <li key={h.k}>
            <span><strong>{h.label}</strong><span className="sub">{`${t('playlists.rule')}: ${p.rules[h.k] ?? ''}`}</span></span>
            <span className="hist-num">{h.text}</span>
          </li>
        ))}
      </ul>
      {p.kinds.map((k) => (
        <section key={k.kind} aria-labelledby={`pl-${k.kind}`}>
          <Text variant="label" id={`pl-${k.kind}`}>{`${kindName(k.kind)} · ${count(k.count, 'playlist')}`}</Text>
          <ul className="rows pl-list">
            {k.rows.map((r) => <ListRow key={r.id} r={r} navigate={navigate} />)}
          </ul>
        </section>
      ))}
    </>
  );
}

function ListRow({ r, navigate }: { r: PlaylistRow } & Nav) {
  const sub = [tf('playlists.tracksIn', { n: count(r.tracks, 'track') }), r.lines ? count(r.lines, 'line') : t('playlists.noLines'),
    r.stale && t('playlists.staleNote')].filter(Boolean).join(' · ');
  return (
    <li>
      <span className="pl-name">
        <Num href={playlistHref(r.slug)} label={r.name} navigate={navigate} />
        <span className="sub">{sub}</span>
      </span>
      <SwitchLine switches={r.switches} slug={r.slug} navigate={navigate} />
    </li>
  );
}

/** The card on LIBRARY's overview. */
export function PlaylistsCard({ navigate }: Nav) {
  const load = useGet<PlaylistList>('/api/playlists');
  if (load.state !== 'ok') return null;
  return (
    <Card label={t('playlists.card')}>
      <div className="stack">
        <Text>{tf('playlists.cardBody', { n: count(load.data.count, 'playlist'), m: load.data.with_lines })}</Text>
        <div><Button variant="secondary" href={PLAYLISTS_PATH} onClick={() => navigate(PLAYLISTS_PATH)}>{t('playlists.open')}</Button></div>
      </div>
    </Card>
  );
}

// --- one playlist -------------------------------------------------------------------------------------------

export function Playlist({ slug, navigate }: { slug: string } & Nav) {
  const load = useGet<PlaylistPage>(playlistApi(slug));
  return (
    <>
      <Band module="L">{t('playlists.sub')}</Band>
      <div className="page stack history playlists">
        <Back href={PLAYLISTS_PATH} label={t('playlists.back')} navigate={navigate} />
        {load.state === 'loading' && <Text>{t('playlists.loading')}</Text>}
        {load.state === 'failed' && <Failed why={load.status === 404 ? 'playlists.notFound' : undefined} />}
        {load.state === 'ok' && <PlaylistBody p={load.data} navigate={navigate} />}
      </div>
    </>
  );
}

const madeBy = (m: string | null) => t(`playlists.madeBy.${m && ['rules', 'filter', 'mix', 'cluster', 'radio'].includes(m) ? m : 'other'}` as StringKey);

function PlaylistBody({ p, navigate }: { p: PlaylistPage } & Nav) {
  const r = p.playlist;
  return (
    <>
      <Text variant="title">{r.name}</Text>
      <Text variant="note">{[kindName(r.kind), `${t('playlists.from')}: ${madeBy(r.made_by)}`, r.stale && t('playlists.staleNote')].filter(Boolean).join(' · ')}</Text>
      {r.summary && <Text>{r.summary}</Text>}
      <div className="hist-grid">
        <SwitchCard switches={r.switches} slug={r.slug} navigate={navigate} />
      </div>
      {p.lines_error && <Card><Status state="needs" label={tf('playlists.linesError', { e: p.lines_error })} /></Card>}
      {p.lines && <div><Button variant="secondary" href={junctionHref(p.lines.query)} onClick={() => navigate(junctionHref(p.lines!.query))}>{t('junction.open')}</Button></div>}
      {p.lines && <JunctionView l={p.lines} src={{ ref: r.slug }} navigate={navigate} />}
      {p.lines && <ReachView tree={p.lines.query} slug={r.slug} navigate={navigate} />}
      {p.lines && <LinesView l={p.lines} src={{ ref: r.slug }} navigate={navigate} />}
      <Stored p={p} navigate={navigate} />
    </>
  );
}

function LinesView({ l, src, navigate }: { l: Lines; src: Source } & Nav) {
  return (
    <section aria-labelledby="pl-lines" className="stack">
      <Text variant="label" id="pl-lines">{t('playlists.lines')}</Text>
      <Text>{tf('playlists.linesSummary', { lines: count(l.lines.length, 'line'), n: l.n, total: count(l.total, 'track'), library: count(l.library, 'track') })}</Text>
      <Text variant="note">{`${t('playlists.rule')}: ${l.rules.count}. ${t('playlists.linesNote')}`}</Text>
      <div className="hist-grid">
        {l.lines.map((x) => <LineCard key={x.id} x={x} n={l.n} src={src} navigate={navigate} />)}
      </div>
    </section>
  );
}

function LineCard({ x, n, src, navigate }: { x: Line; n: number; src: Source } & Nav) {
  return (
    <Card label={x.label ? `${tf('playlists.line', { id: x.id })} · ${x.label}` : tf('playlists.line', { id: x.id })}>
      <div className="stack">
        <Text>{x.words}</Text>
        <ul className="rows">
          <li>
            <span><strong>{t('playlists.lineMatches')}</strong><span className="sub">{tf('playlists.lineShare', { n: x.share, of: n })}</span></span>
            {x.count > 0 ? <Num href={sourceRowsHref(src, x.id)} label={count(x.count, 'track')} of={x.words} navigate={navigate} />
              : <span className="hist-num">{count(0, 'track')}</span>}
          </li>
        </ul>
        <Text variant="label">{t('playlists.conditions')}</Text>
        <Tree node={x.match} src={src} line={x.id} navigate={navigate} />
      </div>
    </Card>
  );
}

const OPS: { part: 'all' | 'any' | 'not'; op: Operator; label: StringKey }[] = [
  { part: 'all', op: 'AND', label: 'playlists.op.all' }, { part: 'any', op: 'OR', label: 'playlists.op.any' },
  { part: 'not', op: 'NOT', label: 'playlists.op.not' },
];

/** A line's conditions: each group's AND, OR and NOT parts, each condition a chip with its count (nesting shown by
 *  indent; a screen reader hears each part's operator in words). */
function Tree({ node, src, line, navigate }: { node: Node; src: Source; line: string } & Nav) {
  if (node.type === 'condition') return <ul className="pl-tree"><Leaf c={node} op="AND" src={src} line={line} navigate={navigate} /></ul>;
  return <GroupView g={node} src={src} line={line} navigate={navigate} />;
}

function GroupView({ g, src, line, navigate }: { g: Group; src: Source; line: string } & Nav) {
  return (
    <ul className="pl-tree">
      {OPS.filter((o) => g[o.part]?.length).map((o) => (
        <li key={o.part} className="pl-part">
          <span className="visually-hidden">{t(o.label)}</span>
          <ul className="pl-tree">
            {g[o.part]!.map((x) => x.type === 'condition'
              ? <Leaf key={x.path} c={x} op={o.op} src={src} line={line} navigate={navigate} />
              : (
                <li key={x.path} className="pl-group">
                  <span className="pl-row">
                    <ConditionChip op={o.op}>{`${t('playlists.group')}: ${x.words}`}</ConditionChip>
                    <CountLink n={x.count} src={src} line={line} path={x.path} of={x.words} navigate={navigate} />
                  </span>
                  <GroupView g={x} src={src} line={line} navigate={navigate} />
                </li>
              ))}
          </ul>
        </li>
      ))}
    </ul>
  );
}

function Leaf({ c, op, src, line, navigate }: { c: Condition; op: Operator; src: Source; line: string } & Nav) {
  return (
    <li className="pl-row">
      <ConditionChip op={op}>{c.text}</ConditionChip>
      <CountLink n={c.count} src={src} line={line} path={c.path} of={c.text} navigate={navigate} />
    </li>
  );
}

function CountLink({ n, src, line, path, of, navigate }: { n: number; src: Source; line: string; path: string; of: string } & Nav) {
  if (n === 0) return <span className="hist-num">{count(0, 'track')}</span>;
  return <Num href={sourceRowsHref(src, line, 'count', path)} label={count(n, 'track')} of={of} navigate={navigate} />;
}

function Stored({ p, navigate }: { p: PlaylistPage } & Nav) {
  const s = p.stored;
  return (
    <section aria-labelledby="pl-stored" className="stack">
      <Text variant="label" id="pl-stored">{`${t('playlists.stored')} · ${count(s.count, 'track')}`}</Text>
      <Text variant="note">{`${tf('playlists.storedNote', { live: count(s.live, 'track') })}${s.count > s.rows.length ? ` ${tf('playlists.storedMore', { n: s.rows.length })}` : ''}`}</Text>
      <TrackList rows={s.rows} why={(i) => tf('playlists.storedWhy', { n: s.offset + i + 1 })} navigate={navigate} />
    </section>
  );
}

function TrackList({ rows, why, navigate }: { rows: TrackRow[]; why: (i: number) => string } & Nav) {
  return (
    <div className="pl-tracks">
      {rows.map((r, i) => (
        <StationRow key={`${r.rating_key}-${i}`} position={i + 1} module="L" title={r.title} artist={r.artist}
          why={r.live ? why(i) : `${why(i)} ${t('playlists.removed')}.`}
          href={r.live ? trackHref(r.rating_key) : undefined} onNavigate={navigate} />
      ))}
    </div>
  );
}

// --- the Junction (T25) -------------------------------------------------------------------------------------

/** jimbo-dj's cap on tracks by one artist (rules.clean: 1 to 20); the cap's lever shows it out of that. */
const MAX_PER_ARTIST = 20;

const lineName = (x: Line) => (x.label ? `${tf('playlists.line', { id: x.id })} · ${x.label}` : tf('playlists.line', { id: x.id }));

/** What the lines pick now: the summary, the drawing (lines meeting in one) with its list view and a summary for
 *  screen readers (L6), read-only levers for each share and the cap, and the picked tracks with their line (B3). */
function JunctionView({ l, src, navigate }: { l: Lines; src: Source } & Nav) {
  const p = l.picked;
  if (!p) return null;
  const href = (line: string, which: Which) => sourceRowsHref(src, line, which);
  const nums: { k: string; label: string; text: string; which: Which; n: number }[] = [
    { k: 'picked', label: t('junction.picked'), text: tf('junction.pickedOf', { n: count(p.count, 'track'), of: l.n }), which: 'picked', n: p.count },
    { k: 'minutes', label: t('junction.minutes'), text: count(p.minutes, 'minute'), which: 'picked', n: p.count },
    { k: 'total', label: t('junction.total'), text: count(l.total, 'track'), which: 'total', n: l.total },
  ];
  const bans = l.bans ?? { songs: 0, artists: 0, styles: 0 };
  return (
    <section aria-labelledby="jn-head" className="stack junction">
      <Text variant="heading" id="jn-head">{t('junction.title')}</Text>
      {l.summary && <Text>{l.summary}</Text>}
      <ul className="rows" aria-label={t('junction.numbers')}>
        {nums.map((h) => (
          <li key={h.k}>
            <span><strong>{h.label}</strong><span className="sub">{`${t('playlists.rule')}: ${l.rules[h.k] ?? ''}`}</span></span>
            {h.n > 0 ? <Num href={href('', h.which)} label={h.text} navigate={navigate} /> : <span className="hist-num">{h.text}</span>}
          </li>
        ))}
        <li>
          <span><strong>{t('junction.bans')}</strong><span className="sub">{`${t('playlists.rule')}: ${l.rules.banned ?? ''}`}</span></span>
          <span className="hist-num">{tf('junction.bansCount', { songs: count(bans.songs, 'song'), artists: count(bans.artists, 'artist'), styles: count(bans.styles, 'style') })}</span>
        </li>
      </ul>

      <section className="map" aria-labelledby="jn-drawing">
        <Text variant="label" id="jn-drawing">{t('junction.drawing')}</Text>
        <p className="visually-hidden">
          {tf('junction.summary', {
            lines: count(l.lines.length, 'line'), n: count(p.count, 'track'), of: l.n,
            each: l.lines.map((x) => tf('junction.summaryLine', { line: lineName(x), got: count(x.got ?? 0, 'track'), share: x.share })).join('; '),
          })}
        </p>
        <div className="jn-drawing" aria-hidden="true">
          <div className="jn-lines line-l">
            {l.lines.map((x, i) => (
              <div key={x.id} className={`jn-line line-l${x.got ? '' : ' is-off'}`} style={{ '--i': i } as CSSProperties}>
                <span className="jn-name">{x.label ?? tf('playlists.line', { id: x.id })}</span>
                <span className="jn-track"><span style={{ width: `${Math.round(100 * (x.got ?? 0) / Math.max(l.n, 1))}%` }} /></span>
              </div>
            ))}
          </div>
          <div className="jn-meet line-l">
            <LineBullet module="L" size={36} decorative />
            <span className="jn-name">{tf('junction.meet', { n: count(p.count, 'track') })}</span>
          </div>
        </div>
        <Text variant="note">{t('junction.drawingNote')}</Text>
      </section>

      <section className="stack" aria-labelledby="jn-list">
        <Text variant="label" id="jn-list">{t('junction.list')}</Text>
        <ul className="lines jn-levers">
          {l.lines.map((x) => (
            <li key={x.id} className="stack">
              <LineLever module="L" title={lineName(x)} detail={x.words} share={(100 * x.share) / Math.max(l.n, 1)} count={x.share} />
              <ul className="rows" aria-label={tf('junction.lineNumbers', { line: lineName(x) })}>
                {([['count', 'junction.matches'], ['got', 'junction.got'], ['available', 'junction.available'], ['banned', 'junction.banned']] as const).map(([w, label]) => {
                  const n = (w === 'count' ? x.count : x[w]) ?? 0;
                  return (
                    <li key={w}>
                      <span><strong>{t(label)}</strong><span className="sub">{l.rules[w] ?? ''}</span></span>
                      {n > 0 ? <Num href={href(x.id, w)} label={count(n, 'track')} of={`${t(label)}, ${lineName(x)}`} navigate={navigate} />
                        : <span className="hist-num">{count(0, 'track')}</span>}
                    </li>
                  );
                })}
              </ul>
            </li>
          ))}
          <li className="stack">
            <LineLever module="L" title={t('junction.cap')} detail={tf('junction.capDetail', { n: l.per_artist, max: MAX_PER_ARTIST })}
              share={(100 * l.per_artist) / MAX_PER_ARTIST} count={l.per_artist} />
            <Text variant="note">{l.shuffle ? tf('junction.shuffleOn', { n: l.shuffle }) : t('junction.shuffleOff')}</Text>
          </li>
        </ul>
        <Text variant="note">{t('junction.leversNote')}</Text>
      </section>

      <section className="stack" aria-labelledby="jn-picked">
        <Text variant="label" id="jn-picked">{`${t('junction.pickedTracks')} · ${count(p.count, 'track')}`}</Text>
        <Text variant="note">{p.order === 'pick' ? t('junction.pickOrder') : t('junction.flowOrder')}</Text>
        <TrackList rows={p.tracks}
          why={(i) => tf('junction.why', { line: p.tracks[i].line_name ? `${tf('playlists.line', { id: p.tracks[i].line })} (${p.tracks[i].line_name})` : tf('playlists.line', { id: p.tracks[i].line }) })}
          navigate={navigate} />
      </section>
      {l.read_only && <Text variant="note">{l.read_only}</Text>}
    </section>
  );
}

/** Any tree in jimbo-dj's URL form: /library/junction?b=…&n=…&per=…&shuffle=…. */
export function Junction({ query, navigate }: { query: string } & Nav) {
  const tree = treeQuery(query);
  return (
    <>
      <Band module="L">{t('junction.sub')}</Band>
      <div className="page stack history playlists">
        <Back href={PLAYLISTS_PATH} label={t('playlists.back')} navigate={navigate} />
        <Text variant="title">{t('junction.pageTitle')}</Text>
        <Text>{t('junction.intro')}</Text>
        {tree.includes('b=') ? <JunctionLoad tree={tree} navigate={navigate} /> : <Card><Text>{t('junction.empty')}</Text></Card>}
      </div>
    </>
  );
}

function JunctionLoad({ tree, navigate }: { tree: string } & Nav) {
  const load = useGet<Lines>(junctionApi(tree));
  if (load.state === 'loading') return <Text>{t('junction.loading')}</Text>;
  if (load.state === 'failed') return <Failed why={load.status === 400 ? 'junction.unreadable' : undefined} />;
  return (
    <>
      <Text variant="note">{`${t('junction.name')}: ${load.data.name}`}</Text>
      <JunctionView l={load.data} src={{ tree }} navigate={navigate} />
      <ReachView tree={tree} navigate={navigate} />
      <LinesView l={load.data} src={{ tree }} navigate={navigate} />
    </>
  );
}

// --- rooted to roaming (T26) -------------------------------------------------------------------------------

const stopName = (s: Stop) => t(`reach.stop.${s}` as StringKey);
const reachLineName = (x: ReachLine) => (x.label ? `${tf('playlists.line', { id: x.id })} · ${x.label}` : tf('playlists.line', { id: x.id }));

/** A tag a stop takes in, in words: its name, how it came in, and whether any album carries it yet. */
function tagText(x: ReachTag): string {
  const how = x.via === 'ladder' ? t('reach.via.ladder')
    : x.via === 'movement' ? tf('reach.via.movement', { name: x.movement_name ?? x.movement ?? '' })
      : x.via === 'neighbour' ? tf('reach.via.neighbour', { of: x.of ?? '' }) : '';
  return [x.name, how && `(${how}${x.in_use ? '' : `, ${t('reach.notInUse')}`})`].filter(Boolean).join(' ');
}

/** How far each line could reach if it followed its tag: rooted (the tag alone), its ladder, its movement and its
 *  neighbours on the map. Per line: a read-only slider drawn as four stops with the line at rooted (jimbo-dj's lines
 *  don't follow tags), a summary for screen readers and the list view with every number opening its rows (L6, W3). */
function ReachView({ tree, slug, navigate }: { tree: string; slug?: string } & Nav) {
  const load = useGet<Reach>(reachApi(tree));
  return (
    <section aria-labelledby="rr-head" className="stack reach">
      <Text variant="heading" id="rr-head">{t('reach.title')}</Text>
      <Text>{t('reach.intro')}</Text>
      {load.state === 'loading' && <Text>{t('reach.loading')}</Text>}
      {load.state === 'failed' && <Failed />}
      {load.state === 'ok' && load.data.following === 0 && <Card><Text>{t('reach.none')}</Text></Card>}
      {load.state === 'ok' && load.data.lines.filter((x) => x.stops.length).map((x) => (
        <ReachLineView key={x.id} x={x} r={load.data} tree={tree} slug={slug} navigate={navigate} />
      ))}
      {load.state === 'ok' && load.data.following > 0 && <Text variant="note">{t('reach.note')}</Text>}
    </section>
  );
}

function ReachLineView({ x, r, tree, slug, navigate }: { x: ReachLine; r: Reach; tree: string; slug?: string } & Nav) {
  const name = reachLineName(x);
  const named = [...new Set(x.follows.flatMap((f) => f.movements.map((m) => m.name)))];
  const href = (stop: Stop, which: 'count' | 'added') => reachRowsHref(tree, x.id, stop, which, slug);
  return (
    <Card label={name}>
      <div className="stack">
        <Text>{tf('reach.follows', { tags: x.follows.map((f) => f.name).join(', ') })}</Text>
        <Text variant="note">{named.length ? tf('reach.namedBy', { movements: named.join(', ') }) : t('reach.noMovement')}</Text>

        <div className="map">
          <p className="visually-hidden">
            {tf('reach.summary', {
              line: name, rooted: count(x.stops[0].count, 'track'),
              each: x.stops.map((s) => tf('reach.summaryStop', { stop: stopName(s.stop), n: count(s.count, 'track'), added: count(s.added, 'track') })).join('; '),
            })}
          </p>
          <div className="rr-slider line-l" aria-hidden="true">
            <span className="rr-rail" />
            <ol className="rr-stops">
              {x.stops.map((s, i) => (
                <li key={s.stop} className={`rr-stop${i === 0 ? ' is-here' : ''}`}>
                  {i === 0 ? <LineBullet module="L" size={28} decorative /> : <span className="rr-dot" />}
                  <span className="rr-name">{stopName(s.stop)}</span>
                  <span className="rr-num">{count(s.count, 'track')}</span>
                  {i === 0 && <span className="rr-here">{t('reach.here')}</span>}
                </li>
              ))}
            </ol>
          </div>
        </div>

        <Text variant="label">{tf('reach.list', { line: name })}</Text>
        <ul className="lines rr-list">
          {x.stops.map((s) => (
            <li key={s.stop} className="stack">
              <ul className="rows" aria-label={`${stopName(s.stop)}, ${name}`}>
                <li>
                  <span><strong>{stopName(s.stop)}</strong><span className="sub">{`${r.rules[s.stop] ?? ''} · ${tf('reach.tagsAt', { n: count(s.tags, 'tag') })}`}</span></span>
                  {s.count > 0 ? <Num href={href(s.stop, 'count')} label={count(s.count, 'track')} of={`${t('reach.matches')}, ${stopName(s.stop)}, ${name}`} navigate={navigate} />
                    : <span className="hist-num">{count(0, 'track')}</span>}
                </li>
                {s.stop !== 'rooted' && (
                  <li>
                    <span><strong>{t('reach.added')}</strong><span className="sub">{r.rules.added ?? ''}</span></span>
                    {s.added > 0 ? <Num href={href(s.stop, 'added')} label={count(s.added, 'track')} of={`${t('reach.added')}, ${stopName(s.stop)}, ${name}`} navigate={navigate} />
                      : <span className="hist-num">{count(0, 'track')}</span>}
                  </li>
                )}
              </ul>
              <Text variant="note">{s.new_tags.length ? tf('reach.takesIn', { tags: s.new_tags.map(tagText).join(', ') }) : t('reach.takesNothing')}</Text>
            </li>
          ))}
        </ul>
      </div>
    </Card>
  );
}

/** The tracks behind a stop's number: all it matches, or only those the rooted line doesn't. */
export function ReachRows({ query, navigate }: { query: string } & Nav) {
  const load = useGet<ReachRowsData>(reachRowsApi(query));
  const q = new URLSearchParams(query);
  const ref = q.get('ref');
  const added = q.get('which') === 'added';
  return (
    <>
      <Band module="L">{t('playlists.rows.sub')}</Band>
      <div className="page stack history playlists">
        <Back href={ref ? playlistHref(ref) : junctionHref(query)} label={ref ? t('playlists.rows.back') : t('junction.back')} navigate={navigate} />
        <Text variant="title">{t(added ? 'reach.rows.titleAdded' : 'reach.rows.title')}</Text>
        {load.state === 'loading' && <Text>{t('rows.loading')}</Text>}
        {load.state === 'failed' && <Failed why={load.status === 404 ? 'playlists.notFound' : undefined} />}
        {load.state === 'ok' && (
          <>
            <Text>{[tf('playlists.line', { id: load.data.line }), load.data.words, stopName(load.data.stop), count(load.data.count, 'track')].join(' · ')}</Text>
            <Text variant="note">{`${t('playlists.rule')}: ${load.data.rule}.`}</Text>
            <TrackList rows={load.data.rows} why={() => tf('reach.rows.why', { stop: stopName(load.data.stop) })} navigate={navigate} />
          </>
        )}
      </div>
    </>
  );
}

// --- the rows behind a count --------------------------------------------------------------------------------

const ROW_TITLES: Record<Which, StringKey> = {
  count: 'playlists.rows.title', got: 'junction.rows.got', available: 'junction.rows.available', banned: 'junction.rows.banned',
  picked: 'junction.rows.picked', total: 'junction.rows.total',
};

export function PlaylistRows({ query, navigate }: { query: string } & Nav) {
  const load = useGet<LineRows>(rowsApi(query));
  const q = new URLSearchParams(query);
  const ref = q.get('ref');
  const which = (q.get('which') ?? 'count') as Which;
  const back = ref !== null ? playlistHref(ref) : junctionHref(query);
  return (
    <>
      <Band module="L">{t('playlists.rows.sub')}</Band>
      <div className="page stack history playlists">
        <Back href={back} label={ref !== null ? t('playlists.rows.back') : t('junction.back')} navigate={navigate} />
        <Text variant="title">{t(ROW_TITLES[which] ?? 'playlists.rows.title')}</Text>
        {load.state === 'loading' && <Text>{t('rows.loading')}</Text>}
        {load.state === 'failed' && <Failed why={load.status === 404 ? 'playlists.notFound' : undefined} />}
        {load.state === 'ok' && (
          <>
            <Text>{[load.data.line && tf('playlists.line', { id: load.data.line }), load.data.words, count(load.data.count, 'track')].filter(Boolean).join(' · ')}</Text>
            <Text variant="note">{which === 'count' ? t('playlists.rows.note') : `${t('playlists.rule')}: ${load.data.rule}.`}</Text>
            <TrackList rows={load.data.rows}
              why={(i) => {
                const line = load.data.rows[i].line;
                if (line) return tf('junction.why', { line: tf('playlists.line', { id: line }) });
                return load.data.words ? tf('playlists.rows.why', { words: load.data.words }) : load.data.rule;
              }}
              navigate={navigate} />
          </>
        )}
      </div>
    </>
  );
}

/** The stored tracks behind a switch's copies: each with whether that server has a copy and, if not, why. */
export function PlaylistCopies({ query, navigate }: { query: string } & Nav) {
  const load = useGet<CopyRows>(copiesApi(query));
  const q = new URLSearchParams(query);
  const ref = q.get('ref') ?? '';
  return (
    <>
      <Band module="L">{t('playlists.rows.sub')}</Band>
      <div className="page stack history playlists">
        <Back href={playlistHref(ref)} label={t('playlists.rows.back')} navigate={navigate} />
        <Text variant="title">{t(q.get('missing') === 'true' ? 'playlists.copies.titleMissing' : 'playlists.copies.title')}</Text>
        {load.state === 'loading' && <Text>{t('rows.loading')}</Text>}
        {load.state === 'failed' && <Failed why={load.status === 404 ? 'playlists.notFound' : undefined} />}
        {load.state === 'ok' && (
          <>
            <Text>{`${serverName(load.data.server)} · ${count(load.data.count, 'track')}`}</Text>
            <Text variant="note">{`${t('playlists.rule')}: ${load.data.rule}.`}</Text>
            <TrackList rows={load.data.rows}
              why={(i) => {
                const r = load.data.rows[i];
                return r.copy ? tf('playlists.copies.yes', { name: serverName(load.data.server) })
                  : tf('playlists.copies.no', { name: serverName(load.data.server), why: r.reason ? (load.data.reasons[r.reason] ?? r.reason) : '' });
              }}
              navigate={navigate} />
          </>
        )}
      </div>
    </>
  );
}
