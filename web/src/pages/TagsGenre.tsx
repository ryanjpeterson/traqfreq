import { useState, type CSSProperties, type ReactNode } from 'react';
import { Band, Button, Card, LineBullet, NavItem, Status, StationRow, Text } from '../components/kit';
import { t, tf, tMaybe, type StringKey } from '../copy/t';
import { useGet } from '../app/api';
import { playsHref, trackHref } from '../app/entities';
import { count, fmt } from '../app/history';
import {
  MAP_API, TAGS_GATE_API, TAGS_MAP, TAGS_PATH, TAGS_PROPOSALS, albumsHref, artistsHref, listHref, params, proposalsHref,
  tagApi, tagHref, tagTracksApi, tagTracksHref,
  type GateAudit, type GateLadder, type GateTracks, type GenreMapData, type MapLine, type Movement, type Station,
  type TagPageData, type TagTracksPage, type TagsGate,
} from '../app/tags';

/** T23: a page per tag, the genre map with its movements, the tracks behind a tag, and the P4 gate card. */

type Nav = { navigate: (href: string) => void };

/** A link to the rows behind a number (W3). A zero is shown without a link: it has no rows. */
function Num({ href, label, of, n, navigate }: { href: string; label: string; of?: string; n?: number } & Nav) {
  if (n === 0) return <span>{label}</span>;
  return (
    <Button variant="quiet" href={href} onClick={() => navigate(href)}>
      {label}{of && <span className="visually-hidden">{`, ${of}`}</span>}
    </Button>
  );
}

function Back({ href = TAGS_PATH, label, navigate }: { href?: string; label?: string } & Nav) {
  return <div><Button variant="quiet" href={href} onClick={() => navigate(href)}>{label ?? t('tags.back')}</Button></div>;
}

function Failed({ why }: { why?: string }) {
  return (
    <Card>
      <div className="stack">
        <Status state="needs" label={t('tags.failed')} />
        <Text>{why ?? t('tags.failedWhy')}</Text>
      </div>
    </Card>
  );
}

function TagLink({ k, name, navigate }: { k: string; name: string } & Nav) {
  const href = tagHref(k);
  return <Button variant="quiet" href={href} onClick={() => navigate(href)}>{name}</Button>;
}

// --- a tag's page -----------------------------------------------------------------------------------------

/** One tag (T23): where it sits, how it got its name, its numbers, plays and sound, and its movements. */
export function TagPage({ tagKey, navigate }: { tagKey: string } & Nav) {
  const load = useGet<TagPageData>(tagApi(tagKey));
  return (
    <>
      <Band module="T">{t('tags.page.sub')}</Band>
      <div className="page stack history tags">
        <div className="hist-actions">
          <Back navigate={navigate} />
          <Back href={TAGS_MAP} label={t('tags.map.back')} navigate={navigate} />
        </div>
        {load.state === 'loading' && <Text>{t('rows.loading')}</Text>}
        {load.state === 'failed' && <Failed why={t('tags.page.notFound')} />}
        {load.state === 'ok' && <TagBody d={load.data} navigate={navigate} />}
      </div>
    </>
  );
}

function broadLine(d: TagPageData): string {
  if (d.junk) return tf('tags.page.junk', { rule: d.junk.label });
  if (!d.broad) return t('tags.page.alone');
  if (d.root) return t('tags.page.root');
  const r = d.broad_rule;
  if (r?.how === 'override') return tf('tags.page.override', { b: r.broad, m: r.match ?? '' });
  if (r?.how === 'family') return tf('tags.page.family', { b: r.broad, f: r.family ?? '', m: r.match ?? '' });
  return tf('tags.page.broad', { b: d.broad });
}

