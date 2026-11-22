import { LineBullet } from './LineBullet';
import { lineClass, moduleName, type ModuleId } from './modules';

type Props = {
  module: ModuleId;
  href: string;
  current?: boolean;
  onNavigate?: (href: string) => void;
};

/** 2 · Nav item: bullet + module name. The current item fills with its module colour (C7) and carries aria-current. */
export function NavItem({ module, href, current = false, onNavigate }: Props) {
  return (
    <a
      className={`kit-nav ${lineClass(module)}${current ? ' is-current' : ''}`}
      href={href}
      aria-current={current ? 'page' : undefined}
      onClick={onNavigate ? (e) => { e.preventDefault(); onNavigate(href); } : undefined}
    >
      <LineBullet module={module} size={24} decorative />
      <span>{moduleName(module)}</span>
    </a>
  );
}
