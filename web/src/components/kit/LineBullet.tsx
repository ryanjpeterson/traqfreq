import { badge, lineClass, moduleName, type ModuleId } from './modules';

export type BulletSize = 22 | 24 | 28 | 36 | 44;

type Props = {
  module: ModuleId;
  size?: BulletSize;
  /** Hide from screen readers when a visible module name sits next to it. */
  decorative?: boolean;
};

/** 1 · Line bullet: square in the module colour with its badge (letter + number), never colour alone. */
export function LineBullet({ module, size = 28, decorative = false }: Props) {
  return (
    <span
      className={`kit-bullet ${lineClass(module)} kit-bullet-${size}`}
      role={decorative ? undefined : 'img'}
      aria-label={decorative ? undefined : moduleName(module)}
      aria-hidden={decorative || undefined}
      data-module={module}
    >
      {badge(module)}
    </span>
  );
}
