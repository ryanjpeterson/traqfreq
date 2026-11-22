import { t } from '../../copy/t';

export type StatusState = 'ready' | 'needs' | 'off';

type Props = {
  state: StatusState;
  /** The word next to the square. Defaults to the state's own word. */
  label?: string;
};

/** 3 · Status: filled = ready, outlined = needs something, dashed = off; always with a word, never coloured (C6). */
export function Status({ state, label }: Props) {
  return (
    <span className={`kit-status is-${state}`} data-state={state}>
      <span className="kit-status-mark" aria-hidden="true" />
      <span>{label ?? t(`kit.status.${state}`)}</span>
    </span>
  );
}