function TagBody({ d, navigate }: { d: TagPageData } & Nav) {
  const n = d.numbers;
  const name = d.name;
  return (
    <>
      <Text variant="title">{name}</Text>
      {d.junk && (
        <Card label={t('tags.page.junkLabel')}>
          <div className="stack">
            <Status state="off" label={d.junk.label} />
            {d.junk.why && <Text>{d.junk.why}</Text>}
          </div>
        </Card>
      )}

      <Card label={t('tags.page.where')}>
        <div className="stack">
          <Text>{broadLine(d)}</Text>
          {d.ladders.length > 0 && (
            <>
              <Text variant="label">{tf('tags.page.ladders', { n: count(d.ladders.length, 'ladder') })}</Text>
              <ul className="rows" aria-label={t('tags.page.laddersList')}>
                {d.ladders.map((path) => (
                  <li key={path.map((x) => x.key).join('|')}>
                    <ol className="gm-ladder line-t" aria-label={tf('tags.page.ladder', { s: path.map((x) => x.name).join(', ') })}>
                      {path.map((x) => (
                        <li key={x.key}>{x.key === d.key ? <strong>{x.name}</strong> : <TagLink k={x.key} name={x.name} navigate={navigate} />}</li>
                      ))}
                    </ol>
                  </li>
                ))}
              </ul>
            </>
          )}
          {d.rung !== null && <Text variant="note">{`${tf('tags.why.rung', { n: d.rung })}. ${d.rules.ladders}.`}</Text>}
          {d.children.length > 0 && (
            <>
              <Text variant="label">{tf('tags.page.children', { n: count(d.children.length, 'tag') })}</Text>
              <ul className="rows" aria-label={t('tags.page.childrenList')}>
                {d.children.map((c) => (
                  <li key={c.key}>
                    <span>
                      <TagLink k={c.key} name={c.name} navigate={navigate} />
                      {c.parents > 1 && <span className="sub">{t('tags.page.shared')}</span>}
                    </span>
                    <Num href={albumsHref(c.key, c.children ? 'under' : 'carries')} n={c.under}
                      label={count(c.under, 'album')} of={c.name} navigate={navigate} />
                  </li>
                ))}
              </ul>
            </>
          )}
          {d.other_heads.length > 0 && <Text variant="note">{tf('tags.why.other', { s: d.other_heads.join(', ') })}</Text>}
        </div>
      </Card>

      <Card label={t('tags.page.numbers')}>
        <ul className="rows" aria-label={t('tags.page.numbers')}>
          <NumLine label={tf('tags.num.albums', { n: count(n.albums, 'album') })} rule={t('tags.page.rule.carries')}
            href={albumsHref(d.key)} n={n.albums} of={name} navigate={navigate} />
          {d.below > 0 && <NumLine label={tf('tags.num.under', { n: count(n.under, 'album') })} rule={t('tags.page.rule.under')}
            href={albumsHref(d.key, 'under')} n={n.under} of={name} navigate={navigate} />}
          {n.missing !== null && <NumLine label={tf('tags.num.missing', { n: count(n.missing, 'album') })} rule={t('tags.page.rule.missing')}
            href={albumsHref(d.key, 'missing')} n={n.missing} of={name} navigate={navigate} />}
          <NumLine label={tf('tags.num.artists', { n: count(n.artists, 'artist') })} rule={t('tags.page.rule.artists')}
            href={artistsHref(d.key)} n={n.artists} of={name} navigate={navigate} />
          <NumLine label={tf('tags.page.tracks', { n: count(n.tracks, 'track') })} rule={d.rules.tracks}
            href={tagTracksHref(d.key, 'album')} n={n.tracks} of={name} navigate={navigate} />
          {n.plays !== null
            ? <NumLine label={tf('tags.page.plays', { n: count(n.plays, 'play') })} rule={d.rules.plays}
              href={tagTracksHref(d.key)} n={n.plays} of={name} navigate={navigate} />
            : <li><span>{t('tags.page.noHistory')}</span></li>}
        </ul>
      </Card>

      <Card label={t('tags.page.sound')}>
        <div className="stack">
          <ul className="rows" aria-label={t('tags.page.sound')}>
            <NumLine label={tf('tags.page.soundAlbums', { n: count(n.sound, 'album') })} rule={d.rules.sound}
              href={albumsHref(d.key, 'sound')} n={n.sound} of={name} navigate={navigate} />
          </ul>
          {d.profile ? (
            <>
              <Text variant="label">{tf('tags.page.profile', { n: count(d.profile.plays ?? 0, 'play') })}</Text>
              <ul className="rows" aria-label={t('tags.page.profileList')}>
                {Object.entries(d.profile).filter(([k]) => k !== 'plays').map(([k, v]) => (
                  <li key={k}><span>{tMaybe(`tags.profile.${k}`) ?? k}</span><span>{k === 'loudness_lufs' ? tf('unit.lufs', { n: v }) : String(v)}</span></li>
                ))}
              </ul>
            </>
          ) : <Text>{t('tags.page.noProfile')}</Text>}
          <Text variant="note">{`${d.rules.profile}.`}</Text>
        </div>
      </Card>

      <Card label={t('tags.page.name')}>
        <div className="stack">
          {d.spellings.length === 0 ? <Text>{t('tags.page.noSpellings')}</Text> : (
            <ul className="rows" aria-label={t('tags.page.name')}>
              {d.spellings.map((s) => (
                <li key={s.raw}>
                  <span>
                    <strong>{s.raw}</strong>
                    <span className="sub">
                      {[s.same ? t('tags.page.asIs') : '', s.split ? t('tags.page.split') : '',
                        s.rules.length ? tf('tags.page.rules', { s: s.rules.map((r) => r.label).join(', ') }) : ''].filter(Boolean).join(' · ')}
                    </span>
                  </span>
                </li>
              ))}
            </ul>
          )}
          {d.issues.length > 0 && (
            <div className="hist-actions">
              {d.issues.map((i) => (
                <Num key={i.kind} href={proposalsHref('kind', i.kind)} label={tf('tags.page.issue', { k: tMaybe(`tags.page.issue.${i.kind}`) ?? i.kind })} navigate={navigate} />
              ))}
            </div>
          )}
          <Text variant="note">{`${d.rules.spellings}.`}</Text>
        </div>
      </Card>

      <Card label={t('tags.page.movements')}>
        <div className="stack">
          {d.movements.length === 0 ? <Text>{t('tags.page.noMovements')}</Text>
            : d.movements.map((m) => <MovementBlock key={m.id} m={m} here={d.key} navigate={navigate} />)}
          <Text variant="note">{`${d.rules.movement}.`}</Text>
        </div>
      </Card>
    </>
  );
}

