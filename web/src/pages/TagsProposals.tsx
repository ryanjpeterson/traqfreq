import { useState, type ReactNode } from 'react';
import { Band, Button, Card, Status, StationRow, Text } from '../components/kit';
import { t, tf, tMaybe, type StringKey } from '../copy/t';
import { useGet } from '../app/api';
import { count, fmt } from '../app/history';
import {
  PROPOSALS_API, PROPOSAL_GROUPS, TAGS_PATH, TAGS_PROPOSALS, fixInPlexHref, params, proposalsApi, proposalsHref,
  tagAlbumHref, type AuditCheck, type Change, type Fix, type Inbox, type ProposalAlbum, type ProposalAlbums,
  type ProposalGroup, type Rec, type RuleQuestion,
} from '../app/tags';

type Nav = { navigate: (href: string) => void };
const FIRST = 15;  // jimbo-dj's overview shows its top 15 fixes (and 12 suggestions); the rest behind a toggle

function Num({ href, label, of, navigate }: { href: string; label: string; of?: string } & Nav) {
  return (
    <Button variant="quiet" href={href} onClick={() => navigate(href)}>
      {label}{of && <span className="visually-hidden">{`, ${of}`}</span>}
    </Button>
  );
}

function Failed() {
  return (
    <Card>
      <div className="stack">
        <Status state="needs" label={t('tags.failed')} />
        <Text>{t('tags.failedWhy')}</Text>
      </div>
    </Card>
  );
}

/** One fix, in words: add Metal, remove 2010s, rename "doom metal" to Doom Metal. */
export function fixWords(f: Pick<Fix, 'op' | 'tag' | 'to'>): string {
  if (f.op === 'add') return f.tag ? tf('tags.prop.op.add', { tag: f.tag }) : t('tags.prop.op.untagged');
  if (f.op === 'remove') return tf('tags.prop.op.remove', { tag: f.tag ?? '' });
  return tf('tags.prop.op.rename', { tag: f.tag ?? '', to: f.to.join(' + ') });
}

/** A change Fix in Plex's preview would make, as its preview says it (jimbo-dj's TagFix why()). */
export function changeWords(c: Change): string {
  const base = fixWords({ op: c.op, tag: c.tag, to: c.to ?? [] });
  return c.because?.length ? `${base} ${tf('tags.prop.for', { s: c.because.join(', ') })}` : base;
}

function srcWords(src: string, v: number): string {
  const name = tMaybe(`tags.prop.src.${src}`) ?? src;
  if (src === 'mb-release' || src === 'mb-artist') return `${name} ${count(v, 'vote')}`;
  if (src === 'plex' || src === 'plex-artist') return name;
  return `${name} ${Math.round(v * 100)}%`;
}

export function recWords(r: Rec): string {
  return `${r.tag} (${Object.entries(r.sources).map(([s, v]) => srcWords(s, v)).join(', ')})`;
}

/** An album's proposed change in one line: before, after Fix in Plex's preview, why, and the rest. */
export function proposalWhy(a: ProposalAlbum): string {
  const none = t('tags.prop.noTags');
  const parts = [tf('tags.prop.before', { s: a.before.join(', ') || none })];
  parts.push(a.changes.length ? tf('tags.prop.after', { s: a.after.join(', ') || none }) : t('tags.prop.unchanged'));
  if (a.changes.length) parts.push(tf('tags.prop.changes', { s: a.changes.map(changeWords).join('; ') }));
  const left = a.issues.filter((i) => !a.changes.some((c) => c.kind === i.kind && c.tag === i.tag));
  if (left.length) parts.push(tf('tags.prop.issues', { s: left.map((i) => `${tMaybe(`tags.prop.kind.${i.kind}`) ?? i.kind}: ${changeWords(i)}`).join('; ') }));
  if (a.recs.length) parts.push(tf('tags.prop.recs', { s: a.recs.map(recWords).join('; ') }));
  if (a.ladder.length) parts.push(tf('tags.prop.ladderLine', { s: a.ladder.map((p) => `${p.tag} ${tf('tags.prop.for', { s: p.because.join(', ') })}`).join('; ') }));
  parts.push(tf('tags.prop.proposed', { s: a.proposed.join(', ') || none }));
  return parts.join(' · ');
}

/** Fix in Plex stays in jimbo-dj until P6: said, with a link there. */
function FixInPlexCard({ f }: { f: Inbox['fix_in_plex'] }) {
  return (
    <Card label={t('tags.prop.where.label')}>
      <div className="stack">
        <Status state="off" label={t('tags.prop.where.status')} />
        <Text>{tf('tags.prop.where.body', { until: f.until })}</Text>
        <div><Button variant="secondary" href={fixInPlexHref(f)}>{t('tags.prop.where.open')}</Button></div>
      </div>
    </Card>
  );
}

