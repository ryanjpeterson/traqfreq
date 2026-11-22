import type { ReactNode } from 'react';
import { t } from '../../copy/t';

export type Operator = 'AND' | 'OR' | 'NOT' | 'true' | 'false';

type Props = {
  op: Operator;
  children: ReactNode;
  /** Shows a remove control when set. */
  onRemove?: () => void;
};

/** 6 · Condition chip: operator in the label face, then the condition. */
export function ConditionChip({ op, children, onRemove }: Props) {
  return (
    <span className="kit-chip" data-op={op}>
      <span className="kit-chip-op">{op}</span>
      <span className="kit-chip-text">{children}</span>
      {onRemove && (
        <button type="button" className="kit-chip-remove" onClick={onRemove} aria-label={t('kit.chip.remove')}>
          <span aria-hidden="true">×</span>
        </button>
      )}
    </span>
  );
}
