import { t, type StringKey } from '../../copy/t';

/** The seven modules: letter, badge number, CSS class. Colours live in the tokens (C2). */
export type ModuleId = 'L' | 'H' | 'T' | 'D' | 'M' | 'F' | 'S';

export const MODULE_IDS: ModuleId[] = ['L', 'H', 'T', 'D', 'M', 'F', 'S'];
const NUMBERS: Record<ModuleId, number> = { L: 1, H: 2, T: 3, D: 4, M: 5, F: 6, S: 0 };

export const badge = (m: ModuleId) => `${m}${NUMBERS[m]}`;
export const moduleName = (m: ModuleId) => t(`module.${m}` as StringKey);
/** Sets --line, --line-ink and --line-outline for the module (kit.css). */
export const lineClass = (m: ModuleId) => `line-${m.toLowerCase()}`;