function Toggle({ n, open, setOpen }: { n: number; open: boolean; setOpen: (v: boolean) => void }) {
  if (n <= FIRST) return null;
  return <div><Button variant="quiet" onClick={() => setOpen(!open)}>{tf(open ? 'tags.prop.fewer' : 'tags.prop.all', { n })}</Button></div>;
}

function Section({ id, title, note, by, children }: { id: string; title: string; note: string; by: 'jimbodj' | 'traqfreq'; children: ReactNode }) {
  return (
    <section aria-labelledby={id} className="stack">
      <Text variant="heading" id={id}>{title}</Text>
      <Text variant="note">{`${t(by === 'jimbodj' ? 'tags.prop.byJimbodj' : 'tags.prop.byTraqfreq')} ${note}`}</Text>
      {children}
    </section>
  );
}

function Fixes({ d, navigate }: { d: Inbox } & Nav) {
  const [open, setOpen] = useState(false);
  const shown = open ? d.fixes : d.fixes.slice(0, FIRST);
  return (
    <Section id="prop-fixes" title={t('tags.prop.fixes')} note={`${t('rows.rule')}: ${d.rule.fix}.`} by="jimbodj">
      {d.fixes.length === 0 ? <Text>{t('tags.prop.noFixes')}</Text> : (
        <ul className="rows" aria-label={t('tags.prop.fixes')}>
          {shown.map((f) => (
            <li key={f.id}>
              <span>{fixWords(f)}<span className="sub">{f.label}</span></span>
              <Num href={proposalsHref('fix', f.id)} label={count(f.albums, 'album')} of={fixWords(f)} navigate={navigate} />
            </li>
          ))}
        </ul>
      )}
      <Toggle n={d.fixes.length} open={open} setOpen={setOpen} />
    </Section>
  );
}

function Suggestions({ d, navigate }: { d: Inbox } & Nav) {
  const [open, setOpen] = useState(false);
  const shown = open ? d.suggestions : d.suggestions.slice(0, FIRST);
  return (
    <Section id="prop-recs" title={t('tags.prop.suggestions')} note={`${t('rows.rule')}: ${d.rule.suggest}.`} by="jimbodj">
      {d.suggestions.length === 0 ? <Text>{t('tags.prop.noSuggestions')}</Text> : (
        <ul className="rows" aria-label={t('tags.prop.suggestions')}>
          {shown.map((s) => (
            <li key={s.key}>
              <span>{s.tag}<span className="sub">{t(s.in_use ? 'tags.prop.inUse' : 'tags.prop.notInUse')}</span></span>
              <Num href={proposalsHref('suggest', s.key)} label={count(s.albums, 'album')} of={s.tag} navigate={navigate} />
            </li>
          ))}
        </ul>
      )}
      <Toggle n={d.suggestions.length} open={open} setOpen={setOpen} />
    </Section>
  );
}

export function questionWords(q: RuleQuestion): string {
  return tf('tags.prop.question', { broad: q.broad, match: q.match, last: q.last });
}

function partLine(m: number, n: number, key: StringKey, ok: boolean, stored: boolean) {
  return (
    <li>
      <span>{tf(key, { m: fmt(m), n: fmt(n) })}{!stored && <span className="sub">{t('tags.prop.check.notStored')}</span>}</span>
      <Status state={ok ? 'ready' : 'needs'} label={t(ok ? 'compare.match' : 'compare.differs')} />
    </li>
  );
}

