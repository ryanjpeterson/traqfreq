import type { ReactNode } from 'react';
import { LineBullet } from './LineBullet';
import { lineClass, moduleName, type ModuleId } from './modules';

type Props = {
  module: ModuleId;
  /** Shown after the module name, for example the screen inside the module. */
  children?: ReactNode;
};

/** 4 · Band: a block of the module colour with its name in white, one line. One per screen at most. */
export function Band({ module, children }: Props) {
  return (
    <div className={`kit-band ${lineClass(module)}`} data-module={module}>
      <LineBullet module={module} size={28} decorative />
      <h2 className="kit-band-title">
        {moduleName(module)}
        {children ? <span className="kit-band-sub"> · {children}</span> : null}
      </h2>
    </div>
  );
}