function NumLine({ label, rule, href, n, of, navigate }: { label: string; rule: string; href: string; n: number; of: string } & Nav) {
  return (
    <li>
      <span>
        <Num href={href} n={n} label={label} of={of} navigate={navigate} />
        <span className="sub">{rule}</span>
      </span>
    </li>
  );
}

function MovementBlock({ m, here, navigate }: { m: Movement; here?: string } & Nav) {
  return (
    <div className="stack">
      <Text variant="heading">{m.name}</Text>
      {m.about && <Text>{m.about}</Text>}
      <Text variant="note">{tf('tags.mov.across', { b: m.broads.join(', '), n: fmt(m.in_use), all: count(m.tags.length, 'tag') })}</Text>
      <ul className="rows" aria-label={tf('tags.mov.tags', { m: m.name })}>
        {m.tags.map((x) => (
          <li key={x.key}>
            <span>
              {x.key === here ? <strong>{x.name}</strong> : x.in_use ? <TagLink k={x.key} name={x.name} navigate={navigate} /> : <span>{x.name}</span>}
              <span className="sub">{[x.broad ? tf('tags.mov.line', { b: x.broad }) : t('tags.noBroad'),
                x.in_use ? '' : t('tags.mov.notInUse')].filter(Boolean).join(' · ')}</span>
            </span>
            {x.in_use && <Num href={albumsHref(x.key)} n={x.albums} label={count(x.albums, 'album')} of={x.name} navigate={navigate} />}
          </li>
        ))}
      </ul>
    </div>
  );
}

// --- the tracks behind a tag's tracks and plays -------------------------------------------------------------