/** Gate check 3: the audit's numbers here next to jimbo-dj's stored run. */
export function AuditCheckCard({ c }: { c: AuditCheck }) {
  const [open, setOpen] = useState(false);
  if (!c.stored || !c.tags || !c.issues || !c.fixes || !c.suggestions) {
    return (
      <Card label={t('tags.prop.check.label')}>
        <div className="stack">
          <Status state="needs" label={t('compare.notPassed')} />
          <Text>{t('tags.prop.check.none')}</Text>
        </div>
      </Card>
    );
  }
  const differing = c.tags.differing;
  return (
    <Card label={t('tags.prop.check.label')}>
      <div className="stack">
        <Status state={c.passed ? 'ready' : 'needs'} label={t(c.passed ? 'compare.passed' : 'compare.notPassed')} />
        <ul className="rows" aria-label={t('tags.prop.check.label')}>
          {partLine(c.tags.ok, c.tags.tags, 'tags.prop.check.tags', c.tags.matches, c.tags.stored)}
          {partLine(c.issues.ok, c.issues.kinds, 'tags.prop.check.issues', c.issues.matches, c.issues.stored)}
          {partLine(c.fixes.ok, c.fixes.items, 'tags.prop.check.fixes', c.fixes.matches, c.fixes.stored)}
          {partLine(c.suggestions.ok, c.suggestions.items, 'tags.prop.check.suggestions', c.suggestions.matches, c.suggestions.stored)}
        </ul>
        <Text variant="note">{`${c.source} · ${t(c.fresh ? 'compare.fresh' : 'compare.stale')}${!c.matches && !c.fresh ? ` · ${t('compare.differsStale')}` : ''}`}</Text>
        <Text variant="note">{`${t('rows.rule')}: ${c.rule}.`}</Text>
        {differing.length > 0 && (
          <>
            <div><Button variant="quiet" onClick={() => setOpen(!open)}>{tf(open ? 'tags.prop.check.hide' : 'tags.prop.check.show', { n: differing.length })}</Button></div>
            {open && (
              <ul className="rows" aria-label={t('tags.prop.check.differList')}>
                {differing.map((r) => (
                  <li key={r.key} className="gate-field">
                    <span>
                      {r.name}
                      <span className="sub">{tf('tags.check.ours', { v: tagNumbers(r.traqfreq) })}</span>
                      <span className="sub">{tf('tags.check.theirs', { v: tagNumbers(r.jimbodj) })}</span>
                    </span>
                    <Status state="needs" label={t('compare.differs')} />
                  </li>
                ))}
              </ul>
            )}
          </>
        )}
      </div>
    </Card>
  );
}

function tagNumbers(r: { albums: number; artists: number; tracks: number; musicbrainz: number; sound: number; issues: unknown[] } | null): string {
  return r ? tf('tags.prop.check.numbers', { albums: fmt(r.albums), artists: fmt(r.artists), tracks: fmt(r.tracks), mb: fmt(r.musicbrainz),
    sound: fmt(r.sound), issues: fmt(r.issues.length) }) : t('tags.check.absent');
}

/** TAGS → the proposals inbox (T22): every album's proposed tag change, shown, never applied. */
export function Proposals({ navigate }: Nav) {
  const load = useGet<Inbox>(PROPOSALS_API);
  return (
    <>
      <Band module="T">{t('tags.prop.sub')}</Band>
      <div className="page stack history tags">
        <div><Button variant="quiet" href={TAGS_PATH} onClick={() => navigate(TAGS_PATH)}>{t('tags.back')}</Button></div>
        <Text variant="title">{t('tags.prop.title')}</Text>
        <Text>{t('tags.prop.intro')}</Text>
        {load.state === 'loading' && <Text>{t('tags.prop.loading')}</Text>}
        {load.state === 'failed' && <Failed />}
        {load.state === 'ok' && <InboxBody d={load.data} navigate={navigate} />}
      </div>
    </>
  );
}

function InboxBody({ d, navigate }: { d: Inbox } & Nav) {
  const s = d.summary;
  return (
    <>
      <FixInPlexCard f={d.fix_in_plex} />
      <Card label={t('tags.prop.sum.label')}>
        <ul className="rows" aria-label={t('tags.prop.sum.label')}>
          <li><Num href={proposalsHref('all')} label={tf('tags.prop.sum.proposed', { n: count(s.proposed, 'album') })} navigate={navigate} /></li>
        </ul>
        <Text variant="note">{tf('tags.prop.sum.note', { albums: count(s.albums, 'album'), clean: fmt(s.clean), fixable: count(s.fixable, 'album') })}</Text>
      </Card>
      <AuditCheckCard c={d.check} />
      <Section id="prop-kinds" title={t('tags.prop.kinds')} note={`${t('rows.rule')}: ${d.rule.kind}.`} by="jimbodj">
        <ul className="rows" aria-label={t('tags.prop.kinds')}>
          {d.kinds.map((k) => (
            <li key={k.kind}>
              <span>{k.label}<span className="sub">{t(k.fixable ? 'tags.prop.fixable' : 'tags.prop.person')}</span></span>
              <Num href={proposalsHref('kind', k.kind)} label={count(k.albums, 'album')} of={k.label} navigate={navigate} />
            </li>
          ))}
        </ul>
      </Section>
      <Fixes d={d} navigate={navigate} />
      <Suggestions d={d} navigate={navigate} />
      <Section id="prop-ladder" title={t('tags.prop.ladder')} note={`${t('rows.rule')}: ${d.rule.ladder}.`} by="traqfreq">
        {d.ladder.length === 0 ? <Text>{t('tags.prop.noLadder')}</Text> : (
          <ul className="rows" aria-label={t('tags.prop.ladder')}>
            {d.ladder.map((g) => (
              <li key={g.key}>
                <span>{tf('tags.prop.op.add', { tag: g.tag })}<span className="sub">{tf('tags.prop.for', { s: g.because.join(', ') })}</span></span>
                <Num href={proposalsHref('ladder', g.key)} label={count(g.albums, 'album')} of={g.tag} navigate={navigate} />
              </li>
            ))}
          </ul>
        )}
      </Section>
      <Section id="prop-rules" title={t('tags.prop.rules')} note={`${t('rows.rule')}: ${d.rule.rule}.`} by="traqfreq">
        {d.rules.length === 0 ? <Text>{t('tags.prop.noRules')}</Text> : (
          <ul className="rows" aria-label={t('tags.prop.rules')}>
            {d.rules.map((q) => (
              <li key={q.key}>
                <span>{q.tag}<span className="sub">{questionWords(q)}</span></span>
                <Num href={proposalsHref('rule', q.key)} label={count(q.albums, 'album')} of={q.tag} navigate={navigate} />
              </li>
            ))}
          </ul>
        )}
      </Section>
    </>
  );
}

