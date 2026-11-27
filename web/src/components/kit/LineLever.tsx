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
  /** Tracks on the line. Leave it out only with `field`, while there are no words yet. */
  count?: number;
  /** Makes the lever adjustable (a real range input). Without it the share is read-only. */
  onChange?: (share: number) => void;
  /** The module is switched off: dashed, not adjustable. */
  off?: boolean;
  /** T28: the lever is words, not a share (the Ask box): a search field whose line is still to be made. Enter or
   *  the page's own button asks. With it, the share bar and percent give way to the field; the count stays. */
  field?: { value: string; onChange: (value: string) => void; onSubmit: () => void; placeholder?: string };
};

/** 7 · Line with lever: bullet, title, detail, share bar, percent and track count. */
export function LineLever({ module, title, detail, share, count, onChange, off = false, field }: Props) {
  const id = useId();
  const pct = Math.max(0, Math.min(100, Math.round(share)));
  return (
    <div className={`kit-lever ${lineClass(module)}${off ? ' is-off' : ''}`} data-module={module}>
      <LineBullet module={module} size={36} />
      <div className="kit-lever-body">
        <p className="kit-lever-title" id={`${id}-t`}>{title}</p>
        <p className="kit-lever-detail" id={`${id}-d`}>{detail}</p>
        {field ? (
          <form role="search" className="kit-lever-form" onSubmit={(e) => { e.preventDefault(); field.onSubmit(); }}>
            <input
              className="kit-lever-field"
              type="search"
              value={field.value}
              placeholder={field.placeholder}
              disabled={off}
              aria-labelledby={`${id}-t`}
              aria-describedby={`${id}-d`}
              onChange={(e) => field.onChange(e.target.value)}
            />
          </form>
        ) : onChange ? (
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
        {!field && <span className="kit-lever-pct">{pct}%</span>}
        {!field && <span className="visually-hidden"> {t('kit.lever.share')}, </span>}
        {count !== undefined && <span className="kit-lever-count">{count} {t('kit.lever.tracks')}</span>}
      </p>
    </div>
  );
}