export function TagTrackRows({ query, navigate }: { query: string } & Nav) {
  const p = params(query);
  const tag = p.get('tag') ?? '';
  const sort = p.get('sort') === 'album' ? 'album' : 'plays';
  const offset = Number(p.get('offset') ?? 0) || 0;
  const load = useGet<TagTracksPage>(tagTracksApi(tag, sort, offset));
  return (
    <>
      <Band module="T">{t('tags.tracksPage.sub')}</Band>
      <div className="page stack">
        <Back href={tagHref(tag)} label={t('tags.page.back')} navigate={navigate} />
        {load.state === 'loading' && <Text>{t('rows.loading')}</Text>}
        {load.state === 'failed' && <Failed why={t('tags.page.notFound')} />}
        {load.state === 'ok' && (() => {
          const d = load.data;
          const b = d.offset + d.limit;
          return (
            <>
              <Text variant="heading">{tf('tags.tracksPage.title', { tag: d.tag.name })}</Text>
              <nav className="hist-choices" aria-label={t('tags.tracksPage.sorts')}>
                {(['plays', 'album'] as const).map((s) => (
                  <NavItem key={s} label={t(`tags.tracksPage.sort.${s}` as StringKey)} href={tagTracksHref(d.tag.key, s)} current={s === d.sort} onNavigate={navigate} />
                ))}
              </nav>
              <Text>{tf('tags.tracksPage.total', { n: count(d.total, 'track'), p: count(d.plays, 'play') })}</Text>
              <Text variant="note">{`${t('rows.rule')}: ${d.rule}. ${d.plays_rule}.`}</Text>
              {d.items.length === 0 ? <Text>{t('tags.rows.none')}</Text> : (
                <ol className="hist-rows">
                  {d.items.map((r, i) => (
                    <StationRow key={r.rating_key} position={d.offset + i + 1} module="T" title={r.title || t('rows.untitled')}
                      artist={[r.artist || t('rows.unknown'), r.album, count(r.plays, 'play')].filter(Boolean).join(' · ')}
                      why={tf('tags.tracksPage.why', { n: count(r.plays, 'play'), tag: d.tag.name })}
                      href={trackHref(r.rating_key)} onNavigate={navigate} />
                  ))}
                </ol>
              )}
              {d.items.some((r) => r.plays > 0) && (
                <div className="hist-actions">
                  {d.items.filter((r) => r.plays > 0).slice(0, 5).map((r) => (
                    <Num key={r.rating_key} href={playsHref(`track=${r.rating_key}`)} label={tf('tags.tracksPage.listens', { t: r.title || t('rows.untitled'), n: count(r.plays, 'play') })} navigate={navigate} />
                  ))}
                </div>
              )}
              {(d.offset > 0 || b < d.total) && (
                <div className="hist-actions">
                  {d.offset > 0 && <Num href={tagTracksHref(d.tag.key, d.sort, Math.max(0, d.offset - d.limit))} label={t('tags.prev')} navigate={navigate} />}
                  {b < d.total && <Num href={tagTracksHref(d.tag.key, d.sort, b)} label={t('tags.next')} navigate={navigate} />}
                </div>
              )}
            </>
          );
        })()}
      </div>
    </>
  );
}

// --- the genre map -----------------------------------------------------------------------------------------

const DRAWN_STOPS = 8; // stops drawn per line (the list below has every station)
const SHOWN = 8;       // first-rung stations shown before "Show all"

/** The genre map (T23): the whole ladder as lines, one per broad tag; the movements across them. */
export function GenreMap({ navigate }: Nav) {
  const load = useGet<GenreMapData>(MAP_API);
  return (
    <>
      <Band module="T">{t('tags.map.sub')}</Band>
      <div className="page stack history tags">
        <Back navigate={navigate} />
        <Text variant="title">{t('tags.map.title')}</Text>
        <Text>{t('tags.map.intro')}</Text>
        {load.state === 'loading' && <Text>{t('tags.loading')}</Text>}
        {load.state === 'failed' && <Failed />}
        {load.state === 'ok' && <MapBody m={load.data} navigate={navigate} />}
      </div>
    </>
  );
}

