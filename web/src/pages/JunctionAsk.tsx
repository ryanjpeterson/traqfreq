import { useEffect, useState } from 'react';
import { Band, Button, Card, LineLever, Status, Text } from '../components/kit';
import { t, tf, type StringKey } from '../copy/t';
import { useGet } from '../app/api';
import { fmt } from '../app/history';
import {
  JUNCTION_PATH, askApi, askRowsApi, askRowsHref, count, junctionHref,
  type AskAnswer, type AskLine, type AskRows as AskRowsData,
} from '../app/playlists';
import { Back, Failed, Num, TrackList, Tree } from './Playlists';

/** T28: the Ask box. A few words become lines for the Junction: typed facet:value parts as they are, the other
 *  words by sound (jimbo-dj's CLAP text server against every analysed track) and, when it's on, by Ollama. Each line
 *  shows its conditions with their counts (W3) and opens in the Junction. Nothing is saved. */

type Nav = { navigate: (href: string) => void };
type Asked = { state: 'loading' } | { state: 'ok'; data: AskAnswer } | { state: 'failed'; status?: number };

export function AskBox({ navigate }: Nav) {
  const [words, setWords] = useState('');
  const [asked, setAsked] = useState('');
  const [answer, setAnswer] = useState<Asked | null>(null);
  useEffect(() => {
    if (!asked) return;
    let live = true;
    setAnswer({ state: 'loading' });
    fetch(askApi(asked))
      .then((r) => (r.ok ? r.json() : Promise.reject(r.status)))
      .then((data: AskAnswer) => live && setAnswer({ state: 'ok', data }))
      .catch((e) => live && setAnswer({ state: 'failed', status: typeof e === 'number' ? e : undefined }));
    return () => { live = false; };
  }, [asked]);
  const ask = () => setAsked(words.trim());
  const first = answer?.state === 'ok' ? answer.data.lines[0] : undefined;
  return (
    <Card>
      <div className="stack">
        <LineLever module="L" title={t('ask.title')} detail={t('ask.detail')} share={0} count={first?.count}
          field={{ value: words, onChange: setWords, onSubmit: ask, placeholder: t('ask.placeholder') }} />
        <div><Button variant="secondary" onClick={ask} disabled={!words.trim()}>{t('ask.button')}</Button></div>
        {answer?.state === 'loading' && <Text>{t('ask.loading')}</Text>}
        {answer?.state === 'failed' && (
          <Status state="needs" label={t(answer.status === 400 ? 'ask.failed' : 'ask.failedOther')} />
        )}
        {answer?.state === 'ok' && <AskAnswerView a={answer.data} navigate={navigate} />}
      </div>
    </Card>
  );
}

const sourceName = (s: AskLine['source']) => t(`ask.source.${s}` as StringKey);

function AskAnswerView({ a, navigate }: { a: AskAnswer } & Nav) {
  return (
    <section className="stack" aria-label={t('ask.lines')}>
      {a.lines.length === 0 && <Text>{t('ask.none')}</Text>}
      {a.lines.map((x) => <AskLineView key={x.source} x={x} navigate={navigate} />)}
      {a.words && <SoundNote a={a} navigate={navigate} />}
      <OllamaNote a={a} />
      <Text variant="note">{a.read_only}</Text>
    </section>
  );
}

function AskLineView({ x, navigate }: { x: AskLine } & Nav) {
  const href = junctionHref(x.query);
  return (
    <div className="stack ask-line">
      <Text variant="label">{`${sourceName(x.source)} · ${x.words} · ${count(x.count, 'track')}`}</Text>
      <Tree node={x.match} src={{ tree: x.query }} line="a" navigate={navigate} />
      <Text variant="note">{`${t('playlists.rule')}: ${x.rule}.`}</Text>
      <div><Button variant="quiet" href={href} onClick={() => navigate(href)}>{t('ask.open')}<span className="visually-hidden">{`, ${sourceName(x.source)}`}</span></Button></div>
    </div>
  );
}

function SoundNote({ a, navigate }: { a: AskAnswer } & Nav) {
  const s = a.sound;
  if (s.state === 'off') return <Text variant="note">{t('ask.sound.off')}</Text>;
  if (s.state === 'unavailable') return <Text variant="note">{t('ask.sound.unavailable')}</Text>;
  if (s.state === 'no_vectors') return <Text variant="note">{t('ask.sound.noVectors')}</Text>;
  if (s.state !== 'ok') return null;
  return (
    <div className="stack">
      <Text variant="label">{t('ask.sound')}</Text>
      <ul className="rows">
        <li>
          <span>{t('ask.sound.nearOf')}<span className="sub">{s.rule}</span></span>
          <Num href={askRowsHref(a.words)} label={tf('ask.sound.near', { n: fmt(s.near ?? 0) })} navigate={navigate} />
        </li>
        {(s.styles ?? []).map((x) => (
          <li key={x.style}>
            <span>{tf('ask.sound.style', { style: x.style })}</span>
            <Num href={askRowsHref(a.words, x.style)} label={tf('ask.sound.onNear', { m: fmt(x.near), n: fmt(s.near ?? 0) })} of={x.style} navigate={navigate} />
          </li>
        ))}
      </ul>
      {!s.styles?.length && <Text variant="note">{t('ask.sound.noStyle')}</Text>}
    </div>
  );
}

function OllamaNote({ a }: { a: AskAnswer }) {
  const o = a.ollama;
  if (o.state === 'off') return <Text variant="note">{t('ask.ollama.off')}</Text>;
  if (o.state === 'unavailable') return <Text variant="note">{t('ask.ollama.unavailable')}</Text>;
  if (o.state !== 'ok') return null;
  const kept = Object.entries(o.kept ?? {}).flatMap(([f, v]) => v.map((x) => `${f}:${x}`));
  const dropped = (o.dropped ?? []).map((d) => `${d.f}:${d.v}`);
  return (
    <div className="stack">
      <Text variant="label">{t('ask.ollama')}</Text>
      <Text variant="note">{kept.length ? tf('ask.ollama.kept', { list: kept.join(', ') }) : t('ask.ollama.nothing')}</Text>
      {dropped.length > 0 && <Text variant="note">{tf('ask.ollama.dropped', { list: dropped.join(', ') })}</Text>}
    </div>
  );
}

/** The rows behind the sound side's numbers: the tracks nearest the words, closest first, with their scores. */
export function AskRows({ query, navigate }: { query: string } & Nav) {
  const load = useGet<AskRowsData>(askRowsApi(query));
  const style = new URLSearchParams(query).get('style');
  return (
    <>
      <Band module="L">{t('playlists.rows.sub')}</Band>
      <div className="page stack history playlists">
        <Back href={JUNCTION_PATH} label={t('ask.rows.back')} navigate={navigate} />
        <Text variant="title">{style ? tf('ask.rows.titleStyle', { style }) : t('ask.rows.title')}</Text>
        {load.state === 'loading' && <Text>{t('rows.loading')}</Text>}
        {load.state === 'failed' && <Failed why={load.status === 503 ? 'ask.sound.unavailable' : undefined} />}
        {load.state === 'ok' && (
          <>
            <Text>{`“${load.data.text}” · ${count(load.data.count, 'track')}`}</Text>
            <Text variant="note">{`${t('playlists.rule')}: ${load.data.rule}.`}</Text>
            <TrackList rows={load.data.rows}
              why={(i) => tf('ask.rows.why', { n: fmt(load.data.rows[i].score), words: load.data.text })} navigate={navigate} />
          </>
        )}
      </div>
    </>
  );
}