function heading(d: ProposalAlbums): string {
  if (d.group === 'kind') return tf('tags.prop.albums.kind', { label: d.label ?? '' });
  if (d.group === 'fix' && d.fix) return tf('tags.prop.albums.fix', { fix: fixWords(d.fix) });
  if (d.group === 'suggest') return tf('tags.prop.albums.suggest', { tag: d.tag ?? '' });
  if (d.group === 'ladder') return tf('tags.prop.albums.ladder', { tag: d.tag ?? '' });
  if (d.group === 'rule') return tf('tags.prop.albums.rule', { tag: d.tag ?? '' });
  return t('tags.prop.albums.all');
}

/** The albums behind one of the inbox's numbers, each before and after Fix in Plex's preview. */
export function ProposalAlbums({ query, navigate }: { query: string } & Nav) {
  const p = params(query);
  const raw = p.get('group');
  const group: ProposalGroup = PROPOSAL_GROUPS.includes(raw as ProposalGroup) ? (raw as ProposalGroup) : 'all';
  const value = p.get('value') ?? undefined;
  const offset = Number(p.get('offset') ?? 0) || 0;
  const load = useGet<ProposalAlbums>(proposalsApi(group, value, offset));
  return (
    <>
      <Band module="T">{t('tags.prop.albums.sub')}</Band>
      <div className="page stack">
        <div><Button variant="quiet" href={TAGS_PROPOSALS} onClick={() => navigate(TAGS_PROPOSALS)}>{t('tags.prop.back')}</Button></div>
        {load.state === 'loading' && <Text>{t('rows.loading')}</Text>}
        {load.state === 'failed' && <Failed />}
        {load.state === 'ok' && (() => {
          const d = load.data;
          const b = d.offset + d.limit;
          return (
            <>
              <Text variant="heading">{heading(d)}</Text>
              {d.question && <Text>{questionWords(d.question)}</Text>}
              <Text>{tf('tags.rows.total', { n: count(d.total, 'album') })}</Text>
              <Text variant="note">{`${t('rows.rule')}: ${d.rule}.`}</Text>
              <Text variant="note">{d.kinds.length ? tf('tags.prop.albums.kinds', { s: d.kinds.map((k) => tMaybe(`tags.prop.kind.${k}`) ?? k).join(', ') }) : t('tags.prop.albums.noKinds')}</Text>
              {d.items.length === 0 ? <Text>{t('tags.rows.none')}</Text> : (
                <ol className="hist-rows">
                  {d.items.map((a, i) => (
                    <StationRow key={a.album_key} position={d.offset + i + 1} module="T" title={a.title || t('rows.untitled')}
                      artist={[a.artist || t('rows.unknown'), a.year].filter(Boolean).join(' · ')}
                      why={proposalWhy(a)} defaultOpen href={tagAlbumHref(a.album_key)} onNavigate={navigate} />
                  ))}
                </ol>
              )}
              {(d.offset > 0 || b < d.total) && (
                <div className="hist-actions">
                  {d.offset > 0 && <Num href={proposalsHref(group, value, Math.max(0, d.offset - d.limit))} label={t('tags.prev')} navigate={navigate} />}
                  {b < d.total && <Num href={proposalsHref(group, value, b)} label={t('tags.next')} navigate={navigate} />}
                </div>
              )}
            </>
          );
        })()}
      </div>
    </>
  );
}