function MapBody({ m, navigate }: { m: GenreMapData } & Nav) {
  const s = m.summary;
  const names = new Map(m.movements.map((x) => [x.id, x.name]));
  return (
    <>
      <Card label={t('tags.map.sumLabel')}>
        <ul className="rows" aria-label={t('tags.map.sumLabel')}>
          <li><Num href={listHref('roots')} n={s.lines} label={tf('tags.map.sum.lines', { n: fmt(s.lines) })} navigate={navigate} /></li>
          <li><Num href={listHref('tags')} n={s.tags} label={tf('tags.sum.tags', { n: count(s.tags, 'tag') })} navigate={navigate} /></li>
          <li><Num href={listHref('shared')} n={s.shared} label={tf('tags.sum.shared', { n: count(s.shared, 'tag') })} navigate={navigate} /></li>
          <li><Num href={listHref('alone')} n={s.alone} label={tf('tags.sum.alone', { n: count(s.alone, 'tag') })} navigate={navigate} /></li>
          <li>
            <Button variant="quiet" href="#gm-movements">{tf('tags.map.sum.movements', { n: fmt(s.movements) })}</Button>
          </li>
        </ul>
      </Card>

      <section className="map" aria-labelledby="gm-drawing">
        <Text variant="label" id="gm-drawing">{t('tags.map.drawing')}</Text>
        <p className="visually-hidden">
          {tf('tags.map.summary', {
            n: fmt(m.lines.length),
            lines: m.lines.map((l) => tf('tags.map.summaryLine', { name: l.name, albums: count(l.under, 'album'), tags: count(l.tags, 'tag') })).join('; ') || t('map.none'),
            alone: count(m.alone.length, 'tag'), movements: fmt(m.movements.length),
          })}
        </p>
        <div className="map-drawing gm-drawing" aria-hidden="true">
          {m.lines.map((l, i) => (
            <div key={l.key} className={`map-line line-t${l.under ? '' : ' is-off'}`} style={{ '--i': i % 6 } as CSSProperties}>
              <LineBullet module="T" size={28} decorative />
              <span className="map-track">
                {l.stations.slice(0, DRAWN_STOPS).map((st) => (
                  <span key={st.key} className={`map-stop${st.movements.length ? ' is-interchange' : ''}`} />
                ))}
              </span>
              <span className="map-name">{l.name}</span>
            </div>
          ))}
        </div>
        <Text variant="note">{`${m.rules.line}.`}</Text>
      </section>

      <section className="stack" aria-labelledby="gm-lines">
        <Text variant="heading" id="gm-lines">{t('tags.map.lines')}</Text>
        <ul className="lines gm-lines">
          {m.lines.map((l) => <LineCard key={l.key} l={l} names={names} navigate={navigate} />)}
        </ul>
      </section>

      <section className="stack" aria-labelledby="gm-movements-h" id="gm-movements">
        <Text variant="heading" id="gm-movements-h">{t('tags.map.movements')}</Text>
        <Text variant="note">{`${m.rules.movement}.`}</Text>
        {m.movements.length === 0 ? <Text>{t('tags.map.noMovements')}</Text> : (
          <ul className="lines">
            {m.movements.map((x) => <li key={x.id}><Card><MovementBlock m={x} navigate={navigate} /></Card></li>)}
          </ul>
        )}
      </section>

      {m.alone.length > 0 && <Alone alone={m.alone} navigate={navigate} />}
    </>
  );
}

function LineCard({ l, names, navigate }: { l: MapLine; names: Map<string, string> } & Nav) {
  const [all, setAll] = useState(false);
  const shown = all ? l.stations : l.stations.slice(0, SHOWN);
  return (
    <li>
      <Card off={!l.under}>
        <div className="stack">
          <div className="line-head">
            <LineBullet module="T" size={28} decorative />
            <Text variant="heading"><TagLink k={l.key} name={l.name} navigate={navigate} /></Text>
          </div>
          <div className="hist-actions">
            <Num href={albumsHref(l.key, 'under')} n={l.under} label={tf('tags.num.under', { n: count(l.under, 'album') })} of={l.name} navigate={navigate} />
            {l.missing !== null && <Num href={albumsHref(l.key, 'missing')} n={l.missing} label={tf('tags.num.missing', { n: count(l.missing, 'album') })} of={l.name} navigate={navigate} />}
          </div>
          {l.stations.length === 0 ? <Text>{t('tags.map.noStations')}</Text> : (
            <ul className="gm-line line-t" aria-label={tf('tags.map.stationsOf', { line: l.name })}>
              {shown.map((st) => <StationItem key={st.key} st={st} names={names} navigate={navigate} />)}
            </ul>
          )}
          {l.stations.length > SHOWN && (
            <div>
              <Button variant="quiet" onClick={() => setAll(!all)}>
                {tf(all ? 'tags.map.fewer' : 'tags.map.all', { n: l.stations.length })}
                <span className="visually-hidden">{`, ${l.name}`}</span>
              </Button>
            </div>
          )}
        </div>
      </Card>
    </li>
  );
}

