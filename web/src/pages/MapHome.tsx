import type { CSSProperties } from 'react';
import { Button, Card, LineBullet, Status, Text, type ModuleId } from '../components/kit';
import { t, tf, type StringKey } from '../copy/t';
import type { ModuleSwitch } from '../app/api';
import { MODULE_PATH } from '../app/route';

type Props = { modules: ModuleSwitch[]; navigate: (href: string) => void };

const name = (m: ModuleId) => t(`module.${m}` as StringKey);

/** Map home: the modules as lines (a drawing), its screen-reader summary and its list view (L6). */
export function MapHome({ modules, navigate }: Props) {
  const on = modules.filter((m) => m.on).map((m) => name(m.id));
  const off = modules.filter((m) => !m.on).map((m) => name(m.id));
  return (
    <>
      <Text variant="title">{t('map.title')}</Text>
      <Text>{t('map.lede')}</Text>

      <section className="map" aria-labelledby="map-drawing">
        <Text variant="label" id="map-drawing">{t('map.drawing')}</Text>
        <p className="visually-hidden">
          {tf('map.summary', { n: modules.length, on: on.join(', ') || t('map.none'), off: off.join(', ') || t('map.none') })}
        </p>
        <div className="map-drawing" aria-hidden="true">
          {modules.map((m, i) => (
            <div key={m.id} className={`map-line line-${m.id.toLowerCase()}${m.on ? '' : ' is-off'}`} style={{ '--i': i } as CSSProperties}>
              <LineBullet module={m.id} size={36} decorative />
              <span className="map-track"><span className="map-stop" /><span className="map-stop" /></span>
              <span className="map-name">{name(m.id)}</span>
            </div>
          ))}
        </div>
      </section>

      <section className="map-list" aria-labelledby="map-list">
        <Text variant="label" id="map-list">{t('map.list')}</Text>
        <ul className="lines">
          {modules.map((m) => (
            <li key={m.id}>
              <Card off={!m.on}>
                <div className="line-head">
                  <LineBullet module={m.id} size={28} decorative />
                  <Text variant="heading">{name(m.id)}</Text>
                  <Status state={m.on ? 'ready' : 'off'} label={t(m.on ? 'status.on' : 'status.off')} />
                </div>
                <Text>{t(`desc.${m.id}` as StringKey)}</Text>
                {m.on ? (
                  <Button href={MODULE_PATH[m.id]} onClick={() => navigate(MODULE_PATH[m.id])}>
                    {`${t('map.open')} ${name(m.id)}`}
                  </Button>
                ) : (
                  <Text variant="note">{t('map.offNote')}</Text>
                )}
              </Card>
            </li>
          ))}
        </ul>
      </section>
    </>
  );
}
