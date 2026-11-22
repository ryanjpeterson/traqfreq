import { useId } from 'react';
import { t } from '../../copy/t';
import { LineBullet } from './LineBullet';
import { lineClass, type ModuleId } from './modules';

type Props = {
  /** The module whose data drives the line; the line takes its colour. */
  module: ModuleId;
  title: string;
  detail: string;
  /** Share of the playlist, 0 to 100. */
  share: number;
  count: number;
  /** Makes the lever adjustable (a real range input). Without it the share is read-only. */
  onChange?: (share: number) => void;
  /** The module is switched off: dashed, not adjustable. */
  off?: boolean;
};

/** 7 · Line with lever: bullet, title, detail, share bar, percent and track count. */
export function LineLever({ module, title, detail, share, count, onChange, off = false }: Props) {
  const id = useId();
  const pct = Math.max(0, Math.min(100, Math.round(share)));
  return (
    <div className={`kit-lever ${lineClass(module)}${off ? ' is-off' : ''}`} data-module={module}>
      <LineBullet module={module} size={36} />
      <div className="kit-lever-body">
        <p className="kit-lever-title" id={`${id}-t`}>{title}</p>
        <p className="kit-lever-detail">{detail}</p>
        {onChange ? (
          <input
            className="kit-lever-range"
            type="range"
            min={0}
            max={100}
            value={pct}
            disabled={off}
            aria-labelledby={`${id}-t`}
            aria-describedby={`${id}-s`}
            onChange={(e) => onChange(Number(e.target.value))}
          />
        ) : (
          <div className="kit-lever-bar" aria-hidden="true"><span style={{ width: `${pct}%` }} /></div>
        )}
      </div>
      <p className="kit-lever-nums" id={`${id}-s`}>
        <span className="kit-lever-pct">{pct}%</span>
        <span className="visually-hidden"> {t('kit.lever.share')}, </span>
        <span className="kit-lever-count">{count} {t('kit.lever.tracks')}</span>
      </p>
    </div>
  );
}