function StationItem({ st, names, navigate }: { st: Station; names: Map<string, string> } & Nav) {
  const notes: string[] = [];
  if (st.also.length) notes.push(tf('tags.why.also', { p: st.also.join(', ') }));
  if (st.movements.length) notes.push(tf('tags.map.inMovement', { m: st.movements.map((id) => names.get(id) ?? id).join(', ') }));
  return (
    <li className={`gm-station${st.movements.length ? ' is-interchange' : ''}`}>
      <span className="gm-stop" aria-hidden="true" />
      <span className="gm-label">
        <TagLink k={st.key} name={st.name} navigate={navigate} />
        <Num href={albumsHref(st.key, st.stations.length ? 'under' : 'carries')} n={st.under} label={count(st.under, 'album')} of={st.name} navigate={navigate} />
        {notes.length > 0 && <span className="sub">{notes.join(' · ')}</span>}
      </span>
      {st.stations.length > 0 && (
        <ul className="gm-branch" aria-label={tf('tags.belowOf', { tag: st.name })}>
          {st.stations.map((c) => <StationItem key={c.key} st={c} names={names} navigate={navigate} />)}
        </ul>
      )}
    </li>
  );
}

function Alone({ alone, navigate }: { alone: GenreMapData['alone'] } & Nav) {
  const [all, setAll] = useState(false);
  const shown = all ? alone : alone.slice(0, 12);
  return (
    <section className="stack" aria-labelledby="gm-alone">
      <Text variant="heading" id="gm-alone">{t('tags.alone')}</Text>
      <ul className="rows" aria-label={t('tags.alone')}>
        {shown.map((a) => (
          <li key={a.key}>
            <TagLink k={a.key} name={a.name} navigate={navigate} />
            <Num href={albumsHref(a.key)} n={a.albums} label={count(a.albums, 'album')} of={a.name} navigate={navigate} />
          </li>
        ))}
      </ul>
      {alone.length > 12 && (
        <div><Button variant="quiet" onClick={() => setAll(!all)}>{tf(all ? 'tags.map.fewer' : 'tags.map.all', { n: alone.length })}</Button></div>
      )}
    </section>
  );
}

// --- the P4 gate card ---------------------------------------------------------------------------------------

/** The P4 gate in one card on SETUP and TAGS (T23): its three checks, each opening the page with its rows. */
export function TagsGateCard({ navigate }: Nav) {
  const load = useGet<TagsGate>(TAGS_GATE_API);
  return (
    <Card label={t('p4gate.card')}>
      <div className="stack">
        {load.state === 'loading' && <Text>{t('p4gate.loading')}</Text>}
        {load.state === 'failed' && <Status state="needs" label={t('p4gate.failed')} />}
        {load.state === 'ok' && <GateBody g={load.data} navigate={navigate} />}
      </div>
    </Card>
  );
}

function CheckLine({ name, passed, rule, children }: { name: string; passed: boolean; rule: string; children: ReactNode }) {
  return (
    <li className="gate-field">
      <span>
        <strong>{name}</strong>
        <span className="sub">{rule}</span>
        {children}
      </span>
      <Status state={passed ? 'ready' : 'needs'} label={t(passed ? 'p3gate.check.passed' : 'p3gate.check.notPassed')} />
    </li>
  );
}

function Open({ href, what, navigate }: { href: string; what: string } & Nav) {
  return (
    <span>
      <Button variant="quiet" href={href} onClick={() => navigate(href)}>
        {t('p3gate.rows')}<span className="visually-hidden">{`, ${what}`}</span>
      </Button>
    </span>
  );
}

