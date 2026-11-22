import { Band, Button, Card, Text, type ModuleId } from '../components/kit';
import { t, type StringKey } from '../copy/t';
import { MODULE_PATH } from '../app/route';

type Props = { module: Exclude<ModuleId, 'S'>; navigate: (href: string) => void };

/** A switched-on module with nothing to show yet. Empty states point to SETUP (D1). */
export function ModulePage({ module, navigate }: Props) {
  return (
    <>
      <Band module={module} />
      <div className="page">
        <EmptyState body={t(`empty.${module}` as StringKey)} navigate={navigate} />
      </div>
    </>
  );
}

export function EmptyState({ body, navigate }: { body: string; navigate: (href: string) => void }) {
  return (
    <Card>
      <div className="stack">
        <Text variant="heading">{t('empty.title')}</Text>
        <Text>{body}</Text>
        <div>
          <Button href={MODULE_PATH.S} onClick={() => navigate(MODULE_PATH.S)}>{t('empty.toSetup')}</Button>
        </div>
      </div>
    </Card>
  );
}