function GateBody({ g, navigate }: { g: TagsGate } & Nav) {
  const [lad, trk, aud] = g.checks;
  return (
    <>
      <Status state={g.passed ? 'ready' : 'needs'} label={t(g.passed ? 'p3gate.passed' : 'p3gate.notPassed')} />
      <ul className="rows" aria-label={t('p4gate.checks')}>
        <CheckLine name={t('p4gate.ladder')} passed={lad.passed} rule={lad.rule}><LadderLines c={lad} /><Open href={TAGS_PATH} what={t('p4gate.ladder')} navigate={navigate} /></CheckLine>
        <CheckLine name={t('p4gate.tracks')} passed={trk.passed} rule={trk.rule}><TrackLines c={trk} /><Open href={TAGS_PATH} what={t('p4gate.tracks')} navigate={navigate} /></CheckLine>
        <CheckLine name={t('p4gate.audit')} passed={aud.passed} rule={aud.rule}><AuditLines c={aud} navigate={navigate} /><Open href={TAGS_PROPOSALS} what={t('p4gate.audit')} navigate={navigate} /></CheckLine>
      </ul>
      <Text variant="note">{`${g.rules.passed} ${g.read_only}`}</Text>
    </>
  );
}

function LadderLines({ c }: { c: GateLadder }) {
  return (
    <>
      <span className="sub">{tf('p4gate.ladder.rules', { m: fmt(c.rules.ok), n: count(c.rules.broad, 'broadTag') })}</span>
      <span className="sub">{tf('p4gate.ladder.ends', { m: fmt(c.ends.ok), n: count(c.ends.tags, 'ladder') })}</span>
      <span className="sub">{c.stored
        ? tf('p4gate.ladder.stored', { m: fmt(c.stored.ok), n: count(c.stored.broad, 'broadTag'), f: t(c.stored.fresh ? 'compare.fresh' : 'compare.stale') })
        : t('p4gate.noStored')}</span>
    </>
  );
}

function TrackLines({ c }: { c: GateTracks }) {
  return (
    <>
      <span className="sub">{tf('p4gate.tracks.tags', { m: fmt(c.tags.ok), n: count(c.tags.tracks, 'track') })}</span>
      <span className="sub">{tf('p4gate.tracks.styles', { m: fmt(c.styles.ok), n: count(c.styles.tracks, 'track'), a: fmt(c.styles.analysed) })}</span>
    </>
  );
}

function AuditLines({ c, navigate }: { c: GateAudit } & Nav) {
  if (!c.stored || !c.tags) return <span className="sub">{t('p4gate.noStored')}</span>;
  return (
    <>
      <span className="sub">{tf('p4gate.audit.tags', { m: fmt(c.tags.ok), n: count(c.tags.tags, 'tag'), f: t(c.fresh ? 'compare.fresh' : 'compare.stale') })}</span>
      <span className="sub">{tf('p4gate.audit.rest', {
        i: fmt(c.issues?.ok ?? 0), ni: fmt(c.issues?.kinds ?? 0), f: fmt(c.fixes?.ok ?? 0), nf: fmt(c.fixes?.items ?? 0),
        s: fmt(c.suggestions?.ok ?? 0), ns: fmt(c.suggestions?.items ?? 0),
      })}</span>
      {c.tags.differing.length > 0 && (
        <ul className="rows" aria-label={t('p4gate.audit.differing')}>
          {c.tags.differing.map((d) => (
            <li key={d.key}>
              <span>
                <TagLink k={d.key} name={d.name} navigate={navigate} />
                <span className="sub">{Object.entries(d.fields).map(([f, [a, b]]) =>
                  (typeof a === 'number' && typeof b === 'number'
                    ? tf('p4gate.audit.field', { f: tMaybe(`p4gate.field.${f}`) ?? f, a: fmt(a), b: fmt(b) })
                    : tf('p4gate.audit.fieldOther', { f: tMaybe(`p4gate.field.${f}`) ?? f }))).join('; ')}</span>
              </span>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
